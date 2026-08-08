#!/usr/bin/env python3
"""Does the MLX forward pass compute the same thing the probe measured?

The check `SEMANTIC_RETRIEVAL.md` registered before the implementation existed:

> If the MLX forward pass reproduces these ten rankings but its margins on the
> hard five differ by more than 0.01, the two implementations are not computing
> the same thing and the difference must be found before either is trusted — the
> rankings agreeing is a weaker check when three of them are decided by 0.013.

So this compares both, against the committed receipts rather than against a
freshly computed reference — a run that regenerated its own baseline could not
fail.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from mlx_minilm import MiniLMEncoder, encode, load_tokenizer
from semantic_retrieval_probe import PIN, _sha256, load_fixtures, meeting_text

VERIFY_SCHEMA = "mlx-minilm-verification/1"

# Registered in `SEMANTIC_RETRIEVAL.md` before this file existed.
MARGIN_TOLERANCE = 0.01


def cosine(left, right) -> float:
    import numpy

    left = numpy.asarray(left, dtype=numpy.float64)
    right = numpy.asarray(right, dtype=numpy.float64)
    return float(
        numpy.dot(left, right) / (numpy.linalg.norm(left) * numpy.linalg.norm(right))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    arguments = parser.parse_args()

    here = Path(__file__).resolve().parent
    reference = json.loads((here / "semantic_retrieval_receipt.json").read_text())
    if reference["fixtures_sha256"] != _sha256(
        (here / "semantic_retrieval_fixtures.json").read_bytes()
    ):
        raise SystemExit("the fixtures moved since the reference run; comparison is void")

    document = load_fixtures()
    meetings = document["meetings"]
    questions = document["questions"]

    encoder = MiniLMEncoder(arguments.model_directory)
    tokenizer = load_tokenizer(arguments.model_directory)

    started = time.monotonic()
    corpus = encode(encoder, tokenizer, [meeting_text(m) for m in meetings])
    corpus_elapsed_s = round(time.monotonic() - started, 6)
    vectors = {m["id"]: corpus[index] for index, m in enumerate(meetings)}

    rows = []
    worst_margin_delta = 0.0
    ranking_disagreements = 0
    for question, reference_row in zip(questions, reference["rows"]):
        asked = encode(encoder, tokenizer, [question["question"]])[0]
        ranked = sorted(
            ((cosine(asked, vector), identifier) for identifier, vector in vectors.items()),
            reverse=True,
        )
        top1 = ranked[0][1]
        margin = round(ranked[0][0] - ranked[1][0], 6)
        margin_delta = abs(margin - reference_row["model_margin"])
        agrees = top1 == reference_row["model_top1"]
        ranking_disagreements += 0 if agrees else 1
        worst_margin_delta = max(worst_margin_delta, margin_delta)
        rows.append(
            {
                "question_sha256": reference_row["question_sha256"],
                "exact_helps": question["exact_helps"],
                "reference_top1": reference_row["model_top1"],
                "mlx_top1": top1,
                "ranking_agrees": agrees,
                "reference_margin": reference_row["model_margin"],
                "mlx_margin": margin,
                "margin_delta": round(margin_delta, 6),
            }
        )

    passed = ranking_disagreements == 0 and worst_margin_delta <= MARGIN_TOLERANCE
    receipt = {
        "schema": VERIFY_SCHEMA,
        "verdict": "agrees" if passed else "differs",
        "margin_tolerance": MARGIN_TOLERANCE,
        "worst_margin_delta": round(worst_margin_delta, 6),
        "ranking_disagreements": ranking_disagreements,
        "reference_receipt_sha256": _sha256(
            (here / "semantic_retrieval_receipt.json").read_bytes()
        ),
        "implementation_sha256": _sha256((here / "mlx_minilm.py").read_bytes()),
        "harness_sha256": _sha256(Path(__file__).read_bytes()),
        "model_weights_sha256": PIN["model"]["expected_model_safetensors_sha256"],
        "corpus_embed_elapsed_s": corpus_elapsed_s,
        "rows": rows,
    }
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
    if arguments.receipt:
        arguments.receipt.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
