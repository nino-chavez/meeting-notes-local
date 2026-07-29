"""How much of the operator does offline echo removal give back? Measured, not argued.

When the far end plays through the laptop speakers it returns through the room
into the microphone, and the voiceprint gate stops recognising the operator in
his own meeting. The question this answers is whether removing the echo is worth
building — and specifically whether it is worth integrating WebRTC's AEC3, which
is a substantial dependency.

That question does not need AEC3 to answer first. A strong offline condition can
be computed in closed form and scored on the outcome that matters, which is
cheap enough to run before committing to an integration. It is evidence about
whether the effect exists on this material, in neither direction a proof: it
does not bound AEC3 from above, since AEC3 adapts where this does not, and a
failure here would not rule AEC3 out either. An earlier version of this line
claimed the second half of that, and it contradicted the paragraph below it.

**What this computes**

  raw        the microphone as captured.
  linear     minus a finite-impulse-response echo estimate, fit by least squares
             in closed form over the spans chosen by --fit-mode, with the bulk
             delay estimated over those same spans. No real-time filter gets to
             see a recording before filtering it.
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

**Four fit modes, because in-sample is the weakest of them**

  full          fit on the whole take. Optimistic: the filter sees the same
                double-talk it is later scored on, and can use the reference to
                predict near-end speech that merely happens to correlate.
  far-end-only  fit only on stretches where the far end plays and the near end
                does not, then score everywhere. This is what a real canceller
                does, since adaptation freezes during double-talk — and it
                REFUSES both of this project's echo recordings, because in them
                the operator talks over the far end almost continuously. It
                fails closed on purpose: a selector that finds nothing safe must
                return nothing, not fall back to everything.
  first-half    fit on the first half. Paired with --score-after, the filter is
                then scored only on audio it never saw. That is the strongest
                claim the EXISTING recordings support, and it is weaker than it
                sounds: holding out the waveform stops the filter fitting the
                samples it is scored on, but a filter and mask can still suppress
                the operator's voice in audio they were never fit to. The
                room-noise control losing two windows of fourteen is that effect
                measured directly.
  prefix        fit only on audio before --fit-before. Intended for a take that
                opens with a deliberate far-end-only calibration phase and
                continues, without anyone moving, into double-talk: fit the
                phase, score what follows. The only arrangement here where the
                near end is absent from the fit because it had not started, not
                because a classifier judged it absent.

**How it is scored**

By the voiceprint gate, on operator retention and household false admission —
not by ERLE. Suppression in dB is a diagnostic here and a misleading headline:
the take that recovers best does so on 1.4 dB of double-talk suppression, while
the take that recovers least has 3.4 dB. A speaker embedding cares which
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
MIN_FIT_TOTAL = 4 * RATE  # under four seconds is not an echo path, it is a guess
DT_RATIO = 0.25         # residual within 6 dB of the echo estimate means near end
PREFIX_GUARD_S = 2.0    # gap between a calibration fit and the audio it is scored on


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
        xs = x[a:b]
        # Zero the output over the run's first `taps` samples. Those are exactly
        # the samples whose history lies outside the run, so including them asks
        # the filter to explain audio from a reference it was not given. Dropping
        # them removes that error from the cross-correlation entirely; only the
        # autocorrelation still carries an edge effect, bounded by taps over run
        # length and damped by the ridge.
        ys = y[a:b].copy()
        ys[:min(taps, len(ys))] = 0.0
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


def far_end_only(mic: np.ndarray,
                 ref: np.ndarray) -> tuple[list[tuple[int, int]], int]:
    """Ranges where the far end plays and the near end does not, and how much
    far-end-active audio there was to choose from.

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
        return [], 0

    # Two passes, because "the microphone is quiet" cannot be read off the
    # microphone. Echo is in it too, so thresholding raw level throws away the
    # loudest 30% of the echo — scattered through every span — and leaves runs
    # far shorter than the filter. Fit once on far-end activity alone, then look
    # at what the filter could NOT explain: that residual is the near end, and
    # it is what double-talk detection actually keys on.
    h = ls_fir(mic, ref, runs=active)
    echo = np.convolve(ref, h)[:len(mic)]
    resid_pw, echo_pw = frame_power(mic - echo), frame_power(echo)
    n = min(len(resid_pw), len(echo_pw))
    # Near-end present where the filter's leftover rivals the echo it removed.
    # A voice-activity detector on the residual was tried first and is the wrong
    # instrument: its absolute floor has no relationship to how loud the echo
    # is, so on quiet material it marked the filter's own error as speech and
    # excluded the entire take, and on loud material it would miss a talker
    # sitting under the floor. The ratio self-calibrates to the fit.
    loud = resid_pw[:n] > DT_RATIO * echo_pw[:n]
    near = np.zeros(len(mic), dtype=bool)
    for i in np.flatnonzero(loud):
        near[i * HOP:i * HOP + NFFT] = True

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

    # Fail closed. An earlier version ended `return runs or active`, which on
    # material where the operator never stops talking handed back every
    # far-end-active span — the exact double-talk this function exists to
    # remove — and reported it as a double-talk-free fit. A selector that finds
    # nothing must say nothing, and let the caller skip the take.
    return runs, sum(b - a for a, b in active)


