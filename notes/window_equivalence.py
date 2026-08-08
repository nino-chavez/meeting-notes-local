#!/usr/bin/env python3
"""Freeze what the measured windowing did, so Rust can be held to it.

`semantic_scale_probe.py` chose the unit the store is built on. Its windowing
lives in one function — `chunk_units(meeting, "window", ...)` — and that function
is nine lines of Python that a Rust reimplementation can plausibly get subtly
wrong: whitespace runs, an exactly-full window, a turn boundary landing mid-window.

So this writes the boundaries down. It imports the probe rather than restating it,
and it never edits the probe: `semantic_scale_receipt.json` records the harness's
own SHA-256, and changing a byte of it would invalidate a committed result.

**The output is a frozen artifact.** Regenerating it after changing the probe is
not a refresh — it is a new measurement, and the receipt it belongs to would have
to be re-run too.

Inputs are drawn from the real composed corpus at size 30 (one target, one near
miss, one filler — the three populations) so the fixture carries realistic
meeting length rather than a toy. Four hand-written edge cases follow, each named
for the property it isolates.

    python3 notes/window_equivalence.py --out notes/window_equivalence_fixture.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import semantic_scale_probe as probe

FIXTURE_SCHEMA = "window-equivalence/1"


def edge_cases() -> list[dict]:
    """Each isolates one thing a reimplementation can get wrong."""
    return [
        {
            "id": "edge-exactly-one-window",
            "why": "128 words exactly: one window, and no empty second one",
            "turns": [" ".join(f"w{index}" for index in range(probe.WINDOW_TOKENS))],
        },
        {
            "id": "edge-one-word-over",
            "why": "129 words: the 129th starts a window of its own",
            "turns": [" ".join(f"w{index}" for index in range(probe.WINDOW_TOKENS + 1))],
        },
        {
            "id": "edge-irregular-whitespace",
            "why": (
                "runs of spaces, tabs and newlines collapse; the window text is "
                "words joined by one space, not the source slice"
            ),
            "turns": ["alpha   beta\tgamma", "  delta \n\n epsilon  "],
        },
        {
            "id": "edge-turn-boundary-mid-window",
            "why": "a window spans turns, because the probe joins them before splitting",
            "turns": [
                " ".join(f"a{index}" for index in range(probe.WINDOW_TOKENS - 2)),
                "b0 b1 b2 b3",
            ],
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()

    corpus = probe.build_corpus(probe.load_corpus_parts(), 30)
    by_kind: dict[str, dict] = {}
    for meeting in corpus:
        by_kind.setdefault(meeting["kind"], meeting)
    sampled = [by_kind[kind] for kind in ("target", "near-miss", "filler") if kind in by_kind]

    cases = []
    for meeting in sampled + edge_cases():
        windows = probe.chunk_units(meeting, "window", None)
        cases.append(
            {
                "id": meeting["id"],
                "why": meeting.get("why", f"composed corpus, {meeting.get('kind')} population"),
                "turns": meeting["turns"],
                "windows": windows,
                "window_word_counts": [len(window.split()) for window in windows],
            }
        )

    document = {
        "schema": FIXTURE_SCHEMA,
        "window_tokens": probe.WINDOW_TOKENS,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(
            Path(probe.__file__).read_bytes()  # type: ignore[arg-type]
        ).hexdigest(),
        "corpus_parts_sha256": hashlib.sha256(
            (Path(probe.__file__).parent / "semantic_scale_corpus.json").read_bytes()
        ).hexdigest(),
        "cases": cases,
    }
    arguments.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases, {sum(len(case['windows']) for case in cases)} windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
