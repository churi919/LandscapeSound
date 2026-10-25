---
language:
- en
library_name: stable-audio-3
license: other
license_name: stable-audio-community
license_link: LICENSE.md
pipeline_tag: text-to-audio
tags:
- audio-generation
- music
- sound-effects
- diffusion
---

# Stable Audio 3 Optimized

> **Note:** This repository contains experimental checkpoints optimised for acceleration on specific hardware. For standard checkpoints, please use [Stable Audio 3 Medium](https://huggingface.co/stabilityai/stable-audio-3-medium) instead.

Please note: For commercial use, please refer to [https://stability.ai/license](https://stability.ai/license)

## Model Description
`Stable Audio 3` is a family of fast latent diffusion models (small, medium, large) for variable length audio generation and editing. Since our models can generate several minutes of audio,
variable-length generations are key to avoid the cost of producing full-length generations for short
sounds. We also support inpainting, enabling targeted audio editing and the continuation of short
recordings. Our latent diffusion models operate on top of a novel semantic-acoustic autoencoder that
projects audio into a compact latent space, enabling efficient diffusion-based generation while preserving audio fidelity and encouraging semantic structure in the latent. Finally, we run adversarial
post-training to both accelerate inference and improve generation quality, reducing the number of inference steps while improving fidelity and prompt adherence. Stable Audio 3 models are trained on
licensed and Creative Commons data to generate music and sounds in less than a 2s on an H200 GPU
and less than a few seconds on a MacBook Pro M4. We release the weights of small and medium,
that can run on consumer-grade hardware, together with their training and inference pipeline.

## Usage

This model can be used with:
1. the [`stable-audio-3`](https://github.com/Stability-AI/stable-audio-3) inference and fine-tuning library
2. the [`stable-audio-tools`](https://github.com/Stability-AI/stable-audio-tools) research library


### Using with `stable-audio-3`
```python
from stable_audio_3 import StableAudioModel

model = StableAudioModel.from_pretrained("medium")
audio = model.generate(
    prompt=(
        "House music that encapsulates the feeling of being at a festival "
        "in the sunny weather with all your friends 124 BPM"
    ),
    duration=180
)
```

### Using with `stable-audio-tools`
```python
import torch
import torchaudio
from einops import rearrange
from stable_audio_tools import get_pretrained_model
from stable_audio_tools.inference.generation import generate_diffusion_cond_inpaint

device = "cuda" if torch.cuda.is_available() else "cpu"
if device == "cuda":
  model_half = True

# Download model
model, model_config = get_pretrained_model("stabilityai/stable-audio-3-medium")
sample_rate = model_config["sample_rate"]
sample_size = model_config["sample_size"]

model = model.to(device)
if model_half:
  model = model.to(torch.float16)
# Set up text and timing conditioning
conditioning = [{
    "prompt": (
        "A dream-like Synthpop instrumental that would accompany "
        "a dream-sequence in a surrealist movie 120 BPM"
    ),
    "seconds_total": 380
}]

# Generate stereo audio
output = generate_diffusion_cond_inpaint(
    model,
    steps=8,
    cfg_scale=1.0,
    conditioning=conditioning,
    sample_size=sample_size,
    sampler_type="pingpong",
    device=device
)

# Rearrange audio batch to a single sequence
output = rearrange(output, "b d n -> d (b n)")

# Peak normalize, clip, convert to int16, and save to file
output = output.to(torch.float32).div(torch.max(torch.abs(output))).clamp(-1, 1).mul(32767).to(torch.int16).cpu()
torchaudio.save("output.wav", output, sample_rate)
```


### Optimized CPU runtime (TFLite / LiteRT)

Portable CPU builds live in [`optimized/tflite`](https://github.com/Stability-AI/stable-audio-3/tree/main/optimized/tflite). The SAME autoencoder ships as static **rung** `.tflite` codecs at `tflite/same-{s,l}/{enc,dec}_{fp32,w8a8}.tflite` — one weight-shared file per encoder/decoder that dispatches a fixed-size subgraph per length, keeping RAM flat and avoiding a chunk-size knob. They require **`ai_edge_litert>=2.2.0`** and are driven by the `RungEncoder` / `RungDecoder` runtime in that directory (`w8a8` is the default; `fp32` is the bit-exact reference). The earlier dynamic-length codecs are preserved under `tflite/same-*/legacy/`.

### Runtime LoRA on TensorRT (NVIDIA)

`dit_fp16_lora.trt` is a DiT with a **runtime low-rank branch** on each adapted linear. All
three DiTs have one:

| engine | DiT | targets | size |
|---|---|---|---|
| `tensorRT/sm_90/sa3-m/dit_fp16_lora.trt` | medium, 24 × 1536 | 229 | 2.96 GB |
| `tensorRT/sm_90/sa3-sm-music/dit_fp16_lora.trt` | small-music, 20 × 1024 | 193 | 0.95 GB |
| `tensorRT/sm_90/sa3-sm-sfx/dit_fp16_lora.trt` | small-sfx, 20 × 1024 | 193 | 0.95 GB |

A TensorRT plan has its weights compiled in, so an adapter cannot be merged into it the way
the CPU runtime does; these engines instead take the adapter as *network inputs* — `A`, `Bt`
and a per-output-row rescale `P` are fed in like activations, with the rank as a dynamic
dimension — and compute `y = W₀·x·(1+P) + Btᵀ·(srow ⊙ (A·x))`.

So loading an adapter is a buffer write rather than a rebuild: adapters swap in milliseconds,
several stack by concatenating along the rank axis (up to a total of 512), and `srow` gives
each one its own strength. `P` is what DoRA needs — its per-row magnitude rescale is a change
to the *base* path that no low-rank branch can express.

The branch costs a flat few ms per step, so its relative price depends on which DiT it is
attached to. On medium that is +13% at L=4096 and +37% at 1292; on the small DiTs the same
absolute cost lands on a base step about 2.7× cheaper, so at stack rank 16 on an H200 it is
+34% at L=4096, +60% at 1292 and +83% at 323. It is paid even with an *empty* stack — in fact
rank 1 is the most expensive configuration, since TensorRT picks a worse tactic below rank 8
— so use `dit_fp16.trt` until an adapter is actually wanted. That matters more on the small
DiTs than on medium.

**Adapters are not portable between the three DiTs**: different depth and width, so a medium
adapter will not load against a small engine.

**sm_90 only**; other architectures build locally in ~5–8 min, since TensorRT bakes the GPU
architecture into the plan. The runtime, the adapter row-norm baking step and the layer maps
all live in
[`optimized/tensorRT/scripts/lora`](https://github.com/Stability-AI/stable-audio-3/tree/main/optimized/tensorRT/scripts/lora)
— this repository holds only the compiled plans.

## Model Details
* **Model type**: `Stable Audio 3` is a latent diffusion model based on a transformer architecture.
* **Language(s)**: English
* **License**: [Stability AI Community License](https://stability.ai/license).
* **Research Paper**: [https://arxiv.org/abs/2605.17991](https://arxiv.org/abs/2605.17991)

We use a publicly available pre-trained T5Gemma model ([t5gemma-b-b-ul2](https://huggingface.co/google/t5gemma-b-b-ul2)) for text conditioning. T5Gemma is redistributed under the [Gemma Terms of Use](LICENSE_GEMMA.md).

## Training dataset

### Datasets Used
Our dataset consists of 1,278,902 audio recordings, where 806,284 recordings are licensed from [AudioSparx](https://www.audiosparx.com/) and a further 472,618 are from [Freesound](https://freesound.org/). 
The Freesound portion consists of recordings licensed under CC-0, CC-BY, or CCSampling+. To ensure no copyrighted content was present in the Freesound data, music recordings were identified
using the PANNs [89] tagger. We flagged audio that activated music-related tags for at least 30s (threshold of 0.15),
that was sent to a trusted content detection company to verify the absence of copyrighted material. All identified copyrighted content was removed. After filtering, the Freesound part includes 266,324 CC-0, 194,840 CC-BY, and 11,454
CC-Sampling+ recordings. The same subset of Freesound audio we used to train Stable Audio Open: https://info.stability.ai/attributions.