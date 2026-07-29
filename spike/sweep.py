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
import random
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


def provenance(take: Path, cancelled: Path, whisper: str) -> dict:
    """Everything a figure here depends on, by digest.

    A recall number is a function of the recording, the schedule, the canceller
    binary and its configuration, the ASR checkpoint and the tokenizer. This file
    used to record none of them, so two runs that disagreed could not be told apart
    from two runs of different things — which happened: the same file returned recall
    from 16.6% to 37.1% across invocations, and there was no way to prove it was the
    same file.
    """
    return {
        "mic_sha256": ab.sha256(take / "mic.wav"),
        "system_sha256": ab.sha256(take / "system.wav"),
        "protocol_sha256": ab.sha256(take / "protocol.json"),
        "system_segments_sha256": ab.sha256(take / "system-segments.json"),
        "cancelled_sha256": ab.sha256(cancelled),
        "aec3_binary_sha256": ab.sha256(AEC3_BIN),
        "aec3_config": "echo_canceller only; agc and ns off",
        "asr_checkpoint": whisper,
        "tokenizer_version": ab.TOKENIZER_VERSION,
    }


def analyse(name: str, take: Path, whisper: str, language: str,
            repeats: int) -> dict:
    """One take: measured level axis, then retention on raw and cancelled.

    The schedule and the microphone segments go through `aec_bound`'s loaders, which
    check both legs' digests and sample counts. Reading the JSON directly — which
    this did — accepts a schedule belonging to a different recording, or one whose
    audio was truncated afterwards so every phase boundary slid underneath it. The
    conditions themselves cannot be bound that way, since they are derived audio;
    they are recorded by digest in `provenance` instead.
    """
    mic_p, sys_p = take / "mic.wav", take / "system.wav"
    protocol = ab.load_protocol(
        take / "protocol.json",
        mic_digest=ab.sha256(mic_p), mic_samples=ab.wav_frames(mic_p),
        sys_digest=ab.sha256(sys_p), sys_samples=ab.wav_frames(sys_p))
    # load_protocol resolves observed boundaries itself; observed_phases would be a
    # second implementation of the same rule over an already-resolved document.
    mic = ab.load_wav(mic_p)
    far_segs = ab.load_segments(
        take / "system-segments.json", digest=ab.sha256(sys_p),
        samples=ab.wav_frames(sys_p), leg="system")

    cancelled = cancel(take)
    row = {"name": name, "take": str(take), "level": signal_to_echo(mic, protocol),
           "provenance": provenance(take, cancelled, whisper),
           "dropped_phases": protocol["dropped_phases"], "conditions": {}}
    for cond, wav in (("raw", mic_p), ("aec3", cancelled)):
        row["conditions"][cond] = ret.score(wav, protocol, far_segs, whisper,
                                            language, repeats)
    return row


