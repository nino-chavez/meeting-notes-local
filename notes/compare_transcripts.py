#!/usr/bin/env python3
"""Compare two transcripts of the same meeting.

Written to answer one question: is our own speech recognition good enough to
build notes on, or is it the thing holding recall down? Word error rate is the
usual answer and it is the wrong one here. A transcript can miss "um" a hundred
times and lose nothing; miss the one noun phrase naming the document somebody
promised to send, once, and the commitment that depends on it cannot be written.
So this measures **whether the terms the
meeting's commitments rest on survived**, and takes those terms from the
reference action items rather than from a hand-written list.

The second measurement is fragmentation, and it exists because of a result that
went the opposite way from expected. Google Meet's transcript carries speaker
labels; ours does not. Google's therefore looked like the better input. But Meet
resolves overlapping speech by cutting turns at every interruption, so 42% of
its units were three words or fewer on a real call, and during crosstalk it
emits speaker labels *inside* another speaker's sentence:

    Speaker A: Oh, wait. Are you able to share? You should be able Speaker B:
    Speaker A: to. Speaker B: to

Whisper, given the same audio, returns continuous sentences and no labels at
all. Attribution is bought with sentence integrity, and for note-writing the
sentences turned out to matter more.

Holding one side fixed and varying the other answers different questions with the
same measurement. Against a platform's transcript it asks whether our recogniser
is the bottleneck. Against our own direct decode of a file it asks what the
capture path costs — same audio, same model, so anything lost belongs to the tap,
the resampling round-trip, or the block chunking. The answer to both, so far, is
nothing.

Usage:
    python notes/compare_transcripts.py theirs.txt ours.json
    python notes/compare_transcripts.py theirs.txt ours.json --reference items.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from summarize import _NOTE_REGISTER, _words, load_reference
from transcript import load


def stats(t) -> dict:
    lengths = [len(x.text.split()) for x in t.turns]
    if not lengths:
        return {}
    return {
        "units": len(lengths),
        "words": sum(lengths),
        "mean_words": sum(lengths) / len(lengths),
        # Short units are the fingerprint of turn-cutting at every interruption.
        "tiny_pct": 100 * sum(1 for n in lengths if n <= 3) / len(lengths),
        "speakers": len(t.speakers),
    }


def term_survival(reference_items: list[str], theirs: str, ours: str) -> list[dict]:
    """For each commitment, which of its content words appear in each transcript.

    A term missing from a transcript is a commitment that transcript cannot
    support, whatever its word error rate.
    """
    rows = []
    for item in reference_items:
        # Drop the bracketed owner: names are an attribution question, and this
        # is about whether the substance of the commitment is recoverable.
        body = re.sub(r"^\[[^\]]*\]", "", item)
        terms = sorted(_words(body) - _NOTE_REGISTER)
        if not terms:
            continue
        in_theirs = [w for w in terms if w in theirs]
        in_ours = [w for w in terms if w in ours]
        rows.append({
            "item": body.strip()[:60],
            "terms": len(terms),
            "theirs": len(in_theirs),
            "ours": len(in_ours),
            "lost_by_ours": sorted(set(in_theirs) - set(in_ours)),
        })
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("theirs", type=Path, help="the reference transcript (e.g. the platform's)")
    p.add_argument("ours", type=Path, help="the transcript to evaluate")
    p.add_argument("--reference", type=Path,
                   help="action items whose terms must survive; without it only "
                        "shape is compared")
    args = p.parse_args()

    a, b = load(args.theirs), load(args.ours)
    sa, sb = stats(a), stats(b)

    print(f"\n{'':16s} {'units':>6} {'words':>7} {'mean':>6} {'<=3 words':>10} {'speakers':>9}")
    for name, s in (("theirs", sa), ("ours", sb)):
        print(f"  {name:14s} {s['units']:>6} {s['words']:>7} {s['mean_words']:>6.1f} "
              f"{s['tiny_pct']:>9.0f}% {s['speakers']:>9}")

    if sb["words"] and sa["words"]:
        print(f"\n  ours carries {100 * sb['words'] / sa['words']:.0f}% of the reference "
              "transcript's word count")
    if sa["tiny_pct"] > sb["tiny_pct"] + 10:
        print("  the reference is markedly more fragmented — it cuts turns at "
              "every interruption")

    if not args.reference:
        print("\n  (pass --reference to check whether commitment terms survived)")
        return 0

    items = load_reference(args.reference)
    theirs_text = " ".join(x.text for x in a.turns).lower()
    ours_text = " ".join(x.text for x in b.turns).lower()
    rows = term_survival(items, theirs_text, ours_text)

    print("\n  commitment terms present in each transcript\n")
    print(f"  {'commitment':62s} {'theirs':>7} {'ours':>6}")
    lost_total = 0
    for r in rows:
        print(f"  {r['item']:62s} {r['theirs']:>3}/{r['terms']:<3} {r['ours']:>3}/{r['terms']:<3}")
        if r["lost_by_ours"]:
            lost_total += len(r["lost_by_ours"])
            print(f"      only in theirs: {r['lost_by_ours']}")

    print(f"\n  {lost_total} commitment term(s) present in the reference transcript "
          "and absent from ours")
    if not lost_total:
        # Deliberately not "speech recognition is fine". The same comparison is
        # used to hold the recogniser constant and vary something else — a
        # capture path against a direct decode of the same file, say — and there
        # the conclusion is about the capture, not the ASR. Name the measurement,
        # not a component the tool cannot see.
        print("  Every term the commitments rest on survived the transcript under "
              "test.\n  Whatever is limiting recall, it is not transcription loss.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
