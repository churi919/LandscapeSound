"""The public demo can play offline without accepting arbitrary local paths."""
import hashlib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from public_demo_ui import build_public_demo_html


def fixture(root):
    folder = root / 'demo_public'; folder.mkdir()
    scene = {'id': 'test_scene'}
    for field, subdir, suffix in [('image', 'images', '.jpg'), ('audio', 'audio', '.ogg'), ('narration', 'narration', '.mp3')]:
        path = folder / subdir / ('test_scene' + suffix); path.parent.mkdir()
        data = ('fixture-only-' + field).encode(); path.write_bytes(data)
        scene[field] = {'file': path.relative_to(folder).as_posix(), 'sha256': hashlib.sha256(data).hexdigest()}
    (folder / 'metadata.json').write_text(json.dumps({'schema_version': 1, 'scenes': [scene]}), encoding='utf-8')
    (folder / 'index.html').write_text('<img src="images/test_scene.jpg"><audio src="audio/test_scene.ogg"></audio><audio src="narration/test_scene.mp3"></audio><script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})));</script>', encoding='utf-8')
    return folder


def test_demo_is_self_contained_and_available_without_local_outputs(tmp_path):
    fixture(tmp_path)
    document = build_public_demo_html(tmp_path)
    assert 'src="data:image/jpeg;base64,' in document
    assert 'src="data:audio/ogg;base64,' in document
    assert 'src="data:audio/mpeg;base64,' in document
    assert 'b.pause()' in document
    source = 'from public_demo_ui import render_public_demo\nfrom pathlib import Path\nrender_public_demo(Path(' + repr(str(tmp_path)) + '))'
    app = AppTest.from_string(source).run()
    assert not app.exception
    assert '已保存的公开示例' in app.info[0].value
    assert len(app.get('iframe')) == 1
    assert not (tmp_path / 'outputs').exists()


def test_demo_rejects_traversal_and_changed_media_before_embedding(tmp_path):
    folder = fixture(tmp_path)
    metadata_path = folder / 'metadata.json'; original = metadata_path.read_text()
    metadata = json.loads(original); metadata['scenes'][0]['audio']['file'] = '../private.ogg'
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    with pytest.raises(ValueError, match='whitelist'):
        build_public_demo_html(tmp_path)
    metadata_path.write_text(original, encoding='utf-8')
    (folder / 'audio/test_scene.ogg').write_bytes(b'changed fixture')
    with pytest.raises(ValueError, match='checksum'):
        build_public_demo_html(tmp_path)
