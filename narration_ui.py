"""Small host controls for exact-text natural narration and image-bound guides."""
import hashlib
import json
from pathlib import Path
import streamlit as st
from ui_i18n import get_language, t


def scene_narration_guide(report, scene_id, root):
    """Use a short spoken guide only for the exact panorama it describes."""
    path=Path(root)/'outputs'/'audio_refinement'/'narration_scripts.json'
    try:
        records=json.loads(path.read_text(encoding='utf-8')).get('items',[])
        for item in records:
            text=item.get('text')
            if (item.get('scene_id')==scene_id and item.get('image_sha256_rgb')==report.get('input',{}).get('sha256_rgb')
                    and isinstance(text,str) and text.strip()
                    and hashlib.sha256(text.encode('utf-8')).hexdigest()==item.get('text_sha256')):
                return item
    except (OSError,ValueError,TypeError):
        pass
    return None


def _original_record(source_text, language):
    digest=hashlib.sha256(source_text.encode('utf-8')).hexdigest()
    return {'source_text_sha256':digest,'text':source_text,'text_sha256':digest,
            'language':language,'provenance':{'method':'original text','translated':False}}


def _checked_record(record, source_text, language):
    from narration import language_for_text
    text=record.get('text') if isinstance(record,dict) else None
    if (not isinstance(text,str) or not text.strip()
            or record.get('source_text_sha256')!=hashlib.sha256(source_text.encode('utf-8')).hexdigest()
            or record.get('text_sha256')!=hashlib.sha256(text.encode('utf-8')).hexdigest()
            or record.get('language')!=language or language_for_text(text)!=language):
        raise ValueError('Localized narration does not match the source text and requested language')
    return record


def _localization_metadata(source_text, language, record=None, cached=None, status='ready'):
    record=record or {};cached=cached or {}
    return {'status':status,'language':language,'source_text':source_text,
        'source_text_sha256':hashlib.sha256(source_text.encode('utf-8')).hexdigest(),
        'text':record.get('text',''),'localized_text':record.get('text',''),
        'text_sha256':record.get('text_sha256'),
        'translation_provenance':record.get('provenance'),
        'available_voice_ids':[voice['voice_id'] for voice in cached.get('voices',[])],
        'voice_provider':cached.get('provider'),'not_human_recording':True}


def prepare_localized_narration(source_text, root, key):
    """Prepare a language overlay without modifying the source report or its job.

    Exact-text translations and voices are read locally first. Missing translated
    speech is prepared once; a failed attempt requires an explicit retry in this
    session, and no original-language fallback is returned to the player.
    """
    from narration import (get_narration_assets, ensure_narration,
                           default_voice_for_language, language_for_text)
    language=get_language()
    if not isinstance(source_text,str) or not source_text.strip():
        return '',_localization_metadata('',language,status='empty')
    source_language=language_for_text(source_text)
    digest=hashlib.sha256(source_text.encode('utf-8')).hexdigest()
    failure_key='localized_narration_failure_'+language+'_'+digest
    record=None;cached=None;read_error=None
    # Native Chinese guides retain the established optional-generation flow.
    require_neural=language=='en' or source_language!=language
    default_voice=default_voice_for_language(language)
    try:
        if source_language==language:
            record=_original_record(source_text,language)
        else:
            from narration_localization import load_localized_text
            record=load_localized_text(source_text,language,root=root)
        if record:
            record=_checked_record(record,source_text,language)
            cached=get_narration_assets(record['text'],root,language=language)
            ready={voice['voice_id'] for voice in cached.get('voices',[])}
            if not require_neural or default_voice in ready:
                st.session_state.pop(failure_key,None)
                return record['text'],_localization_metadata(source_text,language,record,cached)
    except Exception as exc:
        read_error=exc
    previous=st.session_state.get(failure_key)
    retry_rendered=False
    if previous:
        st.warning(t('当前语言的自然导览尚未就绪，未播放其他语言。',
                     'Narration in this language is not ready. Audio in another language has not been substituted.'))
        with st.expander(t('查看配音准备信息','View narration preparation details')):
            st.code(previous,language=None)
        retry=st.button(t('重试当前语言的导览与配音','Retry guide and narration in this language'),
                        key='retry_localized_narration_'+str(key)+'_'+language+'_'+digest[:12])
        retry_rendered=True
        if not retry:
            return '',_localization_metadata(source_text,language,record,cached,status='failed')
        st.session_state.pop(failure_key,None)
    try:
        if read_error:raise read_error
        if record is None:
            from narration_localization import ensure_localized_text
            with st.spinner(t('正在准备中文导览译文…','Preparing the English guide translation…')):
                record=_checked_record(ensure_localized_text(source_text,language,root=root),source_text,language)
            cached=get_narration_assets(record['text'],root,language=language)
        ready={voice['voice_id'] for voice in (cached or {}).get('voices',[])}
        if require_neural and default_voice not in ready:
            with st.spinner(t('正在生成中文自然配音，并保存到本机…',
                              'Generating English neural narration and saving it locally…')):
                cached=ensure_narration(record['text'],voices=[default_voice],root=root,language=language)
            if default_voice not in {voice['voice_id'] for voice in cached.get('voices',[])}:
                raise RuntimeError('The requested language voice did not pass cache verification')
        return record['text'],_localization_metadata(source_text,language,record,cached)
    except Exception as exc:
        st.session_state[failure_key]=f'{type(exc).__name__}: {exc}'
        st.error(t('当前语言的导览或自然配音未准备完成。未回播其他语言；可点击重试。',
                   'The guide or neural narration could not be prepared in this language. No other-language audio will play; you can retry.'))
        # Show a retry control now as well as on subsequent reruns.
        if not retry_rendered and st.button(t('重试当前语言的导览与配音','Retry guide and narration in this language'),
                     key='retry_localized_narration_'+str(key)+'_'+language+'_'+digest[:12]):
            st.session_state.pop(failure_key,None)
            st.rerun()
        return '',_localization_metadata(source_text,language,record,cached,status='failed')


