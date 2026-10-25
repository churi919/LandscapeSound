"""Presentation strings for the photo, panorama and durable-upload interfaces.

Stored scene data, widget values and task identities are never translated.
"""
import re
import inspect
from ui_i18n import get_language, t

TEXT = {
'左侧树木（手动预览）':'Trees on the left (manual preview)','右侧水体（手动预览）':'Water on the right (manual preview)','鸟声（手动预览）':'Bird (manual preview)',
'体验模式':'Experience mode','普通照片':'Ordinary photo','360° 全景测试':'360° panorama',
'01　选择一张景观照片':'01  Choose a landscape photo','照片来源':'Photo source','示例照片':'Sample photo','上传我的照片':'Upload my photo',
'上传 JPG、PNG 或 WebP 照片':'Upload a JPG, PNG or WebP photo','照片名称':'Photo title','分析上传照片':'Analyze uploaded photo',
'选择示例照片':'Choose a sample photo','分析所选照片':'Analyze selected photo','示例照片尚未加入。可以先上传一张景观照片。':'No sample photos are installed. You can upload a landscape photo.',
'### 让聆听更舒适':'### Listen comfortably','每次声景时长（秒）':'Soundscape duration (seconds)',
'普通照片的视野设置':'Field of view for ordinary photos','假定水平视野（度）':'Assumed horizontal field of view (degrees)',
'只用于普通照片；全景固定分析四个90度视角。修改后重新分析生效。':'Applies only to ordinary photos. Panoramas use four fixed 90° views. Reanalyze after changing this setting.',
'分析结果与生成的声音保存在这台电脑，已完成的体验可再次打开。':'Analysis and generated audio stay on this computer. Completed experiences can be reopened.',
'研究原型用于景观预体验，不能据此判断通行或避障。':'A landscape-preview research prototype; not for navigation or obstacle avoidance.',
'正在本机识别景观、计算相对深度并构建声景…':'Analyzing the landscape and relative depth locally…',
'分析完成。可以查看图层、试听空间声音，或调整声源。':'Analysis complete. View the layers, listen to spatial audio or adjust sources.',
'显存暂时不足。请关闭占用显卡的其他应用后再次分析。':'GPU memory is currently insufficient. Retry after reducing other GPU workloads.',
'本地模型文件尚未就绪。请先运行项目的模型下载步骤，再重新分析。':'Local model files are not ready. Complete the model-download step, then retry.',
'本次分析未完成。已有示例仍可使用；技术信息见下方。':'Analysis did not finish. Saved examples remain available; details are below.',
'查看错误信息':'View error details','图片过大，请将照片缩小至 5000 万像素以内再上传。':'This image is too large. Resize it to no more than 50 million pixels.',
'直接打开已跑通的 demo，无需等待推理':'Open a completed demo without waiting for inference','已完成的示例':'Completed examples','打开此 demo':'Open this demo',
'先体验空间声音':'Preview spatial audio','这是手动设置的播放器预览，不是模型分析结果。树声在左、水声在右；鸟声默认关闭。':'This is a manually configured player preview, not a model result. Trees are on the left and water on the right; the bird source is off by default.',
'这是手动试听预览，左侧为树声，右侧为水声。':'This manually configured preview places trees on the left and water on the right.',
'播放器正在准备。照片分析功能就绪后，即可生成可试听的结果。':'The player is not ready. Photo analysis can produce a listening result once its requirements are installed.',
'02　检查这张照片的空间层次':'02  Examine the photo’s spatial layers','查看本次分析与运行信息':'View analysis and runtime details',
'模型推理':'Model inference','显存峰值':'Peak GPU allocation','自动声源':'Automatic sources','运行设备':'Device',
'推理时间包含分割与深度计算，首次模型加载另计。显存为本进程分配峰值。':'Inference time includes segmentation and depth estimation, excluding initial model loading. GPU memory is this process’s allocation peak.',
'原始照片':'Original photo','语义分割叠加':'Semantic segmentation overlay','相对深度':'Relative depth',
'分割：树木绿色、水体蓝色、天空淡蓝色、建筑橙色；其余颜色代表其他语义类别。深度：黄色较近、青色居中、蓝色较远；灰色天空不参与深度归一化。':'Segmentation: trees are green, water blue, sky pale blue and buildings orange; other colors mark other categories. Depth: yellow is relatively near, cyan intermediate and blue far. Gray sky is excluded from normalization.',
'植被':'Vegetation','水体':'Water','天空':'Sky','建筑与顶盖':'Buildings and cover','道路与铺装':'Roads and paving','查看画面要素比例':'View scene-element proportions',
'这张照片未得到有效的相对深度层次。声源使用统一默认虚拟距离，可手动校正。':'No valid relative-depth layers were obtained. Sources use a shared default virtual distance, which you can adjust.',
'03　听见景观，校正你的体验':'03  Listen and adjust your experience',
'播放器已接入 Stable Audio 3 生成素材，可切换 AI、自然录音和原版程序音效；这些均为景观模拟，图像区域用于安排方位与相对远近。':'The player supports Stable Audio 3 material, field-recording controls and earlier procedural effects. These are landscape simulations; image regions provide direction and virtual near/far cues.',
'景观描述来源':'Description source','GPT 辅助描述':'GPT-assisted description','本地规则描述':'Local-rule description','查看 GPT 原始对话':'View original GPT conversation',
'当前描述包含你的人工修改，导出时会保留来源和修改标记。':'The description includes your edits. Its provenance and edit flag are retained in the export.',
'播放器内的实时滑块只用于当次试听；需要保留并导出的修改，请在下方校正表单中应用。':'Player sliders affect this listening session only. Apply changes in the correction form below to retain and export them.',
'校正声源与景观描述':'Adjust sources and description','方位负数在左、正数在右。虚拟距离只控制音频效果，不是现实中的米数。每次修改后点击应用。':'Negative azimuths are left; positive azimuths are right. Virtual distance controls audio rendering, not real-world meters. Apply after editing.',
'启用此声源':'Enable this source','左右方位（度）':'Left/right azimuth (degrees)','虚拟音频距离':'Virtual audio distance','景观描述（可编辑并朗读）':'Description (editable; narration uses the stored text)',
'应用校正并更新试听':'Apply corrections and update playback','播放器尚未完成加载。请检查 assets 目录中的本地音频文件。':'The player could not load. Check the local audio files in assets/.',
'下载结果与校正记录（JSON）':'Download result and corrections (JSON)','查看技术与证据边界':'View methods and evidence limits',
'SegFormer 识别画面中的语义区域；Depth Anything V2 Small 输出单图相对逆深度。排除天空后按 P5 / P95 归一化，再用区域中位数安排声源。最多四个自动声源。':'SegFormer estimates semantic regions; Depth Anything V2 Small produces single-image relative inverse depth. Non-sky values are normalized by P5/P95, and region medians place up to four automatic sources.',
'中文描述可使用本地规则；存在精确匹配照片的 GPT 网页缓存时，可切换为明确标注来源的辅助描述。可见自然要素与开敞特征用于景观描述，不能当作主观 PSD 评分、真实宁静程度或视障用户体验的验证。':'Mandarin descriptions may use local rules, or explicitly attributed GPT website captures matched to the exact photo. Visible nature and openness cues describe the landscape; they are not subjective PSD scores, measured tranquility or validation with visually impaired users.',
'从一幅全景开始':'Start with a panorama','上传新风景，或找回已经完成的体验。':'Upload a new landscape or reopen a completed experience.',
'怎样准备全景图？':'How should I prepare a panorama?','请选择完整的360° × 180°等距柱状全景，常见比例为2:1。普通宽幅照片不能只凭比例当成完整全景。':'Use a complete 360° × 180° equirectangular panorama, normally 2:1. A wide photo is not a full panorama merely because its aspect ratio matches.',
'目前体验水平四个90°视角，不包含天顶和脚下。前后左右以图片中间方向为基准，不代表地理方位。':'The preview covers four horizontal 90° views, excluding zenith and nadir. Front/right/back/left refer to the image orientation, not geographic directions.',
'全景来源':'Panorama source','网上全景示例':'Saved panorama examples','上传我的全景图':'Upload my panorama','选择网上全景':'Choose a saved panorama',
'这张全景图片尚未下载完成，请先选择另一个示例。':'This panorama has not finished downloading. Choose another example.',
'查看原始来源':'View original source','查看素材许可':'View asset license','许可见来源页面':'See the source page for its license','见来源页面':'See source page',
'重新分析并生成专属声音':'Reanalyze and generate image-specific audio','分析并生成专属声音':'Analyze and generate image-specific audio',
'上传完整的 2:1 等距柱状全景图':'Upload a complete 2:1 equirectangular panorama',
'需要横向覆盖 360°、纵向覆盖 180° 的完整全景；普通宽幅照片不能仅凭 2:1 比例当作球面全景。':'The panorama must cover 360° horizontally and 180° vertically. A 2:1 aspect ratio alone does not make an ordinary wide photo spherical.',
'全景名称':'Panorama title','查看上传的完整全景':'View the full uploaded panorama','待分析的全景图':'Panorama awaiting analysis',
'图片过大，请将全景缩小至 5000 万像素以内。':'This panorama is too large. Resize it to no more than 50 million pixels.',
'这张图片的比例接近不了 2:1。请使用完整的等距柱状全景，避免把裁切图误当成 360°。':'The image is not close to 2:1. Use a complete equirectangular panorama rather than treating a crop as 360°.',
'确认后会自动完成整套体验：图片与四方向画面发送给 GPT 理解，声音在本机生成，中文导览文字发送给 Microsoft 神经语音服务配音。GPT 使用本机已登录的官方入口，无需另填密钥；生成完成后，读取和试听本图缓存可离线进行。':'After confirmation, GPT receives this panorama/four-view contact sheet, sound is generated locally, and the Mandarin guide text is sent to Microsoft neural speech. GPT uses the locally signed-in official client without an extra API key. Completed, verified results can be read and played offline.',
'确认这是完整 360° × 180° 全景':'I confirm this is a complete 360° × 180° panorama','确认全景格式后，会自动开始 GPT 理解、专属声景和自然配音。':'Confirm the panorama format to start GPT interpretation, image-specific audio and neural narration automatically.',
'本次自动生成尚未启动，已保存的步骤会保留。':'Automatic generation has not started. Saved stages are retained.','查看本次信息':'View task details',
'点击分析后，会显示四个朝向的分割、深度和声音。':'Run analysis to view segmentation, relative depth and sound for four directions.',
'本图的声音计划未通过图片与来源校验，暂不加载音频。':'The sound plan failed image/provenance verification. Audio is not loaded.','查看声音计划信息':'View sound-plan details',
'这张全景的专属声音':'Sound made for this panorama','这张上传全景已通过本机登录的官方 GPT 入口自动理解。GPT 编写本图的画面依据、分方向声源和中文导览，并保留本图提示词；流水与道路声音另补充声学约束。':'The signed-in official GPT client interpreted this upload automatically. Its image evidence, directional proxies, original prompts and Mandarin guide are retained; water/traffic prompts receive additional acoustic constraints.',
'画面理解来自网页版 GPT；本轮对照后采用更简洁的溪流声音提示，未将它冒称网页 GPT 的原始长提示。':'The image interpretation comes from a GPT website capture. This comparison selected a shorter stream prompt, separately labeled from the original detailed GPT prompt.',
'画面理解来自网页版 GPT；声音提示已进行本轮声学优化，重点区分流水、浪涌与道路声音。':'The image interpretation comes from a GPT website capture. The sound prompts include the recorded acoustic refinements for stream, surf and traffic.',
'提示词来源：网页版 GPT 已理解这张全景与四方向画面，分别写出本图声音的材质、变化节奏与空间设定。':'Prompt source: a GPT website capture interpreting this panorama and its four views, including texture, temporal variation and spatial assumptions.',
'提示词来源：本地分类与人工看图核对的缓存。':'Prompt source: cached local categories and manual image review.','提示词来源：本地粗分类规则；本图尚无匹配的网页版 GPT 理解记录。':'Prompt source: coarse local category rules. No matching GPT website interpretation is available for this image.',
'根据四个方向的树木、水面与画面环境，分别编写提示词并生成独立音频。':'Prompts and independent audio are based on visible trees, water and context across the four views.',
'本图没有识别到可配置的树木或水面声源，暂不添加其他声音。':'No supported tree/water source was identified. Other sounds are not added.',
'本图专属声音已就绪 · 图片与声音计划已匹配 · 非现场录音':'Image-specific audio ready · image/plan verified · not a site recording',
'这张全景还没有可核验的专属声音。':'No verified image-specific audio is ready for this panorama.','生成这张全景的专属声音':'Generate audio for this panorama',
'生成完成。下方已切换为这张全景的专属声音。':'Generation complete. Playback now uses this panorama’s audio.',
'专属声音暂未生成成功。图片分析结果已保留。':'Image-specific audio generation did not finish. Image-analysis results are retained.','查看声音生成信息':'View sound-generation details',
'查看画面依据、声音设定与提示词':'View image evidence, sound assumptions and prompts',
'同一全景四方向共享本图分类素材，再分别安排位置与虚拟远近。图像内容先转成文字提示词，再由 Stable Audio 3 生成；动态声音是模拟，无法从照片确认现场风速、水动、车流或实际声压。':'The four views share this image’s category tracks with separate positions and virtual distances. Image content becomes text prompts for Stable Audio 3. Dynamic sounds are simulated; a photo cannot establish wind, water motion, traffic or actual sound pressure.',
'画面可见内容与声音模拟假设分别记录。提示词限制不保证生成结果完全没有其他声音，也不能把虚拟距离当作米制测距。':'Visible content and sound assumptions are recorded separately. Prompt constraints do not guarantee the absence of incidental sounds. Virtual distance is not a metric measurement.',
'声音来源':'Audio source','本图专属生成':'Generated for this image','通用素材对照':'Shared-material control',
'转向一个方向，慢慢听':'Turn to a direction and listen','先听声音，再按需打开自然导览；随时可以停止。':'Listen first, then start narration if you wish. You can stop at any time.','选择朝向':'Choose a direction',
'这份全景结果未包含有效视角，请重新分析。':'This result contains no valid perspective views. Please reanalyze.','查看本次朗读导览':'View the narration text',
'查看分析图层与运行信息':'View analysis layers and runtime details','深度图黄色较近、蓝色较远。各视角单独估计，不能跨视角比较数值，也不代表米制距离。声音位置为视觉代理，未标定成真实全景声场。':'Yellow depth values are relatively near and blue far. Views are estimated independently; values are neither comparable across views nor metric distances. Sound positions are uncalibrated visual proxies.',
'当前视角推理':'Current-view inference','显存分配峰值':'Peak GPU allocation','当前明确选择通用素材对照；这些声音不是根据本图独立生成的。':'Shared-material control is selected. These sounds were not generated independently for this image.',
'此方向未配置有画面依据的声源，声景保持无声；仍可朗读全景导览。':'No visual source proxy is configured for this direction. The soundscape remains silent; the panorama guide can still be narrated.',
'专属声音就绪后可在此试听；也可主动选择通用素材对照。':'Listen here when image-specific audio is ready, or explicitly select the shared-material control.','本图专属声音生成并校验完成后，可在此试听。':'Playback becomes available after this image’s audio is generated and verified.','当前视角的声音未能加载。':'Audio for the current view could not be loaded.',
'对比：直接平铺输入的原版结果':'Comparison: original flat-image baseline',
'原版把整张 360° 全景当成一张普通照片，并假定整个宽度只有 70° 视野。这会压缩真实方位；等距柱状投影也会拉伸天空、地面和接缝附近的物体。':'The baseline treats the whole 360° panorama as an ordinary photo with only a 70° horizontal field of view. This compresses directions, while equirectangular projection also stretches sky, ground and objects near the seam.',
'这里保留原版结果用于检查差异。透视拆分修正的是输入投影和方向解释，不能据此声称分割或深度准确率已经提高。':'The baseline is retained for comparison. Perspective splitting corrects input projection and directional interpretation; it does not establish improved segmentation or depth accuracy.',
'下载全景四方向结果（JSON）':'Download four-view panorama result (JSON)',
'当前透视画面':'Current perspective view','当前视角的相对深度':'Relative depth for this view',
'正在依据这张全景的内容，在本机生成专属声音；每类声音约需十几至几十秒…':'Generating image-specific sound locally; each category may take tens of seconds…','正在本机把全景转换为四个透视视角，再逐个分析…':'Converting the panorama into four perspective views and analyzing them locally…',
'全景分析完成。可以切换朝向，逐个查看和试听。':'Panorama analysis complete. Switch directions to inspect and listen.','这张全景的专属声音已生成并保存。':'Image-specific audio has been generated and saved.',
'图像分析已保存，专属声音暂未生成。可在下方再次尝试。':'Image analysis is saved, but sound generation did not finish. You can retry below.','当前显存不足，请关闭占用显卡的其他程序后再试。':'GPU memory is insufficient. Retry after reducing other GPU workloads.','本次全景分析未完成。已有的全景示例仍可直接打开。':'Panorama analysis did not finish. Saved examples remain available.','查看本次错误':'View this error',
'最近还没有可恢复的本机全景任务。':'No recoverable local panorama tasks yet.','也可以找回最近的本机任务，无需重新上传；仍会核对原始图片与完整结果。':'Reopen a recent local task without uploading again. Its original image and completed results are still verified.',
'继续查看最近的全景任务':'Reopen a recent panorama task','选择一条本机任务':'Choose a local task','这条本机任务暂时无法恢复。已有文件会保留，可重新上传原图。':'This local task cannot be recovered right now. Files are retained; you can upload the original image again.','查看恢复信息':'View recovery details',
'正在准备自动生成…':'Preparing automatic generation…','正在启动自动生成…':'Starting automatic generation…','本次生成暂未完成，已完成的步骤已保留。':'Generation did not finish. Completed stages are retained.','本次生成已停止，已完成的步骤已保留。':'Generation stopped. Completed stages are retained.',
'GPT理解、专属声景和自然配音已完成。':'GPT interpretation, image-specific audio and neural narration are complete.','正在重新核验与恢复这张全景的完整结果…':'Verifying and recovering this panorama’s complete result…',
'本图缓存未通过完整校验，可保留有效步骤并重新生成缺失内容。':'The cache failed full verification. Valid stages can be retained while missing content is regenerated.','重新核验并继续生成':'Verify and resume generation',
'本次自动生成已停止，已完成的步骤会保留。可继续重试。':'Automatic generation has stopped. Completed stages are retained, and you can retry.','电脑当前可用内存有些紧张。稍后点击继续即可，图片理解和已完成内容不需要重做。':'Available memory is currently limited. Resume later; image interpretation and completed stages do not need to be repeated.','继续自动生成':'Resume automatic generation',
'可以继续查看进度。刷新页面不会重复启动同一张图的任务。':'You can keep checking progress. Refreshing does not start a duplicate task for this image.','停止本次生成':'Stop this generation','已请求停止，当前步骤结束后会保留结果并停止后续步骤。':'Stop requested. The current stage will finish and retain its result; later stages will not start.',
'已保存的完整结果没有通过校验，暂不加载试听。':'The saved result failed verification. Playback is not loaded.','这张全景已自动完成GPT理解、专属声景与自然配音。':'This panorama has completed GPT interpretation, image-specific audio and neural narration.','已加载本图完整结果。重新打开同一张图片时会核验缓存，不重新发送到GPT。':'The complete result is loaded. Reopening the same file verifies its cache without sending it to GPT again.',
'待开始':'Not started','处理中':'Processing','已完成':'Complete','需重试':'Retry needed','已停止':'Stopped','待查看':'Not checked','已完成 · 已保留':'Complete · retained','正在处理':'Processing','稍后开始':'Waiting','可以继续重试':'Ready to retry',
'分析全景与四个方向':'Analyze panorama and four views','GPT 理解画面':'GPT image interpretation','整理声景与中文导览':'Prepare sound plan and Mandarin guide','生成本图声景':'Generate image-specific audio','生成自然配音':'Generate neural narration',
'正在准备全景…':'Preparing panorama…','正在分析全景与四个方向…':'Analyzing panorama and four views…','正在让 GPT 理解这张全景…':'GPT is interpreting this panorama…','正在整理声景提示与中文导览…':'Preparing sound prompts and Mandarin guide…','正在本机生成这张全景的声音…':'Generating this panorama’s audio locally…','正在生成自然中文配音…':'Generating Mandarin neural narration…','全景理解、专属声景和自然配音已完成。':'Panorama interpretation, image-specific audio and neural narration are complete.',
'叶片':'Leaves','水面':'Water surface','海浪':'Surf','流水':'Stream','道路背景':'Road ambience','风声':'Wind','声源':'Source','不可用':'Unavailable',
'此视角暂无景观描述。':'No landscape description is available for this view.','尚未保存':'Not saved yet',
}

