#!/usr/bin/env python3
"""The level sweep: where does cancellation stop recovering the operator?

One take measured 13.3% passage recall after AEC3, with the far end sitting about
7 dB louder than the operator at the microphone. That is one point, and a hostile
one. It cannot distinguish "cancellation cannot recover speech from echo" — a dead
end — from "the playback was simply too loud", which is an envelope the product can
state and warn on.

Separating those needs the same protocol at several playback levels, and the level
has to be *measured* rather than taken from the volume slider. Nothing about a
system volume of 50 predicts the ratio at the microphone: it depends on the room,
the seat, the speaker, and how loudly the operator happens to read.

The measured axis is the estimated signal-to-echo ratio. The cue schedule gives two
kinds of interval on the same recording, which is what makes this available at all:

  silent control intervals — the far end alone reaches the microphone, so their
                            level IS the echo, E.
  speak intervals         — the operator and the echo together, S.

Speech and playback are unrelated signals, so their powers add: S² ≈ O² + E², and
the operator's own level is O ≈ sqrt(S² - E²). The ratio O/E is what the canceller
faces. That estimate leans on incoherence, which is exactly true for unrelated
sources and approximately true here; it is reported as an estimate and it is only
ever used as an axis, never as a result.

Recording cannot be skipped or synthesised. The microphone holds the operator and
the echo already summed, and no post-hoc gain separates them — scaling the file
scales both. So the sweep drives the playback volume itself and records a take at
each level, which also makes the levels reproducible instead of depending on a
slider being nudged the same way twice.

Usage:
    # record and analyse, three levels
    python spike/sweep.py --record --levels 25,45,70 --pairs 3 --out ~/sweep

    # analyse takes that already exist
    python spike/sweep.py --take quiet=~/sweep/level-25 --take loud=~/sweep/level-70
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aec_bound as ab
import retention as ret

REPO = Path(__file__).resolve().parent.parent
AEC3_BIN = REPO / "spike" / "aec3" / "aec3_offline"


def output_volume() -> int | None:
    """The current system output volume, so the sweep can put it back."""
    try:
        out = subprocess.run(["osascript", "-e", "get volume settings"],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for part in out.split(","):
        if "output volume" in part:
            return int(part.split(":")[1])
    return None


def set_output_volume(level: int) -> None:
    subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)


def level_db(x: np.ndarray) -> float:
    return 20 * float(np.log10(np.sqrt((x.astype(np.float64) ** 2).mean()) + 1e-12))


def interval_audio(mic: np.ndarray, protocol: dict, expect: str) -> np.ndarray:
    """Every attributable sample from intervals of one kind, concatenated."""
    margin = protocol["cue_margin_s"]
    parts = []
    for ph in protocol["phases"]:
        if ph["expect"] != expect or ph["role"] == "calibration":
            continue
        span = ab.phase_interior(ph, margin)
        if not span:
            continue
        lo, hi = int(span[0] * ab.RATE), int(span[1] * ab.RATE)
        if hi <= len(mic):
            parts.append(mic[lo:hi])
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def signal_to_echo(mic: np.ndarray, protocol: dict) -> dict:
    """Estimated operator-to-echo ratio at the microphone.

    Returns the components as well as the ratio, because a negative variance under
    the square root is the interesting failure: it means the speak intervals came
    out no louder than the silent ones, so either the operator never spoke or the
    playback swamped the difference. Reporting a ratio there would invent a number.
    """
    echo = interval_audio(mic, protocol, "silence")
    both = interval_audio(mic, protocol, "operator")
    if not len(echo) or not len(both):
        return {"ser_db": None, "why": "the take has no silent control or no speak interval"}
    e2 = float((echo.astype(np.float64) ** 2).mean())
    s2 = float((both.astype(np.float64) ** 2).mean())
    row = {"echo_dbfs": round(level_db(echo), 1), "speak_dbfs": round(level_db(both), 1)}
    if s2 <= e2:
        return {**row, "ser_db": None,
                "why": ("the speak intervals are no louder than the silent ones, so "
                        "the operator's own level cannot be separated from the echo")}
    operator = float(np.sqrt(s2 - e2))
    return {**row, "operator_dbfs": round(20 * float(np.log10(operator + 1e-12)), 1),
            "ser_db": round(20 * float(np.log10(operator / (np.sqrt(e2) + 1e-12))), 1)}


def cancel(take: Path) -> Path:
    """AEC3 over a take's legs, canceller only — the gain controllers measured worse."""
    if not AEC3_BIN.exists():
        sys.exit(f"{AEC3_BIN} is not built. See spike/aec3/README.md.")
    out = take / "aec3.wav"
    subprocess.run([str(AEC3_BIN), "--mic", str(take / "mic.wav"),
                    "--ref", str(take / "system.wav"), "--out", str(out)],
                   check=True, capture_output=True)
    return out


def analyse(name: str, take: Path, whisper: str, language: str) -> dict:
    """One take: measured level axis, then retention on raw and cancelled."""
    doc = json.loads((take / "protocol.json").read_text())
    if doc.get("schema") != "capture-protocol/1":
        sys.exit(f"{take}/protocol.json: expected schema capture-protocol/1")
    protocol = ret.observed_phases(doc)
    mic = ab.load_wav(take / "mic.wav")
    far_segs = json.loads((take / "system-segments.json").read_text()).get("segments") or []

    row = {"name": name, "take": str(take), "level": signal_to_echo(mic, protocol),
           "conditions": {}}
    for cond, wav in (("raw", take / "mic.wav"), ("aec3", cancel(take))):
        segs = ret.transcribe_file(wav, whisper, language)
        rows = ret.measure(protocol, segs, far_segs)
        recall = [r["recall"] for r in rows if r["recall"] is not None]
        leak = [r["leakage"] for r in rows if r["leakage"] is not None]
        row["conditions"][cond] = {
            "recall": round(float(np.mean(recall)), 3) if recall else None,
            "leakage": round(float(np.mean(leak)), 3) if leak else None,
            "intervals": rows}
    return row


