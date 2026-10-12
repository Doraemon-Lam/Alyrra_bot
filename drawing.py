"""明确生图请求路由，独立模型、限额与 QQ 富媒体发送。"""
import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from PIL import Image
from botpy.http import Route
from google.genai import types

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger('alyrra')


async def wait_with_progress(awaitable, timeout=125, interval=15):
    task = asyncio.create_task(awaitable)
    started = time.monotonic()
    try:
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('生图等待超时')
            done, _ = await asyncio.wait({task}, timeout=min(interval, remaining))
            if done:
                return task.result()
            LOG.info('生图仍在等待模型响应：已等待 %.0f 秒，上限 %.0f 秒。',
                     time.monotonic() - started, timeout)
    finally:
        if not task.done():
            task.cancel()
            # 不继续等待 SDK 完成取消，避免超时后锁一直无法释放。
            def consume(t):
                if not t.cancelled():
                    t.exception()
            task.add_done_callback(consume)


def drawing_prompt(text):
    text = re.sub(r'^(?:Alyrra|艾璃拉|艾璃)[，,：:\s]+', '', text, flags=re.I)
    # 不匹配“你能画图吗”“别画图”等讨论，避免额外调用聊天模型做路由。
    match = re.fullmatch(r'(?:/(?:画图|生图)\s+|(?:请)?(?:帮我)?(?:画一张|画个|生成一张图片|生成一张图)\s*)(.+)', text)
    return match.group(1).strip()[:2000] if match else None


async def generate_image(client, prompt):
    parts = [types.Part(text='请根据以下需求生成一张图片。\n' + prompt)]
    reference = ROOT / 'templates' / 'assets' / 'alyrra.jpg'
    if reference.exists() and re.search(r'alyrra|艾璃拉|艾璃|自画像|你自己', prompt, re.I):
        parts.append(types.Part(text='这是 Alyrra 的形象参考。保留薄荷绿长发、蓝紫眼睛、精灵尖耳、大型黑色蝴蝶结、青蓝交叉发饰和黑白青蓝服装的识别特征。'))
        parts.append(types.Part.from_bytes(data=reference.read_bytes(), mime_type='image/jpeg'))
        LOG.info('生图已附带 Alyrra 角色参考图。')
    response = await wait_with_progress(client.aio.models.generate_content(
        model=os.getenv('IMAGE_MODEL', 'gemini-3.1-flash-image'),
        contents=parts,
        config=types.GenerateContentConfig(
            http_options=types.HttpOptions(timeout=120000),
            response_modalities=['TEXT', 'IMAGE'],
            image_config=types.ImageConfig(image_size='1K', aspect_ratio='1:1'),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))), timeout=125)
    LOG.info('生图模型已响应，开始提取和保存图片。')
    for candidate in response.candidates or []:
        for part in candidate.content.parts if candidate.content else []:
            blob = part.inline_data
            if blob and (blob.mime_type or '').startswith('image/') and blob.data:
                def save():
                    with Image.open(io.BytesIO(blob.data)) as image:
                        output = io.BytesIO()
                        image.convert('RGB').save(output, format='JPEG', quality=90)
                        return output.getvalue()
                data = await asyncio.to_thread(save)
                folder = ROOT / 'generated_images'
                folder.mkdir(exist_ok=True)
                path = folder / (datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8] + '.jpg')
                path.write_bytes(data)
                return path, getattr(response.usage_metadata, 'total_token_count', 0) or 0
    raise RuntimeError('模型没有返回图片，可能被拒绝或只返回文字')


class Drawing:
    def __init__(self, chat):
        self.chat = chat
        self.lock = asyncio.Lock()
        self.last = {}
        self.path = ROOT / 'image_usage.json'
        try:
            self.usage = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            self.usage = {}

    def save(self):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.usage), encoding='utf-8')
        temp.replace(self.path)

    async def handle(self, msg, prompt):
        self.chat.reload_settings()
        if not self.chat.settings.get('image_enabled', True):
            await msg.reply(content='画图功能当前已关闭。', msg_type=0)
            return
        if self.lock.locked():
            await msg.reply(content='本精灵正在画另一张图，等完成后再叫我吧。', msg_type=0)
            return
        async with self.lock:
            day = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
            if self.usage.get('day') != day:
                self.usage = dict(day=day, calls=0, tokens=0)
            if self.usage['calls'] >= self.chat.settings.get('image_daily_calls', 10):
                await msg.reply(content='今天的画图次数已经用完啦。', msg_type=0)
                return
            key = (msg.group_openid, msg.author.member_openid)
            now = time.monotonic()
            if now - self.last.get(key, -100000) < self.chat.settings.get('image_cooldown_seconds', 60):
                await msg.reply(content='等一小会儿再画下一张吧。', msg_type=0)
                return
            self.last[key] = now
            self.usage['calls'] += 1
            self.save()  # 失败请求也计入，防止不断重试消耗费用。
            path = None
            try:
                await msg.reply(content='好呀，本精灵开始画啦！', msg_type=0, msg_seq=1)
                LOG.info('生图调用开始：模型=%s', os.getenv('IMAGE_MODEL', 'gemini-3.1-flash-image'))
                started = time.monotonic()
                path, tokens = await generate_image(self.chat.bot.vertex, prompt)
                LOG.info('图片生成完成，耗时 %.1f 秒，本地文件=%s', time.monotonic() - started, path)
                self.usage['tokens'] += tokens
                self.save()
                self.chat.reload_settings()
                if not self.chat.settings.get('image_enabled', True) or self.chat.mode() == 'off':
                    LOG.info('图片已保存，因开关关闭不发送：%s', path)
                    return
                # botpy 1.2.1 上传方法只接收 URL，使用现有鉴权 HTTP 通道上传 base64。
                route = Route('POST', '/v2/groups/{group_openid}/files', group_openid=msg.group_openid)
                LOG.info('开始上传图片到 QQ。')
                media = await asyncio.wait_for(self.chat.bot.api._http.request(route, json={
                    'file_type': 1, 'file_data': base64.b64encode(path.read_bytes()).decode('ascii'),
                    'srv_send_msg': False}), timeout=30)
                if not media.get('file_info'):
                    raise RuntimeError('QQ 未返回 file_info')
                LOG.info('QQ 图片上传成功，正在发送群消息。')
                await msg.reply(content='画好啦！', msg_type=7, media={'file_info': media['file_info']}, msg_seq=2)
                LOG.info('生图发送成功：%s，总 token=%d', path, tokens)
            except Exception as exc:
                LOG.error('生图或发送失败：%s，状态=%s，本地文件=%s',
                          type(exc).__name__, getattr(exc, 'code', '无'), path or '未生成')
                try:
                    detail = ('画好了，但上传或发送失败，图片已保存在电脑。' if path else
                              '这次生图等待超时，请稍后再试。' if isinstance(exc, TimeoutError) else
                              '这次没能画出来，请检查生图模型权限或网络。')
                    await msg.reply(content=detail, msg_type=0, msg_seq=3)
                except Exception:
                    LOG.error('生图错误提示发送失败。')
