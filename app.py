"""Accessible local Streamlit interface for LandscapeSound."""
from __future__ import annotations

import local_config
import os
os.environ.setdefault('HF_HUB_OFFLINE', '1')
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
OUTPUTS = ROOT / "outputs"
ASSETS = ROOT / "assets"
try:
    _manifest = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
    SAMPLE_TITLES = {str(item["id"]): str(item["title"]) for item in _manifest}
except (OSError, ValueError, KeyError, TypeError):
    SAMPLE_TITLES = {}

st.set_page_config(page_title="LandscapeSound · 景观听见", page_icon="🌿", layout="wide")
from ui_theme import apply_theme, render_intro, care_note
apply_theme()


def read_report(path: Path) -> dict | None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report.get("scene"), dict):
            return None
        report.setdefault("report_path", str(path.resolve()))
        return report
    except (OSError, ValueError, AttributeError):
        return None


def demo_reports() -> list[tuple[Path, dict]]:
    directory = OUTPUTS / "demo"
    if not directory.exists():
        return []
    result = []
    paths = sorted(directory.rglob("report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        report = read_report(path)
        if report:
            result.append((path, report))
    return result


def cached_gpt_caption(report: dict, cache: dict | None = None) -> dict | None:
    """Use a cached caption only for the exact RGB image analyzed by the models."""
    image_hash = report.get("input", {}).get("sha256_rgb")
    if not isinstance(image_hash, str) or len(image_hash) != 64:
        return None
    if cache is None:
        try:
            cache = json.loads((OUTPUTS / "gpt_captions.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if not isinstance(cache, dict) or not isinstance(cache.get("items"), list):
        return None
    for item in cache["items"]:
        if not isinstance(item, dict) or item.get("analysis_rgb_sha256") != image_hash:
            continue
        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        return {
            "description": description.strip(),
            "analysis_rgb_sha256": image_hash,
            "sample_id": item.get("sample_id"),
            "provider": str(cache.get("provider", "ChatGPT web")),
            "source_url": cache.get("conversation_url"),
            "review_status": item.get("review_status", cache.get("review_status", "unreviewed")),
        }
    return None


def caption_provenance(report: dict, caption: dict | None, mode: str) -> dict:
    use_gpt = mode == "gpt_assisted" and caption is not None
    image_hash = report.get("input", {}).get("sha256_rgb")
    return {
        "mode": "gpt_assisted" if use_gpt else "local_rules",
        "provider": caption["provider"] if use_gpt else "Local semantic/depth rules",
        "source_url": caption.get("source_url") if use_gpt else None,
        "review_status": caption.get("review_status") if use_gpt else "local_rules",
        "analysis_rgb_sha256": image_hash,
        "cache_analysis_rgb_sha256": caption["analysis_rgb_sha256"] if use_gpt else None,
        "sha256_match": caption["analysis_rgb_sha256"] == image_hash if use_gpt else None,
        "edited_by_user": False,
    }


def activate_report(report: dict) -> None:
    st.session_state.active_report = copy.deepcopy(report)
    st.session_state.corrected_sources = copy.deepcopy(report["scene"].get("sources", []))
    caption = cached_gpt_caption(report)
    mode = "gpt_assisted" if caption else "local_rules"
    st.session_state.description_mode = mode
    st.session_state.description_revision = 0
    st.session_state.description_edited_by_user = False
    st.session_state.description_provenance = caption_provenance(report, caption, mode)
    st.session_state.corrected_description = caption["description"] if caption else report["scene"].get("description", "")
    st.session_state.user_corrected = False
    st.session_state.result_key = hashlib.sha256(
        (str(report.get("report_path", "")) + uuid4().hex).encode("utf-8")
    ).hexdigest()[:12]


def run_analysis(image: Image.Image, title: str, hfov: float) -> None:
    try:
        with st.spinner("正在本机识别景观、计算相对深度并构建声景…"):
            from analyzer import analyze_image

            folder = OUTPUTS / "interactive" / uuid4().hex[:12]
            report = analyze_image(image, folder, title=title, hfov=hfov)
        activate_report(report)
        st.success("分析完成。可以查看图层、试听空间声音，或调整声源。")
    except Exception as exc:
        error = str(exc)
        if "out of memory" in error.lower():
            st.error("显存暂时不足。请关闭占用显卡的其他应用后再次分析。")
        elif any(word in error.lower() for word in ("connection", "offline", "cached", "network")):
            st.error("本地模型文件尚未就绪。请先运行项目的模型下载步骤，再重新分析。")
        else:
            st.error("本次分析未完成。已有示例仍可使用；技术信息见下方。")
        with st.expander("查看错误信息"):
            st.code(f"{type(exc).__name__}: {error}", language=None)


def sample_title(path: Path) -> str:
    return SAMPLE_TITLES.get(path.stem, path.stem.replace("_", " ").replace("-", " "))


def show_image_file(path: str | None, caption: str) -> None:
    if path and Path(path).is_file():
        st.image(path, caption=caption, width="stretch")
    else:
        st.info(f"{caption}文件尚未生成。")


reports = demo_reports()
if "active_report" not in st.session_state:
    st.session_state.active_report = None
    if reports:
        preferred_report = next((r for p, r in reports if p.parent.name == "01_park"), reports[0][1])
        activate_report(preferred_report)

with st.sidebar:
    st.markdown("### 让聆听更舒适")
    duration = st.select_slider("每次声景时长（秒）", options=[8, 12, 20, 30, 45], value=20)
    care_note()
    st.divider()
    with st.expander("普通照片的视野设置"):
        hfov = st.slider("假定水平视野（度）", 30.0, 120.0, 70.0, 5.0,
                         help="只用于普通照片；全景固定分析四个90度视角。修改后重新分析生效。")
    st.caption("分析结果与生成的声音保存在这台电脑，已完成的体验可再次打开。")
    st.caption("研究原型用于景观预体验，不能据此判断通行或避障。")

render_intro(ROOT)

experience_mode = st.radio("体验模式", ["普通照片", "360° 全景测试"],
    index=None if "experience_mode" in st.session_state else 1,
    horizontal=True, key="experience_mode")
if experience_mode == "360° 全景测试":
    from panorama_ui import render_panorama_ui
    render_panorama_ui(ROOT, duration=duration)
    st.stop()

st.subheader("01　选择一张景观照片")
input_mode = st.radio("照片来源", ["示例照片", "上传我的照片"], horizontal=True)
sample_paths = sorted(path for path in SAMPLES.glob("*")
                      if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
if input_mode == "示例照片":
    if sample_paths:
        select_column, button_column = st.columns([3, 1], vertical_alignment="bottom")
        with select_column:
            selected_sample = st.selectbox("选择示例照片", sample_paths, format_func=sample_title)
        with button_column:
            analyze_clicked = st.button("分析所选照片", type="primary", width="stretch")
        if analyze_clicked:
            try:
                with Image.open(selected_sample) as raw:
                    selected_image = ImageOps.exif_transpose(raw).convert("RGB")
                run_analysis(selected_image, sample_title(selected_sample), hfov)
            except (OSError, UnidentifiedImageError) as exc:
                st.error(f"无法读取所选图片：{exc}")
    else:
        st.info("示例照片尚未加入。可以先上传一张景观照片。")
else:
    uploaded = st.file_uploader("上传 JPG、PNG 或 WebP 照片", type=["jpg", "jpeg", "png", "webp"])
    if uploaded is not None:
        title = st.text_input("照片名称", value=Path(uploaded.name).stem, max_chars=120)
        if st.button("分析上传照片", type="primary"):
            try:
                with Image.open(uploaded) as raw:
                    image = ImageOps.exif_transpose(raw).convert("RGB")
                    if image.width * image.height > 50_000_000:
                        st.error("图片过大，请将照片缩小至 5000 万像素以内再上传。")
                    else:
                        run_analysis(image, title or "我的景观照片", hfov)
            except (OSError, UnidentifiedImageError) as exc:
                st.error(f"无法读取上传图片：{exc}")

if reports:
    with st.expander("直接打开已跑通的 demo，无需等待推理"):
        report_choice = st.selectbox("已完成的示例", list(range(len(reports))),
                                    format_func=lambda i: reports[i][1].get("title", reports[i][0].parent.name))
        if st.button("打开此 demo"):
            activate_report(reports[report_choice][1])
            st.rerun()

report = st.session_state.active_report
if report is None:
    st.divider()
    st.subheader("先体验空间声音")
    st.caption("这是手动设置的播放器预览，不是模型分析结果。树声在左、水声在右；鸟声默认关闭。")
    preview_sources = [
        {"id": "preview-trees", "category": "trees", "label": "左侧树木（手动预览）",
         "enabled": True, "azimuth": -30.0, "virtual_radius": 2.3, "area_fraction": 0.2},
        {"id": "preview-water", "category": "water", "label": "右侧水体（手动预览）",
         "enabled": True, "azimuth": 30.0, "virtual_radius": 6.0, "area_fraction": 0.15},
        {"id": "preview-bird", "category": "bird", "label": "鸟声（手动预览）",
         "enabled": False, "azimuth": 0.0, "virtual_radius": 4.8, "area_fraction": 0.0},
    ]
    try:
        from browser_audio import render_audio
        components.html(render_audio(preview_sources, "这是手动试听预览，左侧为树声，右侧为水声。", ASSETS, duration),
                        height=760, scrolling=True)
    except (ImportError, FileNotFoundError) as exc:
        st.info("播放器正在准备。照片分析功能就绪后，即可生成可试听的结果。")
        st.caption(str(exc))
    st.stop()

scene = report["scene"]
metrics = report.get("metrics", {})
result_key = st.session_state.result_key
st.divider()
st.subheader("02　检查这张照片的空间层次")
st.markdown(f"**当前结果：{report.get('title', scene.get('title', '景观照片'))}**")
with st.expander("查看本次分析与运行信息"):
    metric_columns = st.columns(4)
    metric_columns[0].metric("模型推理", f"{metrics.get('inference_seconds', 0):.2f} 秒")
    metric_columns[1].metric("显存峰值", f"{metrics.get('peak_gpu_memory_mb', 0):.0f} MB")
    metric_columns[2].metric("自动声源", f"{len(scene.get('sources', []))} 个")
    metric_columns[3].metric("运行设备", "NVIDIA GPU" if metrics.get("device") == "cuda" else "CPU")
    st.caption("推理时间包含分割与深度计算，首次模型加载另计。显存为本进程分配峰值。")

files = report.get("files", {})
image_columns = st.columns(3)
for column, key, label in zip(image_columns, ["input", "segmentation", "depth"],
                               ["原始照片", "语义分割叠加", "相对深度"]):
    with column:
        st.markdown(f"**{label}**")
        show_image_file(files.get(key), label)
st.caption("分割：树木绿色、水体蓝色、天空淡蓝色、建筑橙色；其余颜色代表其他语义类别。深度：黄色较近、青色居中、蓝色较远；灰色天空不参与深度归一化。")

fractions = scene.get("fractions", {})
fraction_labels = {"vegetation": "植被", "water": "水体", "sky": "天空", "built": "建筑与顶盖", "hardscape": "道路与铺装"}
with st.expander("查看画面要素比例"):
    fraction_columns = st.columns(len(fraction_labels))
    for column, (key, label) in zip(fraction_columns, fraction_labels.items()):
        column.metric(label, f"{fractions.get(key, 0):.1%}")
if scene.get("depth_info", {}).get("status") != "relative":
    st.warning("这张照片未得到有效的相对深度层次。声源使用统一默认虚拟距离，可手动校正。")

st.subheader("03　听见景观，校正你的体验")
st.info("播放器已接入 Stable Audio 3 生成素材，可切换 AI、自然录音和原版程序音效；这些均为景观模拟，图像区域用于安排方位与相对远近。")
caption = cached_gpt_caption(report)
# Existing browser sessions may predate caption support; keep their manual edits.
if "description_mode" not in st.session_state:
    already_edited = st.session_state.corrected_description != scene.get("description", "")
    st.session_state.description_mode = "local_rules" if already_edited or not caption else "gpt_assisted"
    st.session_state.description_revision = 0
    st.session_state.description_edited_by_user = already_edited
    st.session_state.description_provenance = caption_provenance(report, caption, st.session_state.description_mode)
    if caption and not already_edited:
        st.session_state.corrected_description = caption["description"]
if caption:
    description_widget_key = f"description_mode_{result_key}"
    if description_widget_key not in st.session_state:
        st.session_state[description_widget_key] = st.session_state.description_mode
    mode = st.radio("景观描述来源", ["local_rules", "gpt_assisted"],
                    index=None,
                    format_func=lambda value: "GPT 辅助描述" if value == "gpt_assisted" else "本地规则描述",
                    key=description_widget_key, horizontal=True)
else:
    mode = "local_rules"
if mode != st.session_state.description_mode:
    st.session_state.description_mode = mode
    st.session_state.description_revision += 1
    st.session_state.description_edited_by_user = False
    st.session_state.corrected_description = caption["description"] if mode == "gpt_assisted" else scene.get("description", "")
    st.session_state.description_provenance = caption_provenance(report, caption, mode)
if mode == "gpt_assisted":
    st.caption(f"来源：{caption['provider']} · 与当前照片匹配 · {caption['review_status']}。文本已缓存，日常使用可离线朗读。")
    source_url = caption.get("source_url")
    if isinstance(source_url, str) and source_url.startswith(("https://chatgpt.com/", "https://chat.openai.com/")):
        st.link_button("查看 GPT 原始对话", source_url)
if st.session_state.description_edited_by_user:
    st.caption("当前描述包含你的人工修改，导出时会保留来源和修改标记。")
st.write(st.session_state.corrected_description)
st.caption("播放器内的实时滑块只用于当次试听；需要保留并导出的修改，请在下方校正表单中应用。")

with st.expander("校正声源与景观描述", expanded=False):
    st.caption("方位负数在左、正数在右。虚拟距离只控制音频效果，不是现实中的米数。每次修改后点击应用。")
    with st.form(f"correction_form_{result_key}"):
        revised_sources = []
        for index, source in enumerate(st.session_state.corrected_sources):
            revised = copy.deepcopy(source)
            source_key = f"{result_key}_{index}_{source.get('id', index)}"
            st.markdown(f"**{source.get('label', source.get('category', '声源'))}**")
            columns = st.columns([1, 2, 2])
            revised["enabled"] = columns[0].checkbox("启用此声源", value=bool(source.get("enabled", True)), key=f"enabled_{source_key}")
            revised["azimuth"] = columns[1].slider("左右方位（度）", -90.0, 90.0,
                max(-90.0, min(90.0, float(source.get("azimuth", 0)))), 1.0, key=f"azimuth_{source_key}")
            revised["virtual_radius"] = columns[2].slider("虚拟音频距离", 1.8, 7.8,
                max(1.8, min(7.8, float(source.get("virtual_radius", 4.8)))), .1, key=f"radius_{source_key}")
            near = source.get("near_score")
            st.caption(f"区域占图像 {source.get('area_fraction', 0):.1%} · 模型近度 " +
                       (f"{near:.2f}" if near is not None else "不可用"))
            revised_sources.append(revised)
        revised_description = st.text_area("景观描述（可编辑并朗读）", value=st.session_state.corrected_description,
                                          height=180, key=f"description_{result_key}_{st.session_state.description_revision}")
        submitted = st.form_submit_button("应用校正并更新试听", type="primary")
        if submitted:
            st.session_state.corrected_sources = revised_sources
            st.session_state.description_edited_by_user = (
                st.session_state.description_edited_by_user
                or revised_description != st.session_state.corrected_description
            )
            st.session_state.corrected_description = revised_description
            st.session_state.user_corrected = True
            st.rerun()

from narration_ui import render_narration_controls
narration_metadata = render_narration_controls(st.session_state.corrected_description, ROOT, result_key)

try:
    from browser_audio import render_audio
    components.html(render_audio(st.session_state.corrected_sources,
                                 st.session_state.corrected_description, ASSETS, duration),
                    height=760, scrolling=True)
except Exception as exc:
    st.error("播放器尚未完成加载。请检查 assets 目录中的本地音频文件。")
    st.caption(f"{type(exc).__name__}: {exc}")

export_report = copy.deepcopy(report)
export_report["scene"]["sources"] = copy.deepcopy(st.session_state.corrected_sources)
export_report["scene"]["description"] = st.session_state.corrected_description
export_report["narration"] = narration_metadata
export_report["audio_renderer"] = {"version": 2, "material_presets": ["verified_ai_generated", "recording_textures", "legacy_procedural"],
    "legacy_procedural_preset_available": True, "pictured_site_recording": False,
    "material_manifest": str(ASSETS / "natural" / "manifest.json"),
    "ai_generation_manifest": str(ASSETS / "generated" / "manifest.json"),
    "active_playback_settings": "Export from the player to capture the selected preset, levels and offsets."}
export_report["description_provenance"] = copy.deepcopy(st.session_state.description_provenance)
export_report["description_provenance"]["edited_by_user"] = st.session_state.description_edited_by_user
export_report["user_correction"] = {"applied": st.session_state.user_corrected,
                                    "exported_at": datetime.now(timezone.utc).isoformat(),
                                    "original_report_path": report.get("report_path")}
st.session_state.download_json = json.dumps(export_report, ensure_ascii=False, indent=2)
st.download_button("下载结果与校正记录（JSON）", st.session_state.download_json,
                   file_name="landscapesound_result.json", mime="application/json")

with st.expander("查看技术与证据边界"):
    st.write("SegFormer 识别画面中的语义区域；Depth Anything V2 Small 输出单图相对逆深度。排除天空后按 P5 / P95 归一化，再用区域中位数安排声源。最多四个自动声源。")
    st.write("中文描述可使用本地规则；存在精确匹配照片的 GPT 网页缓存时，可切换为明确标注来源的辅助描述。可见自然要素与开敞特征用于景观描述，不能当作主观 PSD 评分、真实宁静程度或视障用户体验的验证。")
    st.caption(f"本次结果保存于：{report.get('report_path', '尚未保存')}")
    st.json({"metrics": metrics, "depth_info": scene.get("depth_info", {}), "audio_info": scene.get("audio_info", {})})
