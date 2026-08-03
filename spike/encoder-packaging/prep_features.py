"""Torch-side preparation: Fbank features for the fixtures, saved to disk.

The ONNX bench must not import torch, or its load-time and memory numbers
would be the packaged-PyTorch arm's numbers. So the shared front end runs
here, once, and the ONNX process reads the features cold. The exported
artifact is embedding-only — full-chain export fails on STFT complex types —
so a native deployment would carry its own mel-filterbank implementation;
these features stand in for that component.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import speaker_gate
from fixtures import synthetic_clips
from speechbrain.inference.speaker import EncoderClassifier


def main() -> None:
    savedir, out_dir = sys.argv[1], Path(sys.argv[2])
    classifier = EncoderClassifier.from_hparams(
        source=speaker_gate.ECAPA_SOURCE, savedir=savedir, run_opts={"device": "cpu"}
    )
    classifier.eval()
    features = []
    with torch.no_grad():
        for clip in synthetic_clips():
            audio = torch.from_numpy(clip).unsqueeze(0)
            feats = classifier.mods.compute_features(audio)
            feats = classifier.mods.mean_var_norm(feats, torch.ones(1))
            features.append(feats.squeeze(0).numpy())
    np.save(out_dir / "features.npy", np.stack(features))
    # Torch reference at the exact boundary the ONNX artifact reproduces:
    # embedding_model output, before the embedding-space normalizer that
    # `encode_batch` applies afterwards. Comparing ONNX against this isolates
    # conversion error from the norm stage, which is reported separately.
    boundary = []
    with torch.no_grad():
        for feats in features:
            emb = classifier.mods.embedding_model(
                torch.from_numpy(feats).unsqueeze(0), torch.ones(1)
            )
            boundary.append(emb.squeeze().numpy())
    np.save(out_dir / "torch_boundary_embeddings.npy", np.stack(boundary))
    print("features:", np.stack(features).shape, "boundary:", np.stack(boundary).shape)


if __name__ == "__main__":
    main()
