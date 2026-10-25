# 本地 Stable Audio 3 运行环境

[English](README.md) | [简体中文](README.zh-CN.md)

公开仓库提供音效环境的安装与生成脚本、文档和许可信息；该环境独立于景观分析使用的 `.venv`。官方原生 Windows LiteRT/TFLite 运行时代码、优化模型权重、虚拟环境和生成结果会在安装及使用时下载或创建到本机，不随仓库分发。

- 官方代码：<https://github.com/Stability-AI/stable-audio-3>
- 代码版本：`77e0398c26f7d22d801ec1bb036307e8b231f741`
- 公开的优化模型：<https://huggingface.co/stabilityai/stable-audio-3-optimized>
- 模型版本：`08b17423649b5714b22eab20f96bf00751f2358a`
- 历史测试环境：Python 3.11.15、LiteRT 2.3.0、XNNPACK CPU、8线程、8个采样步骤。
- Small-SFX：DiT 为 `sm-sfx/w8a8`，解码器为 `SAME-S/w8a8`。共享编码器与这组权重合计1,192,498,584字节。
- Medium：DiT 为 `medium/w8a8`，解码器为 `SAME-L/w8a8`。新增权重合计2,183,090,096字节，各文件的精确指纹记录在 `weights_manifest.json`。

所有音效模型推理均在本机进行。这条路线使用CPU，不假定当前Windows安装具备CUDA或Flash Attention支持。它不改变现有的PyTorch/Transformers主应用环境。安装后的模型、缓存和临时文件目录位于本文件夹下；历史测试电脑的项目位于D盘，其他安装可以使用自行选择的项目磁盘。

## 安装独立音效环境

请先阅读仓库随附的 [Stable Audio Community License](model_LICENSE.md)、[Gemma条款](model_LICENSE_GEMMA.md) 和 [模型说明](model_README.md)。确认这些许可条件适用于你的用途后，从项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\audio_model\install_windows.ps1 -IncludeMedium -AcceptModelLicense
```

安装脚本会创建 `audio_model/.venv`，获取固定代码版本的官方运行时，并下载、校验Small-SFX、共享编码器、Medium和SAME-L权重。它需要联网、Python 3.11或uv，以及Git for Windows。`-AcceptModelLicense` 表示明确确认已阅读并将遵守随附的模型许可；脚本不会替你接受受限服务协议。不加 `-IncludeMedium` 时只安装Small-SFX路线；主应用当前的逐图声景生成使用Medium。

下文的耗时与内存数据均为历史测试电脑上的观察结果。本仓库不包含该电脑生成的候选音频、模型缓存、实验输出或运行日志。

## 生成或校验已保存的候选音频

从项目根目录运行：

```powershell
.\audio_model\.venv\Scripts\python.exe audio_model\generate_candidates.py --only all
```

已存在且通过校验的结果会被复用，该命令不会静默替换已有候选音频。可以向 `--only` 传入单个编号，包括 `trees_soft_20261026`、`water_ripples_20261028`、`trees_soft_cfg2_20261026`、`water_ripples_cfg2_20261028`、`medium_trees_20261026` 或 `medium_water_20261028`。使用 `--only model_comparison` 可生成两条Medium对照候选。

原始生成的立体声WAV保存在 `assets/generated_raw/`。`assets/generated_raw/manifest.json` 和 `outputs/audio_model_run/*.json` 记录提示词、随机种子、CFG、负向提示、时长、采样率、WAV文件指纹、分阶段耗时以及观察到的进程树峰值内存。两个CFG=2案例采用相同随机种子作对照；CFG=1案例按设计不启用负向分支。

最初20秒冒烟测试的WAV曾在包装脚本发生日志解码错误后恢复，未重新生成；该次运行的RSS内存测量不可用，记录为null。之后的候选运行均有完整监测。可选OpenVINO/NPU插件的警告没有阻止官方CPU后端运行；WAV已验证为数值有限、非静音的44.1kHz立体声PCM。

## 历史测试电脑上的实际运行

六条Small-SFX正式候选均为30秒音频，官方CLI运行耗时5.09–7.72秒，计入进程启动后为5.56–8.20秒。进程树RSS峰值为1,712.6–1,806.3 MiB。

两条Medium对照候选与首组Small-SFX使用相同提示词和随机种子，均为30秒、8步骤、CFG=1，且没有启用负向分支。风／树叶候选的CLI耗时为16.86秒，计入启动为17.228秒，进程树RSS峰值为2,085.3 MiB。湖水候选的CLI耗时为16.04秒，计入启动为16.561秒，RSS峰值为2,018.8 MiB。两条均为数值有限、非静音且无削波采样的44.1kHz立体声PCM WAV。这些耗时对应本机固定提示词、精度和8线程配置，不构成延迟保证。

旧版候选生成包装脚本保留原先的启动预检：系统可用内存至少为5 GiB。逐图上传的生成脚本采用本机测得的4.25 GiB预算，即2.5 GiB推理额度、1.25 GiB Windows预留和0.5 GiB余量。该预算依据固定Medium/w8a8/SAME-L运行时约2.0 GiB的进程树峰值制定，不适用于其他模型。它将各场景的模型任务串行执行；若系统可用内存持续低于1.25 GiB，只停止自身的生成子进程。新浅溪上传在4.542 GiB可用内存下启动，测得进程树峰值2,017.7 MiB，运行期间系统可用内存最低仍为2.806 GiB。每次新生成都会记录启动预算与最低内存余量。

这些文件是AI生成的声音效果，不是现场录音，也不是景观照片拍摄地点的录音。数值校验不能证明主观听感良好、完全没有附带的人声／鸟鸣／音乐，或比自然录音更受偏好。

## 许可与下载

在记录的版本中，优化模型仓库可以不登录公开下载。历史下载明确使用 `token=False`，未读取账号凭据，也未接受受限访问协议。模型仍受已发布的Stable Audio Community License及随附Gemma条款约束，文本分别保存在 `model_LICENSE.md` 和 `model_LICENSE_GEMMA.md`。公开可下载不代表这些条件失效。官方运行时代码另有其仓库许可。

`download_weights.py` 下载固定版本的Small-SFX权重，并通过硬链接或复制，将缓存文件放到官方运行时预期的位置。传入 `--include-medium` 可额外下载Medium及SAME-L权重；共享编码器会被复用。`requirements-lock.txt` 记录独立音效环境的依赖版本；安装过程不会向主应用环境安装音效运行时的软件包。
