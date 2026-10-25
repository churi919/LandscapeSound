"""Download public official optimized weights with explicit anonymous requests."""
import os
from pathlib import Path
import json
import time
import argparse
import hashlib

BASE=Path(__file__).resolve().parent
os.environ['HF_HOME']=str(BASE/'hf_cache')
os.environ['HF_HUB_CACHE']=str(BASE/'hf_cache'/'hub')
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120'
os.environ['TEMP']=str(BASE/'.cache'/'tmp')
os.environ['TMP']=str(BASE/'.cache'/'tmp')
from huggingface_hub import HfApi,hf_hub_download

repo='stabilityai/stable-audio-3-optimized'
revision='08b17423649b5714b22eab20f96bf00751f2358a'
parser=argparse.ArgumentParser()
parser.add_argument('--include-medium',action='store_true')
args=parser.parse_args()
api=HfApi(token=False)
info=api.model_info(repo,revision=revision,files_metadata=True,token=False)
assert not info.gated, 'Repository is gated; do not accept terms automatically.'
manifest_path=BASE/'weights_manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'repo_id':repo,'revision':info.sha,'gated':info.gated,'files':[]}
assert manifest['revision']==revision, 'Existing manifest has a different revision; preserve it for review.'
files=['tflite/t5gemma/encoder_fp16.tflite','tflite/sa3-sm-sfx/dit_w8a8.tflite',
       'tflite/same-s/dec_w8a8.tflite']
if args.include_medium:files+=['tflite/sa3-m/dit_w8a8.tflite','tflite/same-l/dec_w8a8.tflite']
dest=BASE/'stable-audio-3'/'optimized'/'tflite'/'models'
for name in files:
    start=time.perf_counter();print('Downloading '+name,flush=True)
    cached=Path(hf_hub_download(repo,name,revision=info.sha,token=False))
    target=dest/Path(name)
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        try:os.link(cached,target)
        except OSError:
            import shutil;shutil.copy2(cached,target)
    if not any(x['repo_path']==name for x in manifest['files']):
        manifest['files'].append({'repo_path':name,'cached_path':str(cached),'runtime_path':str(target),
                                 'bytes':cached.stat().st_size,'download_seconds':round(time.perf_counter()-start,3),
                                 'sha256':hashlib.file_digest(cached.open('rb'),'sha256').hexdigest()})
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Ready '+name+' '+str(cached.stat().st_size),flush=True)
for name in ['README.md','LICENSE.md','LICENSE_GEMMA.md']:
    try:
        path=hf_hub_download(repo,name,revision=info.sha,token=False)
        import shutil;shutil.copy2(path,BASE/('model_'+name))
    except Exception as exc:print('Metadata file unavailable:',name,type(exc).__name__,flush=True)
print(json.dumps(manifest),flush=True)
