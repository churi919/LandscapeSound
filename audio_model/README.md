# Local Stable Audio 3 runtime

This directory is independent of the landscape-analysis `.venv`. It contains the official native Windows LiteRT/TFLite runtime, downloaded optimized weights and a reproducible candidate-generation wrapper.

- Official code: https://github.com/Stability-AI/stable-audio-3
- Code revision: `77e0398c26f7d22d801ec1bb036307e8b231f741`
- Public optimized model: https://huggingface.co/stabilityai/stable-audio-3-optimized
- Model revision: `08b17423649b5714b22eab20f96bf00751f2358a`
- Runtime: Python 3.11.15, LiteRT 2.3.0, XNNPACK CPU, 8 threads, 8 sampling steps.
- Small-SFX: DiT `sm-sfx/w8a8`, decoder `SAME-S/w8a8`. The shared encoder plus these weights total 1,192,498,584 bytes.
- Medium: DiT `medium/w8a8`, decoder `SAME-L/w8a8`. Its additional weights total 2,183,090,096 bytes. Exact per-file hashes are in `weights_manifest.json`.

All model inference is local. This route uses CPU rather than assuming CUDA/Flash Attention support on this Windows installation. It leaves the existing PyTorch/Transformers application environment unchanged. Model/cache/temp directories are under this folder on D:.

## Generate or verify the saved candidates

From the project root:

```powershell
.\audio_model\.venv\Scripts\python.exe audio_model\generate_candidates.py --only all
```

Existing verified outputs are reused. This command does not silently replace existing candidates. Individual IDs may be passed to `--only`, including `trees_soft_20261026`, `water_ripples_20261028`, `trees_soft_cfg2_20261026`, `water_ripples_cfg2_20261028`, `medium_trees_20261026`, or `medium_water_20261028`. Use `--only model_comparison` for both Medium candidates.

Raw generated stereo WAVs are in `assets/generated_raw/`. `assets/generated_raw/manifest.json` and `outputs/audio_model_run/*.json` record prompts, seeds, CFG, negative prompts, durations, sample rates, WAV hashes, per-stage timings and observed process-tree peak memory. The two CFG=2 cases are same-seed comparisons; CFG=1 cases intentionally do not use a negative branch.

The original 20-second smoke output was recovered after a wrapper log-decoding error without re-generating the WAV. Its runtime RSS measurement is unavailable and recorded as null. All later candidates have full monitoring. Optional OpenVINO/NPU plugin warnings did not block the official CPU backend; the WAVs were verified as finite, non-silent 44.1kHz stereo PCM.

## Actual run on this computer

Six Small-SFX formal candidates, each 30 seconds, were generated in 5.09–7.72 seconds of official CLI runtime (5.56–8.20 seconds including process startup). Process-tree RSS peaks were 1,712.6–1,806.3 MiB.

Two Medium comparison candidates use the same prompts and seeds as the first Small-SFX pair, with 30 seconds, 8 steps, CFG=1 and no active negative branch. The wind/leaves candidate took 16.86 seconds of CLI runtime (17.228 seconds including startup), with 2,085.3 MiB process-tree peak RSS. The lake-water candidate took 16.04 seconds (16.561 seconds including startup), with 2,018.8 MiB peak RSS. Both are finite, non-silent 44.1kHz stereo PCM WAVs with no clipped samples. These timings measure the fixed prompts/precision/8-thread configuration on this computer, not a latency guarantee.

The legacy candidate wrapper retains its original 5 GiB available-RAM preflight. The scene-specific upload wrapper uses a measured local budget of 4.25 GiB: 2.5 GiB inference allowance + 1.25 GiB Windows reserve + 0.5 GiB margin. This is based on the fixed Medium/w8a8/SAME-L runtime's approximately 2.0 GiB process-tree peaks, not an allowance for other models. It serializes all scene model workers and stops only its own generator if available memory stays below 1.25 GiB. The new shallow-stream upload started with 4.542 GiB available, measured a 2,017.7 MiB process-tree peak and kept at least 2.806 GiB system RAM available. Each new generation records its preflight budget and minimum headroom.

These files are AI-generated sound effects. They are not field recordings and are not recordings of the landscape photographs. No subjective listening judgement, absence of incidental voices/birds/music, or preference over recorded sounds is established by the numerical checks.

## Licenses and downloads

The optimized model repository was publicly downloadable without login at the recorded revision. Downloads used explicit `token=False`; no account credentials were read and no gated agreement was accepted. The model remains subject to its published Stable Audio Community License and included Gemma terms, saved in `model_LICENSE.md` and `model_LICENSE_GEMMA.md`. Public availability does not remove these conditions. Official runtime code has its own repository license.

`download_weights.py` downloads the pinned Small-SFX weights and exposes cached files at the official runtime's expected locations via hardlinks or copies. Pass `--include-medium` to include the Medium and SAME-L weights. The shared encoder is reused. `requirements-lock.txt` records the installed standalone environment; no package was installed into the main application environment.
