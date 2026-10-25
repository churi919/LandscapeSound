"""Download licensed photo-based ERP examples and prepare labelled GPT inputs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import urllib.request
from PIL import Image, ImageDraw, ImageFont
import local_config

ROOT=local_config.ROOT
CASES=[('fish_hoek_beach','海滩与近岸海浪'),
       ('xanderklinge','林间岩溪与小瀑布'),
       ('urban_street_04','伦敦城市街道')]
USER_AGENT='LandscapeSound local research prototype; non-commercial licensed asset evaluation'


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
    with urllib.request.urlopen(request,timeout=120) as response:
        return response.read()


def font(size):
    for name in ['C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/msyh.ttc']:
        try:return ImageFont.truetype(name,size)
        except OSError:pass
    return ImageFont.load_default()


def contact_sheet(image,scene_id,target):
    from panorama import perspective_view
    canvas=Image.new('RGB',(2048,1600),'#f5f4ee');draw=ImageDraw.Draw(canvas)
    draw.text((64,12),scene_id+' | full 360 x 180 ERP + four 90-degree perspective views',fill='#193e31',font=font(28))
    preview=image.resize((1920,960),Image.Resampling.LANCZOS)
    canvas.paste(preview,(64,62))
    draw.text((64,1025),'ERP center = front (0 deg). Left/right seam = back (180 deg). Headings are not geographic north.',fill='#193e31',font=font(23))
    for index,(name,yaw) in enumerate([('front',0),('right',90),('back',180),('left',-90)]):
        x=64+index*480
        draw.text((x+8,1060),f'{scene_id} | {name} {yaw} deg',fill='#193e31',font=font(21))
        view=perspective_view(image,yaw_degrees=yaw,pitch_degrees=0,hfov=90,size=480)
        canvas.paste(view,(x,1100))
    canvas.save(target,quality=94)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--analyze',action='store_true')
    parser.add_argument('--only',default='');args=parser.parse_args()
    folder=ROOT/'samples'/'panoramas_gpt';raw_folder=folder/'original_downloads'
    folder.mkdir(parents=True,exist_ok=True);raw_folder.mkdir(exist_ok=True)
    manifest_path=folder/'manifest.json'
    records=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []
    selected=[]
    for scene_id,title in CASES:
        if args.only and args.only!=scene_id:continue
        print('Downloading/verifying '+scene_id,flush=True)
        info=json.loads(fetch('https://api.polyhaven.com/info/'+scene_id))
        files=json.loads(fetch('https://api.polyhaven.com/files/'+scene_id))
        (folder/(scene_id+'_official_info.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/(scene_id+'_official_files.json')).write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
        entry=files['tonemapped'];raw_path=raw_folder/(scene_id+'.jpg')
        if not raw_path.exists() or hashlib.md5(raw_path.read_bytes()).hexdigest()!=entry['md5']:
            raw=fetch(entry['url'])
            assert len(raw)==entry['size'] and hashlib.md5(raw).hexdigest()==entry['md5']
            raw_path.write_bytes(raw)
        raw=raw_path.read_bytes();image=Image.open(BytesIO(raw)).convert('RGB')
        source_size=list(image.size)
        assert image.width==image.height*2,'Official tonemapped panorama has unexpected dimensions'
        image=image.resize((4096,2048),Image.Resampling.LANCZOS)
        target=folder/(scene_id+'.jpg');image.save(target,quality=94)
        # Fingerprint decoded saved RGB, exactly what the downstream analyzer sees.
        with Image.open(target) as saved:image=saved.convert('RGB')
        sheet=folder/(scene_id+'_gpt_input.jpg');contact_sheet(image,scene_id,sheet)
        record={'id':scene_id,'title':title,'source_title':info.get('name',scene_id),
            'source_url':'https://polyhaven.com/a/'+scene_id,'source_api_url':'https://api.polyhaven.com/files/'+scene_id,
            'info_api_url':'https://api.polyhaven.com/info/'+scene_id,'download_url':entry['url'],
            'author':info.get('authors',{}),'license':'CC0-1.0','license_url':'https://polyhaven.com/license',
            'projection':'equirectangular','coverage_degrees':[360,180],
            'projection_source':'Poly Haven official HDRI photograph: https://docs.polyhaven.com/en/faq and https://docs.polyhaven.com/en/technical-standards/hdris',
            'width':image.width,'height':image.height,'file':str(target),'source_file':str(raw_path),
            'source_size':source_size,'source_bytes':len(raw),'source_md5':hashlib.md5(raw).hexdigest(),
            'source_sha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'sha256_rgb':hashlib.sha256(image.tobytes()).hexdigest(),'gpt_input_file':str(sheet),
            'gpt_input_sha256':hashlib.sha256(sheet.read_bytes()).hexdigest(),'gpt_input_size':[2048,1600],
            'processing':'Official 8K tonemapped photograph resized to 4096x2048 with Lanczos, JPEG quality94. GPT input contact sheet contains resized full ERP and four labelled 90deg perspective views, without changing scene content.',
            'official_metadata':{'description':info.get('description'),'categories':info.get('categories'),
                                 'tags':info.get('tags'),'date_taken':info.get('date_taken'),'max_resolution':info.get('max_resolution')},
            'credit':'Powered by Poly Haven','verified_utc':datetime.now(timezone.utc).isoformat()}
        previous=next((x for x in records if x['id']==scene_id),{})
        if previous.get('visual_review'):
            record['visual_review']=previous['visual_review']
        records=[x for x in records if x['id']!=scene_id]+[record]
        manifest_path.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        selected.append(record)
        print(json.dumps({'id':scene_id,'file':str(target),'gpt_input':str(sheet),'rgb':record['sha256_rgb']},ensure_ascii=False),flush=True)
    if args.analyze:
        import os
        os.environ['HF_HUB_OFFLINE']='1'
        from analyze_panorama import analyze_panorama
        for record in selected:
            result=analyze_panorama(Image.open(record['file']),ROOT/'outputs'/'gpt_panorama'/record['id'],title=record['title'])
            result['source']={k:record[k] for k in ['source_url','source_title','author','license','download_url','credit']}
            result['gpt_input']={'file':record['gpt_input_file'],'sha256':record['gpt_input_sha256'],'source_rgb_sha256':record['sha256_rgb']}
            Path(result['report_path']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'id':record['id'],'analyzed':True,**result['metrics']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
