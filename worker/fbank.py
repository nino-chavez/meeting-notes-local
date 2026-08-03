"""Torch-free Fbank front end for the preferred (not admitted) ONNX speaker encoder.

The exported ONNX artifact is embedding-only — full-chain export fails on STFT complex
types (see `spike/encoder-packaging/export_onnx.py`) — so the packaged runtime has to
reproduce SpeechBrain's `compute_features` (Fbank) and `mean_var_norm` (InputNormalization)
itself. This module is that reproduction in numpy, on dependencies the runtime already
packages. Its parity against the torch reference is measured and recorded in
`spike/encoder-packaging/FBANK-PARITY.md`; this module certifies nothing by itself, and
nothing about its presence admits an encoder into the product runtime.

Every constant below is read off the pinned snapshot rather than recalled: `hyperparams.yaml`
at `~/.cache/speaker-gate` sets only `n_mels: 80` for `speechbrain.lobes.features.Fbank` and
`norm_type: sentence`, `std_norm: False` for `InputNormalization`, so all remaining values are
the library defaults for speechbrain 1.1.0.

Stage-by-stage mirror (line numbers are speechbrain 1.1.0 as installed in `.venv`):

  `lobes/features.py:147-169`     Fbank.forward — STFT, then spectral_magnitude, then
                                  Filterbank; deltas and context both default False.
  `processing/features.py:131-139` win/hop in ms -> samples via int(round(sr/1000 * ms)),
                                  and the Hamming window, torch's *periodic* variant.
  `processing/features.py:159-170` torch.stft: center=True, pad_mode="constant" (zeros, not
                                  librosa's reflect), normalized=False, onesided=True.
  `processing/features.py:341-378` spectral_magnitude with its default power=1, which returns
                                  re^2 + im^2 — the power spectrum, despite the name. The eps
                                  branch is skipped because it applies only when power < 1.
  `processing/features.py:487-510` mel grid: n_mels+2 points linear in mel, converted back to
                                  Hz; band[i] = hz[i+1]-hz[i], f_central[i] = hz[i+1]; the
                                  frequency axis is linspace(0, sr//2, n_fft//2+1).
  `processing/features.py:588-618` mel scale: 2595*log10(1+hz/700), inverse 700*(10^(m/2595)-1).
  `processing/features.py:620-647` triangular filters: *symmetric* half-width `band` on both
                                  sides of `f_central`, analytic peak 1.0, no area
                                  normalization. 20 of the 80 bands are narrower than the
                                  40 Hz FFT bin spacing, so sampled peaks run 0.19 to 0.9986;
                                  that undersampling is the encoder's training-time input and
                                  must be reproduced, not corrected.
  `processing/features.py:574`     spectrogram @ fbank_matrix.
  `processing/features.py:736-759` amplitude -> dB: 10*log10(clamp(x, amin)) minus a
                                  db_multiplier term that is exactly 0 for ref_value=1.0, then
                                  a per-utterance floor at (max over time and mel) - top_db.
  `processing/features.py:1436-1455` InputNormalization, norm_type="sentence" with
                                  std_norm=False: std collapses to ones, so the stage reduces
                                  to subtracting the per-mel mean over time.

Arithmetic runs in float64 and is cast to float32 on return. SpeechBrain computes the same
chain in float32 (`fwd_default_precision` in `lobes/features.py:147`), so the residual the
parity bench reports is dominated by torch's single-precision rounding, not by a different
pipeline. A native implementation choosing f32 throughout would sit on the other side of that
same gap.
"""

from __future__ import annotations

import math

import numpy as np

SAMPLE_RATE = 16_000
N_FFT = 400
WIN_LENGTH_MS = 25.0
HOP_LENGTH_MS = 10.0
N_MELS = 80
F_MIN = 0.0
F_MAX = float(SAMPLE_RATE // 2)
AMIN = 1e-10
REF_VALUE = 1.0
TOP_DB = 80.0
# Filterbank sets multiplier=10 when power_spectrogram == 2, which is its default.
DB_MULTIPLIER = 10.0

WIN_LENGTH = round((SAMPLE_RATE / 1000.0) * WIN_LENGTH_MS)
HOP_LENGTH = round((SAMPLE_RATE / 1000.0) * HOP_LENGTH_MS)
N_STFT = N_FFT // 2 + 1


def hamming_window(length: int = WIN_LENGTH) -> np.ndarray:
    """Torch's *periodic* Hamming window: 0.54 - 0.46*cos(2*pi*n/length).

    `np.hamming` is the symmetric variant (divisor length-1) and is the wrong window here.
    """
    n = np.arange(length, dtype=np.float64)
    return 0.54 - 0.46 * np.cos(2.0 * np.pi * n / length)


def _to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def _to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def mel_filterbank() -> np.ndarray:
    """(n_stft, n_mels) triangular filters, symmetric in Hz and not area-normalized."""
    mel = np.linspace(_to_mel(F_MIN), _to_mel(F_MAX), N_MELS + 2, dtype=np.float64)
    hz = _to_hz(mel)
    band = (hz[1:] - hz[:-1])[:-1]
    f_central = hz[1:-1]
    all_freqs = np.linspace(0.0, float(SAMPLE_RATE // 2), N_STFT, dtype=np.float64)
    slope = (all_freqs[None, :] - f_central[:, None]) / band[:, None]
    return np.maximum(0.0, np.minimum(slope + 1.0, -slope + 1.0)).T


def stft_power(audio: np.ndarray) -> np.ndarray:
    """(frames, n_stft) power spectrum, matching torch.stft(center=True, pad_mode='constant')."""
    signal = np.asarray(audio, dtype=np.float64).reshape(-1)
    padded = np.pad(signal, N_FFT // 2, mode="constant")
    n_frames = 1 + (len(padded) - N_FFT) // HOP_LENGTH
    starts = np.arange(n_frames) * HOP_LENGTH
    frames = padded[starts[:, None] + np.arange(N_FFT)[None, :]]
    spectrum = np.fft.rfft(frames * hamming_window()[None, :], n=N_FFT, axis=-1)
    return spectrum.real**2 + spectrum.imag**2


def _amplitude_to_db(linear: np.ndarray) -> np.ndarray:
    db = DB_MULTIPLIER * np.log10(np.maximum(linear, AMIN))
    db -= DB_MULTIPLIER * math.log10(max(AMIN, REF_VALUE))
    # Floor is taken over the whole utterance — time and mel jointly — not per frame.
    return np.maximum(db, db.max() - TOP_DB)


def fbank_features(audio: np.ndarray) -> np.ndarray:
    """Normalized log-mel features for one utterance: (frames, 80) float32.

    Equivalent to `compute_features(audio)` followed by `mean_var_norm(feats, ones(1))` on the
    pinned ECAPA snapshot, for a single unpadded utterance.
    """
    log_mel = _amplitude_to_db(stft_power(audio) @ mel_filterbank())
    # norm_type="sentence" with std_norm=False: std is ones, so only the mean is removed.
    normalized = log_mel - log_mel.mean(axis=0, keepdims=True)
    return normalized.astype(np.float32)
