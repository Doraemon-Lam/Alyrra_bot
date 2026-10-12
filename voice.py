"""QQ SILK 输入转换、Gemini TTS 与语音富媒体发送。"""
import asyncio
import base64
import io
import json
import logging
import os
import subprocess
import tempfile
import wave
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import aiohttp
import imageio_ffmpeg
import pilk
from botpy.http import Route
from google.genai import types
from rvc import convert as rvc_convert

LOG = logging.getLogger('alyrra')
ROOT = Path(__file__).resolve().parent


def is_audio(a):
    mime = (a.content_type or '').lower()
    name = (getattr(a, 'filename', '') or '').lower()
    path = urlsplit(a.url or '').path.lower()
    return mime in {'audio', 'voice'} or mime.startswith(('audio/', 'voice/')) or 'silk' in mime or any(
        value.endswith(('.silk', '.amr', '.mp3', '.wav', '.ogg', '.m4a')) for value in (name, path))


def convert_audio(data):
    with tempfile.TemporaryDirectory() as td:
        source, pcm, output = [Path(td) / n for n in ('source', 'audio.pcm', 'audio.wav')]
        source.write_bytes(data)
        if data.startswith((b'#!SILK', b'\x02#!SILK')):
            duration = pilk.decode(str(source), str(pcm), pcm_rate=24000)
            if duration > 60000:
                raise ValueError('语音超过 60 秒')
            with wave.open(str(output), 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'NONE'))
                wav.writeframes(pcm.read_bytes())
        else:
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', str(source),
                '-t', '61', '-ac', '1', '-ar', '24000', str(output)], check=True,
                capture_output=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with wave.open(str(output), 'rb') as wav:
            if wav.getnframes() / wav.getframerate() > 60:
                raise ValueError('语音超过 60 秒')
        return output.read_bytes()


class Voice:
    def __init__(self, chat):
        self.chat = chat
        self.lock = asyncio.Lock()
        self.path = ROOT / 'voice_usage.json'
        try:
            self.usage = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            self.usage = {}

    async def read(self, url):
        url = 'https:' + url if url.startswith('//') else url
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if parsed.scheme not in ('https', 'http') or not (host == 'multimedia.nt.qq.com.cn' or
                any(host == d or host.endswith('.' + d) for d in ('qq.com', 'qpic.cn', 'gtimg.cn'))):
            raise ValueError('语音下载域名未允许')
        url = 'https://' + url[len('http://'):] if url.startswith('http://') else url
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=True) as session:
            async with session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    raise ValueError(f'语音下载 HTTP {response.status}')
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > 8 * 1024 * 1024:
                        raise ValueError('语音超过 8 MB')
        result = await asyncio.to_thread(convert_audio, bytes(data))
        LOG.info('语音已转换为 WAV：%d 字节', len(result))
        return result

    async def synthesize(self, text):
        response = await asyncio.wait_for(self.chat.bot.vertex.aio.models.generate_content(
            model=os.getenv('TTS_MODEL', 'gemini-3.8-flash-tts'),
            contents=[{'role': 'user', 'parts': [{'text': text[:180],
                'speech_metadata': {'style': '清亮活泼的年轻女性声音，轻微傲娇，自然中文，不夸张。'}}]}],
            config=types.GenerateContentConfig(response_modalities=['AUDIO'],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    voice=self.chat.settings.get('tts_voice', os.getenv('TTS_VOICE', 'Kore')))),
                http_options=types.HttpOptions(timeout=90000),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))), timeout=95)
        for candidate in response.candidates or []:
            for part in candidate.content.parts if candidate.content else []:
                blob = part.inline_data
                if blob and blob.data and (blob.mime_type or '').startswith('audio/'):
                    data = blob.data
                    if not data.startswith(b'RIFF'):
                        out = io.BytesIO()
                        with wave.open(out, 'wb') as wav:
                            wav.setparams((1, 2, 24000, 0, 'NONE', 'NONE'))
                            wav.writeframes(data)
                        data = out.getvalue()
                    return data
        raise RuntimeError('TTS 未返回音频')

    async def send(self, msg, text):
        self.chat.reload_settings()
        if self.lock.locked() or self.chat.settings.get('voice_reply_mode', 'auto') == 'off':
            return False
        async with self.lock:
            day = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
            if self.usage.get('day') != day:
                self.usage = dict(day=day, calls=0)
            if self.usage['calls'] >= self.chat.settings.get('voice_daily_calls', 30):
                LOG.info('语音生成每日限额已达上限，保留文字回复。')
                return False
            self.usage['calls'] += 1
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.usage), encoding='utf-8')
            temp.replace(self.path)
            try:
                LOG.info('开始语音合成：%s', os.getenv('TTS_MODEL', 'gemini-3.8-flash-tts'))
                data = await self.synthesize(text)
                self.chat.reload_settings()
                if self.chat.settings.get('rvc_enabled', False):
                    LOG.info('开始 RVC 声音转换。')
                    data = await asyncio.to_thread(rvc_convert, data, self.chat.settings.get('rvc_command', []))
                    data = await asyncio.to_thread(convert_audio, data)
                    LOG.info('RVC 声音转换完成。')
                def encode():
                    with tempfile.TemporaryDirectory() as td:
                        pcm, silk = Path(td) / 'audio.pcm', Path(td) / 'audio.silk'
                        with wave.open(io.BytesIO(data), 'rb') as wav:
                            rate = wav.getframerate()
                            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                                raise ValueError('TTS 音频需为单声道 16 位 PCM')
                            pcm.write_bytes(wav.readframes(wav.getnframes()))
                        pilk.encode(str(pcm), str(silk), pcm_rate=rate, tencent=True)
                        return silk.read_bytes()
                silk = await asyncio.to_thread(encode)
                self.chat.reload_settings()
                if self.chat.mode() == 'off' or self.chat.settings.get('voice_reply_mode', 'auto') == 'off':
                    return False
                media = await asyncio.wait_for(self.chat.bot.api._http.request(
                    Route('POST', '/v2/groups/{group_openid}/files', group_openid=msg.group_openid),
                    json={'file_type': 3, 'file_data': base64.b64encode(silk).decode('ascii'),
                          'srv_send_msg': False}), timeout=30)
                if not media.get('file_info'):
                    raise RuntimeError('QQ 未返回语音 file_info')
                await msg.reply(msg_type=7, media={'file_info': media['file_info']}, msg_seq=2)
                LOG.info('QQ 语音发送成功。')
                return True
            except Exception as exc:
                LOG.error('语音合成或发送失败：%s，code=%s；保留文字回复。', type(exc).__name__, getattr(exc, 'code', '未提供'))
                return False
