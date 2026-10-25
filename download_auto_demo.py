"""Prepare one new public photo panorama for a cold upload-to-audio demo.

This downloads and resizes an official CC0 photograph only. It intentionally
does not analyze the image, invoke GPT, or create audio/narration caches.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

from PIL import Image

ROOT=Path(__file__).resolve().parent
ID='lauter_waterfall'
TITLE='林间溪流与苔藓石岸'
UA='LandscapeSound local research prototype / public CC0 demo asset; Powered by Poly Haven'


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(request,timeout=120) as response:
        return response.read()


def main():
    folder=ROOT/'samples'/'auto_demo';folder.mkdir(parents=True,exist_ok=True)
    originals=folder/'original_downloads';originals.mkdir(exist_ok=True)
    info=json.loads(fetch('https://api.polyhaven.com/info/'+ID))
    files=json.loads(fetch('https://api.polyhaven.com/files/'+ID))
    (folder/(ID+'_official_info.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/(ID+'_official_files.json')).write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
    entry=files['tonemapped'];original=originals/(ID+'.jpg')
    if not original.is_file() or hashlib.md5(original.read_bytes()).hexdigest()!=entry['md5']:
        raw=fetch(entry['url'])
        if len(raw)!=entry['size'] or hashlib.md5(raw).hexdigest()!=entry['md5']:
            raise ValueError('Official panorama download failed size/hash verification')
        original.write_bytes(raw)
    raw=original.read_bytes()
    with Image.open(original) as opened:
        image=opened.convert('RGB');source_size=list(image.size)
        if image.width!=2*image.height:
            raise ValueError('Official panorama has unexpected aspect ratio')
        image=image.resize((4096,2048),Image.Resampling.LANCZOS)
        target=folder/(ID+'.jpg');image.save(target,quality=94)
    with Image.open(target) as opened:
        saved=opened.convert('RGB');rgb=hashlib.sha256(saved.tobytes()).hexdigest()
    item={'id':ID,'title':TITLE,'source_title':info.get('name',ID),
        'source_url':'https://polyhaven.com/a/'+ID,
        'source_api_url':'https://api.polyhaven.com/files/'+ID,
        'info_api_url':'https://api.polyhaven.com/info/'+ID,
        'download_url':entry['url'],'author':info.get('authors',{}),
        'license':'CC0-1.0','license_url':'https://polyhaven.com/license',
        'public_asset_permitted_for_gpt_upload':True,
        'permission_basis':'Public CC0 asset permits use, redistribution and AI-related processing. Human user requested a new public panorama for the automatic GPT demo.',
        'projection':'equirectangular','coverage_degrees':[360,180],
        'projection_basis':'Official Poly Haven photographic HDRI tonemapped panorama. Poly Haven technical standards require photo-based HDRIs, not renders.',
        'projection_source':'https://docs.polyhaven.com/en/technical-standards/hdris',
        'width':saved.width,'height':saved.height,'file':str(target),
        'source_file':str(original),'source_size':source_size,
        'source_bytes':len(raw),'source_md5':hashlib.md5(raw).hexdigest(),
        'source_sha256':hashlib.sha256(raw).hexdigest(),
        'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'sha256_rgb':rgb,
        'processing':'Official 8K tonemapped JPG resized to 4096x2048 with Lanczos, JPEG quality94. No generated content or scene edits.',
        'official_metadata':{k:info.get(k) for k in ['description','categories','tags','date_taken','max_resolution']},
        'credit':'Powered by Poly Haven','prepared_utc':datetime.now(timezone.utc).isoformat(),
        'cold_demo_boundary':'No GPT understanding, local vision inference, sound generation or TTS cache created by this preparation script.'}
    (folder/'manifest.json').write_text(json.dumps([item],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'file':str(target),'source_size':source_size,'working_size':list(saved.size),'sha256_rgb':rgb},ensure_ascii=False))


if __name__=='__main__':main()
