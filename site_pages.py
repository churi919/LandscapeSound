"""Local website pages with language-preserving navigation."""
from pathlib import Path
import html
import re
from urllib.parse import parse_qs, quote, unquote, urlsplit

import streamlit as st

from ui_i18n import app_url, document_name, get_language, t

PUBLIC_REPOSITORY = 'https://github.com/churi919/LandscapeSound'
DOCUMENT_VIEWS = ('guide', 'architecture', 'notices', 'audio')


def current_view():
    value = st.query_params.get('view', '')
    return value if value in ('demo', 'compare', *DOCUMENT_VIEWS) else ''


def render_navigation():
    view = current_view()
    items = [('', t('开始体验', 'Start exploring')),
             ('demo', t('已完成示例', 'Saved examples')),
             ('compare', t('场景对比', 'Compare scenes')),
             ('guide', t('使用说明', 'Guide'))]
    links = []
    for target, label in items:
        selected = ' aria-current="page"' if target == view else ''
        links.append(f'<a href="{html.escape(app_url(target))}" target="_self"{selected}>{html.escape(label)}</a>')
    st.markdown('<nav class="ls-nav" aria-label="' + t('主要导航', 'Main navigation') + '">' + ''.join(links) + '</nav>', unsafe_allow_html=True)


def rewrite_document_links(source, document, root):
    """Map public documentation links to the matching local language page."""
    root = Path(root).resolve()
    document = Path(document).resolve()
    known = {}
    for language in ('zh-CN', 'en'):
        for view in DOCUMENT_VIEWS:
            known[(root / document_name(view, language)).resolve()] = (view, language)

    def link(match):
        prefix, label, raw = match.groups()
        if prefix == '!':
            return match.group(0)
        if raw.startswith(('#', 'https://', 'mailto:')):
            return match.group(0)
        if raw.startswith('http://127.0.0.1:8501/'):
            query = parse_qs(urlsplit(raw).query)
            destination = app_url(query.get('view', [None])[0], query.get('lang', [get_language()])[0])
        elif raw.startswith('http://127.0.0.1:8502/demo_public/'):
            query = parse_qs(urlsplit(raw).query)
            destination = app_url('demo', query.get('lang', [get_language()])[0])
        elif re.match(r'^[a-zA-Z]+:', raw):
            return match.group(0)
        else:
            target, _, fragment = raw.partition('#')
            resolved = (document.parent / unquote(target)).resolve()
            if not resolved.is_relative_to(root):
                return html.escape(label)
            if resolved in known:
                view, language = known[resolved]
                destination = app_url(view, language)
                if fragment:
                    destination += '#' + fragment
            elif resolved == root / 'demo_public/index.html':
                destination = app_url('demo')
            else:
                relative = resolved.relative_to(root).as_posix()
                destination = PUBLIC_REPOSITORY + '/blob/main/' + quote(relative, safe='/')
                if fragment:
                    destination += '#' + fragment
        return f'[{label}]({destination})'

    return re.sub(r'(!?)\[([^\]]*)\]\(([^)]+)\)', link, source)


def render_document(root, view):
    root = Path(root).resolve()
    document = root / document_name(view)
    if not document.is_file():
        st.info(t('这份说明尚未准备好。', 'This guide is not available yet.'))
        return
    source = rewrite_document_links(document.read_text(encoding='utf-8-sig'), document, root)
    # Render local pictures directly, without requiring a second static server.
    position = 0
    for picture in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', source):
        st.markdown(source[position:picture.start()])
        image = (document.parent / unquote(picture.group(2))).resolve()
        if image.is_relative_to(root) and image.is_file():
            st.image(str(image), caption=picture.group(1), width='stretch')
        position = picture.end()
    st.markdown(source[position:])


def render_site_view(root):
    view = current_view()
    if view in ('demo', 'compare'):
        from public_demo_ui import render_public_demo
        st.title(t('对比不同风景的声音', 'Compare the sounds of different landscapes') if view == 'compare'
                 else t('先听一幅已完成的风景', 'Listen to a completed landscape'))
        st.caption(t('画面、声景与中文导览来自同一组已完成示例。可逐个试听，按自己的节奏比较。',
                     'Explore the pictures, soundscapes and original Chinese guides from four saved examples, one at a time.'))
        render_public_demo(root)
        return True
    if view in DOCUMENT_VIEWS:
        render_document(root, view)
        return True
    return False
