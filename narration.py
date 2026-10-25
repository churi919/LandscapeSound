"""Exact-text, checksum-verified neural narration cache with no network on read.

The main visual app imports this stdlib-only module. Online synthesis runs in
the independent .venv_narration environment only when explicitly requested.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess


ROOT=Path(__file__).resolve().parent
NARRATION_VERSION='microsoft-edge-neural-1'
PROVIDER='Microsoft Edge online neural TTS via edge-tts'
DEFAULT_VOICE='zh-CN-XiaoxiaoNeural'
VOICES={
    'zh-CN-XiaoxiaoNeural':{'label':'自然女声 · 晓晓','gender':'Female'},
    'zh-CN-YunxiNeural':{'label':'自然男声 · 云希','gender':'Male'},
}
SYNTHESIS_CONFIG={'rate':'-3%','pitch':'+0Hz','volume':'+0%'}


def text_sha256(text):
    if not isinstance(text,str) or len(text)>20000:
        raise ValueError('Narration needs text of at most 20000 characters')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _read_json(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def _voice_record(text,voice,root):
    digest=text_sha256(text)
    folder=Path(root)/'assets'/'narration'/digest
    metadata=_read_json(folder/(voice+'.json'))
    path=folder/(voice+'.mp3')
    if (metadata.get('text_sha256')!=digest or metadata.get('text')!=text
            or metadata.get('voice_id')!=voice or metadata.get('neural') is not True
            or metadata.get('provider')!=PROVIDER or metadata.get('version')!=NARRATION_VERSION
            or metadata.get('synthesis_config')!=SYNTHESIS_CONFIG):return None
    try:
        audio=path.read_bytes()
        if len(audio)<1024 or len(audio)>40_000_000:return None
        if hashlib.sha256(audio).hexdigest()!=metadata.get('sha256'):return None
        seconds=metadata.get('duration_seconds')
        if not isinstance(seconds,(int,float)) or not .5<seconds<3600:return None
    except (OSError,ValueError):return None
    return {**metadata,'file':str(path.resolve()),'label':VOICES[voice]['label'],
        'mime_type':'audio/mpeg','audio_base64':base64.b64encode(audio).decode('ascii')}


def get_narration_assets(text,root=None):
    """Return only exact-text, valid neural audio; never synthesize or fallback."""
    digest=text_sha256(text);root=Path(root or ROOT).resolve()
    voices=[record for voice in VOICES if (record:=_voice_record(text,voice,root)) is not None] if text.strip() else []
    default=DEFAULT_VOICE if any(x['voice_id']==DEFAULT_VOICE for x in voices) else (voices[0]['voice_id'] if voices else None)
    return {'available':bool(voices),'text_sha256':digest,'default_voice':default,'voices':voices,
        'provider':PROVIDER,'neural':True,'not_human_recording':True,
        'runtime_boundary':'Read-only exact-text audio cache. New text is not sent to a service by this function.'}


def ensure_narration(text,voices=None,root=None):
    """Explicitly create missing neural voice files in a separate interpreter.

    Synthesis sends only the requested narration text to Microsoft Edge's
    online read-aloud service; saved MP3 playback is local afterward.
    """
    root=Path(root or ROOT).resolve();digest=text_sha256(text)
    if not text.strip():raise ValueError('Cannot synthesize an empty narration')
    requested=list(voices or VOICES)
    if not requested or any(voice not in VOICES for voice in requested):
        raise ValueError('Only configured Chinese neural voices may be requested')
    folder=root/'assets'/'narration'/digest;folder.mkdir(parents=True,exist_ok=True)
    text_file=folder/'text.txt';text_file.write_text(text,encoding='utf-8')
    interpreter=root/'.venv_narration'/'Scripts'/'python.exe'
    script=root/'synthesize_narration.py'
    for voice in requested:
        if _voice_record(text,voice,root) is not None:continue
        if not interpreter.is_file() or not script.is_file():
            raise RuntimeError('自然配音生成环境尚未就绪。未自动改用系统配音。')
        command=[str(interpreter),str(script),'--text-file',str(text_file),'--voice',voice,'--root',str(root)]
        completed=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',
            errors='replace',timeout=100,check=False)
        if completed.returncode:
            raise RuntimeError('自然配音在线生成未完成，已有音频保留；未自动换回系统声。\n'+completed.stderr[-1500:])
        if _voice_record(text,voice,root) is None:raise RuntimeError('自然配音文件未通过校验。')
    result=get_narration_assets(text,root)
    if not set(requested).issubset({x['voice_id'] for x in result['voices']}):
        raise RuntimeError('Requested narration voices are not all available')
    return result
