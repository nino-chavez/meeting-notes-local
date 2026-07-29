"""How much of the operator does offline echo removal give back? Measured, not argued.

When the far end plays through the laptop speakers it returns through the room
into the microphone, and the voiceprint gate stops recognising the operator in
his own meeting. The question this answers is whether removing the echo is worth
building — and specifically whether it is worth integrating WebRTC's AEC3, which
is a substantial dependency.

That question does not need AEC3 to answer. A strong offline reference condition
can be computed in closed form, and if *that* fails to restore the operator, no
real-time canceller will. What it measures is a floor under the decision, not a
ceiling over it. Read the limits below before quoting any number from here.

**What this computes**

  raw        the microphone as captured.
  linear     minus a finite-impulse-response echo estimate, fit by least squares
             in closed form over the spans chosen by --fit-mode, with the bulk
             delay supplied by cross-correlation over the whole recording. No
             real-time filter gets to see a recording before filtering it.
  masked     then a Wiener-style time-frequency gain built from that same echo
             estimate: G = |E|^2 / (|E|^2 + |Y_hat|^2).

**What this is NOT**

It is *not* an oracle, and an earlier version of this file's results called it
one. An oracle mask requires the true isolated echo, which would mean having the
echo premixed and separate; what is available here is an *estimate* of the echo
from the same least-squares fit, so the mask inherits every error the fit makes.

It is also *not* an upper bound on AEC3. A single static fit cannot track a
moving echo path, cannot re-converge after the operator shifts position, and
holds no double-talk logic. AEC3 adapts continuously, estimates delay and drift,
detects double-talk, and derives its suppression gain from statistics this file
never computes. It is a different algorithm with different information, and on
material where the path moves it can beat a static fit outright.

What can honestly be said: within the filter class this fits — one linear
time-invariant path, estimated in-sample — this is the best that class does on
this material.

**Three fit modes, because in-sample is the weakest of them**

  full          fit on the whole take. Optimistic: the filter sees the same
                double-talk it is later scored on, and can use the reference to
                predict near-end speech that merely happens to correlate.
  far-end-only  fit only where the far end is playing and the microphone is
                quiet, then score everywhere. This is the honest one. It is also
                what a real canceller does, since adaptation freezes during
                double-talk. If recovery survives here, it is not the filter
                quietly cancelling the operator.
  first-half    fit on the first half, score the second. Held out in time rather
                than by regime.

**How it is scored**

By the voiceprint gate, on operator retention and household false admission —
not by ERLE. Suppression in dB is a diagnostic here and a misleading headline:
the take that recovers best does so on 1.3 dB of double-talk suppression, while
a take with more suppression recovers less. A speaker embedding cares which
time-frequency cells are corrupted, not how much total energy was removed.

Windows are fixed-length and non-overlapping by default. Overlapping windows
inflate the count without adding evidence, and voice-activity segments make
window length a confound: with the far end running continuously the hangover
merges a minute into two twenty-second spans, while a quiet take yields
four-second utterances, and embeddings are more stable with more audio.

**This windowing is not what the gate does in production.** `speaker_gate.py`
embeds each complete segment its caller supplies. Fixed windows are an
experimental control for equalising takes, not the shipping contract, and any
figure from here transfers to the product only as far as that difference allows.

Audio never enters the repository. `--out` writes scores and input digests, so a
result can be checked against the recording that produced it without publishing
anyone's voice.
"""
import argparse
import hashlib
import json
import sys
import wave
from itertools import pairwise
from pathlib import Path

import numpy as np

RATE = 16_000
TAPS = 800              # 50 ms; longer buys under 0.1 dB on this material
RIDGE = 1e-4            # relative to rxx[0], with an absolute floor for silence
NFFT, HOP = 1024, 512
MAX_LAG_S = 3.0         # measured start skew between the legs has reached 1.7 s
PHAT_FLOOR = 0.01       # below this there is no relationship to align to
WINDOW_S, HOP_S = 3.0, 3.0
VAD_PCT, VAD_MARGIN_DB, VAD_FLOOR = 10, 8.0, 1e-4
VAD_HANGOVER_S = 0.35
MIN_FIT_RUN = 8 * TAPS  # a fit range shorter than this is mostly wrong history
ALIGN_MARGIN = TAPS // 8  # headroom so the direct path lands at a positive lag


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != RATE:
            raise ValueError(f"{path}: expected mono s16le at {RATE} Hz")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def gcc_phat(a: np.ndarray, b: np.ndarray, max_lag: int) -> tuple[int, float]:
    """Delay of `a` relative to `b`, whitened.

    Plain cross-correlation on speech peaks on the loudest formant rather than
    on the impulse, which puts the delay wherever the talker's voice happens to
    be strongest. Phase transform is the standard repair.
    """
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    A, B = np.fft.rfft(a, n), np.fft.rfft(b, n)
    R = A * np.conj(B)
    R /= np.abs(R) + 1e-12
    cc = np.fft.irfft(R, n)
    cc = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])
    i = int(np.argmax(cc))
    return i - max_lag, float(cc[i])


