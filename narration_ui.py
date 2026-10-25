"""Small host controls for exact-text natural narration and image-bound guides."""
import hashlib
import json
from pathlib import Path
import streamlit as st
from ui_i18n import get_language, t
from audio_player_v2 import original_text_language


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


def render_narration_controls(text, root, key):
    """Generation is explicit; reading or rendering a page never uploads text."""
    from narration import get_narration_assets,ensure_narration,VOICES,DEFAULT_VOICE
    chinese_text=original_text_language(text)!='en'
    try:
        cached=get_narration_assets(text,root)
    except ValueError as exc:
        st.caption(str(exc));return None
    ready={x['voice_id'] for x in cached['voices']}
    if DEFAULT_VOICE in ready:
        if chinese_text:
            st.caption(t('朗读已备好自然女声“晓晓”。可在播放器里切换配音；缓存音频可离线播放。',
                'Chinese neural female narration (Xiaoxiao) is ready for this original guide. It is not an English translation. Cached audio plays offline.'))
        else:
            st.caption(t('这段英文原文已有使用中文音色“晓晓”生成的配音缓存。未进行翻译；可手动选择英文系统配音。',
                'This exact English text has cached narration using Xiaoxiao, a Chinese-configured neural voice. No translation was performed. An English system voice can be selected explicitly.'))
    else:
        st.info(t('当前文字尚未生成自然配音。生成后，朗读按钮会使用神经语音。',
            'Neural narration for this original text has not been generated. Once generated, the reading button will use the cached neural voice.'))
    with st.expander(t('自然配音设置','Chinese narration settings' if chinese_text else 'Narration settings')):
        if chinese_text:
            st.caption(t('采用神经语音合成，保留系统旧配音作为对照。生成新配音需要联网，会把这段朗读文字发送到 Microsoft 语音服务；已缓存的播放在本机完成。',
                'Chinese neural speech is used; the legacy Chinese system voice remains available for comparison. Generating new narration sends the original guide text to Microsoft speech services. No translation is performed. Cached playback stays local.'))
        else:
            st.caption(t('当前神经配音使用中文音色，尚未配置专门的英文神经音色。可手动选择本机英文系统配音朗读英文原文。生成按钮会把原文发送到 Microsoft 语音服务，使用现有中文音色生成缓存，不进行翻译。',
                'The configured neural voices are Chinese; an English neural voice has not been configured. You can explicitly select a local English system voice to read the unchanged English text. Generation sends the original text to Microsoft speech services and uses the configured Chinese voice, without translation.'))
        missing=[voice for voice in VOICES if voice not in ready]
        if missing:
            available=(Path(root)/'.venv_narration'/'Scripts'/'python.exe').is_file()
            label=(t('生成自然配音','Generate Chinese narration') if not ready else t('补充另一种自然配音','Add another Chinese neural voice')) if chinese_text else (t('使用中文音色生成配音','Generate using a Chinese voice') if not ready else t('补充另一种中文音色','Add another Chinese voice'))
            if st.button(label,key='natural_narration_'+str(key)+'_'+cached['text_sha256'][:12],disabled=not available):
                try:
                    with st.spinner(t('正在生成自然配音，并保存到本机…','Generating neural narration with the configured Chinese voice and saving it locally…')):
                        cached=ensure_narration(text,voices=missing,root=root)
                    st.success(t('自然配音已就绪，下方播放器已更新。','Neural narration is ready. The player below has been updated.'))
                except Exception as exc:
                    st.error(t('本次自然配音未生成完成，未自动换回系统配音。',
                        'Neural narration did not finish. The system voice was not selected automatically.'))
                    if get_language()=='en':
                        with st.expander('Original service diagnostic'):
                            st.code(f'{type(exc).__name__}: {exc}',language=None)
                    else:
                        st.caption(f'{type(exc).__name__}: {exc}')
                    cached=get_narration_assets(text,root)
            if not available:
                st.caption(t('自然配音生成环境尚未安装。','The Chinese neural narration environment is not installed.'))
        else:
            st.write(t('女声“晓晓”和男声“云希”均已缓存，可在播放器中选择。',
                'Chinese-configured neural voices Xiaoxiao (female) and Yunxi (male) are both cached for the original text and can be selected in the player.'))
    return {'text_sha256':cached['text_sha256'],'available_voice_ids':[x['voice_id'] for x in cached['voices']],
            'provider':cached['provider'],'not_human_recording':True,
            'active_voice_setting':'Export from player to capture the selected narration voice.'}
