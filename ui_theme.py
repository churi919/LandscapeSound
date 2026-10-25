"""Calm, accessible product styling; presentation never changes pipeline state."""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


PALETTE = {
    "ink": "#132C3B", "muted": "#506473", "paper": "#F3F6F7",
    "navy": "#102B3B", "teal": "#126C69", "mint": "#B9F0DF",
    "warm": "#7B541B", "warm_surface": "#FFF4DE",
}

STYLE = """<style>
:root{--ls-ink:#132c3b;--ls-muted:#506473;--ls-paper:#f3f6f7;--ls-teal:#126c69;--ls-line:#d6e0e4;--ls-ease:cubic-bezier(.23,1,.32,1)}
.stApp{background:var(--ls-paper);color:var(--ls-ink);font-family:Inter,system-ui,"Microsoft YaHei",sans-serif}
[data-testid="stMainBlockContainer"]{max-width:1272px;padding:5rem 2rem 4rem}
[data-testid="stHeader"]{background:rgba(243,246,247,.92)}
[data-testid="stSidebar"]{background:#e9eff1;border-right:1px solid #d6e0e4}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:2rem}
[data-testid="stSidebar"] h3{font-size:1rem!important;letter-spacing:0}
h1,h2,h3{color:var(--ls-ink);font-optical-sizing:auto;letter-spacing:-.025em}
h2{font-size:1.65rem!important;line-height:1.35!important}h3{font-size:1.22rem!important;line-height:1.45!important}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{font-size:1rem;line-height:1.8}
[data-testid="stCaptionContainer"] p{color:var(--ls-muted);font-size:.87rem;line-height:1.75}
label,[data-testid="stWidgetLabel"] p{color:var(--ls-ink);font-weight:600}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stLinkButton"] a,
[data-testid="stFormSubmitButton"] button{min-height:48px;border-radius:12px;border-color:#bdcdd4;font-weight:600;padding:.65rem 1.1rem;transition:transform 140ms var(--ls-ease),background-color 140ms ease}
[data-testid="stButton"] button[kind="primary"],[data-testid="stFormSubmitButton"] button[kind="primary"]{background:#126c69;color:white;border-color:#126c69;box-shadow:0 4px 12px #126c6918}
button:active{transform:scale(.98)}
button:focus-visible:active{transform:none}
button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,a:focus-visible,[role="radio"]:focus-visible{outline:3px solid #157eac!important;outline-offset:4px!important}
[data-testid="stRadio"] [role="radiogroup"]{gap:.65rem;flex-wrap:wrap}
[data-testid="stRadio"] label[data-baseweb="radio"]{min-height:48px;padding:.6rem 1rem!important;border:1px solid #cbd8de;border-radius:12px;background:#fff;margin:0!important}
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:#e5f3ee;border-color:#126c69;box-shadow:inset 0 0 0 1px #126c69}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-baseweb="select"]>div{border-radius:11px;font-size:1rem;min-height:48px}
[data-testid="stFileUploaderDropzone"]{background:#fff;border:1px dashed #8baeb3;border-radius:18px;padding:1.7rem 1.3rem;min-height:150px}
[data-testid="stFileUploaderDropzone"] small{color:#506473}
[data-testid="stMetric"]{border:1px solid #d9e3e7;border-radius:16px;background:#fff;padding:1rem 1.2rem}
[data-testid="stMetricValue"]{color:#123c50;font-variant-numeric:tabular-nums}
[data-testid="stImage"] img{border-radius:15px}
[data-testid="stExpander"]{border:1px solid #d6e0e4;border-radius:14px;background:#fff}
[data-testid="stExpander"] summary{min-height:48px;padding:.85rem 1rem}
[data-testid="stAlert"]{border-radius:14px;border:1px solid #d5e4e5}
[data-testid="stProgress"] [role="progressbar"]{border-radius:20px}
[data-testid="stProgress"] [role="progressbar"]>div{background:#126c69}
iframe{border-radius:18px;border:1px solid #d4e0df}
.ls-hero{position:relative;overflow:hidden;background:#102b3b;border:1px solid #274653;border-radius:26px 26px 0 0;padding:2.1rem 2.3rem 1.2rem;color:#fff;isolation:isolate}
.ls-hero::after{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at 88% 35%,#2063674d,transparent 55%);pointer-events:none;z-index:-1}
.ls-brand{font-size:.75rem;font-weight:700;letter-spacing:.16em;color:#b9f0df;margin:0 0 1.05rem}
.ls-hero h1{font-size:clamp(2rem,3.8vw,3.5rem)!important;line-height:1.25!important;letter-spacing:-.04em;color:#fff!important;margin:0!important;padding:0!important;max-width:760px}
.ls-hero h1 span{color:#b9f0df}.ls-hero p{font-size:1rem!important;line-height:1.8!important;color:#d7e5e9;max-width:680px;margin:1rem 0 .6rem}
.ls-hero-meta{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1.2rem}.ls-hero-meta span{font-size:.77rem;color:#e4eeee;border:1px solid #45626d;border-radius:999px;padding:.3rem .65rem}
.ls-wave{position:absolute;width:230px;right:2.2rem;bottom:2rem;opacity:.35;pointer-events:none}
.st-key-hero_actions{background:#102b3b;border:1px solid #274653;border-top:0;border-radius:0 0 26px 26px;padding:0 2.3rem 1.7rem;margin-top:-1rem}
.st-key-hero_actions [data-testid="stButton"] button[kind="primary"]{background:#b9f0df;color:#123a3d;border-color:#b9f0df;box-shadow:none}
.st-key-hero_actions [data-testid="stButton"] button:not([kind="primary"]),.st-key-hero_actions [data-testid="stLinkButton"] a{background:#1e3d4c;border-color:#56717b;color:#f3faf9}
.ls-path{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:.45rem 0 1rem}
.ls-path article{display:flex;gap:.85rem;align-items:flex-start;padding:1.05rem 1.1rem;border:1px solid #d9e3e7;border-radius:16px;background:#fff}
.ls-path b{color:#126c69;font-size:.8rem;background:#e9f5f1;border-radius:9px;padding:.4rem .5rem;letter-spacing:.04em}
.ls-path strong{font-size:.95rem;display:block;margin-bottom:.25rem;color:#132c3b}.ls-path small{color:#506473;font-size:.83rem;line-height:1.6;display:block}
.ls-care{background:#fff4de;border:1px solid #ead8b3;border-radius:15px;padding:1rem 1.1rem;color:#644617;font-size:.9rem;line-height:1.8}
.ls-care strong{display:block;margin-bottom:.25rem;color:#5a3d12}.ls-section{margin:1.3rem 0 .5rem}.ls-section small{font-size:.72rem;letter-spacing:.15em;color:#126c69;font-weight:700}.ls-section h2{margin:.3rem 0!important;padding:0!important}.ls-section p{color:#506473;margin:.3rem 0 1rem!important}
.ls-pipeline{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;margin:.8rem 0 1rem;list-style:none;padding:0}
.ls-pipeline li{padding:.9rem .8rem;border:1px solid #d8e2e6;background:#fff;border-radius:12px;color:#506473;font-size:.82rem;line-height:1.6}
.ls-pipeline li strong{display:block;color:#193d4d;font-size:.86rem}.ls-pipeline li[data-state="complete"],.ls-pipeline li[data-state="cached"]{background:#edf7f3;border-color:#a8cfc2}
.ls-pipeline li[data-state="running"]{background:#eaf5f7;border-color:#15758a;box-shadow:inset 0 0 0 1px #15758a}
.ls-pipeline li[data-state="failed"]{background:#fff4de;border-color:#c3a16b}
@media(hover:hover) and (pointer:fine){[data-testid="stButton"] button:hover,[data-testid="stLinkButton"] a:hover{border-color:#126c69}}
@media(max-width:760px){[data-testid="stMainBlockContainer"]{padding:4.5rem 1rem 3rem}.ls-hero{padding:1.5rem 1.25rem 1.1rem}.ls-wave{display:none}.st-key-hero_actions{padding:0 1.25rem 1.3rem}.ls-path{grid-template-columns:1fr;gap:.6rem}.ls-path article{padding:.8rem 1rem}.ls-pipeline{grid-template-columns:1fr 1fr}.ls-pipeline li:last-child{grid-column:1/-1}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}button:active{transform:none!important}}
@media(prefers-reduced-transparency:reduce){[data-testid="stHeader"]{background:#f3f6f7;backdrop-filter:none}}
@media(prefers-contrast:more){:root{--ls-muted:#2f4655;--ls-line:#6e8793}[data-testid="stExpander"],[data-testid="stMetric"],.ls-path article{border-color:#6e8793}}
</style>"""


