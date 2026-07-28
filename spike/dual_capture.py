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
            try:
                self.log_lines.append(json.loads(line))
            except (ValueError, TypeError):
                pass

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
            l for l in self.log_lines
            if l.get("message_type") in ("error", "fatal")
        ]


class MicLeg(Leg):
    def __init__(self):
        super().__init__("mic")
        self.stream = None

    def start(self):
        self.stream = sd.InputStream(
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


def bleed(mic, tap):
    """Peak normalised cross-correlation between the two legs' envelopes.

    High correlation means the microphone is hearing what the speakers are
    playing — the Me/Them split is contaminated and needs echo cancellation or
    headphones.
    """
    a, b = envelope(mic), envelope(tap)
    n = min(len(a), len(b))
    if n < ENVELOPE_HZ:  # under a second of overlap
        return None
    a, b = a[:n], b[:n]
    a = a - a.mean()
    b = b - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
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
    return {"peak_r": best_r, "lag_ms": best_lag * 1000 / ENVELOPE_HZ}


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
    stats = {}
    for leg in (mic_leg, tap_leg):
        s = leg.rate_stats()
        stats[leg.name] = s
        if not s:
            print(f"  {leg.name:7s} too few blocks to measure")
            continue
        print(
            f"  {leg.name:7s} measured {s['measured_rate']:.3f} Hz "
            f"({s['ppm']:+.0f} ± {s['uncertainty_ppm']:.0f} ppm) over {s['span_s']:.2f}s"
        )

    if stats.get("mic") and stats.get("system"):
        rel_ppm = stats["mic"]["ppm"] - stats["system"]["ppm"]
        # Endpoint quantisation is independent per leg, so the relative figure
        # carries both legs' uncertainty.
        rel_unc = (
            stats["mic"]["uncertainty_ppm"] ** 2 + stats["system"]["uncertainty_ppm"] ** 2
        ) ** 0.5
        print(f"\n  relative drift  {rel_ppm:+.0f} ± {rel_unc:.0f} ppm")

        if abs(rel_ppm) <= rel_unc:
            worst = max(s["block_period_s"] for s in stats.values() if s)
            need_min = worst / 50e-6 / 60
            print(
                "  INDISTINGUISHABLE FROM ZERO at this capture length — the "
                "measurement\n  cannot resolve real hardware drift (tens of ppm) "
                f"until the capture runs\n  ~{need_min:.0f} minutes. Do not quote "
                "the number above as a finding."
            )
        else:
            hour_ms = rel_ppm * 3600 / 1000
            hour_unc = rel_unc * 3600 / 1000
            print(f"  projected over 60 min: {hour_ms:+.0f} ± {hour_unc:.0f} ms of divergence")

    start_skew = None
    if stats.get("mic") and stats.get("system"):
        start_skew = (stats["mic"]["first_arrival"] - stats["system"]["first_arrival"]) * 1000
        print(f"  start skew (first block arrival): {start_skew:+.0f} ms")

    b = bleed(mic, tap)
    print("\n=== speaker bleed ===")
    if not b:
        print("  not enough overlapping audio to measure")
    else:
        print(f"  peak envelope correlation {b['peak_r']:+.3f} at {b['lag_ms']:+.0f} ms lag")
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
    if b and abs(b["peak_r"]) > 0.5:
        print(
            "  NOTE: bleed is high, so expect every utterance to appear TWICE —\n"
            "  once as Me and once as Them. That is the contamination, not a\n"
            "  transcription bug. Re-run on headphones to see the real split.\n"
        )
    for start, label, text in merged:
        print(f"  [{int(start // 60):02d}:{start % 60:05.2f}] {label:4s} {text}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--whisper", default="mlx-community/whisper-large-v3-turbo")
    ap.add_argument("--language", default="en")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--out", default=None, help="output dir (default: spike/out)")
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else REPO / "spike" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    mic_leg, tap_leg = MicLeg(), TapLeg()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    tap_leg.start()
    mic_leg.start()
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
