#!/usr/bin/env python3
"""How crowded does the neighbourhood get, and which unit survives it?

Registered in `SEMANTIC_RETRIEVAL.md`. Read the prediction there before reading a
number here.

The 2026-08-08 probe retrieved 10 of 10 on ten short meetings and three of those
turned on margins under 0.04. It also embedded whole meetings only because the
fixtures were 48 tokens; the model reads 256 and truncates the rest in silence.
This measures both of those at once, because they are the same question: **what
happens when the meetings are long and there are many of them.**

# The corpus is composed, not generated wholesale

A meeting is an opening, a substantive block, and a closing. Openings and
closings are logistics and small talk — which is what actually fills the first
minutes of a call, and which pushes the identifying content past the 256-token
window. That is deliberate: a corpus of short dense meetings would hide the
property under test, which is exactly how the ceiling went unnoticed the first
time.

Three populations, kept separate in the result because conflating them inflates
the claim:

- **targets** — the ten meetings the questions are about.
- **near misses** — hand-written, one per target, on the *adjacent* subject.
  Another lease, another rollback, another renewal where usage fell. These are
  the distractors that matter, and they cannot be generated: a bank-composed
  corpus is distinct by construction.
- **filler** — generated from templates with substituted entities, to reach a
  corpus size. Distinct by construction, and reported as such.

# Density is the headline; accuracy is the summary

Top-1 accuracy at a thousand meetings can be 10 of 10 while three distractors sit
within 0.005, and those two facts point opposite ways for a product. So the
reported number is **how many meetings fall within 0.02 of the top hit**, per
question, per unit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

PROBE_SCHEMA = "semantic-scale/1"
CORPUS_SCHEMA = "semantic-scale-corpus/1"

# Registered before the run. A meeting inside this band of the top hit is a
# meeting a person could plausibly have been shown instead.
DENSITY_BAND = 0.02

# Fixed here rather than chosen per run. `SEMANTIC_RETRIEVAL.md` records that the
# comparison is conditional on it: a per-turn arm winning under max might lose
# under mean-of-top-k, which is untested.
AGGREGATION = "max-chunk-similarity"

WINDOW_TOKENS = 128


def _sha256(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def load_corpus_parts(path: Path | None = None) -> dict:
    path = path or Path(__file__).with_name("semantic_scale_corpus.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != CORPUS_SCHEMA:
        raise ValueError("corpus schema is not the registered one")
    return document


def _fill(template: str, banks: dict, seed: int) -> str:
    """Deterministic substitution. No randomness: the corpus at a given size is
    the same corpus on every machine, which is what makes a receipt comparable."""
    out = template
    for index, (name, values) in enumerate(sorted(banks.items())):
        if "{" + name + "}" in out:
            out = out.replace("{" + name + "}", values[(seed * (index + 3)) % len(values)])
    return out


def build_corpus(parts: dict, size: int) -> list[dict]:
    """Targets, then near misses, then filler up to `size`.

    Ordered so a smaller size is a prefix of a larger one: the corpus at 50 is
    the first 50 meetings of the corpus at 1000, so the density curve is measured
    over nested corpora rather than four unrelated ones.
    """
    openings = parts["openings"]
    closings = parts["closings"]
    meetings: list[dict] = []

    def compose(identifier: str, kind: str, substantive: list[str], seed: int) -> dict:
        return {
            "id": identifier,
            "kind": kind,
            "turns": (
                openings[seed % len(openings)]
                + substantive
                + closings[(seed * 5) % len(closings)]
            ),
        }

    for index, target in enumerate(parts["targets"]):
        meetings.append(compose(target["id"], "target", target["turns"], index))
    for index, near in enumerate(parts["near_misses"]):
        meetings.append(compose(near["id"], "near-miss", near["turns"], index + 7))

    seed = 0
    subjects = parts["filler_subjects"]
    while len(meetings) < size:
        template = subjects[seed % len(subjects)]
        substantive = [_fill(turn, parts["filler_banks"], seed + line) for line, turn in enumerate(template)]
        meetings.append(compose(f"filler-{seed:04d}", "filler", substantive, seed + 3))
        seed += 1
    return meetings[:size]


def meeting_text(meeting: dict) -> str:
    return " ".join(meeting["turns"])


def chunk_units(meeting: dict, unit: str, tokenizer) -> list[str]:
    """The text pieces one meeting contributes, under a given unit."""
    if unit == "meeting-truncated":
        # What the 2026-08-08 probe measured. Named for what it does: the
        # reference implementation truncates at 256 without saying so, and this
        # arm exists to show what that costs on a real-length meeting.
        return [meeting_text(meeting)]
    if unit == "turn":
        return list(meeting["turns"])
    if unit == "window":
        words = meeting_text(meeting).split()
        # Words, not tokens, and deliberately conservative: ~128 tokens is fewer
        # than 128 words for this tokenizer, so a window built this way cannot
        # exceed the ceiling.
        stride = WINDOW_TOKENS
        return [" ".join(words[at : at + stride]) for at in range(0, len(words), stride)] or [""]
    raise ValueError(f"unknown unit {unit!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[30, 60, 120, 200])
    parser.add_argument("--receipt", type=Path)
    arguments = parser.parse_args()

    import numpy
    from mlx_minilm import MiniLMEncoder, encode, load_tokenizer

    parts = load_corpus_parts()
    encoder = MiniLMEncoder(arguments.model_directory)
    tokenizer = load_tokenizer(arguments.model_directory)

    def embed(texts: list[str]) -> numpy.ndarray:
        vectors = []
        for at in range(0, len(texts), 64):
            vectors.append(numpy.asarray(encode(encoder, tokenizer, texts[at : at + 64])))
        return numpy.vstack(vectors)

    def normalize(matrix: numpy.ndarray) -> numpy.ndarray:
        return matrix / numpy.linalg.norm(matrix, axis=1, keepdims=True)

    questions = parts["questions"]
    asked = normalize(embed([q["question"] for q in questions]))

    largest = max(arguments.sizes)
    corpus = build_corpus(parts, largest)
    token_counts = [len(tokenizer.encode(meeting_text(m))) for m in corpus]

    results = []
    for unit in ("meeting-truncated", "turn", "window"):
        started = time.monotonic()
        pieces: list[str] = []
        owners: list[int] = []
        for index, meeting in enumerate(corpus):
            for piece in chunk_units(meeting, unit, tokenizer):
                # The truncated arm is the only one that may exceed the ceiling,
                # and it is the arm whose whole point is that it does.
                if unit == "meeting-truncated":
                    piece = " ".join(piece.split()[:200])
                pieces.append(piece)
                owners.append(index)
        vectors = normalize(embed(pieces))
        embed_elapsed_s = round(time.monotonic() - started, 3)
        owners_array = numpy.asarray(owners)

        for size in arguments.sizes:
            keep = owners_array < size
            kept_vectors = vectors[keep]
            kept_owners = owners_array[keep]
            similarity = asked @ kept_vectors.T

            rows = []
            for question_index, question in enumerate(questions):
                scores = similarity[question_index]
                # Max chunk similarity per meeting: the registered aggregation.
                per_meeting = numpy.full(size, -2.0)
                numpy.maximum.at(per_meeting, kept_owners, scores)
                order = numpy.argsort(-per_meeting)
                top = corpus[int(order[0])]["id"]
                margin = float(per_meeting[order[0]] - per_meeting[order[1]])
                within = int(numpy.sum(per_meeting >= per_meeting[order[0]] - DENSITY_BAND) - 1)
                near_id = f"near-{question['target'].split('-', 1)[1]}"
                near_index = next(
                    (i for i, m in enumerate(corpus[:size]) if m["id"] == near_id), None
                )
                rows.append(
                    {
                        "target": question["target"],
                        "top1": top,
                        "correct": top == question["target"],
                        "margin": round(margin, 6),
                        "within_band": within,
                        "near_miss_rank": (
                            int(numpy.where(order == near_index)[0][0]) + 1
                            if near_index is not None
                            else None
                        ),
                    }
                )
            results.append(
                {
                    "unit": unit,
                    "size": size,
                    "pieces": int(keep.sum()),
                    "correct": sum(1 for r in rows if r["correct"]),
                    "median_margin": round(float(numpy.median([r["margin"] for r in rows])), 6),
                    "median_within_band": int(
                        numpy.median([r["within_band"] for r in rows])
                    ),
                    "max_within_band": max(r["within_band"] for r in rows),
                    "near_miss_beat_target": sum(
                        1 for r in rows if r["near_miss_rank"] == 1
                    ),
                    "embed_elapsed_s": embed_elapsed_s,
                    "rows": rows,
                }
            )

    receipt = {
        "schema": PROBE_SCHEMA,
        "aggregation": AGGREGATION,
        "density_band": DENSITY_BAND,
        "window_tokens": WINDOW_TOKENS,
        "corpus_parts_sha256": _sha256(
            Path(__file__).with_name("semantic_scale_corpus.json").read_bytes()
        ),
        "harness_sha256": _sha256(Path(__file__).read_bytes()),
        "implementation_sha256": _sha256(
            Path(__file__).with_name("mlx_minilm.py").read_bytes()
        ),
        "meeting_tokens": {
            "min": int(min(token_counts)),
            "median": int(sorted(token_counts)[len(token_counts) // 2]),
            "max": int(max(token_counts)),
            "over_ceiling": int(sum(1 for count in token_counts if count > 256)),
        },
        "results": results,
    }
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
    if arguments.receipt:
        arguments.receipt.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
