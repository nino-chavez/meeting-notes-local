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
    python spike/dual_capture.py --protocol      # cued echo-calibration take

`--protocol` runs a fixed, timed schedule and writes `protocol.json` beside the
recordings. It exists because the echo experiments need one thing the audio
cannot supply: which intervals held the operator's voice. On speakers the far
end reaches the microphone and transcribes there, so voicing and transcription
both answer "was something audible", not "was it him". The schedule is fixed
before any audio exists, shown as visual cues during capture, and bound to the
recording by digest and sample count.
"""

import argparse
import contextlib
import hashlib
import json
import os
import queue
import signal
import struct
import subprocess
import sys
import textwrap
import threading
import time
import wave
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except ModuleNotFoundError:
    # Recording needs it; writing and reading this file's artifacts does not.
    # aec_bound's controls check that mic-segments.json and protocol.json
    # round-trip through the real writers here, and a control that can only run
    # on a machine with an audio stack is a control that stops being run.
    sd = None

RATE = 16_000
REPO = Path(__file__).resolve().parent.parent
TAP_BIN = REPO / "capture" / "audiotee" / ".build" / "release" / "audiotee"

# Envelope rate for the bleed cross-correlation. 100 Hz is fine enough to
# resolve syllable-scale energy and cheap enough to correlate over an hour.
ENVELOPE_HZ = 100
BLEED_MAX_LAG_S = 0.5

# Above this whole-capture positive correlation the Me/Them split is fiction and
# the transcript stops claiming one. Named rather than repeated: this number
# decided three things independently — the console verdict, the warning about
# doubled utterances, and whether write_transcript clears every speaker label —
# and a fourth now depends on it, since the voiceprint gate must run exactly when
# a label is being claimed. Four literal 0.5s that have to agree is a drift
# waiting to happen, and the drift would be silent in the direction that matters:
# labels cleared while the gate still deletes the operator to protect them.
BLEED_CONTAMINATED_R = 0.5
BLEED_MODERATE_R = 0.25

# Independent hardware clocks typically differ by tens of ppm, so a run has to
# resolve that scale before it can report a drift value rather than a bound.
HARDWARE_DRIFT_PPM = 50

# Speech gate. A segment is kept when this fraction of its span sits this far
# above the leg's own noise floor. The floor is estimated per leg rather than
# fixed, because a built-in microphone in a quiet room and one beside a fan
# differ by more than any constant survives. The absolute term catches the case
# the percentile cannot: a tap on an idle output device emits *exact* digital
# zero, and no multiplier lifts zero off the ground.
SPEECH_FLOOR_PCT = 10
SPEECH_MARGIN_DB = 8
SPEECH_ABS_FLOOR = 1e-4
SPEECH_MIN_VOICED = 0.25

# Per-segment bleed gate. A mic segment is dropped when its envelope is this
# correlated with the tap's around the lag bleed() measured, over at least this
# much span, searching this far either side of that lag. All three come from
# measurement — see drop_bled for the null, the positives, why the span floor is
# the load-bearing one, and what the gate does to a segment carrying the
# operator and the far end at once.
BLEED_SEG_R = 0.75
BLEED_SEG_MIN_S = 2.0
BLEED_SEG_LAG_S = 0.05

# There is deliberately no "tolerance" constant here. An earlier version had one
# set against segment duration, on the reasoning that divergence had to approach
# the length of a turn to reorder it. That is the wrong quantity: reordering
# depends on the gap between adjacent turns across the two legs, and two
# utterances 100 ms apart swap under 100 ms of slip however long they run.
# Measured on the 75-minute capture, cross-leg gaps ran a median of 1.9 s but 7%
# fell under a quarter-second — so no achievable bound makes reordering
# impossible, only rare. The report states the bound and names the quantity that
# decides it, rather than issuing a verdict it cannot support.


class WavWriter:
    """16-bit WAV written block by block, openable at every instant.

    Both legs used to accumulate in memory and reach disk only once the capture
    had finished, so anything that killed the process — a crash, a closed lid, a
    Ctrl-C caught in the wrong place — cost the meeting rather than the last few
    seconds of it.

    Frames now go down as they arrive and the two RIFF size fields are patched
    afterwards, so a run that dies mid-capture leaves a short file rather than
    no file. Killed with SIGKILL three seconds in, the result reopens at exactly
    the fourteen blocks that had been handed over.

    The sizes are patched with pwrite at fixed offsets rather than by seeking
    back and returning, because a seek-based patch has to restore the append
    position afterwards and anything interrupting it between the two leaves the
    next block writing into the header. Writing the sizes *after* the frames
    they describe is the other half of it: the reverse order leaves a header
    claiming frames that were never written, which is the failure that looks
    like a valid file and is not.

    The thread is not decoration. Mic blocks arrive on sounddevice's callback,
    where a blocking syscall risks a dropout in the recording this exists to
    protect, so the callback only hands the block over.

    flush() is the right durability level here. The page cache outlives a killed
    process, which is the failure being defended against; a power loss would
    need fsync and is not.

    The first block opens the file, not the constructor. A capture that dies
    before any audio arrives — an unresolvable --input-device, a tap that will
    not build — must not truncate the previous run's recording on its way to
    reporting why it failed.
    """

    def __init__(self, path):
        self.path = path
        self.file = None
        self.frames = 0
        self.error = None
        self.pending = queue.SimpleQueue()
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    @staticmethod
    def _header(frames):
        n = frames * 2
        return (
            b"RIFF" + struct.pack("<I", 36 + n)
            + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
            + b"data" + struct.pack("<I", n)
        )

    def write(self, samples):
        self.pending.put(samples)

    def _drain(self):
        try:
            while (samples := self.pending.get()) is not None:
                if self.file is None:
                    # Not a context manager: the file is open for the length of
                    # the capture and closed by close(), which is the class.
                    self.file = open(self.path, "wb")  # noqa: SIM115
                    self.file.write(self._header(0))
                self.file.write((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
                self.file.flush()
                self.frames += len(samples)
                # pwrite rather than seek-and-return: it lands at an offset
                # without moving the append position, so there is no ordering
                # left to get wrong between the two writes.
                fd = self.file.fileno()
                os.pwrite(fd, struct.pack("<I", 36 + self.frames * 2), 4)
                os.pwrite(fd, struct.pack("<I", self.frames * 2), 40)
        except Exception as exc:
            # Stashed rather than raised. A writer that dies silently is the
            # same defect as a gate that drops speech silently — the caller
            # reports it and rewrites the leg from memory.
            self.error = exc

    def close(self):
        self.pending.put(None)
        self.thread.join(timeout=10)
        if self.file is not None:
            self.file.close()


class Leg:
    """One capture leg: float32 mono blocks plus the wall time each arrived."""

    def __init__(self, name, wav_path):
        self.name = name
        self.blocks = []
        self.arrivals = []  # (monotonic, samples_in_this_block)
        self.dropouts = []  # (monotonic, driver status) — see MicLeg._callback
        self.lock = threading.Lock()
        self.writer = WavWriter(wav_path)

    def add(self, samples):
        if not len(samples):
            return
        self.writer.write(samples)
        with self.lock:
            self.blocks.append(samples)
            self.arrivals.append((time.monotonic(), len(samples)))

    def stop(self):
        """Drain the incremental writer. Subclasses stop their source first."""
        self.writer.close()

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

    def __init__(self, wav_path):
        super().__init__("system", wav_path)
        self.proc = None
        self.reader = None
        self._tail = b""   # half a sample carried between pipe reads
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
            #
            # A pipe read can split a sample across two reads. The odd byte used
            # to be DISCARDED, which is not a rounding error: dropping one byte
            # shifts every following sample by one, so the low byte of each pairs
            # with the high byte of the next and the remainder of the capture
            # decodes as noise. Carrying it forward is the only way the stream
            # stays sample-aligned, and it costs one byte of state.
            raw = self._tail + raw
            if len(raw) % 2:
                raw, self._tail = raw[:-1], raw[-1:]
            else:
                self._tail = b""
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
        super().stop()

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

    def __init__(self, device, wav_path):
        super().__init__("mic", wav_path)
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
        # `status` was discarded. It carries input overflow, which is the
        # hardware telling us samples were lost — the one event that silently
        # breaks alignment between the legs, because the leg keeps counting
        # blocks while the timeline underneath it has a hole. Recording it is
        # what lets report() say so instead of presenting a shortened leg as a
        # complete one.
        if status:
            self.dropouts.append((time.monotonic(), str(status)))
        self.add(indata[:, 0].copy())

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        super().stop()


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
    best_pos_r, best_pos_lag = 0.0, 0
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
        if r > best_pos_r:
            best_pos_r, best_pos_lag = r, lag
    return {
        # Two readings of one correlogram, for two different questions.
        # peak_r is by |r| and answers "are these legs related at all", which is
        # what the attribution contract needs — unchanged.
        "peak_r": best_r,
        "lag_ms": best_lag * 1000 / ENVELOPE_HZ,
        # The acoustic path can only add a POSITIVE copy of the far end, so
        # anything centring a search on the lag of the strongest correlation
        # needs this one. On all four quiet captures measured here the |r| peak
        # is negative — turn-taking, at a lag with no physical meaning — and
        # searching around it would look for bleed where bleed cannot be, find
        # nothing, and say nothing.
        "positive_r": best_pos_r,
        "positive_lag_ms": best_pos_lag * 1000 / ENVELOPE_HZ,
        "analysed_frac": analysed,
        "analysed_s": n / ENVELOPE_HZ,
    }


def contaminated(b):
    """Whether this capture's Me/Them split is fiction.

    positive_r, not abs(peak_r). An acoustic path ADDS the far end to the mic, so
    bleed is positive correlation; a strong negative peak is turn-taking, which is
    the signature of a clean headphones capture. Judging on absolute value
    condemns exactly the captures this verdict exists to certify — two perfectly
    complementary legs give peak_r = -1.0 and were once reported as contaminated.

    `None` means nothing played, so nothing could leak. Not contaminated.
    """
    return b is not None and b["positive_r"] > BLEED_CONTAMINATED_R


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
        # A run that resolves no drift value still bounds one, and reporting
        # only "cannot resolve" throws that away. A 75-minute capture bounded
        # the two legs at under a quarter-second of divergence per hour, which
        # is a usable engineering figure even though it is not a value.
        lines.append(
            f"  no value resolvable, but bounded: under {bound_ms:.0f} ms of "
            "divergence per hour"
        )
        lines.append(
            "  what that costs depends on how close adjacent turns are ACROSS the "
            "two legs,\n  not on how long they run — see spike/RESULTS.md for the "
            "measured spacing"
        )
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


def voiced_fraction(env, start, end, thresh):
    """How much of [start, end) sits above `thresh`, in envelope frames."""
    lo = max(int(start * ENVELOPE_HZ), 0)
    hi = min(max(int(end * ENVELOPE_HZ), lo + 1), len(env))
    window = env[lo:hi]
    return float((window > thresh).mean()) if len(window) else 0.0


def drop_unvoiced(segs, audio, label):
    """Remove transcript segments that no voiced audio backs.

    Whisper does not return nothing when handed silence — it returns text. The
    microphone leg of a 75-minute capture of an empty room produced 400 turns,
    92 of them the single line "Thank you." at 30-second intervals: one
    confabulation per empty decode window. Left in, they reach the merge, are
    given a speaker label because bleed measured low, and arrive at the notes
    half as things the operator said. Bleed corrupts the Me/Them split when the
    capture is dirty; this corrupts it when the capture is clean.

    Energy alone does not separate them. A keyboard click clears any peak
    threshold that a hallucination fails, so a peak test removed 85% of the
    confabulations only by discarding 11% of everything else. Sustained voicing
    separates them properly: measured over that capture's 400 turns, the
    fraction of each segment's span above the leg's own noise floor ran a median
    of 0.01 for the repeated confabulation against 0.75 for the rest. With a
    gap that wide the exact cut point barely matters, which is the sign of a
    feature that is actually measuring the right thing.

    This runs after transcription rather than gating the audio before it. Gating
    first would save the compute, but it decides what Whisper never sees, and
    the failure it risks — silently dropping real speech — is worse than the one
    it prevents. Filtering afterwards is checkable against the transcript that
    was actually produced.
    """
    if not segs:
        return segs
    env = envelope(audio)
    if not len(env):
        return segs
    floor = float(np.percentile(env, SPEECH_FLOOR_PCT))
    thresh = max(floor * 10 ** (SPEECH_MARGIN_DB / 20), SPEECH_ABS_FLOOR)
    kept = [
        s for s in segs
        if voiced_fraction(env, s["start"], s["end"], thresh) >= SPEECH_MIN_VOICED
    ]
    if len(kept) != len(segs):
        print(
            f"  {label}: dropped {len(segs) - len(kept)} of {len(segs)} segments with "
            f"no voiced audio behind them (floor {thresh:.5f})"
        )
    return kept


def segment_bleed_r(mic_env, tap_env, start, end, lag_frames):
    """Peak correlation of one mic segment's envelope against the tap's.

    bleed() pairs mic frame j with tap frame j + lag, so the same convention
    holds here: the window comes from the mic, its comparison window from the
    tap, shifted by the lag the capture already measured. Both sides are clipped
    to whatever overlap survives the shift rather than the shift being skipped
    when it runs off an end. Skipping returns 0.0, which reads as clean, and the
    segments it would silently exempt are the ones at the very start of a
    capture — where a negative lag always runs off — which is exactly where a
    speakers run puts its first bled utterance.

    Positive correlation only, because the acoustic path can only add a positive
    copy of the far end. A mic segment that anti-correlates with the tap is two
    people taking turns, which is the opposite of bleed. Empirically this buys
    little at the duration floor drop_bled applies — over the null there, the
    signed 99th percentile is 0.392 against 0.424 unsigned, and the maxima are
    identical — so it is here on the physics, not on the margin.

    Returns 0.0 when the tap is flat across the window, or when no shift leaves
    BLEED_SEG_MIN_S to compare. Nothing was playing, so nothing could leak.
    """
    lo = max(int(start * ENVELOPE_HZ), 0)
    hi = min(int(end * ENVELOPE_HZ), len(mic_env))
    # round, not int: 0.05 has no exact binary form, and a product landing a
    # hair under would silently narrow the search without failing anything.
    search = round(BLEED_SEG_LAG_S * ENVELOPE_HZ)
    best = 0.0
    for lag in range(lag_frames - search, lag_frames + search + 1):
        t_lo = max(lo + lag, 0)
        # The floor applies to the span actually compared, not to the segment's
        # nominal duration — a clipped window is shorter than the caller thinks.
        n = min(hi + lag, len(tap_env)) - t_lo
        n = min(n, len(mic_env) - (t_lo - lag))
        if n < BLEED_SEG_MIN_S * ENVELOPE_HZ:
            continue
        a = mic_env[t_lo - lag:t_lo - lag + n].astype(np.float64)
        b = tap_env[t_lo:t_lo + n].astype(np.float64)
        a = a - a.mean()
        b = b - b.mean()
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            continue
        best = max(best, float(np.dot(a, b)) / denom)
    return best


def drop_bled(segs, mic, tap, b, label):
    """Remove mic segments that are the far end arriving back through the room.

    bleed() answers this question for the whole capture and its answer is
    all-or-nothing: above 0.5 every label is dropped, below it every label is
    kept. A capture bled across only part of its span reads clean by that test.
    Synthesised at the level the two real speakers captures recorded — the far
    end mixed into the quiet stretches of the 75-minute capture, 25 ms late, at
    a microphone RMS of 0.005 against the 0.006 those captures measured — the
    whole-capture figure comes back at +0.43. Under the cut, labels kept, and
    every bled span reaches the notes half as something the operator said. This
    gate drops 88% of them and none of that capture's 275 real mic segments; at
    half the bleed level, where the whole-capture figure is +0.19, it still
    drops 68% and still none of the 275.

    The expensive half of acoustic echo cancellation is estimating what the far
    end sounded like. The tap is that signal exactly, and bleed() has already
    measured the lag, so a segment can simply be asked whether it is a copy of
    it. This gate is drop_unvoiced one level up: that one asks whether a segment
    has audio behind it, this one asks whether the audio is the far end.

    Both classes below are measured on real recordings:

      null      the volume-0 capture, whose mic leg is a room the far end never
                reached. Its 197 segments of at least two seconds, scored at 21
                lags across the search window because the lag is itself a draw:
                4137 trials, median 0.000, p99 0.392, maximum 0.679, none at or
                above the cut.
      bled      the only two captures in this project with real speaker bleed,
                at +0.809 and +0.889 whole-capture. Their mic segments score
                0.920 and 0.956.

    The cut is 0.75, and any cut from 0.68 to 0.92 gives the same verdict on
    every real segment on either side. That insensitivity is the point — it is
    the same wide-gap signature drop_unvoiced has, and the same reason to
    believe the feature rather than the threshold.

    The two-second floor is not caution; it is where the null becomes usable at
    all. The same capture's 78 shorter segments reach 0.679's neighbourhood and
    beyond — 0.840, one of them over the cut — across the same lags. Duration-
    matched windows say it from the other side: half-second windows of that room
    reach 0.981, as convincing as real bleed, against 0.838 at a second and
    0.661 at two. Segments under the floor are kept, and that is the residual
    this gate ships with: 78 of that capture's 275 turns are too short to test.

    The lag is bleed()'s POSITIVE peak, not its |r| peak. On all four quiet
    captures measured here the |r| peak is negative — turn-taking, at a delay no
    echo can have — and a search centred there looks for bleed where bleed
    cannot be, finds nothing, and prints nothing, which is the worst available
    way for this gate to fail. The search spans ±50 ms around that lag because
    it is one average over the capture's whole active span: at the +4 ppm
    relative drift this project measured that covers hours, and at the ±63 ppm
    its error bars still permit, thirteen minutes.

    What this does NOT catch is the operator talking over the far end. Modelled
    in the envelope domain — power-summing the tap into the 76 gated segments
    where it was playing at all, which is a model and not a measurement, since
    no capture in this project has both voices on the mic leg at once — the gate
    stays silent 6 dB below the operator's own level at the microphone, fires on
    a tenth of segments 3 dB below it, and on two thirds at equal level. The two
    speakers captures put bled speech at 0.006 RMS against 0.010 for room speech
    on the same microphone, so a real
    operator, closer to it than the room is, sits below that line. Untested
    rather than safe: no recording of the operator on this microphone exists,
    which is the same missing sample RESULTS.md names as the blocker for the
    voiceprint gate.

    Only the mic leg is gated. Bleed has one direction — the room cannot leak
    into a tap that reads the render stream before it reaches any hardware.
    """
    if not segs or b is None:
        return segs
    mic_env, tap_env = envelope(mic), envelope(tap)
    if not len(mic_env) or not len(tap_env):
        return segs
    # positive_lag_ms, not lag_ms. bleed() reports its peak by |r|, and on a
    # capture with no bleed that peak is routinely negative at a lag with no
    # physical meaning — all four quiet captures behave that way. Centring the
    # segment search there would hunt for an echo at a delay no echo can have.
    lag_frames = round(b["positive_lag_ms"] * ENVELOPE_HZ / 1000)
    kept, dropped_s = [], 0.0
    for s in segs:
        if segment_bleed_r(mic_env, tap_env, s["start"], s["end"], lag_frames) >= BLEED_SEG_R:
            dropped_s += s["end"] - s["start"]
        else:
            kept.append(s)
    if len(kept) != len(segs):
        # Reported, always. A gate that silently discards speech is a worse
        # defect than the contamination it replaces, because the transcript then
        # omits words with no record that it did — the failure Teams warns about
        # for the same class of gate.
        print(
            f"  {label}: dropped {len(segs) - len(kept)} of {len(segs)} segments "
            f"({dropped_s:.1f}s) carrying the far end back through the room "
            f"(r >= {BLEED_SEG_R:.2f} at {b['positive_lag_ms']:+.0f} ms)"
        )
    return kept


def load_voiceprint(path, model_dir):
    """The operator's profile, its threshold, and where the encoder is cached.

    Loaded before capture starts, not before the transcript is filtered. A bad
    path or a profile from a different embedding space should cost the operator an
    error message, not a meeting — by the time the gate runs, the audio is
    recorded and the ASR has already spent minutes on it.
    """
    import speaker_gate as sg

    profile, threshold, doc = sg.load_profile(Path(path))
    doc["model_dir"] = model_dir
    return profile, threshold, doc


def drop_offprint(segs, mic, voiceprint, b, label, embed=None):
    """Remove mic segments that are not the operator's voice.

    The third and last filter on the microphone leg, and it asks the third
    question. `drop_unvoiced` asks whether audio is behind a segment.
    `drop_bled` asks whether that audio is the far end coming back through the
    room. This asks whether it is the operator at all — the case both of those
    are blind to, because a colleague at the next desk is voiced and is not the
    far end. Measured on the 75-minute capture: 114 of 802 merged turns, 14.2%,
    were other people talking near the laptop, transcribed cleanly and delivered
    to the notes labelled as the operator.

    **It runs only when a speaker label is being claimed.** Above
    `BLEED_CONTAMINATED_R` the transcript has already dropped every label, and the
    same audio is where the gate performs worst: 1 of 7 voiced microphone windows
    admitted with the far end on the speakers. Those seven are windows of unknown
    composition — with the far end on the speakers the microphone is voiced either
    way, so some hold no operator at all — which makes it an unlabelled outcome
    rather than a recovery rate, and the reason not to trust the gate there
    regardless of which reading is right.

    What that skip costs is worth stating exactly, because "nothing is lost" would
    be false. The label is already gone, so no attribution is being protected —
    but the room's *segments* still reach the merged transcript and the notes, and
    `notes/EVAL.md` measured that content cost as real: the 75-minute capture's
    14.2% room turns changed the output deterministically, three action items with
    them in against five with them out. So this accepts a known content
    contamination in order not to risk deleting the operator, which is the worse
    of the two failures. It is a choice between costs, not a free skip.

    Both halves read the same `contaminated()`, so the two decisions cannot drift.

    The threshold comes from the profile file, never from this module. There is no
    constant here to fall back to, because a plausible one would be
    indistinguishable from a measured one to every later reader — see
    speaker_gate's own opening note.

    `embed` exists so the filtering path can be exercised without a 153 MB install
    and an 89 MB model fetch. That is the same reason `speaker_gate.load_encoder`
    is imported lazily and its controls run on a fixture: a test that needs the
    real model is a test that stops being run, and the index arithmetic below is
    what decides whether the operator survives. Production passes nothing and gets
    the real encoder.

    Rejections are reported, always, including how many were close calls and
    whether the dropped speech keeps coming back as one voice. That last one is
    the Teams alert: someone co-located is being deleted from the transcript, and
    a gate that removes a real participant silently is worse than the
    contamination it replaces, because the transcript then omits speech with no
    record that it did.
    """
    if not segs or voiceprint is None:
        return segs
    if contaminated(b):
        print(f"  {label}: voiceprint gate SKIPPED — bleed is high, so the speaker "
              f"labels are already dropped and on this audio the gate is measured "
              f"to reject the operator as well. The room's words stay in the "
              f"transcript; that content cost is accepted rather than risked "
              f"against deleting the operator.")
        return segs

    import speaker_gate as sg

    profile, threshold, manifest = voiceprint
    if embed is None:
        embed = sg.load_encoder(manifest["model_dir"])
    embeddings = sg.embed_segments(mic.astype(np.float32), segs, embed)
    result = sg.gate(profile, segs, embeddings, threshold)

    # From the enrollment list itself, which load_profile refuses to load without.
    # Reading it out of the nested operating point instead let an older or
    # hand-edited profile print "None sitting(s)" and skip the over-tight warning
    # entirely — the warning most needed by exactly the profile missing the field.
    sittings = len(manifest["sittings"])
    print(f"  {label}: voiceprint gate at {threshold:.3f} "
          f"(profile {profile.seconds:.0f}s over {sittings} sitting(s))")
    print(f"    kept {len(result.kept)} ({result.kept_seconds:.1f}s), "
          f"dropped {len(result.rejected)} ({result.rejected_seconds:.1f}s), "
          f"too short to judge {len(result.unscorable)} "
          f"({result.unscorable_seconds:.1f}s)")
    if result.borderline:
        print(f"    {len(result.borderline)} of those rejections were close calls "
              f"(within one profile spread of the line) — the gate guessing, not working")
    if result.persistent_other:
        # Reported as roughly-how-much rather than a bare flag, because the number
        # is what tells the operator whether to care.
        share = result.coherent_share
        print(f"    ALERT: {share:.0%} of the dropped speech is one recurring voice "
              f"(~{share * result.rejected_seconds:.0f}s). Someone beside you is being "
              f"removed from this transcript. If that is a participant, this capture "
              f"is missing their words.")
    if sittings == 1:
        print("    NOTE: the profile came from one sitting, which is measurably "
              "over-tight — expect more of the operator dropped than the target asked.")

    # Unscorable segments are KEPT. The gate returns them as their own bucket
    # precisely so this decision is made here and visibly: they are 28% of the
    # long capture's mic segments carrying 12% of its words, and short turns are
    # "yes", "agreed", "I'll do that" — the commitments the tool exists to record.
    # Dropping them to keep the room out would lose exactly those. Keeping them
    # leaks whatever short utterances the room contributed, and that cost is
    # stated above rather than hidden in a default.
    keep = set(result.kept) | set(result.unscorable)
    return [s for i, s in enumerate(segs) if i in keep]


def report(mic_leg, tap_leg, args, out_dir, phases=None, shown_at=None):
    mic = mic_leg.audio()
    tap = tap_leg.audio()

    print("\n=== capture ===")
    for leg, audio in (("mic", mic), ("system", tap)):
        secs = len(audio) / RATE
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean())) if len(audio) else 0.0
        print(f"  {leg:7s} {len(audio):>9d} samples  {secs:6.2f}s  rms {rms:.5f}")

    # A dropout is a hole in the timeline that leaves the sample count looking
    # healthy, so it has to be said out loud or a leg with gaps reads as a leg
    # without them. It also disqualifies the capture as an echo-cancellation
    # reference, where alignment is the whole premise.
    for leg in (mic_leg, tap_leg):
        if leg.dropouts:
            print(f"\n  {leg.name}: {len(leg.dropouts)} driver dropout(s) — samples were "
                  f"lost, so this leg's timeline has holes")
            t0 = leg.arrivals[0][0] if leg.arrivals else leg.dropouts[0][0]
            for when, what in leg.dropouts[:5]:
                print(f"    at {when - t0:6.1f}s  {what}")

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
        # The verdict comes from contaminated(), which owns the reading of
        # positive_r over peak_r and the cut itself, so this line cannot disagree
        # with the one that clears the speaker labels.
        if contaminated(b):
            print("  HIGH — the mic is hearing the speakers; Me/Them split is contaminated")
        elif b["positive_r"] > BLEED_MODERATE_R:
            print("  MODERATE — some bleed present")
        else:
            print("  LOW — legs are acoustically independent (headphones, or quiet room)")

    print()
    for leg, audio in ((mic_leg, mic), (tap_leg, tap)):
        path = out_dir / f"{leg.name}.wav"
        how = "written as it was captured"
        if leg.writer.error is not None:
            # The file on disk stops wherever the writer died, but the audio is
            # still in memory at this point — rewriting costs a second and is
            # the difference between a truncated capture and a complete one.
            print(f"  {leg.name}: incremental writer failed ({leg.writer.error})")
            write_wav(path, audio)
            how = "rewritten from memory — the run was NOT crash-safe"
        elif leg.writer.file is None or leg.writer.frames != len(audio):
            # The invariant worth checking: the file on disk IS this capture.
            # Both halves are load-bearing. A writer that fell behind leaves a
            # short file. A leg that captured nothing never opened one at all —
            # and since out_dir is reused across runs, saying nothing there
            # would leave the PREVIOUS run's recording in place and report it as
            # this one, which is how two sessions end up correlated against each
            # other. Zero frames and zero samples agree, so counting alone
            # misses it.
            write_wav(path, audio)
            how = "written at the end; the incremental file was not this capture"
        print(f"  wrote {path} ({len(audio) / RATE:.2f}s, {how})")

    if phases:
        # After both WAVs are on disk, so the digests are of the files a consumer
        # will actually open, and before the transcription that may take minutes
        # and may fail — the schedule is the part that cannot be reconstructed.
        write_protocol(out_dir / "protocol.json", phases,
                       out_dir / "mic.wav", len(mic),
                       out_dir / "system.wav", len(tap), shown_at)

    if args.no_transcribe:
        return

    print("\n=== transcript ===")
    t0 = time.monotonic()
    mic_voiced = drop_unvoiced(transcribe(mic, args.whisper, args.language), mic, "mic")
    write_leg_segments(out_dir / "mic-segments.json", mic_voiced, len(mic) / RATE,
                       out_dir / "mic.wav", len(mic), "mic")
    mic_segs = drop_bled(mic_voiced, mic, tap, b, "mic")
    # After drop_bled, not before. The bled segments are the far end, and asking a
    # voiceprint whether the far end is the operator wastes an embedding per
    # segment to arrive at the answer the cheaper acoustic test already gave.
    gating = voiceprint_provenance(args.voiceprint, b, bool(mic_segs))
    mic_segs = drop_offprint(mic_segs, mic, args.voiceprint, b, "mic")
    tap_segs = drop_unvoiced(transcribe(tap, args.whisper, args.language), tap, "system")
    write_leg_segments(out_dir / "system-segments.json", tap_segs, len(tap) / RATE,
                       out_dir / "system.wav", len(tap), "system")
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
            merged.append((seg["start"] + offset, seg["end"] + offset, label, seg["text"]))
    merged.sort(key=lambda r: r[0])

    if not merged:
        print("  (no speech detected on either leg)")
        return

    # The artifact lands before the 1200 lines of console output, not after.
    # When this ran the other way round, a crash while serialising discarded
    # four and a half minutes of transcription that had already succeeded —
    # the expensive work was complete and unrecoverable because the cheap
    # step downstream of it failed.
    write_transcript(out_dir / "transcript.json", merged, b, gating)

    if contaminated(b):
        print(
            "  NOTE: bleed is high, so expect every utterance to appear TWICE —\n"
            "  once as Me and once as Them. That is the contamination, not a\n"
            "  transcription bug. Re-run on headphones to see the real split.\n"
        )
    for start, _end, label, text in merged:
        print(f"  [{int(start // 60):02d}:{start % 60:05.2f}] {label:4s} {text}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# The calibration protocol. An echo-cancellation experiment needs two things no
# ordinary capture supplies: a stretch of the far end playing while the operator
# is silent, to fit on, and per-interval ground truth about who was talking, to
# score against.
#
# Neither can be recovered from the recording afterwards. Transcribing the
# microphone does not answer "was the operator silent here" — on speakers the
# far end reaches the microphone and transcribes there too, which is the whole
# premise of this project's `drop_bled`. A silent operator and a talking one
# both produce microphone segments during playback.
#
# So the schedule is decided BEFORE any audio exists and shown as a visual cue
# during capture. A keypress mark would be simpler and is the wrong shape: it is
# the operator attesting afterwards to what he did, which is the class of
# evidence this project keeps refusing. A schedule written in advance cannot be
# fitted to the result, and compliance with it is independently checkable from
# the microphone's own energy — a "speak" interval with no voiced audio in it is
# a missed cue and says so.
#
# Cues are visual, never audible. A beep would be recorded by the microphone,
# and on speakers it would also reach the tap, putting a marker signal into both
# legs of an experiment about what leaks between them.
CUE_POLL_S = 0.05        # how often the loop looks at the clock
CUE_MARGIN_S = 1.0       # trimmed off each phase edge before anything is scored
PROTOCOL_TAIL_S = 2.0    # recorded past the last cue, so the last interval fits
FAR_END_CHECK_S = 5.0    # into the calibration phase, before a word has been read
FAR_END_MIN_RMS = 1e-4   # the tap is digital, so real silence is exactly zero
CALIBRATION_S = 35.0
SPEAK_S, CONTROL_S = 10.0, 6.0
DEFAULT_PAIRS = 5


# One passage per speak interval, shown as the cue and read aloud for the whole
# interval. They exist so compliance can be checked from content rather than
# assumed, per segment rather than per interval.
#
# A single short phrase was the first attempt and it labels the wrong thing. Read
# once at the top of a ten-second interval, it establishes that the operator
# spoke somewhere in there — and then every segment in the interval gets counted
# as his, including the ones during a pause, which on speakers hold the far end
# and nothing else. "Then keep talking" was carrying the weight, and it is an
# assumption, not a measurement.
#
# A passage long enough to fill the interval moves the evidence down to the
# segment. Each segment's own transcript can be asked how much of it comes from
# the passage: a segment of the operator reading is almost all passage words, a
# segment of far-end echo is almost none. That is a per-segment label rather than
# an interval-wide one.
#
# The check is one-directional and has to stay that way. Echo-contaminated speech
# transcribes badly — that is the condition under study — so a segment that fails
# to match is not evidence the operator was silent in it. It is unverified, and
# unverified segments are reported apart rather than counted.
#
# Chosen to be unlike anything a meeting or a podcast contains, so a match is
# hard to produce by accident, and roughly twenty-five words so that reading at a
# normal pace fills ten seconds. The far-end leg is transcribed too and any
# passage that turns up in IT is excluded from the evidence rather than credited.
SCRIPT = [
    (
        "seventeen violet anchors drifted past the harbour while eleven paper foxes "
        "counted gravel in the courtyard and the copper lantern hummed beneath a "
        "crooked staircase near the tilted greenhouse"
    ),

    (
        "nine amber turtles argued about the wrong timetable until the velvet piano "
        "leaned against a rusted weather vane and four glass herons folded maps "
        "inside a very quiet elevator"
    ),

    (
        "an iron sparrow rehearsed arithmetic beside the canal where thirty marzipan "
        "lighthouses catalogued the tide and a woollen compass disagreed with every "
        "chimney on the northern terrace"
    ),

    (
        "the lopsided kettle whistled at twelve ceramic badgers sorting umbrellas by "
        "weight while a phosphorescent ladder measured the orchard and forgot which "
        "orchard it had measured"
    ),

    (
        "fifteen bramble accountants audited a carousel of borrowed lanterns before "
        "the marble heron filed its objection and the tin observatory misplaced "
        "another Tuesday afternoon entirely"
    ),

    (
        "a saffron bicycle negotiated with the drawbridge about eight hundred "
        "peppercorns while the plaster nightingale transcribed the wrong argument "
        "onto a folded linen envelope"
    ),

    (
        "twenty obsidian teaspoons queued politely outside the cartographer's shed "
        "where a lacquered otter rearranged the constellations and denied having "
        "touched the barometer at all"
    ),

    (
        "the hexagonal greengrocer weighed six reluctant meteorites against a bundle "
        "of clockwork asparagus while the granite librarian recited postcodes to an "
        "indifferent brass pelican"
    ),
]


def build_schedule(calibration_s=CALIBRATION_S, pairs=DEFAULT_PAIRS,
                   speak_s=SPEAK_S, control_s=CONTROL_S):
    """Calibration, then alternating speak/silent intervals, all on the mic clock.

    The silent intervals after the calibration phase are not padding. They are
    the far end playing with no operator behind it, which makes them two things
    at once: the negative control for the voiceprint gate — audio that must NOT
    be admitted as the operator, in any condition — and the first echo-only
    audio in this project, which is what an honest echo-return-loss figure needs
    and what every earlier one lacked.

    Phase lengths are set by what has to fit inside them once CUE_MARGIN_S is
    trimmed from each edge: a 6 s silent interval leaves 4 s, which admits two
    segments at speaker_gate's 2 s floor, and a 10 s speak interval leaves 8 s.
    Shortening either below 2 * CUE_MARGIN_S + 2.0 makes the interval yield
    nothing and the control decorative.
    """
    interior = min(speak_s, control_s) - 2 * CUE_MARGIN_S
    if interior < 2.0:
        raise ValueError(
            f"phases of {min(speak_s, control_s):g}s leave {interior:g}s after "
            f"{CUE_MARGIN_S:g}s of margin at each edge, which is below the 2s a "
            f"segment needs to be scorable. The interval would yield nothing.")
    if pairs < 1:
        raise ValueError(
            "a schedule with no speak intervals is not a degenerate calibration "
            "take, it is not a schedule: there would be nothing to score and "
            "nothing to hold the gate's negative control against.")
    phases = [{"start": 0.0, "end": calibration_s,
               "expect": "silence", "role": "calibration", "script": None}]
    t = calibration_s
    for k in range(pairs):
        phases.append({"start": t, "end": t + speak_s, "expect": "operator",
                       "role": "speak", "script": SCRIPT[k % len(SCRIPT)]})
        t += speak_s
        phases.append({"start": t, "end": t + control_s,
                       "expect": "silence", "role": "control", "script": None})
        t += control_s
    return phases


CUE_TEXT = {
    "calibration": "SAY NOTHING — let the far end play. This is the fit interval.",
    "speak": "READ THIS ALOUD, over the playback, until the cue changes:",
    "control": "SAY NOTHING — playback continues.",
}


def run_cues(mic_leg, tap_leg, phases, stop, shown_at, abandoned):
    """Show each cue at its scheduled point on the microphone's own clock.

    Timed from the arrival of the first microphone block, so phase boundaries
    are the same numbers that index mic.wav. The two known offsets are small
    against CUE_MARGIN_S: one block of capture latency between a sample being
    recorded and arriving here, and up to CUE_POLL_S of scheduling granularity.
    Operator reaction time is the large one, and it is what the margin is for.

    Each cue's ACTUAL display time lands in `shown_at`, keyed by phase index,
    and goes into the artifact beside the schedule. The schedule is what was
    intended; a stalled interpreter, a busy terminal or a swapped-out process
    can put the cue somewhere else, and then every segment in that interval is
    labelled against a boundary the operator never saw. Storing the intent alone
    makes that failure invisible. The harness refuses a take whose cues landed
    further out than the attribution margin.

    Five seconds into the calibration phase this also checks that the far end is
    actually playing, and abandons the take if it is not. Nothing here plays
    anything — the tap records whatever the machine is already outputting — so a
    run started before the far end does is a two-minute recording of a quiet room
    with the operator reading five passages into it, which measures nothing about
    echo. That condition was already detected, in `report`, AFTER the capture: the
    cost of finding out there was the whole take. Five seconds in, nothing has been
    read yet and the only cost is starting again.
    """
    while not mic_leg.arrivals and not stop.is_set():
        time.sleep(CUE_POLL_S)
    if stop.is_set():
        return
    t0 = mic_leg.arrivals[0][0]
    total = phases[-1]["end"]
    live = sys.stdout.isatty()
    shown = None
    checked = False
    while not stop.is_set():
        now = time.monotonic() - t0
        if now >= total:
            break
        if not checked and now >= FAR_END_CHECK_S:
            checked = True
            far = tap_leg.audio()
            level = (float(np.sqrt((far.astype(np.float64) ** 2).mean()))
                     if len(far) else 0.0)
            if level < FAR_END_MIN_RMS:
                print(f"{chr(13) if live else chr(10)}"
                      f"  nothing is coming out of the speakers — the system leg is "
                      f"silent after {now:.0f}s.\n"
                      f"  This tool records the far end; it does not play it. Start "
                      f"the playback\n"
                      f"  first — a call, a video, anything audible — then run this "
                      f"again.\n"
                      f"  Abandoning the take now, before you have read anything.")
                abandoned.set()
                stop.set()
                return
        cur = next((p for p in phases if p["start"] <= now < p["end"]), None)
        if cur is None:
            break
        if cur is not shown:
            shown = cur
            shown_at[phases.index(cur)] = round(now, 3)
            print(f"\n  [{now:6.1f}s] {CUE_TEXT[cur['role']]}")
            if cur["script"]:
                # Wrapped, because a twenty-five-word passage on one terminal
                # line is not something anyone reads at a steady pace.
                for line in textwrap.wrap(cur["script"], 66):
                    print(f"             {line}")
                print("             (repeat from the start if you reach the end)")
        if live:
            # Only where a carriage return means what it looks like. Redirected
            # to a file this line does not overwrite itself, and a two-minute
            # capture buries the cues under a thousand countdown fragments.
            print(f"\r           {cur['end'] - now:4.1f}s left ", end="", flush=True)
        time.sleep(CUE_POLL_S)
    # Run past the last cue so the final interval is comfortably inside the
    # audio, then end the capture from here. This thread is the only one holding
    # the microphone's clock; a wall-clock deadline in main() starts before the
    # first block arrives and would cut the schedule short by that much.
    time.sleep(PROTOCOL_TAIL_S)
    print(f"{chr(13) if live else chr(10)}  protocol complete — recording stops here.        ")
    stop.set()


def write_protocol(path, phases, mic_path, mic_samples, tap_path, tap_samples,
                   shown_at=None):
    """The schedule, bound to both recordings it was displayed over.

    Both bindings matter. The digest says this schedule belongs to this audio
    and not to another take with the same phase lengths; the sample count says
    the recording was not truncated afterwards, which would slide every phase
    boundary relative to the audio underneath it while leaving the digest of a
    re-written file self-consistent.

    The system leg is bound too, and to its own count rather than the
    microphone's — the two legs run on independent clocks and legitimately
    differ by thousands of samples over a couple of minutes. Anything measuring
    echo suppression has to know the far end was actually playing, which means
    reading this leg, which means being sure it is the right one.
    """
    payload = {
        "schema": "capture-protocol/1",
        "timeline": "mic-local",
        "rate": RATE,
        "mic_sha256": sha256(mic_path),
        "mic_samples": int(mic_samples),
        "system_sha256": sha256(tap_path),
        "system_samples": int(tap_samples),
        "cue_margin_s": CUE_MARGIN_S,
        "cue_poll_s": CUE_POLL_S,
        "phases": [dict(ph, shown_at_s=(shown_at or {}).get(i))
                   for i, ph in enumerate(phases)],
    }
    path.write_text(json.dumps(payload, indent=2))
    speak = sum(1 for p in phases if p["expect"] == "operator")
    ctrl = sum(1 for p in phases if p["role"] == "control")
    late = [round(v - phases[i]["start"], 2)
            for i, v in (shown_at or {}).items()]
    drift = f", worst cue {max(late, key=abs):+.2f}s off schedule" if late else ""
    print(f"  wrote {path} ({speak} speak, {ctrl} silent-control intervals, "
          f"{phases[-1]['end']:.0f}s scheduled{drift})")


def write_leg_segments(path, segs, duration_s, audio_path, audio_samples, leg):
    """One leg's own speech, on its own clock, before any cross-leg filtering.

    `transcript.json` is a presentation artifact and is wrong for every job that
    indexes back into `mic.wav`, in three separate ways:

    * **It holds both legs.** And when bleed is detected it deliberately clears
      every speaker label, so nothing downstream can tell an operator turn from
      a far-end one. Anything scoring "the operator's segments" against it is
      scoring a mixture.
    * **Its clock is the merged session's, not the microphone's.** Each leg is
      offset by when its first block arrived so the two can be interleaved.
      Slicing `mic.wav` with those numbers is off by the startup skew, which has
      run to 1.7 s on these captures.
    * **It is filtered by `drop_bled`.** That is right for a transcript and
      exactly wrong for measuring echo cancellation: the segments it removes are
      the contaminated operator speech such an experiment exists to recover.

    So this is written before the merge and before `drop_bled`, carrying one leg,
    only its own timeline, and a schema marker so a consumer that needs those
    guarantees can insist on them rather than hope.

    What it does NOT carry is who was speaking. "Microphone-only" names the
    channel, not the talker: on speakers, the far end arrives here too, so the
    mic list holds the operator's turns and the echo of the far end's, mixed and
    indistinguishable. Anything that needs the difference has to get it from
    somewhere outside the audio — `protocol.json` is that somewhere.

    The system leg gets the same treatment, and not for symmetry. The protocol's
    script phrases are checked against it: a phrase the far end happens to say
    is a phrase its echo can put in the mic transcript, so any that appear here
    are struck from the compliance evidence rather than credited to the operator.

    The digest and sample count bind the list to the recording it indexes.
    Without them a same-schema file from another take loads silently and every
    segment points at the wrong audio.
    """
    payload = {
        "schema": "mic-segments/1",
        "timeline": f"{leg}-local",
        "leg": leg,
        "duration_s": round(duration_s, 3),
        "filtered": ["voicing"],
        "labels": None,
        "audio_sha256": sha256(audio_path),
        "audio_samples": int(audio_samples),
        "segments": [
            {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"]}
            for s in segs
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
    first = f", first speech at {segs[0]['start']:.1f}s" if segs else ""
    print(f"  wrote {path} ({len(segs)} {leg} segments{first})")


def voiceprint_provenance(voiceprint, b, had_segments):
    """What gated the microphone leg, for the artifact to carry.

    Several states, and the reason this is not a boolean is that a reader six
    months later cannot tell them apart from the segments alone. A leg can be
    ungated because no profile was supplied, because bleed sent the gate down the
    skip path, or because there was nothing on the leg to gate. `null` would report
    all of those as the first, which reads as "nobody asked for a gate" when what
    happened is "a gate was asked for and did not run".

    `had_segments` mirrors `drop_offprint`'s own early return. Without it a capture
    whose microphone leg transcribed nothing wrote `applied: true` — a gate result
    for a gate that never executed.
    """
    if voiceprint is None:
        return None
    _profile, threshold, doc = voiceprint
    op = doc.get("operating_point") or {}
    if contaminated(b):
        why = "bleed above the attribution cut"
    elif not had_segments:
        why = "no microphone segments survived the earlier filters"
    else:
        why = None
    return {
        "applied": why is None,
        "skipped_reason": why,
        "threshold": threshold,
        "target_frr": op.get("target_frr"),
        "n_sittings": len(doc["sittings"]),
        "profile_seconds": doc.get("seconds"),
        "encoder": doc.get("encoder"),
    }


def write_transcript(path, merged, b, gating=None):
    """Hand the capture to the notes half, carrying the bleed verdict with it.

    The attribution level is derived here rather than downstream, because this
    is the only place that knows how the audio was actually captured. A capture
    whose legs turned out to be correlated is not a Me/Them transcript that
    happens to be noisy — it is a transcript with no speaker information at all,
    and it has to arrive downstream saying so. Otherwise the measurement in this
    file and the notes written from it can disagree, and the notes will win.

    See notes/transcript.py for what each level licenses.
    """
    unattributed = contaminated(b)
    payload = {
        "source": f"capture {time.strftime('%Y-%m-%d %H:%M')}",
        "attribution": "none" if unattributed else "channel",
        "bleed": {"peak_r": b["peak_r"], "positive_r": b["positive_r"],
                  "analysed_s": b["analysed_s"]} if b else None,
        # Whether the mic leg holds the operator or whoever was audible. The
        # attribution level above says which CHANNEL a turn came from; this says
        # whether anything checked that the channel held the person it names.
        # Computed by the caller, which is the only place that knows whether the
        # gate actually executed — see voiceprint_provenance.
        "voiceprint": gating,
        "turns": [
            # Labels are dropped, not merely marked, when the split is fiction.
            {
                "start": round(start, 2),
                # The end was carried this far and then dropped, which left every
                # consumer inferring it from the next turn's start — swallowing
                # each pause, and at a speaker change the next speaker's onset
                # too. That silently corrupted one dataset in this project
                # before anyone noticed, and it is the reason the voiceprint
                # measurements had to re-derive boundaries from voicing.
                "end": round(end, 2),
                "speaker": None if unattributed else label,
                "text": text,
            }
            for start, end, label, text in merged
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
    verdict = (
        "unattributed — bleed made the split unusable"
        if unattributed else "Me/Them preserved"
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
    ap.add_argument(
        "--protocol", action="store_true",
        help="run the echo-calibration protocol: show timed visual cues during "
             "capture and write protocol.json beside the recordings. Start the "
             "far end playing first and leave it playing throughout; the cues "
             "only say when to talk.",
    )
    ap.add_argument("--protocol-pairs", type=int, default=DEFAULT_PAIRS,
                    help="speak/silent interval pairs after the calibration phase")
    ap.add_argument(
        "--voiceprint", type=Path, default=None,
        help="a profile from speaker_gate.py --enroll-out. Removes microphone "
             "segments that are not the operator — the room, a colleague, a TV. "
             "Without it the mic leg is whoever was audible, and on the 75-minute "
             "capture that was 14.2%% other people delivered to the notes as things "
             "the operator said.",
    )
    ap.add_argument(
        "--model-dir", type=Path, default=Path.home() / ".cache" / "speaker-gate",
        help="where the ECAPA checkpoint the voiceprint gate uses is cached",
    )
    args = ap.parse_args()

    if sd is None:
        ap.error("sounddevice is not installed, so no audio can be captured. "
                 "pip install -r spike/requirements.txt")

    # Before the microphone opens. A profile that cannot be read, or that was
    # enrolled in a different embedding space, must cost an error rather than a
    # recorded meeting whose gate fails after the ASR has already run.
    if args.voiceprint is not None:
        if args.no_transcribe:
            ap.error("--voiceprint gates transcript segments, so it does nothing "
                     "with --no-transcribe. Drop one of them.")
        args.voiceprint = load_voiceprint(args.voiceprint, args.model_dir)
    else:
        print("no --voiceprint: the microphone leg will carry whoever was audible, "
              "including the room, labelled as the operator.\n")

    try:
        phases = build_schedule(pairs=args.protocol_pairs) if args.protocol else None
    except ValueError as exc:
        ap.error(str(exc))
    if phases:
        if args.seconds:
            ap.error("--protocol sets its own duration; drop --seconds")
        # A backstop only. The cue thread ends the capture on the microphone's
        # own clock; this fires solely if that thread never starts, which is
        # what a microphone that produces no audio at all looks like.
        args.seconds = phases[-1]["end"] + PROTOCOL_TAIL_S + 30.0

    if args.list_devices:
        print(sd.query_devices())
        return

    device = args.input_device
    if device is not None and device.isdigit():
        device = int(device)

    out_dir = Path(args.out) if args.out else REPO / "spike" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    shown_at = {}                    # phase index -> mic-clock time it appeared
    mic_leg = MicLeg(device, out_dir / "mic.wav")
    tap_leg = TapLeg(out_dir / "system.wav")
    stop = threading.Event()
    # Distinct from `stop`, because Ctrl-C and "the far end was never playing" end
    # the capture the same way and mean opposite things: one is the operator
    # deciding they have enough, the other is a take that cannot be scored.
    abandoned = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    # Both starts sit inside the try. An unresolvable --input-device raises out
    # of mic_leg.start(), and outside it that left the tap subprocess orphaned
    # and both legs' writer threads holding their files open. Neither stop() has
    # anything to undo on a leg that never started.
    try:
        tap_leg.start()
        mic_leg.start()

        # Name both devices before any audio arrives. The tap follows the
        # default OUTPUT device, so that is the one that decides what lands on
        # the system leg — worth seeing alongside the microphone.
        out_name = sd.query_devices(sd.default.device[1])["name"]
        print(f"  mic    → {mic_leg.device_name}")
        print(f"  system → tap on default output: {out_name}")
        print(f"capturing — {'Ctrl-C to stop' if not args.seconds else f'{args.seconds:g}s'}")

        if phases:
            print(f"\n  protocol: {phases[-1]['end']:.0f}s. Far end should already "
                  f"be playing, at the volume and seat you would really use.\n"
                  f"  Follow the cues and change nothing else until it stops.")
            cue = threading.Thread(target=run_cues,
                                   args=(mic_leg, tap_leg, phases, stop,
                                         shown_at, abandoned),
                                   daemon=True)
            cue.start()

        deadline = time.monotonic() + args.seconds if args.seconds else None
        while not stop.is_set():
            if deadline and time.monotonic() >= deadline:
                break
            time.sleep(CUE_POLL_S)
    finally:
        mic_leg.stop()
        tap_leg.stop()

    # An abandoned take gets no schedule written beside it. load_protocol would
    # refuse the short recording anyway, but leaving the artifact there makes the
    # directory look like a take that can be scored, and the next person to find it
    # has to work out why it cannot be.
    report(mic_leg, tap_leg, args, out_dir,
           None if abandoned.is_set() else phases,
           None if abandoned.is_set() else shown_at)
    return 1 if abandoned.is_set() else 0


if __name__ == "__main__":
    sys.exit(main())
