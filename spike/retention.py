#!/usr/bin/env python3
"""Did the words survive? Passage recall per condition, on a cued take.

Every echo figure in this project so far measures *suppression* — how much of the
far end came out. That is not what the product ships on. A canceller that removes
40 dB of echo and takes the operator's voice with it scores beautifully and
destroys the thing being built.

This measures the other direction, and it is the only measurement here that needs
no assumption about who was talking. The cue schedule fixed each passage before any
audio existed, so the words are known in advance. Transcribe a condition, look
inside each speak interval, and count how many of the passage's content words came
back. That is transcript retention, against external ground truth.

It is worth being precise about why this escapes the problem that limits
`aec_bound.py`. There, whether a segment holds the operator is decided by reading
the raw microphone transcript — the contaminated signal under test — so the segments
it keeps are a biased sample and the result is reported as an interval rather than
a number. Here nothing is selected. Every speak interval is measured, the passage it
should contain is known from the schedule, and recall is the fraction recovered.
The contaminated transcript is the thing being scored, not the thing choosing what
to score.

Two numbers per interval, because a canceller can fail in both directions:

  recall   — content words of the passage that came back. What was kept.
  leakage  — transcribed content words that belong to the FAR END rather than the
             passage, taken from the system leg's own transcript over the same
             interval. What should not have been there.

Recall alone would reward a condition that transcribes everything including the
playback; leakage alone would reward one that transcribes nothing. Both together
are the tradeoff the product actually makes.

Usage:
    python spike/retention.py --protocol take/protocol.json \
        --far take/system-segments.json \
        --condition raw=take/mic.wav --condition aec3=take/aec3.wav
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aec_bound as ab
import dual_capture as dc


def interval_text(segs: list[dict], lo: float, hi: float) -> str:
    """Everything transcribed that overlaps this interval.

    Overlap rather than containment, which is the opposite of `aec_bound.classify`
    and deliberate. There, a segment straddling a cue is excluded because it cannot
    be attributed to one interval's *speaker*. Here the interval's content is known
    from the schedule, so a segment that starts early and runs in still carries
    evidence about which words survived — dropping it would report a word as lost
    when the transcript found it.
    """
    return " ".join(s.get("text", "") for s in segs
                    if s["end"] > lo and s["start"] < hi).strip()


def measure(protocol: dict, segs: list[dict], far_segs: list[dict]) -> list[dict]:
    """Recall and leakage for each speak interval."""
    margin = protocol["cue_margin_s"]
    rows = []
    for ph in protocol["phases"]:
        if ph["expect"] != "operator" or not ph["script"]:
            continue
        span = ab.phase_interior(ph, margin)
        if not span:
            continue
        lo, hi = span
        want = ab.tokens(ph["script"])
        far = ab.tokens(interval_text(far_segs, lo, hi))
        heard = ab.tokens(interval_text(segs, lo, hi))

        # Words the far end also says cannot be credited to either side, so they
        # leave both numerator and denominator rather than being assigned. This is
        # the same rule protocol_compliance uses, for the same reason: a token in
        # both is evidence of nothing.
        contested = want & far
        want_clean = want - contested
        heard_clean = heard - contested

        recovered = heard_clean & want_clean
        leaked = heard_clean & (far - want)
        rows.append({
            "start": ph["start"], "end": ph["end"],
            "passage_words": len(want_clean),
            "recovered": len(recovered),
            "recall": round(len(recovered) / len(want_clean), 3) if want_clean else None,
            "leaked_words": len(leaked),
            "leakage": (round(len(leaked) / len(heard_clean), 3)
                        if heard_clean else None),
            "contested_words": len(contested),
            "heard": interval_text(segs, lo, hi)[:300] or None,
        })
    return rows


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--protocol", type=Path, required=True,
                   help="the take's protocol.json — the passages, fixed before the "
                        "audio existed, which is what makes this ground truth")
    p.add_argument("--far", type=Path,
                   help="the take's system-segments.json. Without it, words the "
                        "playback also said are credited to the operator, and a "
                        "condition that transcribes the far end scores as recall")
    p.add_argument("--condition", action="append", metavar="NAME=WAV", default=[],
                   required=True, help="a condition's audio, repeatable")
    p.add_argument("--whisper", default="mlx-community/whisper-large-v3-turbo")
    p.add_argument("--language", default="en")
    p.add_argument("--out", type=Path,
                   help="write the per-interval rows here. Carries what was "
                        "transcribed, so it is a transcript and cannot go in the repo")
    args = p.parse_args()

    if args.out and ab.inside_repo(args.out):
        p.error(f"--out {args.out} is inside the repository. This carries what was "
                f"said. Write it beside the recordings instead.")

    doc = json.loads(args.protocol.read_text())
    if doc.get("schema") != "capture-protocol/1":
        p.error(f"{args.protocol}: expected schema capture-protocol/1")
    # Read directly rather than through load_protocol, which binds to the mic and
    # system WAVs by digest. Conditions are derived audio — that is the point of
    # this tool — so a binding check would refuse every one of them. The passages
    # and cue times are what is needed here, and both are in the file.
    kept = doc.get("phases") or []
    for i, ph in enumerate(kept):
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        ph["obs_start"] = ph.get("shown_at_s") if ph.get("shown_at_s") is not None else ph["start"]
        ph["obs_end"] = (nxt.get("shown_at_s") if nxt and nxt.get("shown_at_s") is not None
                         else ph["end"])
    protocol = {"phases": kept, "cue_margin_s": doc["cue_margin_s"]}

    far_segs = []
    if args.far:
        far_doc = json.loads(args.far.read_text())
        far_segs = far_doc.get("segments") or []
    else:
        print("no --far: words the playback also said will be credited as recall\n")

    results = {}
    for spec in args.condition:
        name, _, path = spec.partition("=")
        wav = Path(path).expanduser()
        if not wav.exists():
            p.error(f"condition {name}: no {wav}")
        audio = ab.load_wav(wav)
        segs = dc.transcribe(audio, args.whisper, args.language)
        rows = measure(protocol, segs, far_segs)
        results[name] = {"audio": str(wav), "sha256": ab.sha256(wav),
                         "seconds": round(len(audio) / ab.RATE, 2), "intervals": rows}

        recall = [r["recall"] for r in rows if r["recall"] is not None]
        leak = [r["leakage"] for r in rows if r["leakage"] is not None]
        if not recall:
            print(f"{name:10s} {len(segs):3d} segments   nothing measurable — no "
                  f"speak interval had usable words left after contested ones went")
        else:
            print(f"{name:10s} {len(segs):3d} segments   "
                  f"recall {np.mean(recall) * 100:5.1f}% mean "
                  f"({min(recall) * 100:.0f}-{max(recall) * 100:.0f}% over "
                  f"{len(recall)} intervals)   "
                  f"far-end leakage {np.mean(leak) * 100:5.1f}%"
                  if leak else "   leakage unmeasured")
        for r in rows:
            print(f"           {r['start']:6.0f}s  recall {r['recall']}  "
                  f"({r['recovered']}/{r['passage_words']} words)  "
                  f"leakage {r['leakage']}  contested {r['contested_words']}")

    if args.out:
        args.out.write_text(json.dumps(results, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
