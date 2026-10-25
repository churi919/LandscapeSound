"""Language overlays preserve source text and never substitute another language."""
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
from narration_localization import ensure_localized_text, store_reviewed_translation


def assets(text, language, ready=True):
    voice='en-US-JennyNeural' if language=='en' else 'zh-CN-XiaoxiaoNeural'
    return {'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'provider':'Fixture neural speech',
            'language':language,'voices':[{'voice_id':voice}] if ready else []}


def script(source, root, language='en'):
    return ("import streamlit as st\nfrom pathlib import Path\nfrom ui_i18n import set_language\n"
            "from narration_ui import prepare_localized_narration\n"
            f"set_language({language!r})\n"
            f"text,meta=prepare_localized_narration({ascii(source)},Path({ascii(str(root))}),'fixture')\n"
            "st.session_state['playback']=text\nst.session_state['metadata']=meta\n")


def test_verified_english_overlay_and_voice_are_reopened_without_network(tmp_path):
    source='石块之间可见一条溪流，声音是模拟而非现场录音。'
    english='A stream is visible between the rocks. Its sound is simulated, not a site recording.'
    store_reviewed_translation(source,english,'en',{'method':'reviewed test fixture'},root=tmp_path)
    with patch('narration.get_narration_assets',return_value=assets(english,'en')) as read, \
         patch('narration_localization.ensure_localized_text',side_effect=AssertionError('translation network')) as translate, \
         patch('narration.ensure_narration',side_effect=AssertionError('speech network')) as generate:
        app=AppTest.from_string(script(source,tmp_path)).run()
        assert not app.exception
        assert app.session_state['playback']==english
        meta=app.session_state['metadata']
        assert meta['source_text']==source and meta['localized_text']==english
        assert meta['translation_provenance']['method']=='reviewed test fixture'
        assert meta['available_voice_ids']==['en-US-JennyNeural']
        assert read.call_args.kwargs['language']=='en'
        translate.assert_not_called();generate.assert_not_called()


def test_missing_translation_and_voice_are_created_once_then_reused_across_sessions(tmp_path):
    source='前方可见海面，浪声为模拟。';english='The sea is visible ahead. The surf sound is simulated.'
    translator=Mock(return_value={'text':english,'provenance':{'method':'mock GPT text translation'}})
    voice_cache={}
    def read(text,root,language=None):
        return voice_cache.get((text,language),assets(text,language,False))
    def synthesize(text,voices,root,language=None):
        assert text==english and voices==['en-US-JennyNeural'] and language=='en'
        value=assets(text,language);voice_cache[text,language]=value;return value
    def translate(text,language,root=None):
        return ensure_localized_text(text,language,root=root,translator=translator)
    with patch('narration.get_narration_assets',side_effect=read), \
         patch('narration_localization.ensure_localized_text',side_effect=translate) as prepare_text, \
         patch('narration.ensure_narration',side_effect=synthesize) as generate:
        for _ in range(2):
            app=AppTest.from_string(script(source,tmp_path)).run()
            assert not app.exception
            assert app.session_state['playback']==english
            assert app.session_state['metadata']['source_text']==source
        assert translator.call_count==1 and prepare_text.call_count==1 and generate.call_count==1


def test_speech_failure_blocks_fallback_and_retries_only_after_explicit_click(tmp_path):
    source='眼前可见树木。';english='Trees are visible ahead.'
    store_reviewed_translation(source,english,'en',{'method':'reviewed test fixture'},root=tmp_path)
    with patch('narration.get_narration_assets',return_value=assets(english,'en',False)) as read, \
         patch('narration.ensure_narration',side_effect=[RuntimeError('temporary speech failure'),assets(english,'en')]) as generate:
        app=AppTest.from_string(script(source,tmp_path)).run()
        assert not app.exception
        assert app.session_state['playback']==''
        assert app.session_state['metadata']['localized_text']==english
        assert app.session_state['metadata']['status']=='failed'
        app.run()
        assert not app.exception and app.session_state['playback']=='' and generate.call_count==1
        retry=next(button for button in app.button if button.key.startswith('retry_localized_narration_'))
        retry.click().run()
        assert not app.exception and app.session_state['playback']==english and generate.call_count==2
        assert all(call.args[0]==english for call in read.call_args_list)


def test_translation_failure_is_not_repeated_and_never_sends_chinese_to_english_tts(tmp_path):
    source='这里是一条溪流。'
    with patch('narration_localization.ensure_localized_text',side_effect=RuntimeError('translation unavailable')) as translate, \
         patch('narration.ensure_narration',side_effect=AssertionError('must not speak source text')) as generate:
        app=AppTest.from_string(script(source,tmp_path)).run()
        app.run()
        assert not app.exception and app.session_state['playback']==''
        assert translate.call_count==1
        generate.assert_not_called()


def test_chinese_ui_translates_english_original_and_keeps_source_unchanged(tmp_path):
    source='Water is visible to the right. Its sound is simulated.';chinese='右侧可见水面，声音是模拟。'
    translator=Mock(return_value={'text':chinese,'provenance':{'method':'mock GPT text translation'}})
    def translate(text,language,root=None):
        return ensure_localized_text(text,language,root=root,translator=translator)
    with patch('narration_localization.ensure_localized_text',side_effect=translate), \
         patch('narration.get_narration_assets',return_value=assets(chinese,'zh-CN',False)), \
         patch('narration.ensure_narration',return_value=assets(chinese,'zh-CN')) as generate:
        app=AppTest.from_string(script(source,tmp_path,'zh-CN')).run()
        assert not app.exception
        assert app.session_state['playback']==chinese and app.session_state['metadata']['source_text']==source
        generate.assert_called_once_with(chinese,voices=['zh-CN-XiaoxiaoNeural'],root=tmp_path,language='zh-CN')


def test_controls_offer_only_the_current_language_and_reject_wrong_text(tmp_path):
    english='This is an English landscape guide.'
    def code(text):
        return ("from pathlib import Path\nfrom ui_i18n import set_language\n"
                "from narration_ui import render_narration_controls\nset_language('en')\n"
                f"render_narration_controls({ascii(text)},Path({ascii(str(tmp_path))}),'fixture')\n")
    with patch('narration.get_narration_assets',return_value=assets(english,'en')) as read, \
         patch('narration.ensure_narration',side_effect=AssertionError('render is read-only')) as generate:
        app=AppTest.from_string(code(english)).run()
        assert not app.exception
        assert app.expander[0].label=='English narration settings'
        assert any(button.label=='Add another English neural voice' for button in app.button)
        assert any('Jenny and Guy' in item.value for item in app.caption)
        assert read.call_args.kwargs['language']=='en'
        generate.assert_not_called()
        read.reset_mock()
        app=AppTest.from_string(code('原始中文不能回播为英文配音。')).run()
        assert not app.exception
        assert any('Prepare the English guide' in item.value for item in app.info)
        read.assert_not_called();generate.assert_not_called()
