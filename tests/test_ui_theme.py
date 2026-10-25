"""Contrast and actual entry-point checks for the refreshed product UI."""
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from ui_theme import PALETTE


def contrast(a, b):
    def luminance(hex_value):
        values=[int(hex_value[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v,w in zip(linear,[.2126,.7152,.0722]))
    light,dark=sorted([luminance(a),luminance(b)],reverse=True)
    return (light+.05)/(dark+.05)


class VisualAccessTests(unittest.TestCase):
    def test_upload_navigation_is_explicit_and_consumed_only_once(self):
        code=("import streamlit as st\nfrom ui_theme import focus_upload_when_requested\n"
              "st.session_state['ls_focus_panorama_upload']=True\n"
              "st.write(focus_upload_when_requested())\n"
              "st.write(focus_upload_when_requested())\n")
        with patch('ui_theme.components.html') as render:
            app=AppTest.from_string(code,default_timeout=10).run()
            self.assertFalse(app.exception)
            render.assert_called_once()
            self.assertFalse(app.session_state.filtered_state.get('ls_focus_panorama_upload',False))
            script=render.call_args.args[0]
            self.assertIn('[data-testid="stFileUploader"]',script)
            self.assertIn("behavior:'instant'",script)
            self.assertIn('preventScroll:true',script)
            self.assertEqual(render.call_args.kwargs,{'height':0,'scrolling':False})

    def test_no_upload_navigation_without_a_button_intent(self):
        code="from ui_theme import focus_upload_when_requested\nfocus_upload_when_requested()\n"
        with patch('ui_theme.components.html') as render:
            app=AppTest.from_string(code,default_timeout=10).run()
            self.assertFalse(app.exception)
            render.assert_not_called()

    def test_failed_progress_keeps_a_readable_title(self):
        status={'status':'failed','message':'Traceback\nRuntimeError: internal details',
                'steps':[{'id':'audio','label':'生成本图声景','status':'failed'}]}
        code="from auto_pipeline_ui import _show_steps\n_show_steps("+ascii(status)+")"
        app=AppTest.from_string(code,default_timeout=10).run()
        self.assertFalse(app.exception)
        title=app.get('progress')[0].proto.text
        self.assertIn('已完成的步骤已保留',title)
        self.assertNotIn('Traceback',title)
        self.assertNotIn('internal details',title)

    def test_text_and_action_colors_meet_normal_text_contrast(self):
        pairs=[('ink','paper'),('muted','paper'),('mint','navy'),('warm','warm_surface')]
        for foreground,background in pairs:
            with self.subTest(foreground=foreground):
                self.assertGreaterEqual(contrast(PALETTE[foreground],PALETTE[background]),4.5)
        self.assertGreaterEqual(contrast('#FFFFFF',PALETTE['teal']),4.5)

    def test_default_and_hero_actions_open_the_intended_workflows(self):
        root=Path(__file__).resolve().parents[1]
        with patch('auto_pipeline_ui.launch_pipeline_worker',side_effect=AssertionError('UI entry invoked a worker without upload')), \
             patch('scene_audio_runtime.ensure_scene_audio',side_effect=AssertionError('Unexpected model generation')), \
             patch('narration.ensure_narration',side_effect=AssertionError('Unexpected online speech')):
            app=AppTest.from_file(str(root/'app.py'),default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key='experience_mode').value,'360° 全景测试')
            self.assertEqual(app.radio(key='panorama_source_kind').value,'上传我的全景图')
            self.assertEqual(len(app.get('file_uploader')),1)
            app.button(key='preview_panorama').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key='panorama_source_kind').value,'网上全景示例')
            app.button(key='begin_panorama').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key='panorama_source_kind').value,'上传我的全景图')


if __name__=='__main__':unittest.main()
