"""Arm A: the pinned SpeechBrain/PyTorch ECAPA path, measured as packaged.

Run cold (fresh process) for load timing, then warm for per-segment latency.
Prints a small JSON blob to stdout; RESULTS.md is the human record.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fixtures import synthetic_clips


def peak_rss_mb() -> float:
    # ru_maxrss is bytes on macOS.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def main() -> None:
    t0 = time.perf_counter()
    import torch  # noqa: F401

    torch_import_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    import speaker_gate

    embed = speaker_gate.load_encoder(sys.argv[1])
    load_s = time.perf_counter() - t1

    clips = synthetic_clips()
    t2 = time.perf_counter()
    first = embed(clips[0])
    first_embed_s = time.perf_counter() - t2

    latencies = []
    embeddings = [first]
    for clip in clips[1:]:
        t3 = time.perf_counter()
        embeddings.append(embed(clip))
        latencies.append(time.perf_counter() - t3)

    fingerprint = speaker_gate.encoder_fingerprint(sys.argv[1])
    out = {
        "arm": "torch-speechbrain",
        "torch_import_s": round(torch_import_s, 3),
        "encoder_load_s": round(load_s, 3),
        "first_embed_s": round(first_embed_s, 3),
        "warm_embed_mean_s": round(sum(latencies) / len(latencies), 4),
        "warm_embed_max_s": round(max(latencies), 4),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "embedding_dim": len(first),
        "encoder_fingerprint": fingerprint,
    }
    print(json.dumps(out))
    import numpy as np

    np.save(sys.argv[2], np.stack(embeddings))


if __name__ == "__main__":
    main()
