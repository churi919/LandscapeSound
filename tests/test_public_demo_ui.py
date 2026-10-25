"""The public demo can play offline without accepting arbitrary local paths."""
import hashlib
import json
from pathlib import Path
import re

import pytest
from streamlit.testing.v1 import AppTest

from public_demo_ui import build_public_demo_html
from scripts import build_public_demo as builder
from ui_i18n import set_language


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


def bilingual_fixture(root):
    """Use real public prose with tiny media; no models or private outputs."""
    original = json.loads((Path(__file__).resolve().parents[1] / 'demo_public/metadata.json').read_text(encoding='utf-8'))
    scene = original['scenes'][0]
    folder = root / 'demo_public'; folder.mkdir()
    for field in ('image', 'audio', 'narration'):
        path = folder / scene[field]['file']; path.parent.mkdir()
        data = ('bilingual-fixture-' + field).encode(); path.write_bytes(data)
        scene[field]['sha256'] = hashlib.sha256(data).hexdigest()
    metadata = {'schema_version': 1, 'scenes': [scene]}
    (folder / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    (folder / 'index.html').write_text(builder.render(metadata), encoding='utf-8')
    for filename in ('README.md', 'README.zh-CN.md', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.zh-CN.md'):
        (root / filename).write_text('Fixture documentation', encoding='utf-8')
    return folder, metadata


def demo_config(document):
    return json.loads(re.search(r'<script id="ls-demo-config" type="application/json">(.*?)</script>', document, re.S).group(1))


def test_bilingual_page_has_complete_localized_content_and_honest_narration(tmp_path):
    folder, metadata = bilingual_fixture(tmp_path)
    document = (folder / 'index.html').read_text(encoding='utf-8')
    chinese = re.search(r'<template id="demo-zh-CN">(.*?)</template>', document, re.S).group(1)
    english = re.search(r'<template id="demo-en">(.*?)</template>', document, re.S).group(1)
    assert '暂停所有声音' in chinese and 'Pause all audio' in english
    assert '溪流还是雨：问题仍然存在' in chinese
    assert 'Stream or rain: the problem remains' in english
    assert '0.535' in english and '0.620' in english and '0.861' in english
    assert 'complete equirectangular panorama' in english
    assert 'Mossy stream and small cascades' in english
    assert 'Chinese narration (original)' in english
    assert 'English translation for reading only' in english
    assert metadata['scenes'][0]['narration']['text'] in english
    assert 'href="../THIRD_PARTY_NOTICES.zh-CN.md"' in chinese
    assert 'href="../THIRD_PARTY_NOTICES.md"' in english
    # Language is resolved in the head before either template is mounted.
    assert document.index('document.documentElement.lang=demoLanguage') < document.index('<body>')
    assert 'new URLSearchParams(location.search).get(\'lang\')' in document
    assert 'other.pause()' in document


def test_embedded_language_and_compare_routes_are_explicit_and_media_stay_offline(tmp_path):
    bilingual_fixture(tmp_path)
    try:
        set_language('en')
        document = build_public_demo_html(tmp_path, view='compare')
        config = demo_config(document)
        assert config['language'] == 'en' and config['forced_language'] is True
        assert config['embedded'] is True and config['current_view'] == 'compare'
        assert '<html lang="en">' in document
        for lang in ('en', 'zh-CN'):
            links = config['app_links'][lang]
            assert links['compare'] == '?lang=' + lang + '&view=compare'
            assert links['demo'] == '?lang=' + lang + '&view=demo'
            assert links['guide'] == '?lang=' + lang + '&view=guide'
            assert links['notices'] == '?lang=' + lang + '&view=notices'
        assert all(source.startswith('data:') for source in re.findall(r'\bsrc="([^"]+)"', document))
        assert 'href="?lang=en&amp;view=notices"' in document
        # Explicit language overrides the current session context.
        assert demo_config(build_public_demo_html(tmp_path, language='zh-CN'))['language'] == 'zh-CN'
    finally:
        set_language('zh-CN')


def test_html_only_build_is_reproducible_without_touching_public_assets(tmp_path, monkeypatch):
    folder, _ = bilingual_fixture(tmp_path)
    before = {path.relative_to(folder): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in folder.rglob('*') if path.is_file() and path.name != 'index.html'}
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'OUTPUT', folder)
    result = builder.build_html_only()
    first_page = (folder / 'index.html').read_bytes()
    builder.build_html_only()
    assert (folder / 'index.html').read_bytes() == first_page
    assert result['artifact_hashes_verified']
    assert {path.relative_to(folder): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob('*') if path.is_file() and path.name != 'index.html'} == before


def test_english_streamlit_demo_has_english_status_and_no_new_outputs(tmp_path):
    bilingual_fixture(tmp_path)
    source = ('from public_demo_ui import render_public_demo\nfrom pathlib import Path\n'
              'render_public_demo(Path(' + repr(str(tmp_path)) + '), language="en")')
    app = AppTest.from_string(source).run()
    assert not app.exception
    assert app.info[0].value.startswith('Saved public examples:')
    assert app.caption[0].value.startswith('This page plays saved results')
    assert len(app.get('iframe')) == 1
    assert not (tmp_path / 'outputs').exists()
