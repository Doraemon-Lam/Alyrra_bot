"""QQ 全群文字与图片聊天，通过 Vertex ADC 按预算生成回复。"""
import argparse
import asyncio
import logging
import os
import re
from collections import OrderedDict
from pathlib import Path

import botpy
import google.auth
from botpy.message import GroupMessage
from dotenv import load_dotenv
from google import genai
from google.genai import types
from group_chat import GroupChat

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
LOG = logging.getLogger('alyrra')


def make_vertex():
    # 显式使用 ADC，不受 GOOGLE_API_KEY / GEMINI_API_KEY 影响。
    credentials, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform'])
    return genai.Client(
        vertexai=True, credentials=credentials,
        project=os.environ['GOOGLE_CLOUD_PROJECT'],
        location=os.getenv('GOOGLE_CLOUD_LOCATION', 'global'),
        http_options=types.HttpOptions(timeout=45000,
            retry_options=types.HttpRetryOptions(attempts=1)))


def system_prompt():
    persona = (ROOT / os.getenv('PERSONA_FILE', 'Alyrra.md')).read_text(encoding='utf-8')
    return (
        '你在 QQ 群中扮演 Alyrra。按下面的角色设定自然交流，使用中文短句，'
        '通常回复 1 至 4 句，最多 400 字。傲娇适度，不要每句话都说哼或才不是。'
        '不输出 Markdown 表格，不长篇复述设定。作者隐藏设定不是角色已知事实。'
        '魔法行为仅是虚构描写，不能声称实际操作手机、治病或施法。'
        '不知道的现实信息直接说明不确定。\n\n' + persona)


class Alyrra(botpy.Client):
    def __init__(self, vertex, prompt, **kwargs):
        super().__init__(**kwargs)
        self.vertex = vertex
        self.prompt = prompt
        self.sessions = OrderedDict()
        self.seen = OrderedDict()
        self.guard = asyncio.Lock()
        self.allowed = {s.strip() for s in os.getenv('ALLOWED_GROUP_OPENIDS', '').split(',') if s.strip()}
        self.chat = GroupChat(self)

    async def on_ready(self):
        LOG.info('Alyrra 已连接 QQ；全群文字与图片缓冲已启用，可直接叫“艾璃拉”。')
        LOG.info('聊天模式：%s', '积极回复（本地调用限额已取消）' if self.chat.active else '节省调用')

    async def bot_connect(self, session):
        # 同时处理普通群消息和 @事件；去重在 GroupChat 中完成。
        self._connection.parser['group_message_create'] = self.chat.parse
        self._connection.parser['group_at_message_create'] = lambda payload: self.chat.parse(payload, direct=True)
        await super().bot_connect(session)

    async def on_group_message_create(self, message: GroupMessage):
        await self.chat.receive(message, direct=False)

    async def on_group_at_message_create(self, message: GroupMessage):
        await self.chat.receive(message, direct=True)


async def check_vertex(vertex, prompt):
    response = await asyncio.wait_for(vertex.aio.models.generate_content(
        model=os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'), contents='你好，简短介绍一下你自己。',
        config=types.GenerateContentConfig(system_instruction=prompt, max_output_tokens=2048,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))), timeout=50)
    if not response.text:
        raise RuntimeError('模型未返回文本')
    print(response.text)
    await vertex.aio.aclose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='只测试 ADC 与人格回复，不连接 QQ')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', force=True)
    if not args.check and not os.getenv('QQ_BOT_APPSECRET', '').strip():
        raise SystemExit('请先在 .env 中填入新的 QQ_BOT_APPSECRET，再启动。')
    LOG.info('正在加载 Vertex 默认凭据…')
    vertex = make_vertex()
    prompt = system_prompt()
    LOG.info('Vertex 客户端与 Alyrra 人格已加载。')
    if args.check:
        asyncio.run(check_vertex(vertex, prompt))
        return
    client = Alyrra(vertex, prompt, intents=botpy.Intents(public_messages=True),
                    is_sandbox=os.getenv('QQ_BOT_SANDBOX', 'false').lower() == 'true',
                    bot_log=None, log_level=logging.INFO)
    LOG.info('正在连接 QQ WebSocket；成功后会显示“已连接 QQ”。')
    client.run(appid=os.environ['QQ_BOT_APPID'], secret=os.environ['QQ_BOT_APPSECRET'])


if __name__ == '__main__':
    main()
