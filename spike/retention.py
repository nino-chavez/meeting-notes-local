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


def observed_phases(doc: dict) -> dict:
    """The schedule with each phase's OBSERVED boundaries resolved.

    Read straight from the document rather than through `aec_bound.load_protocol`,
    which binds the schedule to the mic and system WAVs by digest. Every condition
    this measures is derived audio — that is the point — so a binding check would
    refuse all of them. The passages and the cue display times are what is needed,
    and both are in the file.

    Boundaries come from when each cue actually appeared, matching
    `load_protocol`'s rule so the two tools attribute the same audio to the same
    interval: an instruction stands until the next cue replaces it, so a late
    successor extends its predecessor. Shared here rather than reimplemented,
    because two copies of this drift and the drift is invisible.
    """
    kept = doc.get("phases") or []
    for i, ph in enumerate(kept):
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        shown = ph.get("shown_at_s")
        ph["obs_start"] = ph["start"] if shown is None else shown
        nxt_shown = nxt.get("shown_at_s") if nxt else None
        ph["obs_end"] = ph["end"] if nxt_shown is None else nxt_shown
    return {"phases": kept, "cue_margin_s": doc["cue_margin_s"]}


def transcribe_file(wav: Path, whisper: str, language: str) -> list[dict]:
    """One condition's WAV through the same ASR the capture uses."""
    return dc.transcribe(ab.load_wav(wav), whisper, language)


REPEATS = 3


def score(wav: Path, protocol: dict, far_segs: list[dict], whisper: str,
          language: str, repeats: int = REPEATS) -> dict:
    """Recall and leakage for one condition, over several transcription passes.

    One pass is not a measurement of this. mlx_whisper is stable *within* a process
    — the same call three times running returns the same text — and moves between
    processes, because MLX's Metal kernels are not bit-reproducible and
    autoregressive decoding turns a last-bit difference into a different token and
    then a different sentence. On the same cancelled file, four separate invocations
    returned 16.6%, 30.7%, 31.2% and 37.1% recall.

    That band is wider than several differences this project published as findings.
    A one-point gap between two conditions is inside it and means nothing; the gap
    between 0% and 30% is far outside it and means what it appears to. Reporting the
    mean with the spread beside it is what lets a reader tell those apart, so the
    spread is not decoration and is never dropped from the output.

    Fixing the decoder instead was tried and rejected: `temperature=0.0` disables
    Whisper's fallback and IS reproducible, at 19.2% against the default's 31.2% on
    the same audio. It removes the variance by removing the retries that recover
    hard speech, which is precisely the audio under study. Measuring the decoder the
    product would actually ship, several times, beats measuring a crippled one once.
    """
    runs = []
    for _ in range(max(1, repeats)):
        rows = measure(protocol, transcribe_file(wav, whisper, language), far_segs)
        recall = [r["recall"] for r in rows if r["recall"] is not None]
        leak = [r["leakage"] for r in rows if r["leakage"] is not None]
        runs.append({
            "recall": float(np.mean(recall)) if recall else None,
            "leakage": float(np.mean(leak)) if leak else None,
            "rows": rows})

    def band(key: str) -> dict | None:
        vals = [r[key] for r in runs if r[key] is not None]
        if not vals:
            return None
        return {"mean": round(float(np.mean(vals)), 3), "min": round(min(vals), 3),
                "max": round(max(vals), 3), "runs": [round(v, 3) for v in vals]}

    return {"recall": band("recall"), "leakage": band("leakage"),
            "passes": len(runs), "intervals": runs[0]["rows"]}


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
    p.add_argument("--repeats", type=int, default=REPEATS,
                   help="transcription passes per condition — see score()")
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
    protocol = observed_phases(doc)

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
        scored = score(wav, protocol, far_segs, args.whisper, args.language,
                       args.repeats)
        rows = scored["intervals"]
        results[name] = {"audio": str(wav), "sha256": ab.sha256(wav),
                         "seconds": round(len(audio) / ab.RATE, 2), **scored}
        rb, lb = scored["recall"], scored["leakage"]
        print(f"{name:10s} {scored['passes']} passes   "
              f"recall {rb['mean'] * 100:.0f}% ({rb['min'] * 100:.0f}-"
              f"{rb['max'] * 100:.0f}% across passes)   "
              f"leakage {lb['mean'] * 100:.0f}%" if rb and lb
              else f"{name:10s} nothing measurable")
        # The per-interval detail is from the first pass only, and says so. Averaging
        # it across passes would hide the thing that made repeats necessary — which
        # interval a pass gave up on differs between passes.
        print(f"           per-interval, first pass of {scored['passes']}:")
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
