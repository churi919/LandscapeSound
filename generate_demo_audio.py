"""Generate original procedural mono sound placeholders; no models or recordings.

The files test spatialisation, not acoustic realism or the presence of real sound.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import wave

import numpy as np


SAMPLE_RATE = 22050


def _coloured_noise(rng: np.random.Generator, n: int, sr: int,
                    low: float, high: float, slope: float = 0.0) -> np.ndarray:
    freq = np.fft.rfftfreq(n, 1 / sr)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    band = (1 - np.exp(-((freq / max(low, 1)) ** 3))) * np.exp(-((freq / high) ** 4))
    band *= np.maximum(freq, 30) ** (-slope / 2)
    signal = np.fft.irfft(spectrum * band, n)
    return signal / max(float(np.std(signal)), 1e-9)


def _write_wav(path: Path, signal: np.ndarray, sr: int) -> dict:
    signal = np.nan_to_num(signal).astype(np.float64)
    signal -= np.mean(signal)
    signal *= 0.13 / max(float(np.sqrt(np.mean(signal ** 2))), 1e-8)
    peak = float(np.max(np.abs(signal)))
    if peak > 0.70:
        signal *= 0.70 / peak
    # Brief fades also keep a standalone WAV preview free of start/stop clicks.
    fade = min(int(sr * 0.035), len(signal) // 3)
    ramp = np.sin(np.linspace(0, np.pi / 2, fade)) ** 2
    signal[:fade] *= ramp
    signal[-fade:] *= ramp[::-1]
    pcm = np.round(np.clip(signal, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sr)
        out.writeframes(pcm.tobytes())
    return {'file': path.name, 'sample_rate': sr, 'channels': 1,
            'duration_seconds': round(len(signal) / sr, 3),
            'rms': round(float(np.sqrt(np.mean(signal ** 2))), 5),
            'peak': round(float(np.max(np.abs(signal))), 5),
            'origin': 'original procedural synthesis; not recording or AI generation'}


def generate_assets(out_dir: str | Path = 'assets', duration: float = 12.0,
                    sample_rate: int = SAMPLE_RATE) -> list[dict]:
    """Write reproducible trees/water/bird WAV files and their provenance."""
    if not 1 <= duration <= 120 or not 8000 <= sample_rate <= 96000:
        raise ValueError('duration must be 1–120 s and sample_rate 8000–96000 Hz')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261025)
    n = round(duration * sample_rate)
    t = np.arange(n) / sample_rate
    wind = _coloured_noise(rng, n, sample_rate, 70, 3600, 1.1)
    rustle = _coloured_noise(rng, n, sample_rate, 650, 6500, 0.2)
    gust = 0.48 + 0.22 * np.sin(2 * np.pi * t / duration * 2 + 0.5)
    gust += 0.10 * np.sin(2 * np.pi * t / duration * 5)
    trees = wind * gust + rustle * (0.10 + 0.09 * np.sin(2 * np.pi * t * 1.5) ** 2)

    wash = _coloured_noise(rng, n, sample_rate, 100, 5700, 0.4)
    water = wash * (0.30 + 0.09 * np.sin(2 * np.pi * t / duration * 4))
    # Short descending resonances suggest droplets without using a real recording.
    for onset in rng.uniform(0.15, duration - 0.20, max(6, int(duration * 5))):
        length = min(int(sample_rate * 0.16), n - int(onset * sample_rate))
        local = np.arange(length) / sample_rate
        freq = rng.uniform(800, 2600)
        chirp = np.sin(2 * np.pi * (freq * local - freq * local ** 2 * 1.5))
        envelope = (1 - np.exp(-local * 900)) * np.exp(-local * 30)
        start = int(onset * sample_rate)
        water[start:start + length] += chirp * envelope * rng.uniform(0.05, 0.18)

    bird = np.zeros(n)
    for onset in np.arange(0.8, duration - 0.5, 2.5):
        for offset in (0.0, 0.24, 0.55):
            length = int(sample_rate * 0.20)
            local = np.arange(length) / sample_rate
            chirp = np.sin(2 * np.pi * (2200 * local + 3800 * local ** 2))
            envelope = np.sin(np.linspace(0, np.pi, length)) ** 2
            start = int((onset + offset) * sample_rate)
            if start + length <= n:
                bird[start:start + length] += 0.4 * chirp * envelope
    records = [_write_wav(out_dir / f'{name}.wav', signal, sample_rate)
               for name, signal in [('trees', trees), ('water', water), ('bird', bird)]]
    manifest = {'provenance': 'Original procedural placeholder sound effects',
                'not_site_recording': True, 'not_ai_generated': True,
                'bird_requires_manual_confirmation': True, 'files': records}
    (out_dir / 'audio_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=Path(__file__).parent / 'assets')
    parser.add_argument('--duration', type=float, default=12.0)
    args = parser.parse_args()
    print(json.dumps(generate_assets(args.out_dir, args.duration), ensure_ascii=False, indent=2))
