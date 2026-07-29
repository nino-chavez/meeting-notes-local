#!/usr/bin/env python3
"""Dual-leg capture spike: system audio (Core Audio tap) + microphone.

Answers the two questions the design docs could not:

  1. How far do two independently-clocked 16 kHz streams drift over a meeting?
  2. Does the mic/system split actually produce a usable Me/Them transcript,
     or does speaker bleed contaminate the mic leg?

The system leg is the vendored `audiotee` binary (Core Audio process tap),
resampling to 16 kHz s16le inside the tap so the Python side never resamples.
The mic leg is sounddevice at 16 kHz float32 — the same capture path
`local-dictation` already uses.

Run:
    python spike/dual_capture.py --seconds 60
    python spike/dual_capture.py                 # until Ctrl-C
"""

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

RATE = 16_000
REPO = Path(__file__).resolve().parent.parent
TAP_BIN = REPO / "capture" / "audiotee" / ".build" / "release" / "audiotee"

# Envelope rate for the bleed cross-correlation. 100 Hz is fine enough to
# resolve syllable-scale energy and cheap enough to correlate over an hour.
ENVELOPE_HZ = 100
BLEED_MAX_LAG_S = 0.5

# Independent hardware clocks typically differ by tens of ppm, so a run has to
# resolve that scale before it can report a drift value rather than a bound.
HARDWARE_DRIFT_PPM = 50

# What the merge can absorb. It sorts Whisper segments, which run seconds long —
# a 57-minute meeting decoded into 769 of them, averaging 4.5 s. Divergence has
# to approach that scale before it can put two turns in the wrong order, so a
# bound comfortably under a second per hour settles the question for the merge
# even when it cannot produce a value.
MERGE_TOLERANCE_MS = 1000


class Leg:
    """One capture leg: float32 mono blocks plus the wall time each arrived."""

    def __init__(self, name):
        self.name = name
        self.blocks = []
        self.arrivals = []  # (monotonic, samples_in_this_block)
        self.lock = threading.Lock()

    def add(self, samples):
        if not len(samples):
            return
        with self.lock:
            self.blocks.append(samples)
            self.arrivals.append((time.monotonic(), len(samples)))

    def audio(self):
        with self.lock:
            if not self.blocks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self.blocks)

    def rate_stats(self):
        """Measured sample rate between first and last arrival, with error bars.

        Samples in the first block were produced before we saw it, so they are
        excluded — otherwise the first chunk's duration is counted against a
        wall span that had not yet started.

        The sample count is exact; the wall span is not. Both endpoints are
        known only to within roughly one block period, because a block is
        timestamped when the reader thread wakes up, not when the hardware
        produced it. That quantisation dominates the result at short spans:
        over 20 seconds of 200 ms blocks the uncertainty is ~9000 ppm, so any
        drift figure from a short capture is noise wearing a decimal point.
        Reported here so the caller cannot read the number without it.
        """
        with self.lock:
            arrivals = list(self.arrivals)
        if len(arrivals) < 3:
            return None
        t_first, _ = arrivals[0]
        t_last, _ = arrivals[-1]
        span = t_last - t_first
        produced = sum(n for _, n in arrivals[1:])
        if span <= 0:
            return None
        measured = produced / span
        block_period = np.median([n for _, n in arrivals[1:]]) / RATE
        return {
            "span_s": span,
            "samples_after_first": produced,
            "measured_rate": measured,
            "ppm": (measured / RATE - 1) * 1e6,
            "uncertainty_ppm": block_period / span * 1e6,
            "block_period_s": block_period,
            "first_arrival": t_first,
        }


