"""English presentation must not translate stored data or invoke generation."""
import copy
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from ui_i18n import set_language
from auto_pipeline_ui import _show_steps
from panorama_ui import _narration_only_page


def test_fresh_homepage_keeps_default_panorama_upload_mode_on_repeated_reruns():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'))
    app.query_params['lang']='en'
    # Start with no prefilled session values, just as a new browser session does.
    with patch('auto_pipeline_ui.launch_pipeline_worker') as worker, patch('panorama_ui._run_panorama') as analyze:
        app.run(timeout=20)
        assert not app.exception
        uploader_id=app.get('file_uploader')[0].proto.id
        for _ in range(3):
            app.run(timeout=20)
            assert not app.exception
            assert not app.warning
            assert app.radio(key='experience_mode').value=='360° 全景测试'
            assert app.radio(key='panorama_source_kind').value=='上传我的全景图'
            assert app.get('file_uploader')[0].proto.id==uploader_id
        app.radio(key='ui_language_picker').set_value('zh-CN').run(timeout=20)
        assert not app.exception
        assert app.radio(key='experience_mode').value=='360° 全景测试'
        assert app.radio(key='panorama_source_kind').value=='上传我的全景图'
        assert app.get('file_uploader')[0].proto.id==uploader_id
        worker.assert_not_called(); analyze.assert_not_called()
    set_language('zh-CN')


def test_language_switch_preserves_original_report_and_never_starts_generation():
    report={'title':'原始中文标题','input':{'sha256_rgb':'a'*64},
        'scene':{'description':'原始中文导览。','sources':[], 'fractions':{},
                 'depth_info':{'status':'relative'}},'metrics':{},'files':{}}
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'))
    app.query_params['lang']='en'
    for key,value in {'experience_mode':'普通照片','active_report':report,
                      'corrected_sources':[],'corrected_description':'原始中文导览。',
                      'result_key':'language-preserved-report','user_corrected':False}.items():
        app.session_state[key]=copy.deepcopy(value)
    with patch('auto_pipeline_ui.launch_pipeline_worker') as worker, patch('panorama_ui._run_panorama') as analyze, \
         patch('narration_ui.prepare_localized_narration',return_value=('Original Chinese guide translated for this fixture.',
             {'localized_text':'Original Chinese guide translated for this fixture.'})):
        app.run(timeout=20)
        assert not app.exception
        assert app.radio(key='experience_mode').value=='普通照片'
        assert app.radio(key='experience_mode').options==['Ordinary photo','360° panorama']
        assert any(item.label=='Photo source' for item in app.radio)
        assert any('neural narration are prepared and cached in the selected language' in item.value for item in app.caption)
        app.radio(key='ui_language_picker').set_value('zh-CN').run(timeout=20)
        assert not app.exception
        assert app.radio(key='experience_mode').value=='普通照片'
        assert app.session_state['active_report']['input']['sha256_rgb']=='a'*64
        assert app.session_state['corrected_description']=='原始中文导览。'
        assert app.session_state['result_key']=='language-preserved-report'
        assert any(item.label=='照片来源' for item in app.radio)
        worker.assert_not_called(); analyze.assert_not_called()
    set_language('zh-CN')


def test_known_pipeline_messages_and_cards_are_localized_without_changing_state():
    status={'status':'running','message':'正在生成自然中文配音…',
            'steps':[{'id':'narration','label':'生成自然配音','status':'running'}]}
    before=copy.deepcopy(status)
    set_language('en')
    try:
        with patch('auto_pipeline_ui.st.progress') as progress, patch('auto_pipeline_ui.st.markdown') as markdown:
            _show_steps(status)
        assert progress.call_args.kwargs['text']=='Generating Mandarin neural narration…'
        markup=markdown.call_args.args[0]
        assert 'Generate neural narration' in markup and 'Processing' in markup
        assert '自动生成进度' not in markup and '生成自然配音' not in markup
        assert status==before
    finally:set_language('zh-CN')


def test_translated_controls_keep_nondefault_values_and_uploader_identity():
    app=AppTest.from_string('''
import streamlit as st
from ui_i18n import init_language, render_language_switcher, t
from ui_labels import keep_ui_widget, localized_uploader, ui_formatter
init_language()
render_language_switcher()
keep_ui_widget(st.radio, t('照片来源','Photo source'), ['示例照片','上传我的照片'],
               key='source', format_func=ui_formatter())
keep_ui_widget(st.select_slider, t('时长','Duration'), [8,20,45], value=20, key='duration')
keep_ui_widget(st.slider, t('视野','Field of view'), 30.,120.,70.,5., key='field')
keep_ui_widget(st.text_input, t('标题','Title'), value='原始名称', key='title')
keep_ui_widget(st.checkbox, t('确认','Confirm'), key='confirmed')
localized_uploader(t('上传全景图','Upload panorama'), type=['png'], key='upload')
'''.encode('ascii','backslashreplace').decode('ascii'))
    app.query_params['lang']='en'
    app.run()
    uploader_id=app.get('file_uploader')[0].proto.id
    app.radio(key='source').set_value('上传我的照片')
    app.select_slider(key='duration').set_value(45)
    app.slider(key='field').set_value(95.)
    app.text_input(key='title').set_value('用户输入的原始名称')
    app.checkbox(key='confirmed').check().run()
    for language in ['zh-CN','en']:
        app.radio(key='ui_language_picker').set_value(language).run()
        assert not app.exception
        assert not app.warning
        assert app.radio(key='source').value=='上传我的照片'
        assert app.select_slider(key='duration').value==45
        assert app.slider(key='field').value==95.
        assert app.text_input(key='title').value=='用户输入的原始名称'
        assert app.checkbox(key='confirmed').value is True
        assert app.get('file_uploader')[0].proto.id==uploader_id
    set_language('zh-CN')


def test_narration_only_page_uses_stable_structure_in_both_player_languages():
    original='原始中文导览。'
    for language,main_label,stop_label in [('en','Soundscape audio and narration player','Stop all audio'),('zh-CN','景观声音与描述播放器','停止全部声音')]:
        set_language(language)
        page=f'<style></style><main id="landscape-player" aria-label="{main_label}"><button id="stop" class="stop">{stop_label}</button><div id="status" role="status">Ready</div></main>'
        result=_narration_only_page(page,original)
        assert result.count('id="narration-only-intro"')==1
        assert original in result
        assert ('Stop narration' if language=='en' else '停止朗读') in result
        if language=='en':assert 'English panorama guide' in result and '全景导览' not in result
    set_language('zh-CN')