def apply_theme():
    st.markdown(STYLE, unsafe_allow_html=True)


def _choose_panorama(upload=True):
    st.session_state["experience_mode"] = "360° 全景测试"
    st.session_state["panorama_source_kind"] = "上传我的全景图" if upload else "网上全景示例"
    if upload:
        st.session_state["ls_focus_panorama_upload"] = True
    else:
        st.session_state.pop("ls_focus_panorama_upload", None)


UPLOAD_FOCUS_SCRIPT = """<!doctype html><html><meta charset="utf-8"><script>
// User-initiated navigation only. No content, files, values or network access.
(() => {
  try {
    const doc = window.parent.document;
    let done = false, observer = null, timeout = null;
    const locate = () => {
      if (done) return;
      const target = doc.querySelector('[data-testid="stFileUploader"]');
      if (!target) return;
      done = true;
      if (observer) observer.disconnect();
      if (timeout) clearTimeout(timeout);
      // Instant for mouse and keyboard alike; no motion preference is ignored.
      target.scrollIntoView({block:'center', behavior:'instant'});
      const browse = target.querySelector('button');
      if (browse) browse.focus({preventScroll:true});
    };
    locate();
    if (!done) {
      observer = new MutationObserver(locate);
      observer.observe(doc.body, {childList:true, subtree:true});
      timeout = setTimeout(() => observer.disconnect(), 2000);
    }
  } catch (_) { /* Navigation assistance never blocks the uploader. */ }
})();
</script></html>"""


