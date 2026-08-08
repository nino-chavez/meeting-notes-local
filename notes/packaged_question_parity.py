#!/usr/bin/env python3
"""Does the packaged embedder answer a *question*, having only ever been fed passages?

Every measurement to date sent `worker/embedding.py` 128-word windows. Semantic
search sends it a sentence, alone, in a request of one. That is a new input shape
through a path with two known-silent defaults, and this measures it before the
surface ships rather than after somebody notices bad results.

# The registration, written before the run

**Leg 1 — padding must not reach the pooled vector.** `PackagedTokenizer` calls
`enable_padding`, so a batch pads to its longest member. A question batched with
128-word windows is padded to roughly ten times its own length. Predicted: a
question embedded alone and the same question embedded inside a ragged batch
agree to a cosine of at least 1 - 1e-6.

*Falsifier, and what it would mean:* any question below that threshold says the
attention mask does not fully exclude padding, and that a question's vector then
depends on what it happened to travel with. `corpus_search` sends a question
alone and `fill_vectors` sends windows in batches of 24, so the two would be
computing in different spaces and every ranking would be against a vector the
corpus was not embedded in.

**Leg 2 — a question must rank its own passage first.** For each pair, predicted:
the target scores above the distractor, on all pairs.

*Falsifier:* any inversion. Note what this does **not** measure. These pairs are
written to be clearly separable, and the number that matters for retrieval is the
one from the 200-meeting run — **7 of 10, and 3 of 5 on the questions exact
search cannot answer** (`notes/SEMANTIC_RETRIEVAL.md`). A clean sweep here is not
evidence against that figure and must never be quoted as an accuracy result. It
tests that the packaged path can answer a question at all.

**Leg 3 — the packaged path must agree with the measured one.** The same strings
through `worker.embedding.embed_windows` and through `mlx_minilm.encode`
directly. Predicted: identical to a cosine of at least 1 - 1e-6. This is the leg
that attributes: both run in one process against one set of weights, so a
difference is the worker wrapper and nothing else.

# Running it

    apps/desktop/runtime/python-runtime/bin/python3 notes/packaged_question_parity.py \\
      --model-directory apps/desktop/runtime/models/all-MiniLM-L6-v2 \\
      --receipt notes/packaged_question_receipt.json

The staged runtime's own interpreter, deliberately: a probe run under a
development virtualenv would measure a different set of wheels than the one the
app ships.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

SCHEMA = "packaged-question-parity/1"

# Deliberately hand-written rather than drawn from a corpus. A pair here is one
# passage a question is about and one it is not, and both are ordinary meeting
# speech; drawing them from generated filler would repeat the material the scale
# run already showed this model has no purchase on.
PAIRS = [
    {
        "question": "when does the lease end",
        "target": (
            "so the roof lease runs through the end of March and after that we are "
            "month to month unless somebody signs the extension the landlord sent "
            "over last week which nobody has read yet as far as I can tell"
        ),
        "distractor": (
            "the second round loop is four people now instead of six and we moved "
            "the take home exercise to before the panel because candidates kept "
            "dropping out somewhere between the two"
        ),
    },
    {
        "question": "what did we decide about hiring",
        "target": (
            "we agreed to stop running the take home exercise for senior candidates "
            "and replace it with a paired session because the completion rate was "
            "under half and the people who did finish it all had time nobody else had"
        ),
        "distractor": (
            "the invoice from the vendor is thirty days out and finance wants it "
            "coded against the platform line rather than the general one because of "
            "how the quarter closed"
        ),
    },
    {
        "question": "the conversation about slow page loads",
        "target": (
            "the p95 on the checkout page went from about four hundred milliseconds "
            "to over two seconds after the release and it tracks almost exactly with "
            "the new image pipeline going live on the same day"
        ),
        "distractor": (
            "she is out the first two weeks of next month so anything that needs her "
            "sign off has to land before then or wait which mostly affects the "
            "onboarding work"
        ),
    },
    {
        "question": "who is covering while someone is away",
        "target": (
            "while she is out the first two weeks of next month I will pick up the "
            "onboarding reviews and anything urgent on the platform side goes to the "
            "shared channel rather than to her directly"
        ),
        "distractor": (
            "the roof lease runs through the end of March and after that we are month "
            "to month unless somebody signs the extension the landlord sent over"
        ),
    },
    {
        "question": "the budget argument",
        "target": (
            "finance pushed back on coding it against the platform line because that "
            "budget is already committed through the quarter and they would rather "
            "it sat in general even though nobody thinks that is where it belongs"
        ),
        "distractor": (
            "the checkout p95 went from four hundred milliseconds to over two seconds "
            "after the release which tracks with the new image pipeline going live"
        ),
    },
]


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cosine(left, right) -> float:
    import numpy

    left = numpy.asarray(left, dtype="float64")
    right = numpy.asarray(right, dtype="float64")
    scale = float(numpy.linalg.norm(left) * numpy.linalg.norm(right))
    if scale == 0.0:
        return 0.0
    return float(numpy.dot(left, right) / scale)


def through_worker(encoder, tokenizer, texts: list[str]):
    """Vectors in the order asked, through the packaged worker entry point.

    `embed_windows` keys by digest and collapses identical text, so the caller
    re-orders by digest rather than assuming a list came back.
    """
    import base64

    import numpy
    from worker.embedding import embed_windows

    windows = [
        {"text_sha256": hashlib.sha256(t.encode("utf-8")).hexdigest(), "text": t}
        for t in texts
    ]
    replies = embed_windows(encoder, tokenizer, windows)
    return [
        numpy.frombuffer(base64.b64decode(replies[w["text_sha256"]]), dtype="<f4")
        for w in windows
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    arguments = parser.parse_args()

    from mlx_minilm import encode
    from worker.embedding import load

    encoder, tokenizer = load(arguments.model_directory)

    questions = [pair["question"] for pair in PAIRS]
    passages = [pair["target"] for pair in PAIRS] + [
        pair["distractor"] for pair in PAIRS
    ]

    # Leg 1. Each question alone, then the same questions inside one ragged
    # batch beside every passage — the widest padding a real request could
    # produce, since a batch is capped at 24 and this is 15.
    alone = [through_worker(encoder, tokenizer, [q])[0] for q in questions]
    mixed_texts = questions + passages
    mixed = through_worker(encoder, tokenizer, mixed_texts)
    padding = [
        {
            "question": question,
            "cosine": cosine(alone[index], mixed[index]),
        }
        for index, question in enumerate(questions)
    ]

    # Leg 2. Rank each question against its own pair.
    question_vectors = alone
    target_vectors = [through_worker(encoder, tokenizer, [p["target"]])[0] for p in PAIRS]
    distractor_vectors = [
        through_worker(encoder, tokenizer, [p["distractor"]])[0] for p in PAIRS
    ]
    ranking = []
    for index, pair in enumerate(PAIRS):
        target = cosine(question_vectors[index], target_vectors[index])
        distractor = cosine(question_vectors[index], distractor_vectors[index])
        ranking.append(
            {
                "question": pair["question"],
                "target": target,
                "distractor": distractor,
                "margin": target - distractor,
                "target_wins": target > distractor,
            }
        )

    # Leg 3. The worker wrapper against the forward pass it wraps, same process.
    direct = encode(encoder, tokenizer, questions)
    wrapper = [
        {
            "question": question,
            "cosine": cosine(alone[index], direct[index]),
        }
        for index, question in enumerate(questions)
    ]

    receipt = {
        "schema": SCHEMA,
        "model_directory_name": arguments.model_directory.name,
        "harness_sha256": digest_of(Path(__file__)),
        "embedding_sha256": digest_of(ROOT / "worker" / "embedding.py"),
        "mlx_minilm_sha256": digest_of(HERE / "mlx_minilm.py"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "mlx": metadata.version("mlx"),
            "numpy": metadata.version("numpy"),
            "tokenizers": metadata.version("tokenizers"),
        },
        "padding_independence": {
            "batch_size": len(mixed_texts),
            "worst_cosine": min(row["cosine"] for row in padding),
            "rows": padding,
        },
        "question_ranking": {
            "pairs": len(PAIRS),
            "targets_first": sum(1 for row in ranking if row["target_wins"]),
            "smallest_margin": min(row["margin"] for row in ranking),
            "rows": ranking,
        },
        "wrapper_parity": {
            "worst_cosine": min(row["cosine"] for row in wrapper),
            "rows": wrapper,
        },
    }
    arguments.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt["padding_independence"], indent=2))
    print(json.dumps(receipt["question_ranking"], indent=2))
    print(json.dumps(receipt["wrapper_parity"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
