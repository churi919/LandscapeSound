"""Reproducible batch demos and an offline repeat on the same hardware."""
import local_config
import argparse
import json
from pathlib import Path
from PIL import Image
from browser_audio import render_audio

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--offline',action='store_true')
    args.add_argument('--only',default='')
    options=args.parse_args()
    if options.offline:
        import os
        os.environ['HF_HUB_OFFLINE']='1'
    from analyzer import analyze_image
    manifest=json.loads((local_config.ROOT/'samples'/'manifest.json').read_text(encoding='utf-8'))
    results=[]
    for sample in manifest:
        if options.only and sample['id'] != options.only: continue
        group = 'checks' if options.only else 'demo'
        out=local_config.ROOT/'outputs'/group/sample['id']
        report=analyze_image(Image.open(sample['file']),out,title=sample['title'])
        (out/'listen.html').write_text(render_audio(report['scene']['sources'],report['scene']['description'],local_config.ROOT/'assets'),encoding='utf-8')
        print(json.dumps({'id':sample['id'],'sources':len(report['scene']['sources']),**report['metrics']},ensure_ascii=False),flush=True)
        results.append(report)
    if not options.only:
        (local_config.ROOT/'outputs'/'demo'/'batch_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