def focus_upload_when_requested():
    """Consume one explicit CTA navigation intent after the uploader exists."""
    if not st.session_state.pop("ls_focus_panorama_upload", False):
        return False
    components.html(UPLOAD_FOCUS_SCRIPT, height=0, scrolling=False)
    return True


def render_intro(root: Path):
    bars = "".join(f'<rect x="{i * 7}" y="{(90-h)/2}" width="3" height="{h}" rx="1.5"/>'
                   for i, h in enumerate([8,14,22,12,36,52,30,65,43,80,52,37,62,90,58,76,43,28,56,34,68,45,27,54,32,18,30,15,10]))
    st.markdown('<section class="ls-hero" aria-label="LandscapeSound 景观听见">'
        '<div class="ls-brand">LANDSCAPESOUND · 景观听见</div>'
        '<h1>让风景，<span>慢慢被听见。</span></h1>'
        '<p>上传一张全景，用属于这幅画面的声音和自然讲述，感受眼前的方向、层次与细节。</p>'
        '<div class="ls-hero-meta"><span>GPT 画面理解</span><span>本图专属声景</span><span>自然中文导览</span></div>'
        f'<svg class="ls-wave" viewBox="0 0 203 90" fill="#b9f0df" aria-hidden="true">{bars}</svg></section>',
        unsafe_allow_html=True)
    with st.container(key="hero_actions"):
        left, middle, right = st.columns([1.2, 1.1, 1.2])
        left.button("上传全景，开始体验", type="primary", on_click=_choose_panorama,
                    key="begin_panorama", width="stretch")
        middle.button("先听一个已完成示例", on_click=_choose_panorama, args=(False,),
                      key="preview_panorama", width="stretch")
        if (Path(root)/"docs"/"multiscene_automatic_evaluation.html").is_file():
            right.link_button("溪流 · 海岸 · 街道对比", "http://127.0.0.1:8502/docs/multiscene_automatic_evaluation.html", width="stretch")
        elif (Path(root)/"docs"/"automatic_panorama_demo.html").is_file():
            right.link_button("查看完整体验记录", "http://127.0.0.1:8502/docs/automatic_panorama_demo.html", width="stretch")
    st.markdown('<section class="ls-path" aria-label="三步开始体验">'
        '<article><b>01</b><div><strong>带来一幅风景</strong><small>上传完整全景，或选择已完成示例。</small></div></article>'
        '<article><b>02</b><div><strong>等待本图理解与生成</strong><small>进度随时可见，已完成的步骤会保留。</small></div></article>'
        '<article><b>03</b><div><strong>按自己的节奏听</strong><small>切换方向，朗读导览，也可以随时停止。</small></div></article></section>',
        unsafe_allow_html=True)


def section(kicker, title, description=""):
    st.markdown('<div class="ls-section"><small>'+html.escape(kicker)+'</small><h2>'+html.escape(title)+
                '</h2>'+('<p>'+html.escape(description)+'</p>' if description else '')+'</div>',unsafe_allow_html=True)


def care_note():
    st.markdown('<aside class="ls-care"><strong>先把音量放轻一点。</strong>'
        '建议戴上耳机，从舒适的音量开始。你可以先听一侧，再慢慢转向另一侧；声音与朗读都能随时停止。</aside>',
        unsafe_allow_html=True)