DIRECTIONS = {'front': ('正前方','Front'), 'right': ('右方','Right'), 'back': ('后方','Back'), 'left': ('左方','Left')}
CATEGORIES = {'trees': ('叶片','Leaves'), 'water': ('水面','Water'), 'surf': ('海浪','Surf'), 'stream': ('流水','Stream'), 'traffic': ('道路背景','Road ambience'), 'wind': ('风声','Wind'), 'bird': ('鸟鸣（人工）','Bird (manual)')}

def direction_label(identifier, fallback='', language=None):
    language = language or get_language()
    values=DIRECTIONS.get(identifier)
    return values[1 if language == 'en' else 0] if values else tr_ui(fallback or identifier, language)

def category_label(identifier, fallback=''):
    values=CATEGORIES.get(identifier)
    return t(*values) if values else tr_ui(fallback or identifier)

def ui_formatter():
    # Streamlit may serialize widget options outside the render context.
    # Capture the displayed language rather than consulting mutable context.
    language=get_language()
    return lambda value: tr_ui(value, language)


def keep_ui_widget(widget, *args, **kwargs):
    """Restore a widget's existing value when its presentation language changes.

    Streamlit 1.50 includes labels and displayed options in widget identity, even
    with an explicit key. Copying a value through public Session State before
    rendering the translated widget keeps its data stable in this session.
    """
    import streamlit as st
    key = kwargs['key']
    language = get_language()
    previous = st.session_state.setdefault('_ui_widget_languages', {})
    changed = key in previous and previous[key] != language
    previous[key] = language
    if changed and key in st.session_state:
        st.session_state[key] = st.session_state[key]
        bound = inspect.signature(widget).bind(*args, **kwargs)
        parameters = inspect.signature(widget).parameters
        # A stored value is authoritative; do not also supply a new default.
        if 'index' in parameters:
            bound.arguments['index'] = None
        elif 'value' in parameters:
            bound.arguments['value'] = None
        return widget(*bound.args, **bound.kwargs)
    return widget(*args, **kwargs)


