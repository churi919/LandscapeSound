# LandscapeSound · 景观听见

**用一张全景图，生成对应的空间声景与中文导览。**

LandscapeSound is a Windows-first research prototype for image-guided soundscape previews: panorama interpretation, local audio generation, spatial playback, and neural Chinese narration.

上传完整的 360° 全景后，应用会自动完成 GPT 看图、本图专属音效生成和中文配音。你可以切换四个朝向，对照画面试听，也可以随时停止声音或朗读。声音是依据图片设计的模拟，**不是拍摄地点的现场录音**。

[体验方式](#先听已有-demo) · [安装运行](#安装运行主应用) · [技术架构](docs/architecture.md) · [第三方来源与许可](THIRD_PARTY_NOTICES.md)

![岩壁瀑布全景示例](demo_public/images/crystal_falls.jpg)

摄影：[Crystal Falls](https://polyhaven.com/a/crystal_falls) · Greg Zaal · [Poly Haven CC0](https://polyhaven.com/license)。图像仅为完整全景的缩略展示，生成声音另行标记。

## 先听已有 Demo

仓库内的 [demo_public](demo_public/index.html) 保存四张公开摄影全景的轻量展示、生成声景和自然女声，整个试听包约2.1 MB。照片为完整 ERP 缩略图，声景为 OGG Vorbis 有损试听副本，女声保留原 MP3。查看这些结果不需要下载模型或登录 GPT，也可直接用浏览器打开其中的 `index.html`。

GitHub 的源码页面不会直接运行 HTML。下载或克隆仓库后，在项目根目录启动静态服务：

```powershell
py -3.11 -m http.server 8502 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8502/demo_public/>。这只是已保存结果的试听页；上传新图需要启动下方的主应用。

启动主应用后，“先听一个已完成示例”也可直接读取这组内嵌演示，无需另开静态服务器、下载模型或调用 GPT。

| 本轮新场景 | 摄影来源 | 生成结果 |
| --- | --- | --- |
| 林间浅溪与低跌水 | [Monbachtal Riverbank](https://polyhaven.com/a/monbachtal_riverbank) | 本图独立水声音轨与导览 |
| 岩壁瀑布与水潭 | [Crystal Falls](https://polyhaven.com/a/crystal_falls) | 本图独立流水音轨与导览 |
| 沙石海滩与近岸浪线 | [Secluded Beach](https://polyhaven.com/a/secluded_beach) | 本图独立海浪音轨与导览 |
| 住宅街道与路边停车 | [Urban Street 03](https://polyhaven.com/a/urban_street_03) | 明确作为设想的稀疏道路声音与导览 |

照片来自 Poly Haven 的 CC0 资产，作者与处理信息保留在公开演示元数据中。生成音效、神经配音和原照片的来源分别记录，不混用许可。

## 可以做什么

- 上传完整的 2:1 等距柱状全景，自动拆为正前、右、后、左四个 90° 透视视角。
- 在本机运行语义分割和相对深度估计，查看原图与分析图层。
- 用已登录 ChatGPT 的官方 Codex 客户端理解本图，分别记录可见事实、声音模拟假设和不确定性。
- 在本机用 Stable Audio 3 Medium 生成每图必要的独立音轨，支持流水、海浪、道路、风、叶片和微浪。
- 生成本图中文神经语音导览；声景与朗读互停，停止按钮同时停止二者。
- 核验并恢复本机任务，失败后保留已完成阶段；相同原文件的完整结果可读缓存。
- 导出本图的计划、声音来源、导览文字和方位设置。普通照片模式也保留本地分析与校正入口。

同一张全景的四方向共享本图音轨，再按各方向的可见景物安排声像。没有配置视觉代理声源的方向保持声景无声，仍可朗读导览。

## 当前效果与限制

**流水像雨的问题尚未解决。** 四张新图已通过主应用实际运行，但自动内容诊断暴露了流水方案的泛化不足。

| 检查对象 | 本轮观察 |
| --- | --- |
| 浅溪 | CLAP 溪流标签接近度 0.535，雨标签 0.620，仍有雨声混淆信号 |
| 岩壁瀑布 | 溪流 0.638、雨 0.619、瀑布 0.463，较大水势表达不足 |
| 不同水景 | 两条新流水音轨的表征相似度 0.861，区别不足；海边与流水也偏相近 |
| 街道 | 与三种水景的表征相似度约 0.200–0.263，区分较清楚 |
| 中文配音 | 四段晓晓导览约 25.7–27.8 秒，文字、音频指纹与播放检查通过；未给自然度打分 |

这些 CLAP 数值是探索性的内容表征比较，**不是人耳辨识率、自然度评分或事件发生概率**。数值基于统一28秒、约−23 LUFS的未压缩对照 WAV；公开 OGG 是有损试听副本，未重新评分。新图与旧图不同，跨轮差异也不能单独归因于提示词改善。

相对深度和虚拟半径不是米制测距，不能跨视角直接比较。静态图片不能确认实际风速、水势、车流、响度或通行条件。该原型用于景观预体验研究，尚未证明对盲人／低视力用户的空间理解或使用体验有改善，也不能用于导航、避障或安全判断。

## 安装运行主应用

### 环境

优先支持 **Windows 10/11、Python 3.11**。已经运行过的配置为 Intel i9-14900HX、32 GB 内存、NVIDIA RTX 4060 Laptop 8 GB。图像模型可选择 CUDA 或 CPU；当前音效生成使用独立的 LiteRT/TFLite **CPU** 环境，不要求将音效模型放入显卡。

首次安装需要联网下载 Python 依赖和模型，并预留数 GB 以上磁盘空间。仓库不包含模型权重、虚拟环境、原始大尺寸摄影文件或本机历史任务。

### 1. 安装图像分析环境

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1 -InstallNarration
```

默认安装 CUDA 12.8 对应的 PyTorch。没有合适的 NVIDIA GPU 时选择 CPU：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1 -TorchBackend cpu -InstallNarration
```

安装过程会下载 SegFormer B0 与 Depth Anything V2 Small。SegFormer 使用 NVIDIA 的研究／评估非商业许可，使用前请阅读 [第三方说明](THIRD_PARTY_NOTICES.md)。已有模型可复用；只安装主环境时可加 `-SkipModelDownload`。

### 2. 安装独立音效环境

先阅读 [Stable Audio Community License](audio_model/model_LICENSE.md)、[Gemma 条款](audio_model/model_LICENSE_GEMMA.md)和 [音效运行说明](audio_model/README.md)。确认适用条件后，在本机显式运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\audio_model\install_windows.ps1 -IncludeMedium -AcceptModelLicense
```

脚本获取固定版本的官方运行代码与模型；这些内容保存在被 Git 忽略的本机目录，不作为本项目代码重新分发。音效环境与主 `.venv`、配音 `.venv_narration` 分开。

### 3. 准备 GPT 登录

安装官方 Codex 客户端，并在本机通过 ChatGPT 账号正常登录。应用从官方程序的可执行路径或 `PATH` 查找客户端；需要时可设置 `LANDSCAPESOUND_CODEX_EXE` 为它在自己电脑上的路径。

当前桥接已在 Codex CLI `0.164.0-alpha.11.1` 上实跑，使用固定模型标识 `gpt-6.1-sol`，需要账号、客户端版本和可用额度支持该标识。此入口使用 **官方客户端的已登录会话，不是 ChatGPT 网页自动点击**，也不要求把 API 密钥写进项目。不要把登录文件、令牌或浏览器资料复制到仓库。GPT 不可用时任务会明确停止并保留已完成阶段，不会将本地分类规则冒充 GPT 理解。

### 4. 启动

双击 `start_windows.bat`，或运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

打开 <http://127.0.0.1:8501/>。默认进入全景上传；确认图像覆盖完整 360° × 180° 后，五阶段流程自动开始。普通宽幅照片不能仅凭 2:1 比例当作球面全景。

刷新后可从“继续查看最近的全景任务”找回本机结果。失败时点击“继续自动生成”补做缺失步骤。退出时在启动终端按 Ctrl+C；也可使用 `stop_windows.ps1` 停止当前项目服务。

## 哪些步骤联网

| 步骤 | 发送或下载的内容 | 已缓存后 |
| --- | --- | --- |
| 首次环境／模型准备 | Python 依赖与模型权重下载 | 图像和音效推理在本机运行 |
| 新图 GPT 理解 | 本图全景／四方向拼图和文字要求发送至 GPT 服务 | 相同原文件的完整任务可读本机缓存 |
| 新文本神经配音 | 导览文字经 `edge-tts` 客户端发送至 Microsoft 在线语音服务 | 精确文字对应的 MP3 可离线播放 |
| 浏览器声景播放 | 读取本机生成的音频，使用 Web Audio 渲染 | 播放本身不需要重新生成 |

晓晓是神经合成配音，不是真人录音。`edge-tts` 是第三方客户端，服务可用性与适用条件由其服务提供方决定。

## 项目结构

```text
app.py / ui_theme.py             主界面与可读性样式
panorama_ui.py                   上传、恢复与四方向查看
panorama_pipeline.py             五阶段任务、缓存校验与失败恢复
gpt_cli_bridge.py / gpt_scene_audio.py
                                GPT 图像入口与结构化计划
analyzer.py / panorama.py        本地图像模型与全景转换
scene_audio_runtime.py           独立音效进程与后处理
audio_model/                    音效脚本、固定版本与许可说明
narration.py / synthesize_narration.py
                                精确文本配音缓存与合成
audio_player* / browser_audio.py 浏览器空间试听与播放控制
tests/                          工程测试
demo_public/                    可发布的轻量结果与来源
docs/architecture.md            实现与数据边界
```

运行时会在 `models/`、`.cache/`、`assets/` 和 `outputs/` 创建本机文件。它们不随公开仓库上传；重新安装和运行可生成需要的目录。已有研究机器上的历史记录仍在本机保留。

## 验证

```powershell
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

在不含模型、历史输出、原始照片和本机环境的干净源码副本中，项目测试为 **142 passed**。测试不要求 GPT 登录或在线配音；安装 Node.js 可运行其中3项浏览器脚本检查，缺少 Node 时这3项会明确跳过。`pytest.ini` 将项目测试与下载的第三方上游测试分开。工程检查验证缓存身份、解析、恢复、音频处理与控制逻辑，不替代分割准确率、声景自然度或目标用户测试。

## 来源与许可

详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。模型、依赖、摄影、生成音效与配音分别遵循各自适用条件。

本项目原创代码尚未指定开源许可证。仓库公开可查看不等于授予通用的复制、修改或再分发许可；不要将第三方素材视为统一的 MIT 授权。
