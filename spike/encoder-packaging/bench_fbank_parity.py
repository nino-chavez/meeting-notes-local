"""Admission check 1: does the torch-free front end preserve the gate's scores?

Runs torch-free, like `bench_onnx.py`, because a front end that only reproduces features
inside a torch process proves nothing about a native deployment. Reads the torch reference
features and boundary embeddings that `prep_features.py` wrote, recomputes the same features
with `native_fbank.py`, and pushes both through the exported ONNX embedding model.

Three embedding sets are compared, because "parity" hides two different errors:

  native  = native features -> ONNX      (front end + conversion, the deployable path)
  bridged = torch features  -> ONNX      (conversion only, the existing `bench_onnx.py` arm)
  torch   = torch features  -> torch     (the reference, pre-embedding-norm boundary)

`native vs bridged` isolates this module's contribution with the encoder held constant.
`native vs torch` is what a native deployment would actually diverge by. Both are reported.

The deciding number is the pairwise cosine score matrix delta, not raw feature equality: the
product thresholds a quantile over cosine scores, so score stability is what determines
whether swapping the front end moves the gate's decisions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import synthetic_clips
from native_fbank import fbank_features

assert "torch" not in sys.modules


def unit(vectors: np.ndarray) -> np.ndarray:
    # float64 deliberately: in float32 the cosines saturate one ULP below 1.0 and the
    # measurement reports its own precision instead of the arms' disagreement.
    wide = vectors.astype(np.float64)
    return wide / (np.linalg.norm(wide, axis=-1, keepdims=True) + 1e-12)


def score_matrix(embeddings: np.ndarray) -> np.ndarray:
    normed = unit(embeddings)
    return normed @ normed.T


def embed(session, features: np.ndarray) -> np.ndarray:
    lengths = np.ones(1, dtype=np.float32)
    rows = [
        session.run(None, {"features": row[None, ...], "lengths": lengths})[0]
        for row in features
    ]
    return np.stack([np.squeeze(row) for row in rows])


def main() -> None:
    model_path, work_dir = sys.argv[1], Path(sys.argv[2])

    torch_features = np.load(work_dir / "features.npy")
    torch_boundary = np.load(work_dir / "torch_boundary_embeddings.npy")
    native_features = np.stack([fbank_features(clip) for clip in synthetic_clips()])

    # A native front end that framed differently would still run, because the export declares
    # a dynamic frame axis — so shape equality has to be asserted, not assumed.
    assert native_features.shape == torch_features.shape, (
        f"shape mismatch: native {native_features.shape} vs torch {torch_features.shape}"
    )
    assert native_features.dtype == np.float32

    reference = torch_features.astype(np.float64)
    diff = np.abs(native_features.astype(np.float64) - reference)
    feature_max_abs = float(diff.max())
    # Pointwise relative diff is reported with the reference cell that produced it, because
    # these features are mean-subtracted: a cell near zero turns a tiny absolute difference
    # into a large ratio, which says nothing about the front end. The span-relative figure is
    # the one to read.
    pointwise = diff / np.maximum(np.abs(reference), 1e-12)
    worst = np.unravel_index(int(pointwise.argmax()), pointwise.shape)
    feature_span = float(reference.max() - reference.min())

    import onnxruntime as ort

    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    native_emb = embed(session, native_features)
    bridged_emb = embed(session, torch_features)

    native_vs_torch = np.sum(unit(native_emb) * unit(torch_boundary), axis=-1)
    native_vs_bridged = np.sum(unit(native_emb) * unit(bridged_emb), axis=-1)

    scores_native = score_matrix(native_emb)
    scores_bridged = score_matrix(bridged_emb)
    scores_torch = score_matrix(torch_boundary)

    print(
        json.dumps(
            {
                "clips": int(native_features.shape[0]),
                "frames_per_clip": int(native_features.shape[1]),
                "n_mels": int(native_features.shape[2]),
                "feature_max_abs_diff": round(feature_max_abs, 9),
                "feature_max_abs_diff_over_span": round(feature_max_abs / feature_span, 12),
                "feature_value_span": round(feature_span, 4),
                "feature_max_pointwise_rel_diff": round(float(pointwise.max()), 6),
                "feature_max_pointwise_rel_reference_value": round(float(reference[worst]), 9),
                # Reported as the deviation from 1, since the cosines themselves round to
                # 1.0 well before the interesting digits.
                "max_one_minus_cosine_native_vs_torch": float(
                    f"{1.0 - float(native_vs_torch.min()):.3e}"
                ),
                "max_one_minus_cosine_native_vs_bridged": float(
                    f"{1.0 - float(native_vs_bridged.min()):.3e}"
                ),
                "score_delta_native_vs_bridged": round(
                    float(np.max(np.abs(scores_native - scores_bridged))), 9
                ),
                "score_delta_native_vs_torch": round(
                    float(np.max(np.abs(scores_native - scores_torch))), 9
                ),
                "score_delta_bridged_vs_torch": round(
                    float(np.max(np.abs(scores_bridged - scores_torch))), 9
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