def ls_fir(y: np.ndarray, x: np.ndarray, taps: int = TAPS,
           runs: list[tuple[int, int]] | None = None) -> np.ndarray:
    """Least-squares FIR from x to y, by the correlation method.

    `runs` restricts the fit to given sample ranges, summing each range's
    correlations. Each range is treated as if the signal were zero outside it,
    which is wrong for the first `taps` samples of the range — the filter is
    handed silence where there was history. MIN_FIT_RUN bounds that error by
    refusing ranges shorter than several filter lengths.

    That restriction is the whole point of the far-end-only fit, and an earlier
    version got it wrong in a way its own controls caught: it selected frames by
    percentile and concatenated whatever came back, which on fragmented material
    produced hundreds of ranges shorter than the filter itself. Every sample was
    then inside the corrupted prefix, and the fit recovered a known echo path at
    13 dB instead of 40.

    The ridge carries an absolute floor as well as a relative one. A genuinely
    silent reference gives rxx[0] == 0, and a purely relative ridge is then also
    zero, so the solve raises instead of returning the correct answer — a filter
    of all zeros. Silence is a real input here.
    """
    spans = runs if runs is not None else [(0, len(y))]
    rxx = np.zeros(taps)
    rxy = np.zeros(taps)
    for a, b in spans:
        ys, xs = y[a:b], x[a:b]
        n = 1 << int(np.ceil(np.log2(2 * max(len(xs), taps))))
        X, Y = np.fft.rfft(xs, n), np.fft.rfft(ys, n)
        rxx += np.fft.irfft(X * np.conj(X), n)[:taps]
        rxy += np.fft.irfft(Y * np.conj(X), n)[:taps]
    i = np.arange(taps)
    R = rxx[np.abs(i[:, None] - i[None, :])]
    R[i, i] += max(RIDGE * rxx[0], 1e-12)
    return np.linalg.solve(R, rxy)


def stft(x: np.ndarray) -> np.ndarray:
    win = np.hanning(NFFT)
    pad = np.concatenate([x, np.zeros(NFFT)])
    n = (len(x) - 1) // HOP + 1
    return np.stack([np.fft.rfft(pad[i * HOP:i * HOP + NFFT] * win) for i in range(n)])


def istft(S: np.ndarray, n_out: int) -> np.ndarray:
    win = np.hanning(NFFT)
    out = np.zeros(len(S) * HOP + NFFT)
    norm = np.zeros_like(out)
    for i, frame in enumerate(S):
        out[i * HOP:i * HOP + NFFT] += np.fft.irfft(frame, NFFT) * win
        norm[i * HOP:i * HOP + NFFT] += win ** 2
    return (out / np.maximum(norm, 1e-8))[:n_out]


def frame_power(x: np.ndarray) -> np.ndarray:
    win = np.hanning(NFFT)
    n = (len(x) - NFFT) // HOP
    return np.array([((x[i * HOP:i * HOP + NFFT] * win) ** 2).sum() for i in range(max(n, 0))])


