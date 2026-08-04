#!/usr/bin/env python3
"""Walk the operator through the three calibration takes the encoder gate needs.

The gate-classification comparison (`encoder-packaging/bench_gate_agreement.py`)
needs exactly three recordings: two sittings of the operator talking, at least an
hour apart, and one take of speech that is known not to be the operator. The
capture tool records them, but it narrates nothing: run bare, `dual_capture.py`
opens the microphone and prints audio statistics until Ctrl-C, and the operator
is left to remember which take this is, whether to speak, whether anything may
be playing, and when to stop. The first documented version of this errand also
told the operator to pass `--no-transcribe` — which returns before
`mic-segments.json` is ever written, so the harness's `prepare` step would have
failed after all three takes were already recorded. Segments come FROM
transcription; the flag and the errand are incompatible.

So this wrapper owns the scenario and nothing else. Before each take it says
what the room must sound like, when to speak, and when the recording stops.
After each take it validates against the floors `speaker_gate.py` actually
enforces — imported from there, not copied — so a bad take costs four minutes,
not the discovery a week later that the whole errand has to be redone. When all
three takes pass, it prints the exact harness commands with the real paths
filled in.

What is stored, and where: transcription is on, so what the operator says lands
as text in `mic-segments.json` beside each recording. It stays on this machine,
the comparison uses only the segment timestamps, and the refusal below keeps
the directory outside the repository. The operator deletes the tree after the
admission verdict; only the report's numbers survive into RESULTS.md.

Run (from the repository root, inside the venv):
    .venv/bin/python spike/calibrate_voice.py                 # guides the next take
    .venv/bin/python spike/calibrate_voice.py --status        # report only, no recording
    .venv/bin/python spike/calibrate_voice.py --take negative # redo one take
    .venv/bin/python spike/calibrate_voice.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import wave
from pathlib import Path
from typing import NamedTuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aec_bound as ab
import speaker_gate as sg

DEFAULT_DIR = Path.home() / "calib"
SITTING_SECONDS = 300.0
NEGATIVE_SECONDS = 240.0

# speaker_gate refuses to score a sitting with only MIN_ENROLL_SEGMENTS scorable
# segments, because leave-one-out needs one more than the enrollment floor. The
# +1 is that rule, not a preference of this file.
MIN_SITTING_SCORABLE = sg.MIN_ENROLL_SEGMENTS + 1

TAKES = ("sitting1", "sitting2", "negative")

CARDS = {
    "sitting": (
        "Quiet room. Nothing playing on this Mac or nearby — the take is refused "
        "if the system leg heard playback, because a sitting must be your voice "
        "alone.",
        "Talk naturally the WHOLE time, the way you would in a meeting: think out "
        "loud, describe your day, narrate what you're working on. Reading aloud "
        "works but runs flatter than conversation. Pauses are fine.",
        f"It records for {SITTING_SECONDS / 60:.0f} minutes and stops itself.",
        "What you say is transcribed into mic-segments.json in this folder. It "
        "never leaves this machine and the comparison uses only the timestamps; "
        "delete the folder after the admission verdict.",
        "macOS may ask for microphone access — allow it.",
    ),
    "negative": (
        "You stay SILENT for the whole take.",
        "Start spoken audio playing FIRST, before you continue — a podcast or "
        "audiobook, talking rather than music, loud enough that this Mac's "
        "microphone hears it. Speakers, not headphones. Playing it from another "
        "device also works.",
        f"It records for {NEGATIVE_SECONDS / 60:.0f} minutes and stops itself.",
        "This is the 'known not to be you' evidence. If a consenting person "
        "speaks instead of playback, the final command's source class changes "
        "from public-or-licensed to consenting-person.",
    ),
}


class Verdict(NamedTuple):
    state: str  # "absent" | "retake" | "ok"
    detail: str


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def _leg(take_dir: Path, leg: str) -> tuple[list[dict], dict]:
    """One leg's segments, digest-bound, plus the raw payload for captured_at.

    `sg.load_segments` already refuses the six ways a segment file can lie about
    its recording; re-parsing here would be the weaker second copy that file's
    own docstring warns against. The raw payload is read only for `captured_at`,
    which the loader does not return.
    """
    segs = sg.load_segments(take_dir / f"{leg}-segments.json",
                            take_dir / f"{leg}.wav", leg=leg)
    payload = json.loads((take_dir / f"{leg}-segments.json").read_text())
    return segs, payload


def _scorable(segs: list[dict]) -> list[float]:
    return [s["end"] - s["start"] for s in segs
            if s["end"] - s["start"] >= sg.MIN_SCORABLE_S]


def assess_take(take_dir: Path, take: str) -> Verdict:
    """Whether one recorded take satisfies the floors the harness will enforce.

    Everything here re-derives from the recording; nothing trusts this wrapper's
    own earlier printout. The floors come from speaker_gate so a change there
    changes this verdict without a second edit.
    """
    if not take_dir.is_dir():
        return Verdict("absent", "not recorded yet")
    if not (take_dir / "mic-segments.json").exists():
        return Verdict("retake", "capture did not finish — no mic-segments.json "
                                 "was written. Re-record this take.")
    try:
        mic_segs, _ = _leg(take_dir, "mic")
    except Exception as exc:  # the loader's refusals are the diagnosis
        return Verdict("retake", f"mic segments unusable: {exc}")

    scorable = _scorable(mic_segs)
    if take == "negative":
        seconds = float(sum(scorable))
        if (len(scorable) < sg.MIN_NEGATIVE_SCORABLE_SEGMENTS
                or seconds < sg.MIN_NEGATIVE_SCORABLE_SECONDS):
            return Verdict(
                "retake",
                f"only {len(scorable)} scorable segments / {seconds:.0f}s of "
                f"scorable speech; the registered floor is "
                f"{sg.MIN_NEGATIVE_SCORABLE_SEGMENTS} segments and "
                f"{sg.MIN_NEGATIVE_SCORABLE_SECONDS:.0f}s. Use continuous spoken "
                f"audio (not music), louder or longer, and re-record.")
        return Verdict("ok", f"{len(scorable)} scorable segments, {seconds:.0f}s")

    # A sitting: enough of the operator, and nobody else.
    if len(scorable) < MIN_SITTING_SCORABLE:
        return Verdict(
            "retake",
            f"only {len(scorable)} segments reach {sg.MIN_SCORABLE_S:g}s; at "
            f"least {MIN_SITTING_SCORABLE} are needed to score any one of them. "
            f"Talk more continuously and re-record.")
    try:
        sys_segs, _ = _leg(take_dir, "system")
    except Exception as exc:
        return Verdict("retake", f"system-leg segments unusable: {exc}")
    if sys_segs:
        return Verdict(
            "retake",
            f"this Mac was playing audio during the sitting ({len(sys_segs)} "
            f"speech segments on the system leg). A sitting must be your voice "
            f"alone — close players and notifications and re-record.")
    return Verdict("ok", f"{len(scorable)} scorable segments")


def _captured_at(take_dir: Path) -> dt.datetime:
    _, payload = _leg(take_dir, "mic")
    return dt.datetime.fromisoformat(payload["captured_at"]).astimezone(dt.timezone.utc)


def gap_wait_seconds(root: Path, now: dt.datetime) -> float:
    """Seconds until sitting2 may start; <= 0 means the gap is already met.

    The same `captured_at` window `speaker_gate._sitting_problems` checks —
    enforced here BEFORE recording, because discovering a 40-minute gap after
    a five-minute take costs the take.
    """
    earliest = _captured_at(root / "sitting1") + dt.timedelta(
        seconds=sg.MIN_SITTING_GAP_S)
    return (earliest - now).total_seconds()


def assess_all(root: Path, now: dt.datetime) -> dict[str, Verdict]:
    verdicts = {t: assess_take(root / t, t) for t in TAKES}
    if verdicts["sitting1"].state == "ok" and verdicts["sitting2"].state == "ok":
        gap = (_captured_at(root / "sitting2")
               - _captured_at(root / "sitting1")).total_seconds()
        if gap < sg.MIN_SITTING_GAP_S:
            verdicts["sitting2"] = Verdict(
                "retake",
                f"captured {gap / 60:.0f} minutes after sitting1; separate "
                f"sittings means at least {sg.MIN_SITTING_GAP_S // 3600}h apart. "
                f"Re-record it later — different days are ideal.")
    return verdicts


def next_take(verdicts: dict[str, Verdict], root: Path,
              now: dt.datetime) -> tuple[str | None, str]:
    """Which take to record next, ordered so the mandatory hour is never idle.

    sitting1 first; the negative take fills the enforced gap before sitting2,
    because it is the one take that does not care what time it is.
    """
    if verdicts["sitting1"].state != "ok":
        return "sitting1", "start here"
    if verdicts["negative"].state != "ok":
        return "negative", "records now — it fills the wait before sitting2"
    if verdicts["sitting2"].state != "ok":
        wait = gap_wait_seconds(root, now)
        if wait > 0:
            return None, (f"all that remains is sitting2, and it unlocks in "
                          f"{wait / 60:.0f} min (≥1h after sitting1; different "
                          f"days are ideal). Run this again then.")
        return "sitting2", "the hour has passed"
    return None, "all three takes pass — run the harness commands below"


def completion_commands(root: Path) -> str:
    """The exact harness invocation for this directory, nothing to adapt.

    public-or-licensed is emitted because playback is the documented default;
    the card says when to change it to consenting-person.
    """
    return textwrap.dedent(f"""\
        .venv/bin/python spike/encoder-packaging/bench_gate_agreement.py prepare \\
          --calibrate {root}/sitting1/mic-segments.json {root}/sitting1/mic.wav \\
          --calibrate {root}/sitting2/mic-segments.json {root}/sitting2/mic.wav \\
          --against public-or-licensed {root}/negative/mic-segments.json {root}/negative/mic.wav \\
          --work-dir {root}/agreement-work

        .venv/bin/python spike/encoder-packaging/bench_gate_agreement.py compare \\
          --work-dir {root}/agreement-work \\
          --onnx apps/desktop/vendor/downloads/ecapa-tdnn.onnx \\
          --json-out {root}/agreement.json

        # The work directory holds waveform slices and embeddings of your voice:
        rm -rf {root}/agreement-work""")


def print_status(root: Path, now: dt.datetime) -> dict[str, Verdict]:
    verdicts = assess_all(root, now)
    print(f"\ncalibration material in {root}:")
    for take in TAKES:
        v = verdicts[take]
        mark = {"ok": "PASS", "absent": "  — ", "retake": "REDO"}[v.state]
        print(f"  {mark}  {take:9s} {v.detail}")
    take, why = next_take(verdicts, root, now)
    if take:
        print(f"\nnext: {take} — {why}")
    else:
        print(f"\n{why}")
        if all(v.state == "ok" for v in verdicts.values()):
            print(f"\n{completion_commands(root)}\n")
            print("Record the report's numbers in RESULTS.md under check 1; the "
                  "verdict on what they admit is yours. After it, the whole "
                  f"{root} tree can be deleted — it holds your voice and the "
                  "transcribed text of these takes.")
    return verdicts


def _preflight() -> None:
    """Fail before the microphone opens, not after five minutes of talking.

    A take is validated by transcribing it, so a missing mlx_whisper would cost
    the whole recording at its very last step.
    """
    probe = subprocess.run(
        [sys.executable, "-c", "import sounddevice, mlx_whisper"],
        capture_output=True, text=True)
    if probe.returncode != 0:
        raise SystemExit(
            "the capture dependencies are not importable in this interpreter "
            f"({sys.executable}):\n{probe.stderr.strip()}\n"
            "Run from the repository venv: .venv/bin/python spike/calibrate_voice.py")


def _set_aside(take_dir: Path) -> None:
    """Failed takes move aside rather than being deleted.

    They are recordings of the operator's voice; this tool never deletes audio.
    The operator removes .retake-* directories when they choose.
    """
    if not take_dir.exists():
        return
    n = 1
    while (aside := take_dir.with_name(f"{take_dir.name}.retake-{n}")).exists():
        n += 1
    take_dir.rename(aside)
    print(f"  (previous attempt moved to {aside.name}; delete it whenever)")


def record_take(root: Path, take: str) -> Verdict:
    kind = "negative" if take == "negative" else "sitting"
    seconds = NEGATIVE_SECONDS if kind == "negative" else SITTING_SECONDS
    print(f"\n=== {take} ===")
    for line in CARDS[kind]:
        print(textwrap.fill(line, 78, initial_indent="  • ",
                            subsequent_indent="    "))
    try:
        input("\nPress Enter to start recording (Ctrl-C to stop a take early; "
              "it is validated either way) ")
    except (KeyboardInterrupt, EOFError):
        print("\nnot started.")
        raise SystemExit(1)

    _set_aside(root / take)
    cue = ("keep talking" if kind == "sitting"
           else "stay silent — keep the playback going")
    stop = threading.Event()

    def ticker() -> None:
        # Coarse on purpose: it counts from process spawn, not first audio
        # block, and exists to answer "is it still going?" — the recording's
        # own clock is authoritative for everything that matters.
        elapsed = 0
        while not stop.wait(60):
            elapsed += 60
            left = max(0.0, seconds - elapsed)
            print(f"  … about {left / 60:.0f} min left — {cue}")

    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("dual_capture.py")),
         "--out", str(root / take), "--seconds", str(seconds)])
    threading.Thread(target=ticker, daemon=True).start()
    # Ctrl-C reaches the child through the shared process group; the child
    # treats it as end-of-capture and still transcribes and writes. This parent
    # ignores it so it survives to validate whatever was written.
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        rc = child.wait()
    finally:
        stop.set()
        signal.signal(signal.SIGINT, previous)
    if rc != 0:
        return Verdict("retake", f"capture exited with status {rc} — see its "
                                 f"output above, then re-record.")
    verdict = assess_take(root / take, take)
    mark = "PASS" if verdict.state == "ok" else "REDO"
    print(f"\n  {mark}  {take}: {verdict.detail}")
    return verdict


def self_test() -> bool:
    """The decision logic on synthetic material — no audio, no models, no torch.

    Fixtures mirror `write_leg_segments`' exact payload shape because the real
    loader (`aec_bound.load_segments`) is in the path being tested; a looser
    fixture would test a parser this tool does not use.
    """
    failures: list[str] = []

    def check(name: str, ok: bool) -> None:
        (print(f"  ok  {name}") if ok else failures.append(name))
        if not ok:
            print(f"  FAIL {name}")

    def write_wav(path: Path, seconds: float) -> tuple[str, int]:
        samples = int(seconds * sg.RATE)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sg.RATE)
            w.writeframes(np.zeros(samples, dtype=np.int16).tobytes())
        return ab.sha256(path), samples

    def write_take(root: Path, take: str, mic_spans: list[tuple[float, float]],
                   captured_at: str, sys_spans: list[tuple[float, float]] = ()) -> None:
        d = root / take
        d.mkdir(parents=True)
        duration = max([e for _, e in [*mic_spans, *sys_spans]] or [10.0]) + 1.0
        for leg, spans in (("mic", mic_spans), ("system", sys_spans)):
            digest, samples = write_wav(d / f"{leg}.wav", duration)
            (d / f"{leg}-segments.json").write_text(json.dumps({
                "schema": "mic-segments/1", "timeline": f"{leg}-local",
                "leg": leg, "duration_s": round(duration, 3),
                "filtered": ["voicing"], "labels": None,
                "audio_sha256": digest, "audio_samples": samples,
                "captured_at": captured_at,
                "segments": [{"start": s, "end": e, "text": "fixture"}
                             for s, e in spans],
            }))

    talk = [(i * 10.0, i * 10.0 + 4.0) for i in range(5)]
    chatter = [(i * 5.0, i * 5.0 + 4.0) for i in range(25)]  # 100 s scorable
    now = dt.datetime(2026, 8, 4, 12, 0, tzinfo=dt.timezone.utc)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "calib"
        root.mkdir()
        v = assess_all(root, now)
        take, _ = next_take(v, root, now)
        check("empty directory starts at sitting1", take == "sitting1")

        write_take(root, "sitting1", talk, "2026-08-04T11:40:00+0000")
        v = assess_all(root, now)
        take, _ = next_take(v, root, now)
        check("sitting1 passes its floors", v["sitting1"].state == "ok")
        check("the wait is filled with the negative take", take == "negative")

        write_take(root, "negative", chatter, "2026-08-04T11:50:00+0000")
        v = assess_all(root, now)
        take, why = next_take(v, root, now)
        check("negative passes both registered floors", v["negative"].state == "ok")
        check("sitting2 stays locked until the hour passes",
              take is None and "unlocks" in why)
        check("the lock names the remaining minutes", "40 min" in why)

        later = dt.datetime(2026, 8, 4, 12, 45, tzinfo=dt.timezone.utc)
        take, _ = next_take(assess_all(root, later), root, later)
        check("sitting2 unlocks after the gap", take == "sitting2")

        write_take(root, "sitting2", talk, "2026-08-04T12:20:00+0000")
        v = assess_all(root, later)
        check("a sitting2 recorded early is refused even when present",
              v["sitting2"].state == "retake" and "40 minutes" in v["sitting2"].detail)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "calib"
        write_take(root, "sitting1", talk, "2026-08-04T10:00:00+0000",
                   sys_spans=[(3.0, 6.0)])
        v = assess_take(root / "sitting1", "sitting1")
        check("a sitting with playback on the system leg is refused",
              v.state == "retake" and "playing audio" in v.detail)

        write_take(root, "negative", talk, "2026-08-04T10:00:00+0000")
        v = assess_take(root / "negative", "negative")
        check("thin negative material is refused with both floors named",
              v.state == "retake" and "20 segments" in v.detail)

        write_take(root, "sitting2", [(0.0, 4.0), (5.0, 6.0)],
                   "2026-08-04T12:00:00+0000")
        v = assess_take(root / "sitting2", "sitting2")
        check("a sitting below the scoring floor is refused",
              v.state == "retake" and str(MIN_SITTING_SCORABLE) in v.detail)

        check("completion commands carry the real directory",
              str(root) in completion_commands(root))

    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all controls pass'}")
    return not failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR,
                    help=f"where the takes live (default {DEFAULT_DIR}); must be "
                         f"outside the repository")
    ap.add_argument("--status", action="store_true",
                    help="report and print next step without recording")
    ap.add_argument("--take", choices=TAKES, default=None,
                    help="record this specific take instead of the next needed one")
    ap.add_argument("--self-test", action="store_true",
                    help="run the decision-logic controls and exit")
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(0 if self_test() else 1)

    if ab.inside_repo(args.dir):
        raise SystemExit(f"{args.dir} is inside the repository working tree. "
                         f"These recordings carry your voice and transcribed "
                         f"speech; keep them outside it (default: {DEFAULT_DIR}).")
    args.dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now(dt.timezone.utc)
    verdicts = print_status(args.dir, now)
    take = args.take
    if take is None:
        take, _ = next_take(verdicts, args.dir, now)
        if take is None:
            return
    if args.status:
        return

    _preflight()
    if record_take(args.dir, take).state == "ok":
        print_status(args.dir, dt.datetime.now(dt.timezone.utc))


if __name__ == "__main__":
    main()
