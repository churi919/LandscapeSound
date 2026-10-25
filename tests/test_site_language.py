"""Language routes preserve context and do not alter research artifacts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs
import unittest
from streamlit.testing.v1 import AppTest

from site_pages import rewrite_document_links
from ui_i18n import app_url, document_name, get_language, set_language, t


class LanguageRouteTests(unittest.TestCase):
    def tearDown(self):
        set_language('zh-CN')

    def test_language_is_local_to_each_render_thread(self):
        def render(language):
            set_language(language)
            return t('中文控件', 'English control'), get_language()
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(render, ('zh-CN', 'en')))
        self.assertEqual(values, [('中文控件', 'zh-CN'), ('English control', 'en')])
        self.assertEqual(get_language(), 'zh-CN')

    def test_routes_and_document_choices_follow_current_language(self):
        for language in ('zh-CN', 'en'):
            set_language(language)
            for view in ('demo', 'compare', 'guide', 'architecture', 'notices', 'audio'):
                self.assertEqual(parse_qs(app_url(view)[1:]), {'lang': [language], 'view': [view]})
            self.assertEqual(document_name('guide'), 'README.md' if language == 'en' else 'README.zh-CN.md')
        self.assertEqual(parse_qs(app_url('../../private', 'unknown')[1:]), {'lang': ['zh-CN']})

    def test_language_switch_preserves_the_open_page_and_uses_query_links(self):
        code = ('import streamlit as st\n'
                'from ui_i18n import init_language,render_language_switcher,t,app_url\n'
                'init_language()\nrender_language_switcher()\n'
                'st.write(t(' + ascii('中文界面') + ', "English interface"))\n'
                'st.write(app_url("compare"))\n')
        app = AppTest.from_string(code)
        app.query_params['lang'] = 'en'
        app.query_params['view'] = 'compare'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='ui_language_picker').value, 'en')
        self.assertTrue(any('English interface' in item.value for item in app.markdown))
        app.radio(key='ui_language_picker').set_value('zh-CN').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.query_params['lang'], ['zh-CN'])
        self.assertEqual(app.query_params['view'], ['compare'])
        self.assertTrue(any('中文界面' in item.value for item in app.markdown))
        # A direct English link must override a previous Chinese session choice.
        app.query_params['lang'] = 'en'
        app.run()
        self.assertEqual(app.radio(key='ui_language_picker').value, 'en')

    def test_document_links_use_the_destination_language_and_local_pages(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for language in ('zh-CN', 'en'):
                for view in ('guide', 'architecture', 'notices', 'audio'):
                    path = root / document_name(view, language)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('guide', encoding='utf-8')
            set_language('en')
            source = ('[English](README.md) [中文](README.zh-CN.md) '
                      '[Architecture](docs/architecture.md) [Notice](THIRD_PARTY_NOTICES.md) '
                      '[Demo](demo_public/index.html) [Site](http://127.0.0.1:8501/) '
                      '[Saved](http://127.0.0.1:8502/demo_public/) '
                      '[Chinese site](http://127.0.0.1:8501/?lang=zh-CN) '
                      '[Outside](../private.md)')
            rewritten = rewrite_document_links(source, root / 'README.md', root)
            self.assertIn('[English](?lang=en&view=guide)', rewritten)
            self.assertIn('[中文](?lang=zh-CN&view=guide)', rewritten)
            self.assertIn('[Architecture](?lang=en&view=architecture)', rewritten)
            self.assertIn('[Notice](?lang=en&view=notices)', rewritten)
            self.assertIn('[Demo](?lang=en&view=demo)', rewritten)
            self.assertIn('[Site](?lang=en)', rewritten)
            self.assertIn('[Chinese site](?lang=zh-CN)', rewritten)
            self.assertNotIn('8502', rewritten)
            self.assertNotIn('../private.md', rewritten)


if __name__ == '__main__':
    unittest.main()
