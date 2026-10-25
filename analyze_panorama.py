"""Compare the original flat-image pipeline with four perspective panorama views.

Per-view monocular depth remains independent: it is never stitched into a
globally scaled distance map. Sound playback faces the selected view.
"""
import local_config
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageDraw

VIEWS = [('front',0.,'正前方'),('right',90.,'右方'),
         ('back',180.,'后方'),('left',-90.,'左方')]


def analyze_panorama(image: Image.Image, output_dir: Path, title='360°全景'):
    from panorama import perspective_view, validate_equirectangular, pixel_azimuth_degrees
    from analyzer import analyze_image
    from browser_audio import render_audio
    started=time.perf_counter()
    output_dir=Path(output_dir).resolve();output_dir.mkdir(parents=True,exist_ok=True)
    image=ImageOps.exif_transpose(image).convert('RGB')
    geometry=validate_equirectangular(image)
    original_size=list(image.size)
    image.thumbnail((4096,2048),Image.Resampling.LANCZOS)
    preview=image.copy();preview.thumbnail((1536,768),Image.Resampling.LANCZOS)
    pano_path=output_dir/'panorama.jpg';preview.save(pano_path,quality=92)
    baseline=analyze_image(image,output_dir/'baseline_flat',title=title+' · 原版平铺输入',hfov=70.)
    baseline['evaluation_role']='Known-mismatched baseline: full 360-degree ERP treated as a 70-degree ordinary photograph.'
    views=[]
    for view_id,yaw,label in VIEWS:
        perspective=perspective_view(image,yaw_degrees=yaw,pitch_degrees=0,hfov=90,size=512)
        folder=output_dir/'views'/view_id
        analysis=analyze_image(perspective,folder,title=title+' · '+label,hfov=90.)
        for source in analysis['scene']['sources']:
            source['linear_azimuth_before_projection_correction']=source['azimuth']
            source['azimuth']=pixel_azimuth_degrees(source['centroid_x'],perspective.width,hfov=90.)
            source['panorama_heading']=((yaw+source['azimuth']+180)%360)-180
            source['panorama_view_id']=view_id
        analysis['scene']['audio_info']['azimuth_projection']='pinhole atan using pixel-center rays'
        analysis['scene']['audio_info']['panorama_view_yaw']=yaw
        Path(analysis['report_path']).write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'listen.html').write_text(render_audio(analysis['scene']['sources'],analysis['scene']['description'],local_config.ROOT/'assets'),encoding='utf-8')
        views.append({'id':view_id,'yaw':yaw,'label':label,'report':analysis})
    metrics={'baseline_inference_seconds':baseline['metrics']['inference_seconds'],
             'four_view_inference_seconds':round(sum(x['report']['metrics']['inference_seconds'] for x in views),3),
             'total_seconds':round(time.perf_counter()-started,3),
             'peak_gpu_memory_mb':max([baseline['metrics']['peak_gpu_memory_mb']]+[x['report']['metrics']['peak_gpu_memory_mb'] for x in views]),
             'view_count':4,'perspective_size':[512,512]}
    report={'schema_version':1,'mode':'panorama_views','title':title,
            'input':{'original_size':original_size,'projection':'equirectangular','working_size':list(image.size),
                     'sha256_rgb':hashlib.sha256(image.tobytes()).hexdigest(),'geometry_validation':geometry},
            'files':{'panorama':str(pano_path),'overview':str(output_dir/'overview.jpg')},
            'views':views,'baseline':baseline,'metrics':metrics,
            'coverage':{'horizontal_headings':[0,90,180,-90],'view_hfov':90,
                        'pitch':0,'zenith_and_nadir_analyzed':False,
                        'north_reference':'Image center is an arbitrary 0-degree heading, not geographic north.'},
            'limitations':[
                'Four horizontal perspective views; this is not a complete spherical semantic/depth reconstruction.',
                'Depth is normalized independently inside each view; virtual radii cannot be compared between views.',
                'Playback faces the selected view; no continuously rotating listener or full-surround shared sound field.',
                'Reprojection and local sampling resolution both differ from the flat baseline; no accuracy improvement is established without annotations.',
                'Stereo HRTF and procedural illustrative sounds; no field recordings or user-perception validation.',
                'No panoramic GPT description has been generated; the new views use local rules.'
            ],'report_path':str(output_dir/'report.json')}
    overview(report)
    Path(report['report_path']).write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report


def overview(report):
    width=1200;row_h=340
    canvas=Image.new('RGB',(width,row_h*5),'#f5f4ee');draw=ImageDraw.Draw(canvas)
    rows=[('flat_360_as_70',report['baseline'])]+[(x['id']+' yaw='+str(int(x['yaw'])),x['report']) for x in report['views']]
    for row,(name,analysis) in enumerate(rows):
        for col,key in enumerate(('input','segmentation','depth')):
            im=Image.open(analysis['files'][key]);im.thumbnail((390,300),Image.Resampling.LANCZOS)
            canvas.paste(im,(400*col+(400-im.width)//2,row_h*row+32))
            draw.text((400*col+10,row_h*row+8),name+' / '+key,fill='#183e31')
    canvas.save(report['files']['overview'],quality=92)


def main():
    import argparse,os
    parser=argparse.ArgumentParser();parser.add_argument('--only',default='')
    options=parser.parse_args();os.environ['HF_HUB_OFFLINE']='1'
    manifest=json.loads((local_config.ROOT/'samples'/'panoramas'/'manifest.json').read_text(encoding='utf-8'))
    results=[]
    for item in manifest:
        if options.only and item['id']!=options.only:continue
        result=analyze_panorama(Image.open(item['file']),local_config.ROOT/'outputs'/'panorama'/item['id'],title=item['title'])
        result['source']={k:item[k] for k in ['source_url','source_title','author','license','download_url','credit']}
        Path(result['report_path']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append(result)
        print(json.dumps({'id':item['id'],**result['metrics'],
                          'water_by_view':{v['id']:round(v['report']['scene']['fractions']['water'],4) for v in result['views']}},ensure_ascii=False),flush=True)
    if not options.only:
        (local_config.ROOT/'outputs'/'panorama'/'batch_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