class TapLeg(Leg):
    """System audio via the vendored audiotee binary."""

    def __init__(self):
        super().__init__("system")
        self.proc = None
        self.reader = None
        self.stderr_reader = None
        self.log_lines = []
        self._stop = threading.Event()

    def start(self):
        if not TAP_BIN.exists():
            raise SystemExit(
                f"tap binary missing: {TAP_BIN}\n"
                f"build it with:  (cd {TAP_BIN.parents[2]} && swift build -c release)"
            )
        self.proc = subprocess.Popen(
            [str(TAP_BIN), "--sample-rate", str(RATE)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.reader = threading.Thread(target=self._read_audio, daemon=True)
        self.reader.start()
        self.stderr_reader = threading.Thread(target=self._read_logs, daemon=True)
        self.stderr_reader.start()

    def _read_audio(self):
        fd = self.proc.stdout.fileno()
        while not self._stop.is_set():
            try:
                raw = os.read(fd, 1 << 16)
            except OSError:
                break
            if not raw:
                break
            # s16le mono -> float32 in [-1, 1), matching sounddevice's dtype.
            if len(raw) % 2:
                raw = raw[:-1]
            self.add(np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0)

    def _read_logs(self):
        for line in self.proc.stderr:
            # A malformed log line must never take down the capture thread.
            with contextlib.suppress(ValueError, TypeError):
                self.log_lines.append(json.loads(line))

    def stop(self):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.reader:
            self.reader.join(timeout=2)
        if self.stderr_reader:
            self.stderr_reader.join(timeout=2)

    def tap_error(self):
        """Upstream reports failures as JSON on stderr; surface them verbatim."""
        return [
            entry for entry in self.log_lines
            if entry.get("message_type") in ("error", "fatal")
        ]


class MicLeg(Leg):
    """Microphone capture.

    The device is resolved and named at startup rather than left implicit.
    sounddevice binds whatever macOS has as default input at the moment the
    stream opens, so connecting headphones after launch leaves the capture on
    the built-in microphone — or on silence. Across a 70-minute run that is
    unrecoverable, so the resolved device is printed before any audio arrives.
    """

    def __init__(self, device=None):
        super().__init__("mic")
        self.stream = None
        self.device = device
        self.device_name = None

    def start(self):
        self.device_name = sd.query_devices(
            self.device if self.device is not None else sd.default.device[0]
        )["name"]
        self.stream = sd.InputStream(
            device=self.device,
            samplerate=RATE,
            channels=1,
            dtype="float32",
            blocksize=RATE // 5,  # 200 ms, matching the tap's chunk duration
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, indata, frames, time_info, status):
        self.add(indata[:, 0].copy())

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None


def envelope(audio, rate=RATE, hz=ENVELOPE_HZ):
    """RMS energy envelope, used for the bleed correlation."""
    step = rate // hz
    n = len(audio) // step
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    trimmed = audio[: n * step].reshape(n, step)
    return np.sqrt((trimmed.astype(np.float64) ** 2).mean(axis=1)).astype(np.float32)


def active_span(env, floor_frac=0.05):
    """First and last frame where the envelope is meaningfully above silence.

    Returns None if nothing clears the floor.
    """
    if not len(env):
        return None
    loud = np.flatnonzero(env > floor_frac * float(env.max()))
    if not len(loud):
        return None
    return int(loud[0]), int(loud[-1]) + 1


def bleed(mic, tap):
    """Peak normalised cross-correlation between the two legs' envelopes.

    High correlation means the microphone is hearing what the speakers are
    playing — the Me/Them split is contaminated and needs echo cancellation or
    headphones.

    Measured over the system leg's active span rather than the whole capture.
    Silence on the system leg cannot demonstrate bleed in either direction — no
    audio is playing, so none can leak — but it still contributes microphone
    noise to the correlation's denominator and drags the result toward zero.
    Measured on a real capture, appending 40 minutes of empty room to a 14-second
    recording pulled +0.927 down to +0.826. That is the dangerous direction: a
    contaminated capture reads as clean, and the Me/Them split gets trusted when
    it shouldn't be. Trimming to the span makes a long over-run harmless.
    """
    a, b = envelope(mic), envelope(tap)
    n = min(len(a), len(b))
    if n < ENVELOPE_HZ:  # under a second of overlap
        return None
    a, b = a[:n], b[:n]

    span = active_span(b)
    if span is None:
        return None
    lo, hi = span
    if hi - lo < ENVELOPE_HZ:  # under a second of system-side activity
        return None
    analysed = (hi - lo) / n
    a, b = a[lo:hi], b[lo:hi]
    n = hi - lo
    a = a - a.mean()
    b = b - b.mean()
    # float() here at the boundary rather than at the call site. numpy's norm
    # returns a float32, and the `r /= denom` below silently converts every
    # correlation back into one — which json.dumps refuses to encode. That
    # surfaced as a crash in write_transcript at the very end of a 75-minute
    # capture, after both legs had already been transcribed, and it means the
    # handoff to the notes half had never once completed on a capture where
    # bleed was measurable at all.
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return None
    max_lag = int(BLEED_MAX_LAG_S * ENVELOPE_HZ)
    lags = range(-max_lag, max_lag + 1)
    best_r, best_lag = 0.0, 0
    for lag in lags:
        if lag < 0:
            r = float(np.dot(a[-lag:], b[: n + lag]))
        elif lag > 0:
            r = float(np.dot(a[: n - lag], b[lag:]))
        else:
            r = float(np.dot(a, b))
        r /= denom
        if abs(r) > abs(best_r):
            best_r, best_lag = r, lag
    return {
        "peak_r": best_r,
        "lag_ms": best_lag * 1000 / ENVELOPE_HZ,
        "analysed_frac": analysed,
        "analysed_s": n / ENVELOPE_HZ,
    }


def write_wav(path, audio):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def transcribe(audio, repo_id, language):
    import mlx_whisper

    if len(audio) < RATE // 2:
        return []
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=repo_id, language=language,
        condition_on_previous_text=False,
    )
    return [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
        for s in result.get("segments", [])
        if s.get("text", "").strip()
    ]


def start_skew_ms(stats):
    """How far apart the two legs' first blocks arrived, in milliseconds."""
    if not (stats.get("mic") and stats.get("system")):
        return None
    return (stats["mic"]["first_arrival"] - stats["system"]["first_arrival"]) * 1000


def drift_lines(stats):
    """The clock-drift section, returned rather than printed.

    Separated out because one of its branches was wrong for as long as it was
    unreachable. Reaching the branch where the divergence is bounded tightly
    requires a capture over an hour long, so nobody ever read its output: it
    told a 75-minute capture that it needed to run for 67 minutes, and quietly
    discarded the bound the run had actually established. A function taking a
    plain dict can be checked at any capture length in a second.
    """
    lines = []
    for name in ("mic", "system"):
        s = stats.get(name)
        if not s:
            lines.append(f"  {name:7s} too few blocks to measure")
            continue
        lines.append(
            f"  {name:7s} measured {s['measured_rate']:.3f} Hz "
            f"({s['ppm']:+.0f} ± {s['uncertainty_ppm']:.0f} ppm) over {s['span_s']:.2f}s"
        )

    if not (stats.get("mic") and stats.get("system")):
        return lines

    rel_ppm = stats["mic"]["ppm"] - stats["system"]["ppm"]
    # Endpoint quantisation is independent per leg, so the relative figure
    # carries both legs' uncertainty.
    rel_unc = (
        stats["mic"]["uncertainty_ppm"] ** 2 + stats["system"]["uncertainty_ppm"] ** 2
    ) ** 0.5
    lines.append(f"\n  relative drift  {rel_ppm:+.0f} ± {rel_unc:.0f} ppm")

    bound_ms = rel_unc * 3600 / 1000
    if abs(rel_ppm) > rel_unc:
        hour_ms = rel_ppm * 3600 / 1000
        lines.append(f"  projected over 60 min: {hour_ms:+.0f} ± {bound_ms:.0f} ms of divergence")
    else:
        # A run that resolves no drift value still bounds one, and the bound is
        # the figure the merge actually needs. Reporting only "cannot resolve"
        # throws that away: a 75-minute capture bounded the two legs at under a
        # quarter-second of divergence per hour, which answers the question the
        # merge asks even though it is not a value.
        lines.append(
            f"  no value resolvable, but bounded: under {bound_ms:.0f} ms of "
            "divergence per hour"
        )
        lines.append("  " + (
            "that is below the seconds-long segments the merge sorts, so drift "
            "cannot\n  reorder turns"
            if bound_ms <= MERGE_TOLERANCE_MS else
            "that is looser than the segments the merge sorts, so reordering is "
            "not\n  ruled out"
        ))
        if rel_unc > HARDWARE_DRIFT_PPM:
            worst = max(s["block_period_s"] for s in stats.values() if s)
            # The relative figure carries both legs' uncertainty in quadrature,
            # so each leg has to land a factor of sqrt(2) tighter than the
            # target for their difference to reach it. Sizing the run from a
            # single leg under-states the length by 41%, which is how a
            # 75-minute capture came back advising a 67-minute one.
            need_min = worst * 2 ** 0.5 / (HARDWARE_DRIFT_PPM * 1e-6) / 60
            lines.append(
                f"  measuring an actual drift value needs ~{need_min:.0f} min at this "
                f"{worst * 1000:.0f} ms block period,\n  or the same run with smaller "
                "blocks — the bound scales with both"
            )

    skew = start_skew_ms(stats)
    lines.append(f"  start skew (first block arrival): {skew:+.0f} ms")
    return lines


def report(mic_leg, tap_leg, args, out_dir):
    mic = mic_leg.audio()
    tap = tap_leg.audio()

    print("\n=== capture ===")
    for leg, audio in (("mic", mic), ("system", tap)):
        secs = len(audio) / RATE
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean())) if len(audio) else 0.0
        print(f"  {leg:7s} {len(audio):>9d} samples  {secs:6.2f}s  rms {rms:.5f}")

    errors = tap_leg.tap_error()
    if errors:
        print("\n  tap reported errors:")
        for e in errors:
            print(f"    {json.dumps(e.get('data', e))}")

    print("\n=== clock drift ===")
    stats = {leg.name: leg.rate_stats() for leg in (mic_leg, tap_leg)}
    for line in drift_lines(stats):
        print(line)
    start_skew = start_skew_ms(stats)

    b = bleed(mic, tap)
    print("\n=== speaker bleed ===")
    if not b:
        print("  no system-side audio to measure against — nothing was playing")
    else:
        print(f"  peak envelope correlation {b['peak_r']:+.3f} at {b['lag_ms']:+.0f} ms lag")
        print(
            f"  measured over {b['analysed_s']:.0f}s of system-side activity "
            f"({b['analysed_frac'] * 100:.0f}% of the capture)"
        )
        if start_skew is not None:
            # The legs are correlated from their own sample zero, so the raw lag
            # is dominated by however far apart they started. Subtracting the
            # independently-measured start skew leaves the acoustic path.
            print(
                f"  minus start skew: {b['lag_ms'] - start_skew:+.0f} ms "
                "(the acoustic component)"
            )
        if abs(b["peak_r"]) > 0.5:
            print("  HIGH — the mic is hearing the speakers; Me/Them split is contaminated")
        elif abs(b["peak_r"]) > 0.25:
            print("  MODERATE — some bleed present")
        else:
            print("  LOW — legs are acoustically independent (headphones, or quiet room)")

    write_wav(out_dir / "mic.wav", mic)
    write_wav(out_dir / "system.wav", tap)
    print(f"\n  wrote {out_dir}/mic.wav and {out_dir}/system.wav")

    if args.no_transcribe:
        return

    print("\n=== transcript ===")
    t0 = time.monotonic()
    mic_segs = transcribe(mic, args.whisper, args.language)
    tap_segs = transcribe(tap, args.whisper, args.language)
    print(f"  (transcribed both legs in {time.monotonic() - t0:.1f}s)\n")

    # Offset each leg by when its first block arrived, so the merge is against
    # one session clock rather than two per-leg clocks that started apart.
    origin = min(
        s["first_arrival"] for s in stats.values() if s
    ) if any(stats.values()) else 0.0
    merged = []
    for segs, leg, label in ((mic_segs, mic_leg, "Me"), (tap_segs, tap_leg, "Them")):
        s = stats.get(leg.name)
        offset = (s["first_arrival"] - origin) if s else 0.0
        for seg in segs:
            merged.append((seg["start"] + offset, label, seg["text"]))
    merged.sort(key=lambda r: r[0])

    if not merged:
        print("  (no speech detected on either leg)")
        return

    # The artifact lands before the 1200 lines of console output, not after.
    # When this ran the other way round, a crash while serialising discarded
    # four and a half minutes of transcription that had already succeeded —
    # the expensive work was complete and unrecoverable because the cheap
    # step downstream of it failed.
    write_transcript(out_dir / "transcript.json", merged, b)

    if b and abs(b["peak_r"]) > 0.5:
        print(
            "  NOTE: bleed is high, so expect every utterance to appear TWICE —\n"
            "  once as Me and once as Them. That is the contamination, not a\n"
            "  transcription bug. Re-run on headphones to see the real split.\n"
        )
    for start, label, text in merged:
        print(f"  [{int(start // 60):02d}:{start % 60:05.2f}] {label:4s} {text}")


