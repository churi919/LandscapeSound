# 第三方来源与许可

[English](THIRD_PARTY_NOTICES.md) | [简体中文](THIRD_PARTY_NOTICES.zh-CN.md)

[返回项目说明](README.zh-CN.md)

本文件列明本项目调用的主要第三方组件与演示素材。各组件许可彼此独立；项目公开不会改变第三方条款，也不会把模型权重、依赖或媒体统一改为 MIT。

## 图像模型

| 组件 | 本项目用途 | 来源与许可 |
| --- | --- | --- |
| `nvidia/segformer-b0-finetuned-ade-512-512` | ADE20K 语义类别估计 | [模型卡](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512)指向 [NVIDIA SegFormer License](https://github.com/NVlabs/SegFormer/blob/master/LICENSE)，其中使用限制为研究／评估非商业用途；权重未随本仓库分发 |
| `depth-anything/Depth-Anything-V2-Small-hf` | 相对单目深度估计 | [Small 模型卡](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)标注 Apache-2.0；不把该标注推及其他尺寸或模型版本；权重未随本仓库分发 |

模型安装由各自上游提供，下载后应保留对应许可与模型卡。依赖接口不使本项目成为已验证的空间测量系统。

## 音效模型和运行代码

- [Stability-AI/stable-audio-3](https://github.com/Stability-AI/stable-audio-3) 官方代码使用 [MIT License](https://github.com/Stability-AI/stable-audio-3/blob/main/LICENSE)。本项目固定代码 revision 为 `77e0398c26f7d22d801ec1bb036307e8b231f741`，运行时单独获取，不将上游源码或其 Git 历史作为本项目文件提交。
- [stabilityai/stable-audio-3-optimized](https://huggingface.co/stabilityai/stable-audio-3-optimized) 模型固定 revision 为 `08b17423649b5714b22eab20f96bf00751f2358a`。权重适用 **Stable Audio Community License** 及所附 **Gemma** 条款。许可原文保存在 [model_LICENSE.md](audio_model/model_LICENSE.md) 与 [model_LICENSE_GEMMA.md](audio_model/model_LICENSE_GEMMA.md)。代码的 MIT 许可不覆盖模型权重。
- 当前本机路径使用 LiteRT/TFLite 与 XNNPACK CPU。依赖由包管理器安装，其版权声明和许可仍属于各自项目；环境本身不随仓库发布。
- `demo_public/` 中的声音由模型生成，经过本项目音频处理，再编码为 OGG Vorbis 有损试听副本；它们不是摄影地点的现场实录。其生成方式、提示词和处理信息以演示元数据为准，不以照片的 CC0 许可代替音频适用条件。

## 中英文神经配音

[edge-tts](https://github.com/rany2/edge-tts) 是调用 Microsoft Edge 在线语音服务的第三方 Python 客户端。本项目使用 7.3.1；其主要文件使用 LGPLv3，`srt_composer.py` 单独使用 MIT，详见[上游 LICENSE](https://github.com/rany2/edge-tts/blob/master/LICENSE)。客户端安装在独立环境，通过外部进程调用，未修改或捆绑其源码。

客户端开源许可不等于 Microsoft 语音服务或合成输出的许可。调用服务与使用合成语音仍需遵循提供方适用条件。公开示例中文使用晓晓，英文使用 Jenny，两者均为神经合成语音，不是真人或现场录音；应用还支持可选的中文云希与英文 Guy 声线。不得据此暗示配音者为项目背书。公开英文导览为对应中文导览的审阅译文，文字与语音指纹按语言分别记录。

## 摄影全景

公开演示使用以下 Poly Haven 摄影资产。Poly Haven 将资产以 [CC0](https://polyhaven.com/license) 提供；这里保留作者和资产来源。图片仅进行缩放／编码以便展示，不生成或替换景物。网站标识、网页文案或示例渲染不应与资产本身混为一谈。

| 资产 | 作者／贡献 | 官方来源 |
| --- | --- | --- |
| Monbachtal Riverbank | Andreas Mischok | [资产页](https://polyhaven.com/a/monbachtal_riverbank) |
| Crystal Falls | Greg Zaal | [资产页](https://polyhaven.com/a/crystal_falls) |
| Secluded Beach | Greg Zaal；Rico Cilliers（Backplates） | [资产页](https://polyhaven.com/a/secluded_beach) |
| Urban Street 03 | Andreas Mischok | [资产页](https://polyhaven.com/a/urban_street_03) |

Powered by Poly Haven. `demo_public/` 的摄影许可不延伸到 AI 音效、配音或项目原创代码。

## 历史自然录音与旧素材

本地研究流程曾使用 Freesound 的公开 HQ MP3 预览作自然录音对照：

| 来源 | 作者 | 当时记录的许可 |
| --- | --- | --- |
| [Tree/wind 183496](https://freesound.org/people/ecfike/sounds/183496/) | ecfike | CC0-1.0 |
| [Lake water 523392](https://freesound.org/people/Anya_Media/sounds/523392/) | Anya_Media | CC0-1.0 |
| [Brook 465619](https://freesound.org/people/Nox_Sound/sounds/465619/) | Nox_Sound | CC0-1.0 |

这些转码素材属于其他地点的录音，未包含在本次 `demo_public/` 包中，也不声称是原始无损 WAV 或全景拍摄地录音。历史机器上另有个人普通照片与过程输出，它们不进入公开仓库。

浏览器空间化使用 Web Audio `PannerNode` 的 HRTF 模式，由浏览器实现。仓库未另行分发 SOFA、HRIR 或个人 HRTF 数据集。程序生成的旧占位音效与生成式 AI 声音也分别标记。

## 其他依赖及原创代码

探索性内容评价使用 [`laion/clap-htsat-unfused`](https://huggingface.co/laion/clap-htsat-unfused)，其模型卡标注 Apache-2.0。它不参与主应用的声景生成，评价模型权重也不随仓库分发。需要重新评价时，应查阅该模型卡和对应上游条件。

Python、PyTorch、Transformers、Streamlit、NumPy、SciPy、Pillow、Hugging Face Hub、mutagen 与测试依赖均保留各自上游版权与许可。[pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) 和 [future](https://github.com/PythonCharmers/python-future) 的安装包元数据标注 MIT。安装清单用于指定环境，不捆绑这些包的源代码或二进制。

本项目原创代码尚未指定开源许可证。公开展示不自动授予第三方代码或媒体的复用权；进一步分发或商业使用时，应分别核对所用模型、依赖、服务和素材的适用条件。
