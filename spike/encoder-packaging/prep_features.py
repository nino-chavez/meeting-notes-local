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


def torch_features(classifier: EncoderClassifier, clip) -> np.ndarray:
    audio = torch.from_numpy(clip).unsqueeze(0)
    feats = classifier.mods.compute_features(audio)
    feats = classifier.mods.mean_var_norm(feats, torch.ones(1))
    return feats.squeeze(0).numpy()


def torch_boundary(classifier: EncoderClassifier, feats) -> np.ndarray:
    emb = classifier.mods.embedding_model(torch.from_numpy(feats).unsqueeze(0), torch.ones(1))
    return emb.squeeze().numpy()


def main() -> None:
    savedir, out_dir = sys.argv[1], Path(sys.argv[2])
    classifier = EncoderClassifier.from_hparams(
        source=speaker_gate.ECAPA_SOURCE, savedir=savedir, run_opts={"device": "cpu"}
    )
    classifier.eval()
    features = []
    with torch.no_grad():
        for clip in synthetic_clips():
            features.append(torch_features(classifier, clip))
    np.save(out_dir / "features.npy", np.stack(features))
    # Torch reference at the exact boundary the ONNX artifact reproduces:
    # embedding_model output, before the embedding-space normalizer that
    # `encode_batch` applies afterwards. Comparing ONNX against this isolates
    # conversion error from the norm stage, which is reported separately.
    boundary = []
    with torch.no_grad():
        for feats in features:
            boundary.append(torch_boundary(classifier, feats))
    np.save(out_dir / "torch_boundary_embeddings.npy", np.stack(boundary))
    print("features:", np.stack(features).shape, "boundary:", np.stack(boundary).shape)

    # Optional third argument: the registered LibriSpeech fixtures directory.
    # Clips have unequal lengths, so per-clip features go into one npz keyed
    # by fixture name; boundary embeddings stack at a fixed 192.
    if len(sys.argv) > 3:
        from public_fixtures import load_public_clips

        clips = load_public_clips(Path(sys.argv[3]))
        public_features = {}
        public_boundary = []
        with torch.no_grad():
            for name, audio in clips:
                feats = torch_features(classifier, audio)
                public_features[name] = feats
                public_boundary.append(torch_boundary(classifier, feats))
        np.savez(out_dir / "features_public.npz", **public_features)
        np.save(out_dir / "torch_boundary_public.npy", np.stack(public_boundary))
        print("public:", len(clips), "clips, boundary:", np.stack(public_boundary).shape)


if __name__ == "__main__":
    main()
