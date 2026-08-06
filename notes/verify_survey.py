#!/usr/bin/env python3
"""Re-derive every survey tally published in docs/journeys.md.

The survey export is gitignored. Six colleagues answered questions about their own
meetings on the understanding that it informed this tool, and in a small organisation
a job title names one person — so the raw responses stay off a public repo while the
numbers derived from them ship.

That trade only works if the numbers stay checkable, which is what this file is for.
It is the same shape as `fetch_corpus.py`: the data is absent from the repo and the
means of reproducing a result from it is not.

    python3 notes/verify_survey.py [path/to/export.tsv]

Exits non-zero if any published claim no longer matches the export. Every expectation
below is transcribed from the `n=6` snapshot in docs/journeys.md; if that section is
edited, edit this list in the same change or the check stops meaning anything.

**This file holds counts and nothing else, deliberately.** The registered analysis
plan states that the public repository retains no respondent-level rows, free text,
timestamps, or answer combinations — and a committed script that asserted "option X
was chosen only by the three respondents from employer Y" would be an answer
combination published under a role group small enough to name people. An earlier
draft did exactly that. Cohort structure belongs in the export, not here.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

DEFAULT_EXPORT = Path(__file__).resolve().parent.parent / "docs/survey/2026-07-raw.tsv"

# Options whose own text contains a comma. Splitting naively turns these into three
# phantom options each and silently inflates two tallies, which is a mistake this
# script exists partly to stop anyone repeating.
COMPOUND = ("Accept, reject, or defer it", "Filter by person, project, or date")

# (column, option, expected count) — as published.
EXPECTED = [
    ("never", "Share or upload without my action", 6),
    ("never", "Keep audio without showing me", 4),
    ("never", "Change a roadmap or backlog automatically", 3),
    ("never", "Present an inference as a quote", 3),
    ("never", "Invite a bot automatically", 3),
    ("never", "Hide uncertain or missing evidence", 2),
    ("never", "Infer commitments", 2),
    ("privacy", "Nothing is shared without my action", 5),
    ("privacy", "Local-only processing", 1),
    ("privacy", "No account required", 1),
    ("privacy", "Per-meeting consent reminder", 1),
    ("note_contents", "Action items and owners", 6),
    ("note_contents", "Concise summary", 5),
    ("note_contents", "Open questions", 5),
    ("note_contents", "Decisions", 4),
    ("note_contents", "Risks and blockers", 3),
    ("note_contents", "Customer goals and needs", 3),
    ("note_contents", "Follow-up draft", 3),
    ("note_contents", "Exact quotes", 3),
    ("note_contents", "Full transcript", 3),
    ("per_claim", "Stated versus inferred label", 4),
    ("per_claim", "Quote and timestamp", 4),
    ("per_claim", "Speaker", 3),
    ("per_claim", "Accept, reject, or defer it", 3),
    ("per_claim", "Edit or correct it", 2),
    ("per_claim", "Change history and undo", 1),
    ("during_meeting", "Give me a simple note surface", 3),
    ("during_meeting", "Show a live transcript and evidence", 2),
    ("during_meeting", "Nothing beyond Start and Stop", 1),
    ("capture", "Separate speakers", 4),
    ("capture", "Capture microphone and system audio", 3),
    ("capture", "Support in-person conversations", 3),
    ("meeting_types", "Sales or discovery calls", 4),
    ("meeting_types", "Coaching or mentoring", 4),
    ("meeting_types", "1:1s", 3),
    ("meeting_types", "In-person conversations", 3),
    ("jobs", "Share a useful summary", 5),
    ("jobs", "Find a past discussion", 5),
    ("jobs", "Turn feedback into product work", 3),
    ("product_signal", "Propose a Product Signal with its quote for my review", 3),
    ("product_signal", "Include it only in the meeting note", 3),
    ("retention", "Keep locally until I delete it", 3),
    ("retention", "Ask me for each meeting", 2),
    ("retention", "Keep locally for a short period", 1),
]

def options(value: str) -> list[str]:
    """Split a multi-select cell, keeping comma-containing options intact."""
    found = []
    for compound in COMPOUND:
        if compound in value:
            found.append(compound)
            value = value.replace(compound, "")
    return found + [part.strip() for part in value.split(",") if part.strip()]


def tally(rows, column):
    """Count selections for one column. Deliberately returns no respondent identity."""
    counts = collections.Counter()
    for row in rows:
        for option in options(row.get(column) or ""):
            counts[option] += 1
    return counts


def main(argv: list[str]) -> int:
    export = Path(argv[1]) if len(argv) > 1 else DEFAULT_EXPORT
    if not export.exists():
        print(f"export not found: {export}", file=sys.stderr)
        print(
            "docs/survey/ is gitignored on purpose; ask the author for the export.",
            file=sys.stderr,
        )
        return 2

    with export.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    failures = []

    if len(rows) != 6:
        failures.append(f"respondent count: published 6, export has {len(rows)}")

    for column, option, expected in EXPECTED:
        actual = tally(rows, column).get(option, 0)
        if actual != expected:
            failures.append(f"{column} / {option!r}: published {expected}, export has {actual}")

    # Published: "Trust controls were selected by every respondent — at least one each."
    without = sum(1 for row in rows if not options(row.get("per_claim") or ""))
    if without:
        failures.append(
            f"per-claim control published as chosen by all six; {without} respondent(s) chose none"
        )

    # Published: no retention option reaches a majority of six.
    counts = tally(rows, "retention")
    if counts and max(counts.values()) > 3:
        failures.append(
            f"retention published as having no majority; export has a {max(counts.values())}"
        )

    for failure in failures:
        print(f"FAIL  {failure}")
    if failures:
        print(f"\n{len(failures)} published claim(s) no longer match the export.")
        return 1

    print(f"OK  {len(EXPECTED)} tallies + 2 derived claims, counts only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
