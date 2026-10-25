"""Create local demo copies; originals are never changed or uploaded."""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageOps
from local_config import ROOT

SAMPLES = [
    ('01_park', '_DSC2109.jpg', '草地与树木'),
    ('02_marina', '_DSC2069.jpg', '码头水面与帆船'),
    ('03_mangrove', '_DSC2551.jpg', '红树林水道'),
    ('04_lake', '_DSC2690.jpg', '开阔水面与远岸'),
    ('05_courtyard', '_DSC2245.jpg', '建筑下的庭院'),
]

def main():
    result = []
    for slug, name, title in SAMPLES:
        source = Path('D:/Lightroom导出照片') / name
        image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
        image.thumbnail((1280,1280), Image.Resampling.LANCZOS)
        target = ROOT/'samples'/(slug+'.jpg')
        image.save(target,quality=92)
        result.append({'id':slug,'title':title,'file':str(target),'source':str(source),
                       'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                       'demo_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                       'provenance':'Existing local photograph; source retained unchanged. Any optional GPT web processing is recorded separately in outputs/gpt_captions.json.',
                       'processing':'EXIF orientation applied; resized max1280; metadata omitted.'})
    (ROOT/'samples'/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared',len(result),'local demo photographs.')

if __name__ == '__main__': main()