def align(mic: np.ndarray, ref: np.ndarray,
          window: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray, int, float]:
    """Put the reference just before the echo, never on top of it, either sign.

    The margin is not cosmetic. Cross-correlation reports the delay of the
    strongest reflection, and the direct path arrives earlier — so shifting by
    exactly the measured peak puts part of the impulse response at a negative
    lag, where a causal filter cannot represent it at all. On a synthetic path
    with a known answer that cost 26 dB: the fit recovered a 40 dB echo at 14,
    and every downstream conclusion would have inherited it.

    A negative bulk delay — the microphone leading the reference — has the same
    consequence and was previously clamped to zero, which left the echo
    non-causal and cancelled nothing. It cannot happen through a loudspeaker,
    but it happens easily through a capture bug or a mislabelled leg, and a
    harness that silently returns 0.06 dB in that case is a harness that hides
    the bug it should be reporting. Both legs shift.
    """
    # The microphone defines the timeline. Trimming it to a shorter reference
    # discards recorded audio for no reason — on one take that silently dropped
    # the last 1.4 seconds, and the window it contained appeared or vanished
    # depending on which reference the run happened to borrow.
    if len(ref) < len(mic):
        ref = np.concatenate([ref, np.zeros(len(mic) - len(ref))])
    else:
        ref = ref[:len(mic)]
    # Delay is estimated over `window` when given, and the resulting shift is
    # applied to the whole reference. Estimating it over the whole take would
    # let audio the fit is later scored on decide the alignment the fit is built
    # from — a quieter version of the same leak the fit spans exist to close,
    # and one that near-end speech correlated with the reference could bend.
    a, b = window or (0, len(mic))
    bulk, peak = gcc_phat(mic[a:b], ref[a:b], int(MAX_LAG_S * RATE))
    if peak < PHAT_FLOOR:
        bulk = 0                       # nothing to lock onto; do not chop the take
    applied = bulk - ALIGN_MARGIN
    shifted = np.roll(ref, applied)
    if applied > 0:
        shifted[:applied] = 0.0
    elif applied < 0:
        # Rolling left wraps the head of the reference onto its tail, which is
        # fabricated audio the filter would happily fit. Only the reference ever
        # moves: a first version of this shifted the MICROPHONE for negative
        # delays and zeroed its head, which destroyed real recorded audio and
        # showed up as a clean take scoring -0.070 in the no-op control.
        shifted[applied:] = 0.0
    return mic, shifted, bulk, peak


