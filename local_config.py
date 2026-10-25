"""Keep downloads and temporary files on the project's drive."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for key, relative in {
    'HF_HOME': 'models/huggingface',
    'HF_HUB_CACHE': 'models/huggingface/hub',
    'TORCH_HOME': 'models/torch',
    'UV_CACHE_DIR': '.cache/uv',
    'PIP_CACHE_DIR': '.cache/pip',
    'TEMP': '.cache/tmp',
    'TMP': '.cache/tmp',
}.items():
    folder = ROOT / relative
    folder.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(folder)
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '120')
