"""English host controls remain explicit about original Chinese narration."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class NarrationHostLanguageTests(unittest.TestCase):
    def test_english_cached_voice_controls_do_not_translate_or_request_speech(self):
        original='这段原始中文导览必须保持逐字一致。'
        cached={'text_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'voices':[{'voice_id':'zh-CN-XiaoxiaoNeural'}],'provider':'Synthetic fixture provider'}
        with tempfile.TemporaryDirectory() as folder:
            code=("from pathlib import Path\nfrom ui_i18n import set_language\n"
                  "from narration_ui import render_narration_controls\nset_language('en')\n"
                  f"render_narration_controls({ascii(original)},Path({ascii(folder)}),'fixture')\n")
            with patch('narration.get_narration_assets',return_value=cached) as read, \
                 patch('narration.ensure_narration',side_effect=AssertionError('No online speech during rendering')) as generate:
                app=AppTest.from_string(code,default_timeout=10).run()
                self.assertFalse(app.exception)
                self.assertTrue(any('not an English translation' in item.value for item in app.caption))
                self.assertEqual(app.expander[0].label,'Chinese narration settings')
                self.assertTrue(any('Add another Chinese neural voice'==item.label for item in app.button))
                self.assertEqual(read.call_args.args[0],original)
                generate.assert_not_called()

    def test_english_original_preview_is_not_presented_as_a_chinese_guide(self):
        original='This is the original English preview.'
        for ready in [False,True]:
            with self.subTest(ready=ready),tempfile.TemporaryDirectory() as folder:
                cached={'text_sha256':hashlib.sha256(original.encode()).hexdigest(),
                    'voices':[{'voice_id':'zh-CN-XiaoxiaoNeural'}] if ready else [],'provider':'Synthetic fixture provider'}
                code=("from pathlib import Path\nfrom ui_i18n import set_language\n"
                      "from narration_ui import render_narration_controls\nset_language('en')\n"
                      f"render_narration_controls({ascii(original)},Path({ascii(folder)}),'fixture')\n")
                with patch('narration.get_narration_assets',return_value=cached) as read, \
                     patch('narration.ensure_narration',side_effect=AssertionError('No online speech during rendering')) as generate:
                    app=AppTest.from_string(code,default_timeout=10).run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.expander[0].label,'Narration settings')
                    self.assertTrue(any('local English system voice' in item.value for item in app.caption))
                    if ready:
                        self.assertTrue(any('exact English text' in item.value for item in app.caption))
                    else:
                        self.assertTrue(any(item.label=='Generate using a Chinese voice' for item in app.button))
                    self.assertEqual(read.call_args.args[0],original)
                    generate.assert_not_called()


if __name__=='__main__':unittest.main()