def process(mic: np.ndarray, ref: np.ndarray, fit_mode: str,
            fit_before: float = 0.0) -> tuple[dict, dict]:
    """The three conditions, plus what the fit was estimated from."""
    m = min(len(mic), len(ref)) if len(ref) >= len(mic) else len(mic)
    # Alignment is estimated over the same audio the filter is fitted on,
    # wherever that is knowable before fitting.
    if fit_mode == "prefix":
        window = (0, min(int(fit_before * RATE), m))
    elif fit_mode == "first-half":
        window = (0, m // 2)
    else:
        # `full` is in-sample by definition, and `far-end-only` cannot choose
        # its spans until a provisional alignment exists. Both estimate over the
        # whole take, and neither supports an out-of-sample claim.
        window = None
    mic, ref, bulk, peak = align(mic, ref, window)
    m = len(mic)

    excluded = None
    if fit_mode == "full":
        runs = [(0, m)]
    elif fit_mode == "prefix":
        # A calibration prefix the operator deliberately kept silent through.
        # This is the only mode that fits on audio KNOWN to be free of his
        # voice, rather than on audio a classifier believes is free of it.
        runs = [(0, min(int(fit_before * RATE), m))]
        if runs[0][1] < MIN_FIT_TOTAL:
            return {}, {"skipped": f"prefix of {runs[0][1] / RATE:.2f}s is under the "
                                   f"{MIN_FIT_TOTAL / RATE:g}s floor"}
    elif fit_mode == "first-half":
        runs = [(0, m // 2)]
    elif fit_mode == "far-end-only":
        runs, active_samples = far_end_only(mic, ref)
        fitted = sum(b - a for a, b in runs)
        if fitted < MIN_FIT_TOTAL:
            return {}, {"skipped": f"{fitted / RATE:.2f}s of double-talk-free audio in "
                                   f"{len(runs)} runs, under the {MIN_FIT_TOTAL / RATE:g}s "
                                   f"floor"}
        excluded = round(1 - fitted / active_samples, 3) if active_samples else None
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
             "fit_runs": len(runs), "fit_mode": fit_mode,
             "diagnostics": diagnostics(mic, ref, linear, echo),
             # How much far-end-active time the near-end detector actually
             # removed. Near zero means the fit is in-sample in all but name,
             # and the take's result must not be described as double-talk-free.
             "excluded_fraction": excluded})


def diagnostics(mic: np.ndarray, ref: np.ndarray, resid: np.ndarray,
                echo: np.ndarray) -> dict:
    """The signal-processing view, recomputed through the corrected chain.

    These are diagnostics, not the result. An earlier draft carried them from a
    scratch script written before the alignment fix and argued they were
    "directionally safe because the fix only improves the fit" — which does not
    follow. Changing the alignment and the fit spans moves the residual, and
    coherence and level-dependence are not monotone in fit quality. They are
    computed here so they can be quoted.
    """
    mic_pw, ref_pw = frame_power(mic), frame_power(ref)
    res_pw, echo_pw = frame_power(resid), frame_power(echo)
    n = min(len(mic_pw), len(ref_pw), len(res_pw), len(echo_pw))
    mic_pw, ref_pw = mic_pw[:n], ref_pw[:n]
    res_pw, echo_pw = res_pw[:n], echo_pw[:n]
    if n < 20:
        return {}

    playing = ref_pw > np.percentile(ref_pw, 50)
    far_only = playing & (res_pw <= DT_RATIO * echo_pw)
    double_talk = playing & ~far_only
    idle = (~playing) & (mic_pw < np.percentile(mic_pw, 25))
    floor = float(np.median(res_pw[idle])) if idle.sum() > 5 else float(np.percentile(res_pw, 5))

    def db(sel, a, b):
        return (round(float(10 * np.log10((a[sel].mean() + 1e-20) / (b[sel].mean() + 1e-20))), 2)
                if sel.sum() > 5 else None)

    out = {
        "erle_far_end_only_db": db(far_only, mic_pw, res_pw),
        "erle_double_talk_db": db(double_talk, mic_pw, res_pw),
        "far_end_only_seconds": round(float(far_only.sum()) * HOP / RATE, 1),
        "double_talk_seconds": round(float(double_talk.sum()) * HOP / RATE, 1),
    }
    if far_only.sum() > 5:
        out["echo_above_noise_floor_db"] = round(
            float(10 * np.log10((mic_pw[far_only].mean() + 1e-20) / (floor + 1e-20))), 2)
        out["residual_above_noise_floor_db"] = round(
            float(10 * np.log10((res_pw[far_only].mean() + 1e-20) / (floor + 1e-20))), 2)

    # Band-averaged magnitude-squared coherence between microphone and
    # reference, expressed in dB as -10*log10(1 - C^2).
    #
    # NOT a ceiling on achievable suppression, though an earlier version of this
    # called it one and drew conclusions from it. Averaging coherence across a
    # band before the log is not the same quantity as the per-bin bound, and the
    # frames it is computed over are chosen by the same residual-to-echo test
    # used to select the frames ERLE is measured on. On both real takes the
    # measured linear suppression comes out ABOVE this number, which is the
    # arithmetic disproving the claim. It is reported as a descriptive statistic
    # about how linearly related the two legs are, and nothing follows from it
    # about longer filters.
    sel = np.flatnonzero(far_only if far_only.sum() > 20 else playing)
    win = np.hanning(NFFT)
    freqs = np.fft.rfftfreq(NFFT, 1 / RATE)
    sxy = np.zeros(NFFT // 2 + 1, dtype=complex)
    sxx = np.zeros(NFFT // 2 + 1)
    syy = np.zeros(NFFT // 2 + 1)
    gains, levels = [], []
    band = (freqs >= 200) & (freqs < 3000)
    for i in sel:
        s = i * HOP
        X = np.fft.rfft(ref[s:s + NFFT] * win, NFFT)
        Y = np.fft.rfft(mic[s:s + NFFT] * win, NFFT)
        sxy += Y * np.conj(X)
        sxx += np.abs(X) ** 2
        syy += np.abs(Y) ** 2
        xb, yb = (np.abs(X[band]) ** 2).sum(), (np.abs(Y[band]) ** 2).sum()
        if xb > 1e-18:
            levels.append(10 * np.log10(xb))
            gains.append(10 * np.log10(yb + 1e-20) - 10 * np.log10(xb))
    c2 = np.abs(sxy) ** 2 / (sxx * syy + 1e-20)
    out["band_coherence_db"] = {
        f"{lo}-{hi}Hz": round(float(-10 * np.log10(
            1 - min(float(c2[(freqs >= lo) & (freqs < hi)].mean()), 0.999))), 2)
        for lo, hi in ((100, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000))}

    if len(levels) >= 8:
        order = np.argsort(levels)
        g = np.array(gains)
        lo_q, hi_q = order[:len(order) // 4], order[-len(order) // 4:]
        # A linear path holds one gain at every level; a limiter gives back less
        # as you ask for more. This separates "the speaker is compressing" from
        # "the echo is simply weak".
        out["level_dependence_db"] = round(
            float(np.median(g[hi_q]) - np.median(g[lo_q])), 2)
    return out


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

    # 6a. The double-talk selector must fail CLOSED. Near-end speech covering
    #     every far-end interval leaves nothing safe to fit on, and the previous
    #     version returned every far-end-active span instead — handing back the
    #     exact double-talk it exists to remove, labelled double-talk-free.
    # Matched to the echo's level on purpose. A near end 10 dB under the echo is
    # not double-talk in any sense the fit cares about — it barely perturbs the
    # least-squares solution — and a control built at that level would pass
    # while proving nothing. Double-talk is when the two are comparable.
    true_echo = np.convolve(far, h_true)[:len(far)]
    talky = _synth(24.0, 5, 100, 7000)           # the operator never stops
    talky *= np.sqrt((true_echo[gate > 0] ** 2).mean() / (talky ** 2).mean())
    busy = talky + true_echo
    runs, _active = far_end_only(*align(busy, far)[:2])
    print(f"  {'continuous near end leaves no span to fit on':52s} "
          f"{len(runs):6d} runs", end="")
    if not runs:
        print("   ok")
    else:
        print(f"   FAILED (returned {sum(b - a for a, b in runs) / RATE:.1f}s as safe)")
        ok = False
    conds, _ = process(busy, far, "far-end-only")
    print(f"  {'and the run is skipped rather than reported':52s} "
          f"{'skipped' if not conds else 'REPORTED':>13}", end="")
    print("   ok" if not conds else "   FAILED")
    ok &= not conds

    # 6b. A reference that arrives LATER than the echo gives a negative bulk
    #     delay. Through a loudspeaker that cannot happen; through a capture bug
    #     or a mislabelled leg it happens easily, and the delay used to be
    #     clamped to zero, which cancelled nothing and said nothing.
    late_ref = np.roll(far, 500)
    late_ref[:500] = 0.0
    conds, meta = process(mic, late_ref, "full")
    got = _erle(conds["raw"], conds["linear"], far_only)
    print(f"  {'reference arriving after the echo still cancels':52s} ERLE {got:6.1f} dB",
          end="")
    if got > 20 and meta["bulk_delay_ms"] < 0:
        print("   ok")
    else:
        print(f"   FAILED (bulk {meta['bulk_delay_ms']:+.1f} ms; a negative delay "
              f"must not be clamped away)")
        ok = False

    # 7. The calibration-prefix protocol, end to end: fit only on the recorded
    #    far-end-only phase, then measure on the double-talk that follows. This
    #    is the mode the next recording is for, and it is the one arrangement
    #    where the fit provably never saw the near end — because the near end
    #    was not being produced yet, rather than because a classifier said so.
    #    Scored as near-end fidelity, not ERLE. Suppression during double-talk
    #    is capped by how loud the near end is — with the two comparable it
    #    cannot exceed about 3 dB however perfect the filter — so an ERLE
    #    threshold here would fail a working canceller. What the prefix fit has
    #    to deliver is that the residual IS the operator.
    conds, meta = process(mic, far, "prefix", fit_before=12.0)
    dt_after = ~far_only & (gate > 0)
    got = 10 * np.log10(((near[dt_after] ** 2).mean() + 1e-20)
                        / (((conds["linear"][dt_after] - near[dt_after]) ** 2).mean() + 1e-20))
    print(f"  {'prefix fit recovers the near end after it':52s} SNR  {got:6.1f} dB",
          end="")
    if got > 20 and meta["fit_mode"] == "prefix":
        print("   ok")
    else:
        print("   FAILED (expected > 20 on audio after the calibration phase)")
        ok = False
    #    And the delay must come from the prefix alone. Here the audio AFTER the
    #    calibration phase carries a second, louder copy of the reference at a
    #    different lag — a stand-in for anything post-boundary that correlates
    #    with the far end. Estimating alignment over the whole take walks onto
    #    that lag; estimating it over the prefix does not, and the difference is
    #    whether the fit was built from audio it is later scored on.
    decoy = mic.copy()
    after = slice(12 * RATE, len(mic))
    decoy[after] += 3.0 * np.roll(far, 9000)[after]
    _, meta_whole = process(decoy, far, "full")
    _, meta_pref = process(decoy, far, "prefix", fit_before=12.0)
    print(f"  {'prefix alignment ignores a decoy after the boundary':52s} "
          f"{meta_pref['bulk_delay_ms']:6.1f} ms", end="")
    if abs(meta_pref["bulk_delay_ms"] - 15.0) < 1.0 < abs(meta_whole["bulk_delay_ms"] - 15.0):
        print("   ok")
    else:
        print(f"   FAILED (whole-take estimate {meta_whole['bulk_delay_ms']:.1f} ms; "
              f"the decoy must move that one and not this one)")
        ok = False

    short, meta = process(mic, far, "prefix", fit_before=1.0)
    print(f"  {'and a prefix under the floor is refused':52s} "
          f"{'skipped' if not short else 'ACCEPTED':>13}", end="")
    print("   ok" if not short else "   FAILED")
    ok &= not short

    # 8. Silence is a valid reference, not a crash. This is the singular-matrix
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

    # 9. Windows must not overlap by default, or the count overstates the
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
                   choices=("far-end-only", "full", "first-half", "prefix"))
    p.add_argument("--fit-before", type=float, default=0.0, metavar="SECONDS",
                   help="with --fit-mode prefix, fit only on audio before this point. "
                        "Pair it with --score-after at the same boundary and the "
                        "filter is fitted on a recorded far-end-only calibration "
                        "phase and scored on the double-talk that follows it, in one "
                        "continuous take with the acoustic path unchanged")
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
    p.add_argument("--score-after", type=float, default=0.0, metavar="SECONDS",
                   help="score only windows starting at or after this point. Paired "
                        "with --fit-mode first-half it gives a genuinely held-out "
                        "number: the filter is fit on audio it is then never scored on")
    p.add_argument("--window", type=float, default=WINDOW_S)
    p.add_argument("--hop", type=float, default=HOP_S)
    p.add_argument("--threshold", type=float, default=0.580)
    p.add_argument("--model-dir", type=Path, default=Path.home() / ".cache" / "speaker-gate")
    p.add_argument("--label", default="run",
                   help="name this experiment inside the output artifact, so one file "
                        "can hold the measurement and every control beside it")
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
    supplied, segment_digests, schemas = {}, {}, {}
    for spec in args.segments:
        name, _, path = spec.partition("=")
        seg_path = Path(path).expanduser()
        loaded = json.loads(seg_path.read_text())
        if isinstance(loaded, dict) and loaded.get("schema") == "mic-segments/1":
            segs = loaded["segments"]
            schemas[name] = loaded["schema"]
        elif isinstance(loaded, dict) and "turns" in loaded:
            p.error(
                f"{seg_path} is a merged transcript, which cannot index mic.wav. It "
                f"carries both legs with speaker labels cleared whenever bleed is "
                f"detected, so operator and far-end turns are indistinguishable in "
                f"it; its times are on the merged session clock rather than the "
                f"microphone's, off by the startup skew; and its microphone turns "
                f"have already been through drop_bled, which removes exactly the "
                f"contaminated operator speech an echo experiment is trying to "
                f"recover. Use mic-segments.json from the same capture.")
        else:
            segs = loaded            # a bare [{start, end}] list
            schemas[name] = "list"
        if any("end" not in seg for seg in segs):
            p.error(f"{seg_path} has segments with no end. Inferring an end from the "
                    f"next segment's start swallows the pause before it — at a "
                    f"speaker change, the next speaker's onset as well. Supply a "
                    f"segment list with measured ends.")
        supplied[name] = segs
        segment_digests[name] = sha256(seg_path)

    if args.fit_mode == "prefix":
        if not args.fit_before:
            p.error("--fit-mode prefix needs --fit-before")
        if not args.score_after:
            args.score_after = args.fit_before + PREFIX_GUARD_S
        if args.score_after < args.fit_before + PREFIX_GUARD_S:
            p.error(f"--score-after {args.score_after:g} overlaps the fit interval "
                    f"(ends {args.fit_before:g}, needs {PREFIX_GUARD_S:g}s of guard). "
                    f"A prefix run that scores its own calibration audio is not "
                    f"held out, and reporting it as such is the failure this mode "
                    f"exists to prevent.")
        # Enrolment takes are exempt: they exist to build the profile, and their
        # rows are a sanity check rather than the measurement.
        wrong = [n for n in supplied if schemas.get(n) != "mic-segments/1"]
        if wrong:
            p.error(f"--fit-mode prefix needs mic-segments/1 for {', '.join(wrong)}. "
                    f"A bare list carries no guarantee that its times are on the "
                    f"microphone's own clock or that it holds only the microphone, "
                    f"and both have to be true for the result to mean anything.")
        for n, segs in supplied.items():
            early = [g for g in segs if g["start"] < args.fit_before]
            if early:
                p.error(
                    f"{n}: {len(early)} mic segment(s) start inside the calibration "
                    f"prefix, the first at {min(g['start'] for g in early):.1f}s "
                    f"against a boundary of {args.fit_before:g}s. The prefix is "
                    f"supposed to be the operator saying nothing, and this is the "
                    f"check that it was — take the recording again rather than "
                    f"fitting an echo path on audio with his voice in it.")
        missing = [n for n in takes if n not in supplied and n not in enroll_names]
        if missing:
            p.error(f"--fit-mode prefix needs --segments for {', '.join(missing)}. "
                    f"This is the acceptance path, and the gate consumes whole "
                    f"caller-supplied segments; scoring it on fixed windows would "
                    f"measure something the product never runs. Pass the capture's "
                    f"own transcript.json.")


    enc = sg.load_encoder(args.model_dir)
    # The checkpoint identifies the scorer as surely as the recordings identify
    # the input. A score is only reproducible if both are pinned.
    ckpt = args.model_dir / "embedding_model.ckpt"
    encoder_digest = sha256(ckpt.resolve()) if ckpt.exists() else None
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
        "score_after_s": args.score_after or None,
        "supplied_segments": segment_digests,
        "supplied_schemas": schemas,
        # The observed onset, not the boundary that was aimed for. It is what
        # shows the calibration phase was actually free of the operator.
        "first_mic_speech_s": {n: (min(g["start"] for g in segs) if segs else None)
                               for n, segs in supplied.items()},
        "max_lag_s": MAX_LAG_S, "phat_floor": PHAT_FLOOR,
        "min_fit_run": MIN_FIT_RUN, "align_margin": ALIGN_MARGIN,
        "min_fit_total": MIN_FIT_TOTAL, "dt_ratio": DT_RATIO,
        "fit_before_s": args.fit_before or None,
        "harness_sha256": sha256(Path(__file__).resolve()),
        "encoder_sha256": encoder_digest,
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
        conds, meta = process(mic, ref, args.fit_mode, args.fit_before)
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
        segs = [s for s in segs if s["start"] >= args.score_after]
        if not segs:
            print(f"{name:11s} no windows at or after {args.score_after:g}s")
            continue
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
        existing = json.loads(args.out.read_text()) if args.out.exists() else {}
        existing[args.label] = manifest
        args.out.write_text(json.dumps(dict(sorted(existing.items())), indent=2) + "\n")
        print(f"wrote {args.out} [{args.label}]")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