def localized_uploader(label, **kwargs):
    """Translate the visible title without replacing Streamlit's upload widget.

    File-uploader values cannot be assigned through Session State. Its internal
    label therefore stays constant, while the surrounding title is localized.
    """
    import streamlit as st
    st.markdown(label)
    return st.file_uploader('Image upload', label_visibility='collapsed', **kwargs)

def tr_ui(value, language=None):
    if (language or get_language()) != 'en' or not isinstance(value,str):
        return value
    return _english(value)

def _english(value):
    if value in TEXT:
        return TEXT[value]
    if value.startswith('**') and value.endswith('**'):
        return '**'+_english(value[2:-2])+'**'
    patterns = [
      (r'^当前结果：(.*)$',lambda m:'Current result: '+m[1]),
      (r'^当前朝向：(.*) · ([-\d.]+)°$',lambda m:'Current direction: '+{'正前方':'Front','右方':'Right','后方':'Back','左方':'Left'}.get(m[1],m[1])+' · '+m[2]+'°'),
      (r'^当前方向有 (\d+) 个模拟声源。切换方向，相当于转身后重新面向画面。$',lambda m:f'{m[1]} simulated source(s) in this direction. Changing views is like turning to face a new direction.'),
      (r'^([\d.]+) 秒$',lambda m:m[1]+' s'),(r'^(\d+) 个$',lambda m:m[1]),
      (r'^区域占图像 (.*?) · 模型近度 (.*)$',lambda m:'Image area '+m[1]+' · estimated nearness '+_english(m[2])),
      (r'^本次结果保存于：(.*)$',lambda m:'Result saved at: '+_english(m[1])),
      (r'^原版推理：(.*?) 秒；原版声源：(\d+) 个。$',lambda m:f'Baseline inference: {m[1]} s; baseline sources: {m[2]}.'),
      (r'^完整 360° × 180° 等距柱状全景 · (.*)$',lambda m:'Complete 360° × 180° equirectangular panorama · '+m[1]),
      (r'^来源：(.*?) · 与当前照片匹配 · (.*?)。文本已缓存，日常使用可离线朗读。$',lambda m:'Source: '+m[1]+' · exact photo match · '+m[2]+'. Cached text and narration remain available offline.'),
      (r'^公开拍摄素材 · 作者：(.*?) · (.*?) · Powered by Poly Haven$',lambda m:'Public photographic asset · author: '+m[1]+' · '+_english(m[2])+' · Powered by Poly Haven'),
    ]
    for pattern,render in patterns:
        match=re.fullmatch(pattern,value,re.S)
        if match:return render(match)
    for prefix,en in [('无法读取所选图片：','Could not read the selected image: '),('无法读取上传图片：','Could not read the uploaded image: '),('无法读取这张图片：','Could not read this image: '),('画面内容：','Stored scene facts (original Chinese): '),('不能由照片确定：','Cannot be established from the photo (original Chinese data): '),('声音设定：','Sound assumptions (original Chinese data): ')]:
        if value.startswith(prefix):return en+value[len(prefix):]
    for ending,en in [('文件尚未生成。',' file is not generated yet.'),('尚未生成。',' is not generated yet.')]:
        if value.endswith(ending):return _english(value[:-len(ending)])+en
    return value
