"""Explicit online synthesis worker for verified Mandarin neural narration."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from narration import (ROOT,NARRATION_VERSION,PROVIDER,VOICES,SYNTHESIS_CONFIG,
                       text_sha256,get_narration_assets)


async def synthesize(text,voice,root):
    import edge_tts
    from mutagen.mp3 import MP3
    digest=text_sha256(text);folder=root/'assets'/'narration'/digest
    folder.mkdir(parents=True,exist_ok=True)
    cached=get_narration_assets(text,root)
    existing=next((x for x in cached['voices'] if x['voice_id']==voice),None)
    if existing:return {'voice_id':voice,'file':existing['file'],'reused':True}
    lock=folder/(voice+'.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:raise RuntimeError('This exact narration voice is already being generated') from exc
    os.close(fd)
    temporary=folder/(voice+'.'+uuid.uuid4().hex+'.tmp.mp3')
    final=folder/(voice+'.mp3')
    started=time.perf_counter()
    try:
        communicate=edge_tts.Communicate(text,voice,**SYNTHESIS_CONFIG,connect_timeout=10,receive_timeout=45)
        await asyncio.wait_for(communicate.save(str(temporary)),timeout=75)
        info=MP3(temporary).info
        if temporary.stat().st_size<1024 or not .5<info.length<3600:
            raise ValueError('Invalid or silent-length synthesized MP3')
        temporary.replace(final)
        metadata={'version':NARRATION_VERSION,'voice_id':voice,'label':VOICES[voice]['label'],
            'gender':VOICES[voice]['gender'],'provider':PROVIDER,'neural':True,'field_recording':False,
            'not_human_recording':True,'text':text,'text_sha256':digest,'file':str(final.resolve()),
            'sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'mime_type':'audio/mpeg',
            'duration_seconds':float(info.length),'sample_rate':info.sample_rate,'channels':info.channels,
            'bitrate':info.bitrate,'synthesis_config':dict(SYNTHESIS_CONFIG),
            'edge_tts_version':edge_tts.__version__,
            'service_endpoint':'wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1',
            'service_transport':'TLS WebSocket through the open-source edge-tts client',
            'synthesis_was_online':True,'text_sent_to_service':True,'saved_playback_can_be_offline':True,
            'request_seconds':time.perf_counter()-started,'created_utc':datetime.now(timezone.utc).isoformat(),
            'sources':['https://github.com/rany2/edge-tts','https://learn.microsoft.com/zh-tw/azure/ai-services/speech-service/language-support'],
            'subjectively_auditioned':False}
        (folder/(voice+'.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'text.txt').write_text(text,encoding='utf-8')
        records=[]
        for configured in VOICES:
            path=folder/(configured+'.json')
            if path.is_file():records.append(json.loads(path.read_text(encoding='utf-8')))
        (folder/'manifest.json').write_text(json.dumps({'text_sha256':digest,'text':text,'voices':records,
            'provider':PROVIDER,'neural':True,'not_human_recording':True},ensure_ascii=False,indent=2),encoding='utf-8')
        return {'voice_id':voice,'file':str(final),'duration_seconds':info.length,'reused':False,
                'sha256':metadata['sha256'],'request_seconds':metadata['request_seconds']}
    finally:
        temporary.unlink(missing_ok=True);lock.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--text-file',required=True,type=Path)
    parser.add_argument('--voice',choices=list(VOICES),action='append',help='May be repeated; default is Xiaoxiao neural.')
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    text=args.text_file.read_text(encoding='utf-8')
    results=[asyncio.run(synthesize(text,voice,args.root.resolve())) for voice in (args.voice or ['zh-CN-XiaoxiaoNeural'])]
    print(json.dumps(results[0] if len(results)==1 else {'voices':results},ensure_ascii=False))


if __name__=='__main__':main()