def far_end_only(mic: np.ndarray, ref: np.ndarray) -> list[tuple[int, int]]:
    """Sample ranges where the far end plays and the microphone is quiet.

    Far-end activity comes from the same voice-activity detector used on speech,
    not from a percentile of frame power. On material that is mostly playing —
    which a call is — a percentile selects the loudest scattered frames inside
    one long utterance and shatters it into fragments shorter than the filter.
    The detector's hangover keeps a talking stretch in one piece, which is what
    a fit needs.

    Only runs of at least MIN_FIT_RUN samples survive, because a range shorter
    than the filter teaches it nothing except that its own history is silence.

    "Microphone quiet" is still a percentile and so still approximate — it is
    not a guarantee the operator is silent. That error runs in the safe
    direction: operator speech leaking into the fit makes the filter *more*
    likely to cancel him, which depresses the recovery this file reports rather
    than inflating it.
    """
    active = [(int(lo * RATE), min(int(hi * RATE), len(mic))) for lo, hi in voiced_spans(ref)]
    active = [(a, b) for a, b in active if b - a >= MIN_FIT_RUN]
    if not active:
        return []

    # Two passes, because "the microphone is quiet" cannot be read off the
    # microphone. Echo is in it too, so thresholding raw level throws away the
    # loudest 30% of the echo — scattered through every span — and leaves runs
    # far shorter than the filter. Fit once on far-end activity alone, then look
    # at what the filter could NOT explain: that residual is the near end, and
    # it is what double-talk detection actually keys on.
    h = ls_fir(mic, ref, runs=active)
    resid = mic - np.convolve(ref, h)[:len(mic)]
    near = np.zeros(len(mic), dtype=bool)
    for lo, hi in voiced_spans(resid):
        near[int(lo * RATE):min(int(hi * RATE), len(mic))] = True

    runs = []
    for a, b in active:
        start = None
        for i in range(a, b):
            if not near[i] and start is None:
                start = i
            elif near[i] and start is not None:
                if i - start >= MIN_FIT_RUN:
                    runs.append((start, i))
                start = None
        if start is not None and b - start >= MIN_FIT_RUN:
            runs.append((start, b))
    return runs or active


def align(mic: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, float]:
    """Delay the reference to sit just before the echo, never on top of it.

    The margin is not cosmetic. Cross-correlation reports the delay of the
    strongest reflection, and the direct path arrives earlier — so shifting by
    exactly the measured peak puts part of the impulse response at a negative
    lag, where a causal filter cannot represent it at all. On a synthetic path
    with a known answer that cost 26 dB: the fit recovered a 40 dB echo at 14,
    and every downstream conclusion would have inherited it.
    """
    m = min(len(mic), len(ref))
    mic, ref = mic[:m], ref[:m]
    bulk, peak = gcc_phat(mic, ref, int(MAX_LAG_S * RATE))
    if peak < PHAT_FLOOR:
        bulk = 0                       # nothing to lock onto; do not chop the take
    applied = max(bulk - ALIGN_MARGIN, 0)
    shifted = np.roll(ref, applied)
    if applied:
        shifted[:applied] = 0.0
    return mic, shifted, bulk, peak


