"""Export the pinned ECAPA encoder to ONNX for the packaging comparison.

Attempts the full audio -> embedding chain first (Fbank + mean-var norm +
ECAPA-TDNN + embedding norm), because a single self-contained artifact is the
strongest packaging story. If STFT export or the runtime rejects it, falls
back to exporting the embedding model alone with Fbank computed outside, and
says so in the metadata — the fallback means a native deployment would need
its own mel-filterbank implementation, which changes the packaging estimate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speaker_gate
from speechbrain.inference.speaker import EncoderClassifier


class FullChain(torch.nn.Module):
    """audio (1, samples) float32 -> embedding (1, 192)."""

    def __init__(self, classifier: EncoderClassifier):
        super().__init__()
        self.compute_features = classifier.mods.compute_features
        self.mean_var_norm = classifier.mods.mean_var_norm
        self.embedding_model = classifier.mods.embedding_model
        self.mean_var_norm_emb = classifier.hparams.mean_var_norm_emb

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        lengths = torch.ones(audio.shape[0], device=audio.device)
        feats = self.compute_features(audio)
        feats = self.mean_var_norm(feats, lengths)
        emb = self.embedding_model(feats, lengths)
        emb = self.mean_var_norm_emb(emb, torch.ones(emb.shape[0], device=emb.device))
        return emb.squeeze(1)


def main() -> None:
    savedir, out_path = sys.argv[1], Path(sys.argv[2])
    classifier = EncoderClassifier.from_hparams(
        source=speaker_gate.ECAPA_SOURCE, savedir=savedir, run_opts={"device": "cpu"}
    )
    classifier.eval()
    example = torch.zeros(1, 48_000, dtype=torch.float32)
    meta = {"encoder_fingerprint": speaker_gate.encoder_fingerprint(savedir)}

    try:
        chain = FullChain(classifier)
        with torch.no_grad():
            reference = chain(example)
        torch.onnx.export(
            chain,
            (example,),
            str(out_path),
            input_names=["audio"],
            output_names=["embedding"],
            dynamic_axes={"audio": {1: "samples"}},
            opset_version=17,
            dynamo=False,
        )
        meta["scope"] = "full-chain"
        meta["reference_dim"] = int(reference.shape[-1])
    except Exception as full_error:
        embedding_model = classifier.mods.embedding_model
        feats = classifier.mods.compute_features(example)
        torch.onnx.export(
            embedding_model,
            (feats, torch.ones(1)),
            str(out_path),
            input_names=["features", "lengths"],
            output_names=["embedding"],
            dynamic_axes={"features": {1: "frames"}},
            opset_version=17,
            dynamo=False,
        )
        meta["scope"] = "embedding-only"
        meta["full_chain_error"] = f"{type(full_error).__name__}: {full_error}"[:400]

    meta["onnx_bytes"] = out_path.stat().st_size
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