def record(levels: list[int], pairs: int, out: Path, restore: int | None,
           playback: Path | None) -> list[Path]:
    """Drive a take at each playback level.

    With --playback, the sweep starts the SAME audio file from its beginning before
    each take and stops it after. Without it the operator starts whatever is to hand,
    and the first sweep did exactly that: the three system legs correlated at -0.003
    to +0.002 with 9.6-16.2% vocabulary overlap, so level, words, spectrum and running
    order all moved together and no row could be attributed to level. Far-end content
    dominates outcome inside a single level — at one nominal ratio the three intervals
    of one take gave 59%, 65% and 0% recall — so this is the difference between a
    curve and three anecdotes.

    afplay is a separate process rendering to the default output device, which is the
    real condition: the notetaker never renders the far end, and a canceller that only
    works on audio the enabling process played is no use here.

    The volume is set before each take and put back at the end, including on
    Ctrl-C: leaving someone's speakers at 70 because a measurement was interrupted
    is a rude way to fail.
    """
    takes, player = [], None
    try:
        for i, level in enumerate(levels, 1):
            take = out / f"take-{i:02d}-level-{level:02d}"
            set_output_volume(level)
            if playback:
                # Restarted from the top for every take, so each condition hears the
                # same words in the same order. Killed and relaunched rather than
                # left running, which would give every take a different excerpt.
                player = subprocess.Popen(["afplay", str(playback)],
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
            print(f"\n{'=' * 70}\n  take {i} of {len(levels)}, output volume {level}"
                  f"{'' if playback else ' — start the far end playing yourself'}\n"
                  f"  {take}\n  Press Enter when ready.\n{'=' * 70}")
            input()
            # stdout is deliberately not captured: the cues are the operator's
            # interface and piping them somewhere would leave them reading nothing.
            proc = subprocess.run(
                [sys.executable, str(REPO / "spike" / "dual_capture.py"), "--protocol",
                 "--protocol-pairs", str(pairs), "--out", str(take)],
                check=False)
            if player:
                player.terminate()
                player.wait()
                player = None
            if proc.returncode != 0:
                print(f"  take at level {level} was abandoned — skipping it, and the "
                      f"sweep continues with the levels that recorded")
                continue
            takes.append(take)
    finally:
        if player:
            player.terminate()
            player.wait()
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
    p.add_argument("--playback", type=Path,
                   help="the far end: ONE audio file, restarted from its beginning "
                        "before every take, so content is held fixed while level "
                        "varies. Without it the operator starts whatever is to hand "
                        "and the sweep confounds level with words, spectrum and "
                        "order — which is what happened the first time")
    p.add_argument("--replicates", type=int, default=1,
                   help="how many times to record each level. More than one is what "
                        "separates a level effect from a take effect")
    p.add_argument("--shuffle", type=int, metavar="SEED",
                   help="randomise the order takes are recorded in, with this seed "
                        "recorded in the manifest. Sequential 25/45/70 confounds "
                        "level with time: room noise, the operator's voice and their "
                        "attention all drift over a session")
    p.add_argument("--take", action="append", metavar="NAME=DIR", default=[],
                   help="analyse an existing take, repeatable")
    p.add_argument("--whisper", default="mlx-community/whisper-large-v3-turbo")
    p.add_argument("--language", default="en")
    p.add_argument("--repeats", type=int, default=ret.REPEATS,
                   help="transcription passes per condition. One is not a "
                        "measurement: the same file returned 16.6%% to 37.1%% recall "
                        "across separate invocations, because MLX's Metal kernels are "
                        "not bit-reproducible and a last-bit difference becomes a "
                        "different token")
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
        if args.playback and not args.playback.exists():
            p.error(f"--playback {args.playback} does not exist")
        if not args.playback:
            print("no --playback: the far end will be whatever you start yourself, "
                  "so content is not held fixed and level cannot be separated from "
                  "it. The first sweep did this and its rows are not a curve.\n")
        levels = levels * max(1, args.replicates)
        if args.shuffle is not None:
            random.Random(args.shuffle).shuffle(levels)
        print(f"recording order: {', '.join(str(v) for v in levels)}"
              + (f"  (shuffled, seed {args.shuffle})" if args.shuffle is not None else ""))
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "sweep-design.json").write_text(json.dumps({
            "levels": levels, "replicates": args.replicates, "shuffle_seed": args.shuffle,
            "pairs": args.pairs,
            "playback": str(args.playback) if args.playback else None,
            "playback_sha256": ab.sha256(args.playback) if args.playback else None,
        }, indent=2) + "\n")
        for take in record(levels, args.pairs, args.out, output_volume(), args.playback):
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
        rows.append(analyse(name, take, args.whisper, args.language, args.repeats))

    def pct(row: dict, cond: str, key: str) -> str:
        b = row["conditions"][cond][key]
        if b is None:
            return "n/a"
        return f"{b['mean'] * 100:.0f}% ({b['min'] * 100:.0f}-{b['max'] * 100:.0f})"

    def dbfs(v) -> str:
        return f"{v:.1f}" if v is not None else "n/a"

    print(f"\n{'take':12s} {'echo':>8s} {'operator':>9s} {'S/E':>8s}   "
          f"{'raw recall':>14s} {'aec3 recall':>14s}   "
          f"{'raw leak':>14s} {'aec3 leak':>14s}")
    for r in rows:
        lv = r["level"]
        ser = f"{lv['ser_db']:+.1f} dB" if lv.get("ser_db") is not None else "n/a"
        print(f"{r['name']:12s} {dbfs(lv.get('echo_dbfs')):>8s} "
              f"{dbfs(lv.get('operator_dbfs')):>9s} {ser:>8s}   "
              f"{pct(r, 'raw', 'recall'):>14s} {pct(r, 'aec3', 'recall'):>14s}   "
              f"{pct(r, 'raw', 'leakage'):>14s} {pct(r, 'aec3', 'leakage'):>14s}")
        if lv.get("why"):
            print(f"{'':12s} {lv['why']}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
