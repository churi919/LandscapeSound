"""Small host controls for exact-text natural narration and image-bound guides."""
import hashlib
import json
from pathlib import Path
import streamlit as st


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
    try:
        cached=get_narration_assets(text,root)
    except ValueError as exc:
        st.caption(str(exc));return None
    ready={x['voice_id'] for x in cached['voices']}
    if DEFAULT_VOICE in ready:
        st.caption('朗读已备好自然女声“晓晓”。可在播放器里切换配音；缓存音频可离线播放。')
    else:
        st.info('当前文字尚未生成自然配音。生成后，朗读按钮会使用神经语音。')
    with st.expander('自然配音设置'):
        st.caption('采用神经语音合成，保留系统旧配音作为对照。生成新配音需要联网，会把这段朗读文字发送到 Microsoft 语音服务；已缓存的播放在本机完成。')
        missing=[voice for voice in VOICES if voice not in ready]
        if missing:
            available=(Path(root)/'.venv_narration'/'Scripts'/'python.exe').is_file()
            label='生成自然配音' if not ready else '补充另一种自然配音'
            if st.button(label,key='natural_narration_'+str(key)+'_'+cached['text_sha256'][:12],disabled=not available):
                try:
                    with st.spinner('正在生成自然配音，并保存到本机…'):
                        cached=ensure_narration(text,voices=missing,root=root)
                    st.success('自然配音已就绪，下方播放器已更新。')
                except Exception as exc:
                    st.error('本次自然配音未生成完成，未自动换回系统配音。')
                    st.caption(f'{type(exc).__name__}: {exc}')
                    cached=get_narration_assets(text,root)
            if not available:
                st.caption('自然配音生成环境尚未安装。')
        else:
            st.write('女声“晓晓”和男声“云希”均已缓存，可在播放器中选择。')
    return {'text_sha256':cached['text_sha256'],'available_voice_ids':[x['voice_id'] for x in cached['voices']],
            'provider':cached['provider'],'not_human_recording':True,
            'active_voice_setting':'Export from player to capture the selected narration voice.'}
