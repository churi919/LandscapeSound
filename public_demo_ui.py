"""Offline, checksum-bound viewing of the curated public demonstration only."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

import streamlit as st
import streamlit.components.v1 as components

from ui_i18n import app_url, get_language, normalize_language


MEDIA = {'image': ('images', {'.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}),
         'audio': ('audio', {'.ogg': 'audio/ogg'}),
         'narration': ('narration', {'.mp3': 'audio/mpeg'})}


def build_public_demo_html(root, language=None, view='demo'):
    """Embed only manifest-listed, hash-verified assets inside demo_public.

    No model/runtime imports, arbitrary local paths, remote media requests or
    user-uploaded HTML are involved. Existing public-page layout is retained.
    """
    language = normalize_language(language or get_language())
    view = view if view in ('demo', 'compare') else 'demo'
    root = Path(root).resolve()
    folder = (root / 'demo_public').resolve()
    if not folder.is_relative_to(root):
        raise ValueError('Public demo directory must remain inside the project.')
    metadata_file = (folder / 'metadata.json').resolve()
    if not metadata_file.is_relative_to(folder):
        raise ValueError('Public demo metadata must remain inside demo_public.')
    if metadata_file.stat().st_size > 512 * 1024:
        raise ValueError('Public demo metadata is too large.')
    metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
    scenes = metadata.get('scenes')
    if metadata.get('schema_version') != 1 or not isinstance(scenes, list) or not 1 <= len(scenes) <= 8:
        raise ValueError('Public demo metadata is invalid.')
    embedded = {}; seen = set(); total = 0
    for scene in scenes:
        identifier = scene.get('id', '')
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9_-]{1,80}', identifier) or identifier in seen:
            raise ValueError('Public demo scene identifiers must be unique and bounded.')
        seen.add(identifier)
        for field, (subdir, suffixes) in MEDIA.items():
            item = scene.get(field)
            if not isinstance(item, dict):
                raise ValueError('Public demo media entry is missing.')
            relative = item.get('file', '')
            if not isinstance(relative, str) or '\\' in relative or ':' in relative:
                raise ValueError('Only whitelisted relative demo media paths are allowed.')
            posix = PurePosixPath(relative)
            if (len(posix.parts) != 2 or posix.parts[0] != subdir
                    or posix.suffix.lower() not in suffixes
                    or posix.stem != identifier or '..' in posix.parts):
                raise ValueError('Public demo media path is outside its whitelist.')
            path = (folder / relative).resolve()
            if not path.is_relative_to(folder) or path.parent != (folder / subdir).resolve():
                raise ValueError('Public demo media must stay inside demo_public.')
            if not path.is_file() or path.stat().st_size > 8 * 1024**2:
                raise ValueError('Public demo media is missing or too large.')
            data = path.read_bytes(); total += len(data)
            if total > 25 * 1024**2 or hashlib.sha256(data).hexdigest() != item.get('sha256'):
                raise ValueError('Public demo media checksum or size check failed.')
            embedded[relative] = 'data:' + suffixes[posix.suffix.lower()] + ';base64,' + base64.b64encode(data).decode('ascii')
    index = (folder / 'index.html').resolve()
    if not index.is_relative_to(folder):
        raise ValueError('Public demo page must remain inside demo_public.')
    if index.stat().st_size > 512 * 1024:
        raise ValueError('Public demo page is too large.')
    document = index.read_text(encoding='utf-8')

    def media_source(match):
        source = match.group(2)
        if source not in embedded:
            raise ValueError('Demo page requests an unlisted media source.')
        return 'src="' + embedded[source] + '"'

    document = re.sub(r'\bsrc\s*=\s*([\"\'])(.*?)\1', media_source, document, flags=re.I)
    # srcdoc does not inherit the parent's query string. Pass both the selected
    # language and every same-language parent route explicitly into the page.
    config_pattern = r'(<script id="ls-demo-config" type="application/json">)(.*?)(</script>)'
    def embedded_config(match):
        config = json.loads(match.group(2))
        config.update(language=language, forced_language=True, embedded=True,
                      current_view=view,
                      app_links={lang: {name: app_url(None if name == 'home' else name, lang)
                                        for name in ('home', 'demo', 'compare', 'guide', 'notices')}
                                 for lang in ('zh-CN', 'en')})
        return match.group(1) + json.dumps(config, ensure_ascii=False).replace('<', '\\u003c') + match.group(3)
    document = re.sub(config_pattern, embedded_config, document, flags=re.S)
    document = re.sub(r'<html lang="[^"]+">', '<html lang="' + language + '">', document, count=1)
    # Relative metadata/notice links cannot rely on a second local web server.
    meta_data = base64.b64encode(metadata_file.read_bytes()).decode('ascii')
    document = document.replace('href="metadata.json"', 'download="LandscapeSound-demo-metadata.json" href="data:application/json;base64,' + meta_data + '"')
    for lang, filename in (('zh-CN', 'THIRD_PARTY_NOTICES.zh-CN.md'), ('en', 'THIRD_PARTY_NOTICES.md')):
        document = document.replace('href="../' + filename + '"',
            'target="_top" href="' + app_url('notices', lang).replace('&', '&amp;') + '"')
    return document


def render_public_demo(root, language=None):
    language = normalize_language(language or get_language())
    def tr(chinese, english):
        return english if language == 'en' else chinese
    st.info(tr('已保存的公开示例：可直接试听，无需模型或联网。完整上传流程请切换到“上传我的全景图”。',
        'Saved public examples: listen without models or an internet connection. Select “Upload my panorama” for the complete upload workflow.'))
    st.caption(tr('这里播放已生成结果，不会运行新的图像理解，也不把完整全景图伪装成可转向的四方向分析。',
        'This page plays saved results without running new image understanding. Complete panoramas are shown as images, rather than interactive four-direction analysis.'))
    try:
        document = build_public_demo_html(root, language, view=st.query_params.get('view', 'demo'))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        st.warning(tr('公开试听包暂未通过完整校验。你仍可上传自己的全景图。',
            'The public demo package could not be verified. You can still upload your own panorama.'))
        with st.expander(tr('查看示例信息', 'View demo details')):
            st.code(str(exc), language=None)
        return False
    components.html(document, height=1080, scrolling=True)
    return True