def record(levels: list[int], pairs: int, out: Path, restore: int | None) -> list[Path]:
    """Drive a take at each playback level.

    The volume is set before each take and put back at the end, including on
    Ctrl-C: leaving someone's speakers at 70 because a measurement was interrupted
    is a rude way to fail.
    """
    takes = []
    try:
        for level in levels:
            take = out / f"level-{level:02d}"
            set_output_volume(level)
            print(f"\n{'=' * 70}\n  output volume {level}. Start the far end playing, "
                  f"then press Enter.\n  Take {len(takes) + 1} of {len(levels)} → "
                  f"{take}\n{'=' * 70}")
            input()
            # stdout is deliberately not captured: the cues are the operator's
            # interface and piping them somewhere would leave them reading nothing.
            proc = subprocess.run(
                [sys.executable, str(REPO / "spike" / "dual_capture.py"), "--protocol",
                 "--protocol-pairs", str(pairs), "--out", str(take)],
                check=False)
            if proc.returncode != 0:
                print(f"  take at level {level} was abandoned — skipping it, and the "
                      f"sweep continues with the levels that recorded")
                continue
            takes.append(take)
    finally:
        if restore is not None:
            set_output_volume(restore)
            print(f"\n  output volume restored to {restore}")
    return takes


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--record", action="store_true",
                   help="record a take at each --level before analysing")
    p.add_argument("--levels", default="25,45,70",
                   help="system output volumes to sweep, with --record")
    p.add_argument("--pairs", type=int, default=3,
                   help="speak/silence pairs per take. Fewer means less reading per "
                        "level and less evidence per level; three is the floor that "
                        "still gives the silent controls the axis depends on")
    p.add_argument("--out", type=Path, help="parent directory for recorded takes")
    p.add_argument("--take", action="append", metavar="NAME=DIR", default=[],
                   help="analyse an existing take, repeatable")
    p.add_argument("--whisper", default="mlx-community/whisper-large-v3-turbo")
    p.add_argument("--language", default="en")
    p.add_argument("--json", type=Path, help="write the full rows here, outside the repo")
    args = p.parse_args()

    for path in (args.out, args.json):
        if path is not None and ab.inside_repo(path):
            p.error(f"{path} is inside the repository. Recordings and anything "
                    f"carrying what was said belong outside it.")

    takes: list[tuple[str, Path]] = []
    if args.record:
        if not args.out:
            p.error("--record needs --out")
        levels = [int(v) for v in args.levels.split(",") if v.strip()]
        if not levels:
            p.error("--levels parsed to nothing")
        args.out.mkdir(parents=True, exist_ok=True)
        for take in record(levels, args.pairs, args.out, output_volume()):
            takes.append((take.name, take))
        if not takes:
            # Distinguished from "you passed nothing", which is what this used to
            # say to someone who had just spent the session recording: every take
            # abandoning means the far end was never playing, and telling them to
            # pass --record is the least useful sentence available.
            p.error(f"all {len(levels)} takes were abandoned — the far end was not "
                    f"playing for any of them. Start the playback first; it has to "
                    f"be audible before the capture begins, not after.")
    for spec in args.take:
        name, _, path = spec.partition("=")
        takes.append((name, Path(path).expanduser()))
    if not takes:
        p.error("nothing to analyse: pass --record with --out, or --take NAME=DIR")

    rows = []
    for name, take in takes:
        missing = [f for f in ("mic.wav", "system.wav", "protocol.json",
                               "system-segments.json") if not (take / f).exists()]
        if missing:
            print(f"{name:12s} skipped: no {', '.join(missing)} in {take}")
            continue
        rows.append(analyse(name, take, args.whisper, args.language))

    def pct(row: dict, cond: str, key: str) -> str:
        v = row["conditions"][cond][key]
        return f"{v * 100:.1f}%" if v is not None else "n/a"

    def dbfs(v) -> str:
        return f"{v:.1f}" if v is not None else "n/a"

    print(f"\n{'take':12s} {'echo':>8s} {'operator':>9s} {'S/E':>8s}   "
          f"{'raw recall':>10s} {'aec3 recall':>11s}   {'raw leak':>8s} {'aec3 leak':>9s}")
    for r in rows:
        lv = r["level"]
        ser = f"{lv['ser_db']:+.1f} dB" if lv.get("ser_db") is not None else "n/a"
        print(f"{r['name']:12s} {dbfs(lv.get('echo_dbfs')):>8s} "
              f"{dbfs(lv.get('operator_dbfs')):>9s} {ser:>8s}   "
              f"{pct(r, 'raw', 'recall'):>10s} {pct(r, 'aec3', 'recall'):>11s}   "
              f"{pct(r, 'raw', 'leakage'):>8s} {pct(r, 'aec3', 'leakage'):>9s}")
        if lv.get("why"):
            print(f"{'':12s} {lv['why']}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
