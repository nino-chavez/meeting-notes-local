"""Deterministic synthetic audio fixtures for the encoder packaging spike.

Every clip is generated from a fixed seed, so both runtime arms see identical
bytes and the comparison measures the conversion, not the input. The clips are
speech-*shaped* — harmonic stacks with formant-like filtering plus shaped
noise — not speech. That boundary is deliberate and stated in RESULTS.md:
numerical parity on synthetic signals bounds conversion error; it does not
certify behavior on real speech, and no private recording may enter this
experiment.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16_000
CLIP_SECONDS = 3.0
N_CLIPS = 12
SEED = 20260803


def synthetic_clips() -> list[np.ndarray]:
    """Twelve 3 s clips at 16 kHz, float32 in [-1, 1), fully seeded."""
    rng = np.random.default_rng(SEED)
    n = int(SAMPLE_RATE * CLIP_SECONDS)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    clips = []
    for _i in range(N_CLIPS):
        f0 = rng.uniform(90.0, 300.0)
        # Harmonic stack with decaying amplitudes and slow vibrato.
        vibrato = 1.0 + 0.01 * np.sin(2 * np.pi * rng.uniform(4.0, 7.0) * t)
        voiced = np.zeros(n)
        for k in range(1, 12):
            phase = rng.uniform(0, 2 * np.pi)
            voiced += (1.0 / k) * np.sin(2 * np.pi * f0 * k * vibrato * t + phase)
        # Two formant-like resonances applied in the frequency domain.
        spectrum = np.fft.rfft(voiced)
        freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
        shape = np.zeros_like(freqs)
        formants = ((rng.uniform(300, 900), 200.0), (rng.uniform(1200, 2600), 350.0))
        for centre, width in formants:
            shape += np.exp(-0.5 * ((freqs - centre) / width) ** 2)
        voiced = np.fft.irfft(spectrum * (0.15 + shape), n)
        # Amplitude envelope with pauses, like phrasing.
        phrase = 2 * np.pi * rng.uniform(0.4, 1.1) * t + rng.uniform(0, 2 * np.pi)
        envelope = np.clip(np.sin(phrase), 0.0, None)
        noise = rng.normal(0.0, 0.02, n)
        clip = voiced * envelope + noise
        clip = clip / (np.max(np.abs(clip)) + 1e-9) * 0.7
        clips.append(clip.astype(np.float32))
    return clips


if __name__ == "__main__":
    for index, clip in enumerate(synthetic_clips()):
        print(index, clip.shape, float(clip.min()), float(clip.max()))
