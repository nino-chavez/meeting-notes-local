#!/usr/bin/env python3
"""Measure peak memory of the ONNX encoder candidate co-resident with MLX transcription.

Run with the packaged interpreter against a built bundle's Resources root:

    <Resources>/python-runtime/bin/python3.12 -E -s -B \\
        scripts/measure-encoder-beside-mlx.py <Resources>

Admission check 2 requires peak memory acceptable beside MLX transcription — a
number no research-venv harness can give, because it depends on the packaged
runtime's own libraries. This runs both stacks in one process the way the
worker would: the encoder session is created first and stays alive while MLX
transcribes, then embeddings are computed for every transcribed span through
the packaged torch-free front end. The audio is a seeded synthetic harmonic
stack — speech-shaped, but no recorded speech and no private content — so the
transcription text is meaningless; the receipt records only counts, timings,
and memory, never content. Nothing measured here admits an encoder.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path


def maxrss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024), 1)


def synthetic_speech(seconds: float, rate: int):
    """Deterministic speech-shaped signal: pitch-modulated harmonics under a syllabic gate."""
    import numpy as np

    rng = np.random.default_rng(20260803)
    t = np.arange(int(seconds * rate), dtype=np.float64) / rate
    f0 = 120.0 + 30.0 * np.sin(2 * np.pi * 0.31 * t) + 8.0 * rng.standard_normal()
    phase = 2 * np.pi * np.cumsum(f0) / rate
    voice = sum((0.5 / h) * np.sin(h * phase) for h in range(1, 9))
    envelope = 0.25 * (0.55 + 0.45 * np.sin(2 * np.pi * 2.9 * t))
    syllables = (np.sin(2 * np.pi * 4.1 * t) > -0.7).astype(np.float64)
    return (voice * envelope * syllables).astype(np.float32)


def main() -> int:
    resources = Path(sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(resources / "spike"))
    sys.path.insert(0, str(resources))

    receipt: dict = {"schema": "encoder-beside-mlx/1"}
    t0 = time.perf_counter()
    import numpy as np
    import onnxruntime

    from worker.fbank import fbank_features
    from worker.main import load_manifest

    manifest = load_manifest(resources / "app-runtime.json")
    encoder_path = manifest["encoder"]["path"]
    if encoder_path == "encoder-unavailable.identity":
        print("this bundle packages no encoder candidate", file=sys.stderr)
        return 1
    receipt["rss_mb_after_imports"] = maxrss_mb()

    session = onnxruntime.InferenceSession(
        str(resources / encoder_path), providers=["CPUExecutionProvider"]
    )
    receipt["encoder_session_seconds"] = round(time.perf_counter() - t0, 3)
    receipt["rss_mb_after_encoder_session"] = maxrss_mb()

    rate = 16_000
    audio = synthetic_speech(60.0, rate)

    from dual_capture import transcribe  # the app's own MLX call shape

    model_dir = resources / "models/whisper-large-v3-turbo"
    t1 = time.perf_counter()
    segments = transcribe(audio, str(model_dir), "en")
    receipt["transcription_seconds"] = round(time.perf_counter() - t1, 3)
    receipt["segment_count"] = len(segments)
    receipt["rss_mb_after_transcription"] = maxrss_mb()

    t2 = time.perf_counter()
    embeddings = []
    spans = [(s["start"], s["end"]) for s in segments] or [(0.0, 3.0)]
    for start, end in spans:
        clip = audio[int(start * rate) : int(end * rate)]
        if len(clip) < rate // 2:
            continue
        features = fbank_features(clip)
        embeddings.append(
            session.run(
                None,
                {
                    "features": features[np.newaxis, ...],
                    "lengths": np.ones(1, dtype=np.float32),
                },
            )[0].reshape(-1)
        )
    receipt["embedding_seconds"] = round(time.perf_counter() - t2, 3)
    receipt["embedding_count"] = len(embeddings)
    receipt["embedding_dim"] = int(embeddings[0].shape[-1]) if embeddings else 0
    receipt["rss_mb_peak"] = maxrss_mb()
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