def write_transcript(path, merged, b):
    """Hand the capture to the notes half, carrying the bleed verdict with it.

    The attribution level is derived here rather than downstream, because this
    is the only place that knows how the audio was actually captured. A capture
    whose legs turned out to be correlated is not a Me/Them transcript that
    happens to be noisy — it is a transcript with no speaker information at all,
    and it has to arrive downstream saying so. Otherwise the measurement in this
    file and the notes written from it can disagree, and the notes will win.

    See notes/transcript.py for what each level licenses.
    """
    contaminated = b is not None and abs(b["peak_r"]) > 0.5
    payload = {
        "source": f"capture {time.strftime('%Y-%m-%d %H:%M')}",
        "attribution": "none" if contaminated else "channel",
        "bleed": {"peak_r": b["peak_r"], "analysed_s": b["analysed_s"]} if b else None,
        "turns": [
            # Labels are dropped, not merely marked, when the split is fiction.
            {
                "start": round(start, 2),
                "speaker": None if contaminated else label,
                "text": text,
            }
            for start, label, text in merged
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
    verdict = (
        "unattributed — bleed made the split unusable"
        if contaminated else "Me/Them preserved"
    )
    print(f"\n  wrote {path} ({verdict})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--whisper", default="mlx-community/whisper-large-v3-turbo")
    ap.add_argument("--language", default="en")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--out", default=None, help="output dir (default: spike/out)")
    ap.add_argument(
        "--input-device", default=None,
        help="microphone: device index, or a substring of its name "
             "(default: whatever macOS has as default input at launch)",
    )
    ap.add_argument(
        "--list-devices", action="store_true",
        help="print available audio devices and exit",
    )
    args = ap.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    device = args.input_device
    if device is not None and device.isdigit():
        device = int(device)

    out_dir = Path(args.out) if args.out else REPO / "spike" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    mic_leg, tap_leg = MicLeg(device), TapLeg()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    tap_leg.start()
    mic_leg.start()

    # Name both devices before any audio arrives. The tap follows the default
    # OUTPUT device, so that is the one that decides what lands on the system
    # leg — worth seeing alongside the microphone.
    out_name = sd.query_devices(sd.default.device[1])["name"]
    print(f"  mic    → {mic_leg.device_name}")
    print(f"  system → tap on default output: {out_name}")
    print(f"capturing — {'Ctrl-C to stop' if not args.seconds else f'{args.seconds:g}s'}")

    deadline = time.monotonic() + args.seconds if args.seconds else None
    try:
        while not stop.is_set():
            if deadline and time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    finally:
        mic_leg.stop()
        tap_leg.stop()

    report(mic_leg, tap_leg, args, out_dir)


if __name__ == "__main__":
    sys.exit(main())