def process(mic: np.ndarray, ref: np.ndarray, fit_mode: str) -> tuple[dict, dict]:
    """The three conditions, plus what the fit was estimated from."""
    mic, ref, bulk, peak = align(mic, ref)
    m = len(mic)

    if fit_mode == "full":
        runs = [(0, m)]
    elif fit_mode == "first-half":
        runs = [(0, m // 2)]
    elif fit_mode == "far-end-only":
        runs = far_end_only(mic, ref)
        fitted = sum(b - a for a, b in runs)
        if fitted < 8 * TAPS:
            return {}, {"skipped": f"only {fitted} far-end-only samples in "
                                   f"{len(runs)} usable runs"}
    else:
        raise ValueError(f"unknown fit mode: {fit_mode}")

    h = ls_fir(mic, ref, runs=runs)
    echo = np.convolve(ref, h)[:m]
    linear = mic - echo
    E, Y = stft(linear), stft(echo)
    masked = istft(E * (np.abs(E) ** 2 / (np.abs(E) ** 2 + np.abs(Y) ** 2 + 1e-20)), m)

    return ({"raw": mic, "linear": linear, "masked": masked},
            {"bulk_delay_ms": bulk / RATE * 1000, "phat_peak": round(peak, 4),
             "fit_seconds": round(sum(b - a for a, b in runs) / RATE, 2),
             "fit_runs": len(runs), "fit_mode": fit_mode})


def voiced_spans(x: np.ndarray) -> list[tuple[float, float]]:
    """Energy VAD with hangover. Speech at 10 ms resolution is mostly gaps, so
    contiguous above-threshold runs are syllables; bridging short gaps is what
    turns them back into utterances."""
    hz, step = 100, RATE // 100
    n = len(x) // step * step
    env = np.sqrt((x[:n] ** 2).reshape(-1, step).mean(axis=1))
    on = env > max(np.percentile(env, VAD_PCT) * 10 ** (VAD_MARGIN_DB / 20), VAD_FLOOR)
    gap, run = int(VAD_HANGOVER_S * hz), 0
    for i in range(len(on) - 1, -1, -1):
        if on[i]:
            run = gap
        elif run > 0:
            on[i], run = True, run - 1
    out, start = [], None
    for i, v in enumerate([*list(on), False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start / hz, i / hz))
            start = None
    return out


def windows(x: np.ndarray, win_s: float, hop_s: float) -> list[dict]:
    out = []
    for lo, hi in voiced_spans(x):
        t = lo
        while t + win_s <= hi:
            out.append({"start": round(t, 3), "end": round(t + win_s, 3)})
            t += hop_s
    return out


# --------------------------------------------------------------------------
# Controls. These run on numpy alone: the encoder is an argument everywhere it
# is needed, so a machine without torch can still check that the arithmetic in
# this file does what the prose says.
# --------------------------------------------------------------------------

def _synth(seconds: float, seed: int, lo: int, hi: int) -> np.ndarray:
    """Band-limited noise. Stands in for speech: the filter algebra cannot tell
    the difference, and using real audio in a control would make the control
    depend on a recording nobody else has."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(seconds * RATE))
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    X[(f < lo) | (f > hi)] = 0
    y = np.fft.irfft(X, len(x))
    return y / (np.abs(y).max() + 1e-12) * 0.3


def _erle(mic: np.ndarray, resid: np.ndarray, mask: np.ndarray) -> float:
    return 10 * np.log10(((mic[mask] ** 2).mean() + 1e-20) / ((resid[mask] ** 2).mean() + 1e-20))


def run_self_test() -> int:
    print("controls for aec_bound.py\n")
    ok = True

    rng = np.random.default_rng(7)
    # The far end alternates on and off in multi-second blocks, as a talker on a
    # call does. Stationary noise would make every far-end-only run shorter than
    # the filter, which is the failure MIN_FIT_RUN exists to prevent — a control
    # built on it would be testing the wrong thing.
    far = _synth(24.0, 1, 150, 6000)
    gate = np.zeros(len(far))
    for k in range(0, 24, 4):
        gate[k * RATE:(k + 3) * RATE] = 1.0
    far *= gate
    near = _synth(24.0, 2, 100, 7000)
    near[:12 * RATE] = 0.0                       # first half: far end alone
    h_true = np.zeros(TAPS)                      # 15 ms bulk delay, decaying tail
    h_true[240:600] = 0.5 * np.exp(-np.arange(360) / 90) * rng.standard_normal(360)
    mic = near + np.convolve(far, h_true)[:len(far)]
    far_only = (gate > 0) & (np.arange(len(mic)) < 12 * RATE)

    # 1. The echo path is recovered, and the residual collapses where the far
    #    end plays alone. If this fails, nothing else in the file means anything.
    conds, _meta = process(mic, far, "far-end-only")
    got = _erle(conds["raw"], conds["linear"], far_only)
    print(f"  {'known echo path, fit on far-end-only spans':52s} ERLE {got:6.1f} dB", end="")
    if got > 25:
        print("   ok")
    else:
        print("   FAILED (expected > 25)")
        ok = False

    # 2. The near end must survive. A filter that cancels the operator would
    #    also show a large ERLE above, so the two checks only mean something
    #    together.
    dt = ~far_only
    damage = 10 * np.log10(((near[dt] ** 2).mean() + 1e-20)
                           / (((conds["linear"][dt] - near[dt]) ** 2).mean() + 1e-20))
    print(f"  {'near end preserved through double-talk':52s} SNR  {damage:6.1f} dB", end="")
    if damage > 20:
        print("   ok")
    else:
        print("   FAILED (expected > 20)")
        ok = False

    # 3. An unrelated reference must be a no-op. This is the control that
    #    catches a chain which improves everything it touches.
    other = _synth(24.0, 99, 150, 6000)
    noop, _ = process(mic, other, "full")
    drift = _erle(noop["raw"], noop["masked"], np.ones(len(mic), dtype=bool))
    print(f"  {'unrelated reference changes nothing':52s} {drift:+9.2f} dB", end="")
    if abs(drift) < 1.0:
        print("   ok")
    else:
        print("   FAILED (expected within 1 dB of zero)")
        ok = False

    # 4. The other direction: a reference with the same spectrum but no causal
    #    relationship must NOT cancel. Time reversal is the right destroyer
    #    here — a mere delay is not, because align() would simply measure it and
    #    put it back, so testing a shifted reference tests nothing. An earlier
    #    version of this control did exactly that and reported a failure that
    #    was the alignment working.
    wrong, _ = process(mic, far[::-1].copy(), "full")
    got = _erle(wrong["raw"], wrong["linear"], far_only)
    print(f"  {'time-reversed reference fails to cancel':52s} ERLE {got:6.1f} dB", end="")
    if got < 3:
        print("   ok")
    else:
        print("   FAILED (expected < 3: no relationship must not look like a fit)")
        ok = False

    # 5. And alignment must find a delay it was never told, or check 1 could be
    #    passing on a filter long enough to absorb the offset itself.
    _, _, bulk, _ = align(mic, far)
    print(f"  {'alignment recovers the 15 ms path delay':52s} {bulk / RATE * 1000:8.1f} ms", end="")
    if abs(bulk - 240) <= 16:               # one millisecond either way
        print("   ok")
    else:
        print("   FAILED (expected 15.0 ms)")
        ok = False

    # 6. Silence is a valid reference, not a crash. This is the singular-matrix
    #    case the ridge floor exists for.
    label = "silent reference yields the identity"
    try:
        silent, _ = process(mic, np.zeros_like(mic), "full")
        same = bool(np.allclose(silent["raw"], silent["linear"], atol=1e-9))
        print(f"  {label:52s} {'unchanged' if same else 'CHANGED':>13}", end="")
        print("   ok" if same else "   FAILED")
        ok &= same
    except np.linalg.LinAlgError:
        print(f"  {label:52s} {'raised':>13}   FAILED")
        ok = False

    # 7. Windows must not overlap by default, or the count overstates the
    #    evidence behind it.
    speech = _synth(12.0, 3, 100, 7000)
    speech[4 * RATE:6 * RATE] *= 0.001           # a gap the VAD has to respect
    w = windows(speech, WINDOW_S, HOP_S)
    disjoint = all(a["end"] <= b["start"] + 1e-9 for a, b in pairwise(w))
    print(f"  {'default windows are disjoint':52s} {len(w):6d} windows", end="")
    print("   ok" if disjoint and w else "   FAILED")
    ok &= disjoint and bool(w)

    print("\n  all controls behaved as specified" if ok
          else "\n  SOME CONTROLS FAILED — do not trust results from this file")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true",
                   help="run the controls; needs numpy only")
    p.add_argument("--take", action="append", metavar="NAME=DIR", default=[],
                   help="a capture directory holding mic.wav and system.wav")
    p.add_argument("--enroll", metavar="NAMES", default="",
                   help="comma-separated take names to build the operator profile from")
    p.add_argument("--reference-from", metavar="NAME", default="",
                   help="score every take against this take's system audio instead of "
                        "its own. The no-op control: a loud, unrelated reference gives "
                        "the filter every chance to carve out a voice it should not touch")
    p.add_argument("--fit-mode", default="far-end-only",
                   choices=("far-end-only", "full", "first-half"))
    p.add_argument("--segments", action="append", metavar="NAME=FILE", default=[],
                   help="score this take on segments from a JSON list of {start,end} "
                        "instead of fixed windows. This is the gate's actual contract — "
                        "speaker_gate embeds whole caller-supplied segments — so it is "
                        "how a result transfers to the product rather than staying an "
                        "experimental control")
    p.add_argument("--max-seconds", type=float, default=0.0,
                   help="analyse only the first N seconds of each take. The chain is "
                        "O(n) in Python-level STFT frames, so a 75-minute capture used "
                        "as a control costs more than the control is worth")
    p.add_argument("--window", type=float, default=WINDOW_S)
    p.add_argument("--hop", type=float, default=HOP_S)
    p.add_argument("--threshold", type=float, default=0.580)
    p.add_argument("--model-dir", type=Path, default=Path.home() / ".cache" / "speaker-gate")
    p.add_argument("--out", type=Path, help="write per-window scores and input digests here")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()
    if not args.take or not args.enroll:
        p.error("nothing to do: pass --self-test, or --take NAME=DIR with --enroll")

    import speaker_gate as sg

    takes = {}
    for spec in args.take:
        name, _, path = spec.partition("=")
        takes[name] = Path(path).expanduser()
    enroll_names = [n.strip() for n in args.enroll.split(",") if n.strip()]
    supplied = {}
    for spec in args.segments:
        name, _, path = spec.partition("=")
        supplied[name] = json.loads(Path(path).expanduser().read_text())

    enc = sg.load_encoder(args.model_dir)
    embs, durs = [], []
    for name in enroll_names:
        audio = load_wav(takes[name] / "mic.wav").astype(np.float32)
        segs = [{"start": lo, "end": hi} for lo, hi in voiced_spans(audio)
                if hi - lo >= sg.MIN_SCORABLE_S]
        for e, s in zip(sg.embed_segments(audio, segs, enc), segs, strict=True):
            if e is not None:
                embs.append(e)
                durs.append(s["end"] - s["start"])
    profile = sg.enroll(embs, durs)
    print(f"profile: {len(embs)} segments, {sum(durs):.0f}s from {', '.join(enroll_names)}")
    print(f"fit mode: {args.fit_mode}   windows: {args.window:g}s / {args.hop:g}s hop   "
          f"threshold: {args.threshold:+.3f}\n")

    manifest = {"parameters": {
        "reference_from": args.reference_from or None,
        "taps": TAPS, "ridge": RIDGE, "nfft": NFFT, "hop": HOP, "rate": RATE,
        "fit_mode": args.fit_mode, "window_s": args.window, "hop_s": args.hop,
        "threshold": args.threshold, "enrolled_on": enroll_names,
        "max_seconds": args.max_seconds or None,
        "supplied_segments": sorted(supplied),
        "max_lag_s": MAX_LAG_S, "phat_floor": PHAT_FLOOR,
        "min_fit_run": MIN_FIT_RUN, "align_margin": ALIGN_MARGIN,
        "vad": {"pct": VAD_PCT, "margin_db": VAD_MARGIN_DB,
                "floor": VAD_FLOOR, "hangover_s": VAD_HANGOVER_S},
    }, "inputs": {}, "takes": {}}

    print(f"{'take':11s} {'condition':10s} {'n':>4} {'min':>7} {'mean':>7} {'max':>7} "
          f"{'admitted':>10}")
    for name, take in takes.items():
        source = takes[args.reference_from] if args.reference_from else take
        mic_p, ref_p = take / "mic.wav", source / "system.wav"
        manifest["inputs"][name] = {"mic_sha256": sha256(mic_p), "system_sha256": sha256(ref_p)}
        mic, ref = load_wav(mic_p), load_wav(ref_p)
        if args.reference_from and len(ref) < len(mic):
            # Repeat the borrowed reference rather than letting `process` clip
            # the take to its length. Truncating instead would quietly shorten a
            # 75-minute control to 60 seconds and then index segments past the
            # end of the audio — which is how this was first found.
            ref = np.tile(ref, int(np.ceil(len(mic) / len(ref))))[:len(mic)]
        if args.max_seconds:
            cut = int(args.max_seconds * RATE)
            mic, ref = mic[:cut], ref[:cut]
        conds, meta = process(mic, ref, args.fit_mode)
        if not conds:
            print(f"{name:11s} skipped: {meta['skipped']}")
            manifest["takes"][name] = meta
            continue
        if name in supplied:
            limit = len(conds["raw"]) / RATE
            segs = [s for s in supplied[name]
                    if s["end"] - s["start"] >= sg.MIN_SCORABLE_S and s["end"] <= limit]
        else:
            segs = windows(conds["raw"], args.window, args.hop)
        rows = {"meta": meta, "windows": [dict(s) for s in segs]}
        for cond, audio in conds.items():
            scored = sg.embed_segments(audio.astype(np.float32), segs, enc)
            v = np.array([sg.score(profile, e) for e in scored if e is not None])
            if not len(v):
                # Every window came back unscorable. Say so rather than raising
                # from inside a format string, which tells the reader nothing.
                print(f"{name:11s} {cond:10s}    0   (no window reached "
                      f"{sg.MIN_SCORABLE_S:g}s of scorable audio)")
                continue
            for row, e in zip(rows["windows"], scored, strict=True):
                row[cond] = None if e is None else round(float(sg.score(profile, e)), 4)
            print(f"{name:11s} {cond:10s} {len(v):4d} {v.min():+7.3f} {v.mean():+7.3f} "
                  f"{v.max():+7.3f} {(v >= args.threshold).sum():5d}/{len(v):<4d}")
        manifest["takes"][name] = rows
        print()

    if args.out:
        args.out.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
