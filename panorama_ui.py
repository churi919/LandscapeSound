"""Four-direction perspective review for genuine equirectangular panoramas."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
import streamlit as st
import streamlit.components.v1 as components
from ui_i18n import init_language, render_language_switcher, get_language, t
from ui_labels import tr_ui, category_label, direction_label, ui_formatter, keep_ui_widget, localized_uploader


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _show_image(path, caption: str):
    if path and Path(path).is_file():
        st.image(str(path), caption=tr_ui(caption), width="stretch")
    else:
        st.info(tr_ui(f"{caption}尚未生成。"))


def _three_images(report: dict):
    files = report.get("files", {})
    for column, key, label in zip(st.columns(3), ["input", "segmentation", "depth"],
                                   ["当前透视画面", "语义分割叠加", "当前视角的相对深度"]):
        with column:
            st.markdown(tr_ui(f"**{label}**"))
            _show_image(files.get(key), label)


def _author_text(value) -> str:
    if isinstance(value, dict):
        return t("、", ", ").join(str(name) for name in value)
    if isinstance(value, list):
        return t("、", ", ").join(str(name) for name in value)
    return str(value or tr_ui("见来源页面"))


def _narration_only_page(rendered: str, description: str) -> str:
    """Keep the existing narration transport while hiding irrelevant sound UI."""
    styling='''<style id="narration-only-style">
main > h2, main > p:not(#voice-status), main > .toolbar:first-of-type,
main > .mix, main > details, #play, #calibrate, #export,
#narration-voice, label[for="narration-voice"], label[for="narration-volume"]
{display:none!important}
</style>'''
    intro=('<section id="narration-only-intro" aria-label="'+t('仅导览','Narration only')+'">'
           '<h2>'+t('全景导览','Panorama guide')+'</h2><p>'+
           t('此方向没有配置声源，声景保持无声。可以朗读本图的全景导览。',
             'No sound source is configured for this direction. The soundscape stays silent; you can play the English panorama guide when its narration is ready.')+'</p>'
           '<p>'+html.escape(description)+'</p></section>')
    rendered=rendered.replace('<style>',styling+'<style>',1)
    rendered=re.sub(r'(<main\b[^>]*>)',lambda match:match.group(1)+intro,rendered,count=1)
    rendered=re.sub(r'(<button\b[^>]*\bid="stop"[^>]*>).*?(</button>)',
        lambda match:match.group(1)+t('停止朗读','Stop narration')+match.group(2),rendered,count=1,flags=re.S)
    rendered=re.sub(r'(<div\b[^>]*\bid="status"[^>]*>).*?(</div>)',
        lambda match:match.group(1)+t('此方向无声景，可点击朗读全景导览。','No soundscape in this direction. Play the English panorama guide if its narration is ready.')+match.group(2),rendered,count=1,flags=re.S)
    return rendered


def _audio_plan(report: dict, root: Path | None = None, asset_id: str | None = None,
                pipeline_result: dict | None = None):
    if pipeline_result is not None:
        if (pipeline_result.get("status") != "complete"
                or pipeline_result.get("image_sha256_rgb") != report.get("input", {}).get("sha256_rgb")
                or not isinstance(pipeline_result.get("plan"), dict)):
            raise ValueError("自动生成结果与当前全景不匹配。")
        return pipeline_result["plan"]
    root = Path(root or Path(__file__).resolve().parent)
    scene_id = asset_id or report.get("id") or report.get("source_id")
    if isinstance(scene_id, str) and scene_id and Path(scene_id).name == scene_id:
        from optimize_scene_audio import load_optimized_plan
        optimized = load_optimized_plan(report, scene_id, root=root)
        if optimized is not None:
            return optimized
        from gpt_scene_audio import load_gpt_panorama_audio_plan
        cached = load_gpt_panorama_audio_plan(report,
            root / "outputs" / "gpt_audio_demo" / scene_id / "gpt_detailed" / "plan.json")
        if cached is not None:
            return cached
    from scene_audio_plan import build_panorama_audio_plan, load_demo_observations
    return build_panorama_audio_plan(report, load_demo_observations(report))


def _generate_scene_sound(report: dict, root: Path, asset_id: str | None = None):
    from scene_audio_runtime import ensure_scene_audio
    plan = _audio_plan(report, root, asset_id)
    with st.spinner(tr_ui("正在依据这张全景的内容，在本机生成专属声音；每类声音约需十几至几十秒…")):
        return ensure_scene_audio(plan, root=root)


def _run_panorama(image: Image.Image, root: Path, asset_id: str, title: str):
    try:
        with st.spinner(tr_ui("正在本机把全景转换为四个透视视角，再逐个分析…")):
            from analyze_panorama import analyze_panorama

            output = root / "outputs" / "panorama_interactive" / f"{asset_id}_{uuid4().hex[:8]}"
            report = analyze_panorama(image, output, title=title)
        stored = dict(st.session_state.get("panorama_reanalyzed", {}))
        stored[asset_id] = report
        st.session_state.panorama_reanalyzed = stored
        st.success(tr_ui("全景分析完成。可以切换朝向，逐个查看和试听。"))
        try:
            audio = _generate_scene_sound(report, root, asset_id)
            if audio.get("assets_dir"):
                st.success(tr_ui("这张全景的专属声音已生成并保存。"))
        except Exception as exc:
            st.warning(tr_ui("图像分析已保存，专属声音暂未生成。可在下方再次尝试。"))
            with st.expander(tr_ui("查看声音生成信息")):
                st.code(f"{type(exc).__name__}: {exc}", language=None)
        return report
    except Exception as exc:
        if "out of memory" in str(exc).lower():
            st.error(tr_ui("当前显存不足，请关闭占用显卡的其他程序后再试。"))
        else:
            st.error(tr_ui("本次全景分析未完成。已有的全景示例仍可直接打开。"))
        with st.expander(tr_ui("查看本次错误")):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
        return None


def render_panorama_ui(root: Path, duration: float = 12):
    root = Path(root)
    from ui_theme import section
    section(t("01 / 带来一幅风景", "01 / BRING A LANDSCAPE"), tr_ui("从一幅全景开始"), tr_ui("上传新风景，或找回已经完成的体验。"))
    with st.expander(tr_ui("怎样准备全景图？")):
        st.write(tr_ui("请选择完整的360° × 180°等距柱状全景，常见比例为2:1。普通宽幅照片不能只凭比例当成完整全景。"))
        st.caption(tr_ui("目前体验水平四个90°视角，不包含天顶和脚下。前后左右以图片中间方向为基准，不代表地理方位。"))

    samples = []
    for directory, output_kind in [("panoramas", "panorama"), ("panoramas_gpt", "gpt_panorama")]:
        manifest = _read_json(root / "samples" / directory / "manifest.json")
        if isinstance(manifest, list):
            for item in manifest:
                if isinstance(item, dict) and item.get("id"):
                    record = dict(item)
                    record["_output_kind"] = output_kind
                    samples.append(record)
    source_kind = keep_ui_widget(st.radio, tr_ui("全景来源"), ["网上全景示例", "上传我的全景图"],
        index=None if "panorama_source_kind" in st.session_state else 1,
        horizontal=True, key="panorama_source_kind", format_func=ui_formatter())
    image = None
    report = None
    pipeline_result = None
    asset_id = None
    title = "我的全景图"

    if source_kind == "网上全景示例":
        if not samples:
            from public_demo_ui import render_public_demo
            render_public_demo(root)
            return
        sample_by_id = {str(item["id"]): item for item in samples}
        asset_id = keep_ui_widget(st.selectbox, tr_ui("选择网上全景"), list(sample_by_id),
                                format_func=lambda value: sample_by_id[value].get("title", value),
                                key="panorama_sample_id")
        sample = sample_by_id[asset_id]
        title = str(sample.get("title", asset_id))
        source_file = sample.get("file", sample.get("path"))
        if not source_file or not Path(source_file).is_file():
            st.info(tr_ui("这张全景图片尚未下载完成，请先选择另一个示例。"))
            return
        st.caption(tr_ui(f"公开拍摄素材 · 作者：{_author_text(sample.get('author'))} · {sample.get('license', '许可见来源页面')} · Powered by Poly Haven"))
        links = st.columns([1, 1, 3])
        source_url = sample.get("source_url")
        if isinstance(source_url, str) and source_url.startswith("https://"):
            links[0].link_button(tr_ui("查看原始来源"), source_url)
        license_url = sample.get("license_url")
        if isinstance(license_url, str) and license_url.startswith("https://"):
            links[1].link_button(tr_ui("查看素材许可"), license_url)
        with Image.open(source_file) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
        st.image(image, caption=tr_ui(f"完整 360° × 180° 等距柱状全景 · {image.width} × {image.height}"), width="stretch")
        report = st.session_state.get("panorama_reanalyzed", {}).get(asset_id)
        if report is None:
            report = _read_json(root / "outputs" / sample["_output_kind"] / asset_id / "report.json")
        if st.button(tr_ui("重新分析并生成专属声音" if report else "分析并生成专属声音"), type="primary", key="analyze_panorama_sample"):
            updated = _run_panorama(image, root, asset_id, title)
            report = updated or report
    else:
        uploaded = localized_uploader(tr_ui("上传完整的 2:1 等距柱状全景图"), type=["jpg", "jpeg", "png", "webp"], key="panorama_upload")
        from ui_theme import focus_upload_when_requested
        focus_upload_when_requested()
        st.caption(tr_ui("需要横向覆盖 360°、纵向覆盖 180° 的完整全景；普通宽幅照片不能仅凭 2:1 比例当作球面全景。"))
        if uploaded is None:
            from auto_pipeline_ui import render_recent_auto_upload
            pipeline_result = render_recent_auto_upload(root)
            if pipeline_result is not None:
                asset_id = "upload_" + pipeline_result["job_id"][:12]
                title = pipeline_result.get("title", "我的全景图")
        else:
            try:
                with Image.open(uploaded) as raw:
                    if raw.width * raw.height > 50_000_000:
                        st.error(tr_ui("图片过大，请将全景缩小至 5000 万像素以内。"))
                        return
                    image = ImageOps.exif_transpose(raw).convert("RGB")
            except (OSError, UnidentifiedImageError) as exc:
                st.error(tr_ui(f"无法读取这张图片：{exc}"))
                return
            if abs(image.width / image.height - 2.0) > 0.04:
                st.error(tr_ui("这张图片的比例接近不了 2:1。请使用完整的等距柱状全景，避免把裁切图误当成 360°。"))
                return
            asset_id = "upload_" + hashlib.sha256(uploaded.getvalue()).hexdigest()[:12]
            title = keep_ui_widget(st.text_input, tr_ui("全景名称"), value=Path(uploaded.name).stem, key=f"panorama_title_{asset_id}")
            with st.expander(tr_ui("查看上传的完整全景")):
                st.image(image, caption=tr_ui("待分析的全景图"), width="stretch")
            st.caption(tr_ui("确认后会自动完成整套体验：图片与四方向画面发送给 GPT 理解，声音在本机生成，中文导览文字发送给 Microsoft 神经语音服务配音。GPT 使用本机已登录的官方入口，无需另填密钥；生成完成后，读取和试听本图缓存可离线进行。"))
            confirmed = keep_ui_widget(st.checkbox, tr_ui("确认这是完整 360° × 180° 全景"), key=f"panorama_confirm_{asset_id}")
            if not confirmed:
                st.info(tr_ui("确认全景格式后，会自动开始 GPT 理解、专属声景和自然配音。"))
                return
            from auto_pipeline_ui import render_auto_upload
            try:
                pipeline_result = render_auto_upload(uploaded.getvalue(), title or "我的全景图", root)
            except (OSError, ValueError, RuntimeError) as exc:
                st.error(tr_ui("本次自动生成尚未启动，已保存的步骤会保留。"))
                with st.expander(tr_ui("查看本次信息")):
                    st.code(f"{type(exc).__name__}: {exc}", language=None)
                return
        if pipeline_result is None:
            return
        report = pipeline_result["report"]

    if not isinstance(report, dict) or not isinstance(report.get("views"), list) or not report["views"]:
        st.info(tr_ui("点击分析后，会显示四个朝向的分割、深度和声音。"))
        return

    from scene_audio_runtime import load_scene_audio
    try:
        plan = _audio_plan(report, root, asset_id, pipeline_result=pipeline_result)
        audio_result = pipeline_result["audio_result"] if pipeline_result is not None else load_scene_audio(plan, root=root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(tr_ui("本图的声音计划未通过图片与来源校验，暂不加载音频。"))
        with st.expander(tr_ui("查看声音计划信息")):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
        return
    gpt_provenance = plan.get("evidence", {}).get("gpt_provenance")
    uses_gpt = isinstance(gpt_provenance, dict) and gpt_provenance.get("provider") in {"web_chatgpt", "codex_cli"}
    categories = {item["category"] for item in plan.get("stems", plan.get("items", []))}
    st.caption(t('原始全景结果、画面依据与中文基础导览保持不变；当前语言的导览文字与自然配音独立缓存，不重做声景。',
                 'Original panorama results, image evidence and the Mandarin base guide are retained. Guide text and neural narration for the selected language are cached separately without regenerating the soundscape.'))
    generic_comparison_available = categories.issubset({"trees", "water"})
    labels = {"trees": "叶片", "water": "水面", "surf": "海浪", "stream": "流水", "traffic": "道路背景", "wind": "风声"}
    section(t("02 / 为这幅风景而作", "02 / MADE FOR THIS LANDSCAPE"), tr_ui("这张全景的专属声音"))
    if uses_gpt:
        if pipeline_result is not None:
            st.info(tr_ui("这张上传全景已通过本机登录的官方 GPT 入口自动理解。GPT 编写本图的画面依据、分方向声源和中文导览，并保留本图提示词；流水与道路声音另补充声学约束。"))
        elif plan.get("condition") == "category_only_control":
            st.info(tr_ui("画面理解来自网页版 GPT；本轮对照后采用更简洁的溪流声音提示，未将它冒称网页 GPT 的原始长提示。"))
        elif plan.get("evidence", {}).get("acoustic_refinement"):
            st.info(tr_ui("画面理解来自网页版 GPT；声音提示已进行本轮声学优化，重点区分流水、浪涌与道路声音。"))
        else:
            st.info(tr_ui("提示词来源：网页版 GPT 已理解这张全景与四方向画面，分别写出本图声音的材质、变化节奏与空间设定。"))
        if gpt_provenance.get("provider") == "web_chatgpt" and gpt_provenance.get("conversation_url"):
            st.link_button(tr_ui("查看 GPT 原始对话"), gpt_provenance["conversation_url"])
    else:
        reviewed = plan.get("evidence", {}).get("reviewed_observations")
        st.info(tr_ui("提示词来源：本地分类与人工看图核对的缓存。" if reviewed else "提示词来源：本地粗分类规则；本图尚无匹配的网页版 GPT 理解记录。"))
        st.write(tr_ui("根据四个方向的树木、水面与画面环境，分别编写提示词并生成独立音频。"))
    if not plan.get("stems", plan.get("items", [])):
        st.info(tr_ui("本图没有识别到可配置的树木或水面声源，暂不添加其他声音。"))
    elif audio_result and audio_result.get("assets_dir"):
        st.caption(tr_ui("本图专属声音已就绪 · 图片与声音计划已匹配 · 非现场录音"))
    else:
        st.info(tr_ui("这张全景还没有可核验的专属声音。"))
        if st.button(tr_ui("生成这张全景的专属声音"), type="primary", key=f"scene_audio_generate_{plan['cache_key']}"):
            try:
                audio_result = _generate_scene_sound(report, root, asset_id)
                st.success(tr_ui("生成完成。下方已切换为这张全景的专属声音。"))
            except Exception as exc:
                st.error(tr_ui("专属声音暂未生成成功。图片分析结果已保留。"))
                with st.expander(tr_ui("查看声音生成信息")):
                    st.code(f"{type(exc).__name__}: {exc}", language=None)
    with st.expander(tr_ui("查看画面依据、声音设定与提示词")):
        facts = plan.get("evidence", {}).get("visible_facts_zh", [])
        if facts:
            st.write(tr_ui("画面内容：" + "；".join(facts)))
        st.caption(tr_ui("同一全景四方向共享本图分类素材，再分别安排位置与虚拟远近。图像内容先转成文字提示词，再由 Stable Audio 3 生成；动态声音是模拟，无法从照片确认现场风速、水动、车流或实际声压。"))
        if uses_gpt:
            for uncertainty in plan.get("evidence", {}).get("uncertainties_zh", []):
                st.caption(tr_ui("不能由照片确定：" + uncertainty))
        for item in plan.get("stems", plan.get("items", [])):
            shown_label = category_label(item['category']) if get_language() == 'en' else item.get('label_zh', labels.get(item['category'], item['category']))
            st.markdown(f"**{shown_label}**")
            st.write(tr_ui(item.get("visual_facts", [])))
            st.caption(tr_ui("声音设定：" + "；".join(item.get("sound_assumptions", []))))
            st.code(item["prompt"], language=None)
        st.caption(tr_ui("画面可见内容与声音模拟假设分别记录。提示词限制不保证生成结果完全没有其他声音，也不能把虚拟距离当作米制测距。"))
    if generic_comparison_available:
        audio_mode = keep_ui_widget(st.radio, tr_ui("声音来源"), ["本图专属生成", "通用素材对照"], horizontal=True, key=f"panorama_audio_mode_{asset_id}", format_func=ui_formatter())
    else:
        audio_mode = "本图专属生成"

    st.divider()
    section(t("03 / 按自己的节奏聆听", "03 / LISTEN AT YOUR PACE"), tr_ui("转向一个方向，慢慢听"), tr_ui("先听声音，再按需打开自然导览；随时可以停止。"))
    views = [view for view in report["views"] if isinstance(view, dict) and isinstance(view.get("report"), dict)]
    if not views:
        st.info(tr_ui("这份全景结果未包含有效视角，请重新分析。"))
        return
    by_id = {str(view["id"]): view for view in views}
    view_id = keep_ui_widget(st.radio, tr_ui("选择朝向"), list(by_id),
                       format_func=lambda value, language=get_language(): f"{direction_label(value, by_id[value].get('label', value), language)} ({by_id[value].get('yaw', 0):g}°)" if language == 'en' else f"{by_id[value].get('label', value)}（{by_id[value].get('yaw', 0):g}°）",
                       horizontal=True, key=f"panorama_view_{asset_id}")
    selected_view = by_id[view_id]
    selected_report = selected_view["report"]
    scene = selected_report.get("scene", {})
    metrics = selected_report.get("metrics", {})
    playback_sources = plan.get("views", {}).get(view_id, {}).get("sources", scene.get("sources", []))
    st.markdown(tr_ui(f"**当前朝向：{selected_view.get('label', view_id)} · {selected_view.get('yaw', 0):g}°**"))
    st.caption(tr_ui(f"当前方向有 {len(playback_sources)} 个模拟声源。切换方向，相当于转身后重新面向画面。"))
    playback_assets = (audio_result or {}).get("assets_dir") if audio_mode == "本图专属生成" else root / "assets"
    from narration_ui import scene_narration_guide, prepare_localized_narration, render_narration_controls
    guide = pipeline_result["narration_guide"] if pipeline_result is not None else scene_narration_guide(report, asset_id, root)
    description = pipeline_result["narration_text"] if pipeline_result is not None else (guide['text'] if guide else ("；".join(plan.get("evidence", {}).get("visible_facts_zh", [])) if uses_gpt else scene.get("description", "")))
    playback_text, localized_narration = prepare_localized_narration(description, root, asset_id)
    shown_guide = localized_narration.get('localized_text', '')
    picture_column, listening_column = st.columns([1, 1.18], gap="large")
    with picture_column:
        _show_image(selected_report.get("files", {}).get("input"), "当前透视画面")
        if not uses_gpt:
            st.write(tr_ui(scene.get("description", "此视角暂无景观描述。")))
        if guide:
            with st.expander(tr_ui("查看本次朗读导览")):
                if shown_guide:
                    st.write(shown_guide)
                if shown_guide != description:
                    st.caption(t('原始导览文字', 'Original guide text'))
                    st.write(description)
        with st.expander(tr_ui("查看分析图层与运行信息")):
            _show_image(selected_report.get("files", {}).get("segmentation"), "语义分割叠加")
            _show_image(selected_report.get("files", {}).get("depth"), "当前视角的相对深度")
            st.caption(tr_ui("深度图黄色较近、蓝色较远。各视角单独估计，不能跨视角比较数值，也不代表米制距离。声音位置为视觉代理，未标定成真实全景声场。"))
            technical = st.columns(2)
            technical[0].metric(tr_ui("当前视角推理"), tr_ui(f"{metrics.get('inference_seconds', 0):.2f} 秒"))
            technical[1].metric(tr_ui("显存分配峰值"), tr_ui(f"{metrics.get('peak_gpu_memory_mb', 0):.0f} MB"))
    with listening_column:
        if audio_mode == "通用素材对照":
            st.info(tr_ui("当前明确选择通用素材对照；这些声音不是根据本图独立生成的。"))
        narration_metadata = render_narration_controls(playback_text, root, asset_id+'_'+view_id) if playback_text else None
        try:
            from browser_audio import render_audio
            if not playback_sources:
                st.info(tr_ui("此方向未配置有画面依据的声源，声景保持无声；仍可朗读全景导览。"))
            if playback_assets:
                rendered = render_audio(playback_sources, playback_text, playback_assets, duration)
                if not playback_sources:
                    rendered = _narration_only_page(rendered, playback_text)
                components.html(rendered, height=760 if playback_sources else 440, scrolling=True)
            else:
                st.info(tr_ui("专属声音就绪后可在此试听；也可主动选择通用素材对照。" if generic_comparison_available else "本图专属声音生成并校验完成后，可在此试听。"))
        except (ImportError, FileNotFoundError, ValueError) as exc:
            st.error(tr_ui("当前视角的声音未能加载。"))
            st.caption(tr_ui(str(exc)))

    baseline = report.get("baseline")
    if isinstance(baseline, dict):
        with st.expander(tr_ui("对比：直接平铺输入的原版结果")):
            st.write(tr_ui("原版把整张 360° 全景当成一张普通照片，并假定整个宽度只有 70° 视野。这会压缩真实方位；等距柱状投影也会拉伸天空、地面和接缝附近的物体。"))
            st.caption(tr_ui("这里保留原版结果用于检查差异。透视拆分修正的是输入投影和方向解释，不能据此声称分割或深度准确率已经提高。"))
            _three_images(baseline)
            base_metrics = baseline.get("metrics", {})
            st.caption(tr_ui(f"原版推理：{base_metrics.get('inference_seconds', 0):.3f} 秒；原版声源：{len(baseline.get('scene', {}).get('sources', []))} 个。"))

    export_report = dict(report)
    if pipeline_result is not None:
        export_report["automatic_pipeline"] = {key:pipeline_result.get(key) for key in
            ("job_id", "status", "pipeline_version", "input_sha256", "image_sha256_rgb", "completed_utc",
             "report_path", "plan_path", "result_file", "requested_voice_ids", "reused_steps")}
    export_report["scene_audio_plan"] = plan
    export_report["narration"] = {"text":description,"guide_provenance":guide.get("provenance") if guide else None,
                                  "playback_text":playback_text,"localization":localized_narration,"cache":narration_metadata}
    export_report["gpt_audio_provenance"] = gpt_provenance if uses_gpt else None
    export_report["scene_audio_materials"] = {
        "selection": audio_mode,
        "cache_key": plan["cache_key"],
        "assets_dir": str(playback_assets) if playback_assets else None,
        "manifest_path": str((audio_result or {}).get("manifest_path")) if audio_mode == "本图专属生成" and audio_result else None,
        "ready": bool(playback_assets), "selected_view": view_id,
        "view_has_sources": bool(playback_sources), "view_playable": bool(playback_assets and playback_sources),
        "view_sources": playback_sources, "pictured_site_recording": False,
        "prompt_condition": plan.get("condition", "local_content_rules"), "gpt_provenance": gpt_provenance if uses_gpt else None}
    export_report["audio_renderer"] = {"version": 2, "material_presets": ["verified_ai_generated", "recording_textures", "legacy_procedural"] if generic_comparison_available else ["verified_ai_generated"],
        "pictured_site_recording": False, "legacy_procedural_preset_available": generic_comparison_available,
        "active_playback_settings": "Export from the player to capture actual preset, levels and offsets."}
    st.download_button(tr_ui("下载全景四方向结果（JSON）"), json.dumps(export_report, ensure_ascii=False, indent=2),
                       file_name=f"{asset_id}_panorama_result.json", mime="application/json", key=f"panorama_download_{asset_id}")