def render_narration_controls(text, root, key):
    """Offer only this locale's two neural voices; extra voices are explicit."""
    from narration import (get_narration_assets,ensure_narration,
                           default_voice_for_language,voices_for_language,language_for_text)
    language=get_language()
    if not isinstance(text,str) or not text.strip():return None
    if language_for_text(text)!=language:
        st.info(t('请先准备中文导览与配音，再开始朗读。',
                  'Prepare the English guide and narration before playback.'))
        return None
    try:
        cached=get_narration_assets(text,root,language=language)
    except ValueError as exc:
        st.caption(str(exc));return None
    voices=voices_for_language(language)
    default_voice=default_voice_for_language(language)
    ready={voice['voice_id'] for voice in cached['voices'] if voice['voice_id'] in voices}
    if default_voice in ready:
        st.caption(t('自然女声“晓晓”已就绪，缓存配音可离线播放。',
                     'Jenny’s English neural narration is ready. Cached audio plays offline.'))
    else:
        st.info(t('当前中文导览尚未生成自然配音。生成后，朗读按钮会使用神经语音。',
                  'English neural narration is not ready for this guide yet.'))
    with st.expander(t('自然配音设置','English narration settings')):
        st.caption(t('采用中文神经语音。生成新配音会把中文导览文字发送到 Microsoft 语音服务；缓存播放在本机完成。',
                     'English neural voices Jenny and Guy are available. Generating a new voice sends the English guide text to Microsoft speech services; cached playback stays local.'))
        missing=[voice for voice in voices if voice not in ready]
        if missing:
            available=(Path(root)/'.venv_narration'/'Scripts'/'python.exe').is_file()
            label=t('生成自然配音','Generate English narration') if not ready else t('补充另一种自然配音','Add another English neural voice')
            if st.button(label,key='natural_narration_'+str(key)+'_'+language+'_'+cached['text_sha256'][:12],disabled=not available):
                try:
                    with st.spinner(t('正在生成中文自然配音，并保存到本机…',
                                      'Generating English neural narration and saving it locally…')):
                        cached=ensure_narration(text,voices=missing,root=root,language=language)
                    st.success(t('自然配音已就绪，下方播放器已更新。',
                                 'Neural narration is ready. The player below has been updated.'))
                except Exception as exc:
                    st.error(t('本次自然配音未生成完成，未自动换回系统配音。',
                               'Neural narration did not finish. The system voice was not selected automatically.'))
                    with st.expander(t('查看配音服务信息','View speech service details')):
                        st.code(f'{type(exc).__name__}: {exc}',language=None)
                    cached=get_narration_assets(text,root,language=language)
            if not available:
                st.caption(t('自然配音生成环境尚未安装。','The neural narration environment is not installed.'))
        else:
            st.write(t('女声“晓晓”和男声“云希”均已缓存，可在播放器中选择。',
                       'Jenny (female) and Guy (male) are both cached and can be selected in the player.'))
    return {'text_sha256':cached['text_sha256'],'language':language,
            'available_voice_ids':[voice['voice_id'] for voice in cached['voices'] if voice['voice_id'] in voices],
            'provider':cached['provider'],'not_human_recording':True,
            'active_voice_setting':'Export from player to capture the selected narration voice.'}
