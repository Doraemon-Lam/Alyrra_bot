"""本地 RVC 程序接口。命令数组需使用 {input}、{output} 文件占位符。"""
import subprocess
import tempfile
from pathlib import Path


def convert(data, command):
    if not command or not all(isinstance(arg, str) for arg in command):
        raise ValueError('未配置 RVC 命令数组')
    if not any('{input}' in arg for arg in command) or not any('{output}' in arg for arg in command):
        raise ValueError('RVC 命令必须包含 input 和 output 占位符')
    with tempfile.TemporaryDirectory(prefix='alyrra_rvc_') as td:
        source, target = Path(td) / 'input.wav', Path(td) / 'output.wav'
        source.write_bytes(data)
        args = [arg.replace('{input}', str(source)).replace('{output}', str(target)) for arg in command]
        subprocess.run(args, check=True, capture_output=True, timeout=120,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if not target.is_file() or target.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('RVC 未输出有效音频文件')
        return target.read_bytes()
