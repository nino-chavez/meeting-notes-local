"""Arm B: the exported ECAPA embedding model under onnxruntime, torch-free.

This process must never import torch — its load time, latency, and memory are
the packaging claim. Features come precomputed from `prep_features.py`; a real
native deployment would compute them with its own small DSP component, and
that exclusion is stated with the results.

Parity is measured at the exact exported boundary (embedding_model output)
and as pairwise cosine-score deltas, because the product's threshold is a
quantile over cosine scores — score stability, not raw vector closeness, is
what decides whether a converted encoder preserves the gate's behavior.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

assert "torch" not in sys.modules


def unit(vectors: np.ndarray) -> np.ndarray:
    return vectors / (np.linalg.norm(vectors, axis=-1, keepdims=True) + 1e-12)


def main() -> None:
    model_path, work_dir = sys.argv[1], Path(sys.argv[2])

    t0 = time.perf_counter()
    import onnxruntime as ort

    import_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    load_s = time.perf_counter() - t1

    features = np.load(work_dir / "features.npy")
    lengths = np.ones(1, dtype=np.float32)

    t2 = time.perf_counter()
    first = session.run(None, {"features": features[0:1], "lengths": lengths})[0]
    first_s = time.perf_counter() - t2

    outputs = [np.squeeze(first)]
    latencies = []
    for row in features[1:]:
        t3 = time.perf_counter()
        out = session.run(None, {"features": row[None, ...], "lengths": lengths})[0]
        latencies.append(time.perf_counter() - t3)
        outputs.append(np.squeeze(out))
    onnx_embeddings = np.stack(outputs)

    torch_boundary = np.load(work_dir / "torch_boundary_embeddings.npy")
    torch_full = np.load(work_dir / "torch_embeddings.npy")

    # Conversion parity at the exported boundary.
    boundary_cos = np.sum(unit(onnx_embeddings) * unit(torch_boundary), axis=-1)
    # Score parity: the gate thresholds cosine scores, so compare the full
    # pairwise score matrix each arm would produce.
    score_onnx = unit(onnx_embeddings) @ unit(onnx_embeddings).T
    score_torch = unit(torch_boundary) @ unit(torch_boundary).T
    # The norm stage encode_batch applies after the exported boundary.
    norm_stage_cos = np.sum(unit(torch_boundary) * unit(torch_full), axis=-1)

    ru = resource.getrusage(resource.RUSAGE_SELF)
    print(
        json.dumps(
            {
                "arm": "onnxruntime",
                "ort_import_s": round(import_s, 3),
                "session_load_s": round(load_s, 3),
                "first_infer_s": round(first_s, 4),
                "warm_infer_mean_s": round(sum(latencies) / len(latencies), 4),
                "warm_infer_max_s": round(max(latencies), 4),
                "peak_rss_mb": round(ru.ru_maxrss / (1024 * 1024), 1),
                "boundary_cosine_min": round(float(boundary_cos.min()), 8),
                "pairwise_score_max_abs_delta": round(
                    float(np.max(np.abs(score_onnx - score_torch))), 8
                ),
                "norm_stage_cosine_min": round(float(norm_stage_cos.min()), 8),
            }
        )
    )


if __name__ == "__main__":
    main()
