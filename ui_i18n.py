"""Session-local UI language and same-language routes; no model calls."""
from contextvars import ContextVar
import json
from urllib.parse import urlencode

_language = ContextVar('landscapesound_ui_language', default='zh-CN')
LANGUAGES = ('zh-CN', 'en')


def normalize_language(value):
    return 'en' if str(value).lower() in ('en', 'en-us', 'en-gb') else 'zh-CN'


def set_language(value):
    language = normalize_language(value)
    _language.set(language)
    return language


def get_language():
    return _language.get()


def t(chinese, english, **values):
    text = english if get_language() == 'en' else chinese
    return text.format(**values) if values else text


def app_url(view=None, language=None):
    params = {'lang': normalize_language(language or get_language())}
    if view in ('demo', 'compare', 'guide', 'architecture', 'notices', 'audio'):
        params['view'] = view
    return '?' + urlencode(params)


def document_name(kind, language=None):
    english = normalize_language(language or get_language()) == 'en'
    names = {
        'guide': 'README.md' if english else 'README.zh-CN.md',
        'architecture': 'docs/architecture.md' if english else 'docs/architecture.zh-CN.md',
        'notices': 'THIRD_PARTY_NOTICES.md' if english else 'THIRD_PARTY_NOTICES.zh-CN.md',
        'audio': 'audio_model/README.md' if english else 'audio_model/README.zh-CN.md',
    }
    return names[kind]


def init_language():
    import streamlit as st
    requested = st.query_params.get('lang')
    language = normalize_language(requested if requested is not None else st.session_state.get('ui_language', 'zh-CN'))
    st.session_state['ui_language'] = language
    if st.session_state.get('_ui_language_query') != language:
        st.session_state['ui_language_picker'] = language
    st.session_state['_ui_language_query'] = language
    return set_language(language)


def render_language_switcher():
    import streamlit as st

    def changed():
        chosen = normalize_language(st.session_state['ui_language_picker'])
        st.session_state['ui_language'] = chosen
        st.session_state['_ui_language_query'] = chosen
        st.query_params['lang'] = chosen

    chosen = st.radio('语言 / Language', LANGUAGES,
                      index=None if 'ui_language_picker' in st.session_state else 0,
                      format_func=lambda value: 'English' if value == 'en' else '中文',
                      horizontal=True, key='ui_language_picker', on_change=changed)
    set_language(chosen)
    # This updates only accessibility metadata in our own application document.
    import streamlit.components.v1 as components
    language = json.dumps(get_language())
    title = json.dumps(t('LandscapeSound · 景观听见', 'LandscapeSound'))
    components.html('<!doctype html><html><script>try{window.parent.document.documentElement.lang=' + language +
                    ';window.parent.document.title=' + title + ';}catch(e){}</script></html>', height=0)
