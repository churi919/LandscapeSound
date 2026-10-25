"""Fetch new public photographic full panoramas for main-application uploads.

No GPT, visual/audio inference or narration is run by this preparation tool.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'samples' / 'multiscene_auto_20261025'
UA = 'LandscapeSound local research prototype / public CC0 demo assets; Powered by Poly Haven'
ASSETS = [
    ('monbachtal_riverbank', '林间浅溪与石间跌水', 'stream'),
    ('crystal_falls', '林间岩壁瀑布与水潭', 'stream'),
    ('secluded_beach', '沙石海滩与碎浪', 'coast'),
    ('urban_street_03', '阴天城市街道与沿街建筑', 'street'),
]


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(spec):
    identifier, title, group = spec
    info = json.loads(fetch('https://api.polyhaven.com/info/' + identifier))
    files = json.loads(fetch('https://api.polyhaven.com/files/' + identifier))
    entry = files['tonemapped']
    (FOLDER / (identifier + '_official_info.json')).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    (FOLDER / (identifier + '_official_files.json')).write_text(json.dumps(files, ensure_ascii=False, indent=2), encoding='utf-8')
    original = FOLDER / 'original_downloads' / (identifier + '.jpg')
    if not original.is_file() or hashlib.md5(original.read_bytes()).hexdigest() != entry['md5']:
        raw = fetch(entry['url'])
        if len(raw) != entry['size'] or hashlib.md5(raw).hexdigest() != entry['md5']:
            raise ValueError(identifier + ': official size/MD5 verification failed')
        original.write_bytes(raw)
    target = FOLDER / (identifier + '.jpg')
    with Image.open(original) as opened:
        source_size = list(opened.size)
        if opened.width != opened.height * 2:
            raise ValueError(identifier + ': expected full 2:1 ERP')
        opened.convert('RGB').resize((4096, 2048), Image.Resampling.LANCZOS).save(target, quality=94)
    with Image.open(target) as opened:
        image = opened.convert('RGB')
        rgb_hash = hashlib.sha256(image.tobytes()).hexdigest()
    item = {
        'id': identifier, 'title': title, 'comparison_group': group,
        'scene_group': {'stream': 'stream', 'coast': 'surf', 'street': 'traffic'}[group],
        'source_title': info['name'], 'source_url': 'https://polyhaven.com/a/' + identifier,
        'info_api_url': 'https://api.polyhaven.com/info/' + identifier,
        'source_api_url': 'https://api.polyhaven.com/files/' + identifier,
        'download_url': entry['url'], 'author': info.get('authors', {}),
        'license': 'CC0-1.0', 'license_url': 'https://polyhaven.com/license',
        'projection': 'equirectangular', 'coverage_degrees': [360, 180],
        'projection_source': 'https://docs.polyhaven.com/en/technical-standards/hdris',
        'projection_basis': 'Official Poly Haven photographic HDRI tonemapped full panorama; not a render or cropped perspective image.',
        'width': 4096, 'height': 2048, 'file': str(target), 'source_file': str(original),
        'source_size': source_size, 'source_bytes': original.stat().st_size,
        'source_md5': hashlib.md5(original.read_bytes()).hexdigest(),
        'source_sha256': sha(original), 'sha256': sha(target), 'sha256_rgb': rgb_hash,
        'processing': 'Official tonemapped photographic JPG resized to 4096x2048 with Lanczos and saved JPEG quality94. No generated content or scene edits.',
        'official_metadata': {key: info.get(key) for key in ('description', 'category', 'categories', 'tags', 'date_taken', 'max_resolution')},
        'public_asset_permitted_for_gpt_upload': True,
        'permission_basis': 'Public CC0 asset; user explicitly requested new public panorama uploads to the application GPT interpretation workflow.',
        'credit': 'Powered by Poly Haven', 'prepared_utc': datetime.now(timezone.utc).isoformat(),
        'cold_demo_boundary': 'Preparation downloads/resizes photographs only. No GPT, local visual/audio inference or TTS cache is created.',
    }
    (FOLDER / (identifier + '_asset_record.json')).write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
    return item


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    (FOLDER / 'original_downloads').mkdir(exist_ok=True)
    prior = set()
    for path in (ROOT / 'samples').glob('*/manifest.json'):
        if path.parent == FOLDER:
            continue
        value = json.loads(path.read_text(encoding='utf-8'))
        for item in value if isinstance(value, list) else value.get('items', []):
            if isinstance(item, dict):
                prior.add(item.get('id'))
    if prior.intersection(identifier for identifier, _, _ in ASSETS):
        raise ValueError('One selected asset was already used in earlier manifests')
    items = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(prepare, spec): spec for spec in ASSETS}
        for future in as_completed(pending):
            item = future.result()
            items[item['id']] = item
            print(json.dumps({'ready': item['id'], 'file': item['file'], 'sha256': item['sha256']}, ensure_ascii=False), flush=True)
            ordered = [items[identifier] for identifier, _, _ in ASSETS if identifier in items]
            (FOLDER / 'manifest.json').write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding='utf-8')
    print('All four photographs prepared; visual inspection remains separate.', flush=True)


if __name__ == '__main__':
    main()
