#!/usr/bin/env python3
"""Does a small local embedding model retrieve the meeting a person meant?

Research code. It reads `semantic_retrieval_fixtures.json` and nothing else — no
meeting store, no Preview datum, no product record, and no artifact except a
content-free receipt the caller asks for.

Registered in `SEMANTIC_RETRIEVAL.md` before anything was downloaded. Read the
prediction there before reading a number here.

# Two arms, and the control is the point

`control` is a word-overlap ranker with no model in it: shared words between the
question and the transcript, zero overlap meaning no answer. It exists because
the fixtures were once passable by exactly that — 8 of 10 before they were
hardened — and a probe that cannot re-run its own degenerate baseline has to take
on trust that the suite is still hard.

`model` embeds each meeting once and each question once, and ranks by cosine
similarity. One vector per meeting, over the concatenation of its retained turns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import time
from pathlib import Path

PROBE_SCHEMA = "semantic-retrieval/1"
FIXTURES_SCHEMA = "semantic-retrieval-fixtures/1"

PIN = {
    "schema": "semantic-retrieval-runtime/1",
    "role": "research-only",
    "model": {
        "repository": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "license": "Apache-2.0",
        "expected_model_safetensors_bytes": 90_868_376,
        "expected_model_safetensors_sha256": (
            "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db"
        ),
    },
    "package": "sentence-transformers==5.7.0",
    "package_license": "Apache-2.0",
    # Recorded because it decides the packaging path, not the probe. The MLX
    # wrapper is GPL-3.0 and this repository is MIT, so the shipping
    # implementation is a forward pass written here rather than a dependency.
    "rejected_dependency": {"name": "mlx-embeddings", "version": "0.1.0", "license": "GPL-3.0"},
    "product_records": "forbidden",
}

# Crude on purpose. Every word in it earns its place by being a word a person
# would type in any question about anything.
STOP_WORDS = frozenset(
    "the a an and or of to in is it we they i you at on for with that this what "
    "which who when where why how did do does was were are be been our us them "
    "their his her its not no as by from about into over after before".split()
)


def _sha256(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_fixtures(path: Path | None = None) -> dict:
    path = path or Path(__file__).with_name("semantic_retrieval_fixtures.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != FIXTURES_SCHEMA:
        raise ValueError("fixture schema is not the registered one")
    return document


def meeting_text(meeting: dict) -> str:
    """One document per meeting. The unit the probe is about."""
    return " ".join(meeting["turns"])


def content_words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z']+", text.lower())
        if word not in STOP_WORDS and len(word) > 2
    }


def control_rank(question: str, meetings: list[dict]) -> str | None:
    """Word overlap, no model. Zero shared words is no answer, not a tie-break.

    The first version ranked on `(score, id)` and so returned a meeting when
    nothing matched at all, which credited it with an answer it had not found.
    """
    asked = content_words(question)
    scored = [(len(asked & content_words(meeting_text(m))), m["id"]) for m in meetings]
    best = max(score for score, _ in scored)
    if best == 0:
        return None
    return sorted(identifier for score, identifier in scored if score == best)[0]


def verified_model(model_directory: Path):
    """Load the pinned weights, or refuse.

    The digest is checked before the model is constructed, so a substituted file
    stops the run rather than producing numbers about something else.
    """
    weights = model_directory / "model.safetensors"
    if not weights.is_file():
        raise SystemExit("model.safetensors is not in the given directory")
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    if digest != PIN["model"]["expected_model_safetensors_sha256"]:
        raise SystemExit(f"model digest mismatch: {digest}")
    if weights.stat().st_size != PIN["model"]["expected_model_safetensors_bytes"]:
        raise SystemExit("model byte count mismatch")

    import sentence_transformers

    if sentence_transformers.__version__ != PIN["package"].split("==")[1]:
        raise SystemExit(f"package mismatch: {sentence_transformers.__version__}")
    return sentence_transformers.SentenceTransformer(str(model_directory)), digest


def cosine(left, right) -> float:
    import numpy

    return float(
        numpy.dot(left, right)
        / (numpy.linalg.norm(left) * numpy.linalg.norm(right))
    )


def run(document: dict, model_directory: Path | None) -> dict:
    meetings = document["meetings"]
    questions = document["questions"]
    rows: list[dict] = []

    model = digest = None
    corpus_vectors = {}
    embed_elapsed_s = None
    if model_directory is not None:
        model, digest = verified_model(model_directory)
        started = time.monotonic()
        texts = [meeting_text(m) for m in meetings]
        vectors = model.encode(texts, normalize_embeddings=False)
        embed_elapsed_s = round(time.monotonic() - started, 6)
        corpus_vectors = {m["id"]: vector for m, vector in zip(meetings, vectors)}

    for question in questions:
        row = {
            "question_sha256": _sha256(question["question"]),
            "intended_meeting": question["intended_meeting"],
            "exact_helps": question["exact_helps"],
            "control_top1": control_rank(question["question"], meetings),
        }
        row["control_correct"] = row["control_top1"] == question["intended_meeting"]
        if model is not None:
            asked = model.encode([question["question"]], normalize_embeddings=False)[0]
            ranked = sorted(
                ((cosine(asked, vector), identifier) for identifier, vector in corpus_vectors.items()),
                reverse=True,
            )
            row["model_top1"] = ranked[0][1]
            row["model_correct"] = ranked[0][1] == question["intended_meeting"]
            # Rounded, because a receipt that changes in the sixteenth decimal
            # across runs cannot evidence repeatability.
            row["model_margin"] = round(ranked[0][0] - ranked[1][0], 6)
        rows.append(row)

    def score(key: str, only_hard: bool | None = None) -> int:
        return sum(
            1
            for row in rows
            if row.get(key) and (only_hard is None or row["exact_helps"] is not only_hard)
        )

    receipt = {
        "schema": PROBE_SCHEMA,
        "pin": PIN,
        "fixtures_sha256": _sha256(
            Path(__file__).with_name("semantic_retrieval_fixtures.json").read_bytes()
        ),
        "harness_sha256": _sha256(Path(__file__).read_bytes()),
        "python": platform.python_version(),
        "model_weights_sha256": digest,
        "corpus_embed_elapsed_s": embed_elapsed_s,
        "questions": len(questions),
        "control": {
            "overall": score("control_correct"),
            "on_hard": score("control_correct", only_hard=True),
        },
        "rows": rows,
    }
    if model is not None:
        receipt["model"] = {
            "overall": score("model_correct"),
            "on_hard": score("model_correct", only_hard=True),
            "on_easy": score("model_correct", only_hard=False),
        }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--receipt", type=Path)
    arguments = parser.parse_args()

    document = load_fixtures()
    receipt = run(document, arguments.model_directory)
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
    if arguments.receipt:
        arguments.receipt.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
