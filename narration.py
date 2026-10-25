"""Exact-text, checksum-verified neural narration cache with no network on read.

The main visual app imports this stdlib-only module. Online synthesis runs in
the independent .venv_narration environment only when explicitly requested.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT=Path(__file__).resolve().parent
NARRATION_VERSION='microsoft-edge-neural-1'
PROVIDER='Microsoft Edge online neural TTS via edge-tts'
DEFAULT_VOICE='zh-CN-XiaoxiaoNeural'
VOICES={
    'zh-CN-XiaoxiaoNeural':{'label':'自然女声 · 晓晓','gender':'Female','language':'zh-CN'},
    'zh-CN-YunxiNeural':{'label':'自然男声 · 云希','gender':'Male','language':'zh-CN'},
    'en-US-JennyNeural':{'label':'Natural female · Jenny','gender':'Female','language':'en'},
    'en-US-GuyNeural':{'label':'Natural male · Guy','gender':'Male','language':'en'},
}
SYNTHESIS_CONFIG={'rate':'-3%','pitch':'+0Hz','volume':'+0%'}


def normalize_narration_language(language):
    """Normalize the two supported narration languages without a UI dependency."""
    value=str(language or 'zh-CN').lower().replace('_','-')
    if value=='en' or value.startswith('en-'):return 'en'
    if value=='zh' or value.startswith('zh-'):return 'zh-CN'
    raise ValueError('Narration supports only Chinese and English')


def language_for_text(text):
    """Conservative script check, not translation or semantic language detection."""
    if re.search(r'[\u3400-\u9fff]',str(text)):return 'zh-CN'
    if re.search(r'[A-Za-z]',str(text)):return 'en'
    return None


def default_voice_for_language(language):
    return 'en-US-JennyNeural' if normalize_narration_language(language)=='en' else DEFAULT_VOICE


def voices_for_language(language):
    selected=normalize_narration_language(language)
    return {voice:dict(record) for voice,record in VOICES.items() if record['language']==selected}


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
    if voice not in VOICES or language_for_text(text)!=VOICES[voice]['language']:return None
    language=VOICES[voice]['language']
    digest=text_sha256(text)
    folder=Path(root)/'assets'/'narration'/digest
    metadata=_read_json(folder/(voice+'.json'))
    path=folder/(voice+'.mp3')
    if (metadata.get('text_sha256')!=digest or metadata.get('text')!=text
            or metadata.get('voice_id')!=voice or metadata.get('neural') is not True
            or metadata.get('provider')!=PROVIDER or metadata.get('version')!=NARRATION_VERSION
            or metadata.get('synthesis_config')!=SYNTHESIS_CONFIG):return None
    # Only the pre-bilingual Chinese cache is allowed to omit its language.
    if metadata.get('language','zh-CN' if language=='zh-CN' else None)!=language:return None
    try:
        audio=path.read_bytes()
        if len(audio)<1024 or len(audio)>40_000_000:return None
        if hashlib.sha256(audio).hexdigest()!=metadata.get('sha256'):return None
        seconds=metadata.get('duration_seconds')
        if not isinstance(seconds,(int,float)) or not .5<seconds<3600:return None
    except (OSError,ValueError):return None
    return {**metadata,'file':str(path.resolve()),'label':VOICES[voice]['label'],'language':language,
        'mime_type':'audio/mpeg','audio_base64':base64.b64encode(audio).decode('ascii')}


def get_narration_assets(text,root=None,language=None):
    """Read exact-text audio only for the requested or detected text language.

    Mismatched or empty text returns no voices. Reads never synthesize,
    translate, or fall back to an audio record in the other language.
    """
    digest=text_sha256(text);root=Path(root or ROOT).resolve()
    detected=language_for_text(text)
    language=normalize_narration_language(language or detected)
    matching=bool(text.strip()) and detected==language
    voices=[record for voice in voices_for_language(language) if (record:=_voice_record(text,voice,root)) is not None] if matching else []
    preferred=default_voice_for_language(language)
    default=preferred if any(x['voice_id']==preferred for x in voices) else (voices[0]['voice_id'] if voices else None)
    return {'available':bool(voices),'text_sha256':digest,'default_voice':default,'voices':voices,
        'language':language,'text_language':detected,'language_matches_text':matching,
        'provider':PROVIDER,'neural':True,'not_human_recording':True,
        'runtime_boundary':'Read-only exact-text audio cache. New text is not sent to a service by this function.'}


def ensure_narration(text,voices=None,root=None,language=None):
    """Explicitly create missing neural voice files in a separate interpreter.

    Synthesis sends only the requested narration text to Microsoft Edge's
    online read-aloud service; saved MP3 playback is local afterward.
    The original text, requested language and every voice must agree.
    """
    root=Path(root or ROOT).resolve();digest=text_sha256(text)
    if not text.strip():raise ValueError('Cannot synthesize an empty narration')
    language=normalize_narration_language(language or language_for_text(text))
    if language_for_text(text)!=language:
        raise ValueError('Narration text does not match the requested language')
    requested=list(voices_for_language(language) if voices is None else voices)
    if not requested or any(voice not in VOICES for voice in requested):
        raise ValueError('Only configured Chinese or English neural voices may be requested')
    if any(VOICES[voice]['language']!=language for voice in requested):
        raise ValueError('Requested voice does not match the narration language')
    folder=root/'assets'/'narration'/digest;folder.mkdir(parents=True,exist_ok=True)
    text_file=folder/'text.txt';text_file.write_text(text,encoding='utf-8')
    interpreter=root/'.venv_narration'/'Scripts'/'python.exe'
    script=root/'synthesize_narration.py'
    for voice in requested:
        if _voice_record(text,voice,root) is not None:continue
        if any((folder/(voice+suffix)).exists() for suffix in ['.mp3','.json']):
            raise RuntimeError('Existing narration cache is invalid and will not be overwritten')
        if not interpreter.is_file() or not script.is_file():
            raise RuntimeError('自然配音生成环境尚未就绪。未自动改用系统配音。')
        command=[str(interpreter),str(script),'--text-file',str(text_file),'--voice',voice,'--root',str(root),'--language',language]
        completed=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',
            errors='replace',timeout=100,check=False)
        if completed.returncode:
            raise RuntimeError('自然配音在线生成未完成，已有音频保留；未自动换回系统声。\n'+completed.stderr[-1500:])
        if _voice_record(text,voice,root) is None:raise RuntimeError('自然配音文件未通过校验。')
    result=get_narration_assets(text,root,language=language)
    if not set(requested).issubset({x['voice_id'] for x in result['voices']}):
        raise RuntimeError('Requested narration voices are not all available')
    return result
