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

**And neither windows nor segments say who was talking.** Both come from voicing
on the microphone, and on speakers the microphone is voiced whenever the far end
plays — so a count of them mixes the voice being recovered with the voice being
cancelled. Transcribing does not separate them either, with more confidence and
the same error. Every figure here measured before --protocol existed used that
mixture as its denominator, which makes those ratios floors on recovery rather
than measures of it: an interval holding no operator can only count as a miss.

--protocol is the way out, and prefix mode requires it. `dual_capture.py
--protocol` shows the operator timed visual cues and writes the schedule beside
the recordings, bound to the audio by digest and sample count. Segments are then
scored in three groups — wholly inside a speak interval, wholly inside a silent
one, straddling a cue — with a second trimmed off each interval's edges for
reaction time. The silent intervals do double duty: audio that must not be
admitted as the operator under any condition, and the only echo-only stretches
in this project, which is what a suppression figure needs to mean anything.

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
FLOOR_FRAME_MS = 25.0   # frame length for the noise-floor estimate
FLOOR_RATIO_MIN = 2.5   # against a FRAME floor, where noise itself scores 1.05
MIN_CLASS_SEGMENTS = 3  # per scored class, below which a run is inconclusive
MIN_CLASS_SECONDS = 8.0
MIN_ECHO_ONLY_S = 4.0   # far-end-active audio needed before suppression is a number
REF_ACTIVE_DB = 20.0    # within this of the reference's loud level counts as playing
REF_ACTIVE_FLOOR = 1e-4  # and above this absolutely, so digital silence never counts
SCRIPT_OVERLAP_MIN = 0.5   # of a passage, in the far end, before it is unusable
SEGMENT_PRECISION_MIN = 0.5  # of a segment's own words that must come from the passage
MIN_SEGMENT_TOKENS = 3     # fewer than this transcribed is unverified, not judged


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wav_frames(path: Path) -> int:
    """Length from the header. Pre-flight validation must not depend on reading
    a 75-minute control into memory to find out that its schedule is wrong."""
    with wave.open(str(path)) as w:
        return w.getnframes()


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

    return ({"raw": mic, "linear": linear, "masked": masked,
             # Not scored conditions. Carried because every consumer downstream
             # works on the microphone's timeline, and the reference does not
             # arrive on it — `align` shifted a private copy by up to the 1.7 s
             # of startup skew this project has measured. Anything selecting
             # "where the far end was playing" from the caller's own array is
             # selecting the wrong samples, silently.
             "_aligned_ref": ref, "_echo": echo},
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
# Ground truth. Everything below answers one question the audio cannot: which
# intervals held the operator's voice.
#
# Voicing does not answer it. On speakers the far end reaches the microphone,
# so a voiced microphone interval means "something was audible here", and both
# a talking operator and a silent one produce those. Transcribing does not
# answer it either, for the same reason and with more confidence. Every earlier
# number in this file used voiced microphone windows as its denominator, which
# is a mixture, and this is what replaces that.
# --------------------------------------------------------------------------

class SourceError(Exception):
    """A supplied artifact cannot support the claim the run would make from it."""


def _check_binding(path: Path, doc: dict, digest: str, samples: int,
                   prefix: str, wav: str) -> None:
    """An artifact indexes one specific recording or it indexes nothing.

    Both fields are load-bearing. The digest catches a same-schema file from a
    different take, which otherwise loads in silence and points every segment at
    unrelated audio. The sample count catches the same recording trimmed after
    the fact — that slides all the times relative to the audio while leaving a
    rewritten file's digest perfectly self-consistent with itself.

    Each leg is checked against its own count. The two run on independent clocks
    and legitimately differ — 848000 against 851200 over a two-minute capture on
    this machine — so cross-checking them would reject every real recording.
    """
    for field in (f"{prefix}_sha256", f"{prefix}_samples"):
        if doc.get(field) is None:
            raise SourceError(
                f"{path} carries no {field}, so nothing ties it to {wav}. "
                f"Re-run the capture: dual_capture writes both.")
    if doc[f"{prefix}_sha256"] != digest:
        raise SourceError(
            f"{path} was written for a different recording "
            f"({doc[f'{prefix}_sha256'][:12]}..., this {wav} is {digest[:12]}...). "
            f"Its times index audio that is not here.")
    if int(doc[f"{prefix}_samples"]) != int(samples):
        raise SourceError(
            f"{path} was written against {doc[f'{prefix}_samples']} samples and "
            f"this {wav} has {samples}. The recording changed length after the "
            f"artifact was written, so every time in it has moved.")


def load_segments(path: Path, *, digest: str, samples: int,
                  leg: str = "mic") -> list[dict]:
    """Read a mic-segments/1 list, or refuse with the reason it cannot be used."""
    loaded = json.loads(Path(path).read_text())
    if not isinstance(loaded, dict):
        raise SourceError(
            f"{path} is a bare list. A list carries no guarantee that its times "
            f"are on the microphone's own clock or that it holds only the "
            f"microphone, and both have to be true for the result to mean "
            f"anything. Use mic-segments.json from the capture.")
    if loaded.get("schema") != "mic-segments/1":
        if "turns" in loaded:
            raise SourceError(
                f"{path} is a merged transcript, which cannot index mic.wav. It "
                f"carries both legs with speaker labels cleared whenever bleed "
                f"is detected, so operator and far-end turns are "
                f"indistinguishable in it; its times are on the merged session "
                f"clock rather than the microphone's, off by the startup skew; "
                f"and its microphone turns have already been through drop_bled, "
                f"which removes exactly the contaminated operator speech an echo "
                f"experiment is trying to recover. Use mic-segments.json from "
                f"the same capture.")
        raise SourceError(f"{path}: expected schema mic-segments/1, got "
                          f"{loaded.get('schema')!r}.")
    if loaded.get("timeline") != f"{leg}-local":
        raise SourceError(f"{path} declares timeline {loaded.get('timeline')!r}, "
                          f"not {leg}-local. Only that leg's own times index "
                          f"{leg}.wav.")
    if "voicing" not in (loaded.get("filtered") or []):
        raise SourceError(
            f"{path} does not declare the voicing filter, so it is not the "
            f"artifact this expects. A list that has been through drop_bled "
            f"would also arrive here, and that one has had the contaminated "
            f"operator speech removed from it already.")
    _check_binding(Path(path), loaded, digest, samples, "audio", f"{leg}.wav")
    segs = loaded["segments"]
    if any("end" not in s for s in segs):
        raise SourceError(
            f"{path} has segments with no end. Inferring an end from the next "
            f"segment's start swallows the pause before it — at a speaker "
            f"change, the next speaker's onset as well.")
    for a, b in pairwise(segs):
        if b["start"] < a["end"] - 1e-9:
            raise SourceError(
                f"{path} has overlapping segments ({a['start']:.2f}-{a['end']:.2f} "
                f"and {b['start']:.2f}-{b['end']:.2f}). Overlap counts the same "
                f"audio more than once, which inflates every count and every "
                f"duration computed from this list — three copies of one "
                f"three-second span satisfy an eight-second requirement.")
        if b["start"] < a["start"] - 1e-9:
            raise SourceError(f"{path} is not in time order.")
    return segs


def load_protocol(path: Path, *, mic_digest: str, mic_samples: int,
                  sys_digest: str, sys_samples: int) -> dict:
    """Read the cue schedule that says who was supposed to be talking when.

    Phases running past the end of the recording are dropped rather than
    refused: a take stopped early still carries whatever intervals completed,
    and throwing those away would be its own kind of waste. A calibration phase
    that does not fit IS refused, because a prefix fit has nothing to stand on
    without it.
    """
    doc = json.loads(Path(path).read_text())
    if not isinstance(doc, dict) or doc.get("schema") != "capture-protocol/1":
        raise SourceError(f"{path}: expected schema capture-protocol/1.")
    if doc.get("timeline") != "mic-local":
        raise SourceError(f"{path} declares timeline {doc.get('timeline')!r}. "
                          f"Only mic-local times index mic.wav.")
    if doc.get("rate") != RATE:
        raise SourceError(f"{path} was recorded at {doc.get('rate')} Hz, not {RATE}.")
    _check_binding(Path(path), doc, mic_digest, mic_samples, "mic", "mic.wav")
    _check_binding(Path(path), doc, sys_digest, sys_samples, "system", "system.wav")
    phases = doc.get("phases") or []
    for ph in phases:
        if not {"start", "end", "expect", "role", "script"} <= set(ph):
            raise SourceError(
                f"{path}: a phase is missing start/end/expect/role/script.")
        if ph["expect"] not in ("silence", "operator"):
            raise SourceError(f"{path}: unknown expect {ph['expect']!r}.")
    if any(a["end"] > b["start"] + 1e-9 for a, b in pairwise(phases)):
        raise SourceError(f"{path}: phases overlap, so an interval has two labels.")

    duration = mic_samples / RATE
    cal = [ph for ph in phases if ph["role"] == "calibration"]
    if not cal:
        raise SourceError(f"{path} declares no calibration phase.")
    if not any(ph["expect"] == "operator" for ph in phases):
        raise SourceError(
            f"{path} declares no speak interval, so it schedules nothing to "
            f"score and nothing to hold a negative control against.")
    if cal[-1]["end"] > duration:
        raise SourceError(
            f"{path}: the calibration phase ends at {cal[-1]['end']:.1f}s and the "
            f"recording is {duration:.1f}s. The take was stopped before the fit "
            f"interval finished — record it again.")
    kept = [ph for ph in phases if ph["end"] <= duration]
    for i, ph in enumerate(kept):
        # Attribution runs off the boundaries the OPERATOR saw, not the ones the
        # schedule intended. A cue displayed late used to eat the reaction margin
        # instead of moving the interval: a control cue 0.9s late against a 1.0s
        # margin left 0.1s to stop talking before the echo-only window opened,
        # and any overrun scored as far-end-only audio. Both edges move, because
        # what ends an interval is the next cue appearing, not the clock: an
        # instruction stands until it is replaced, so a late successor genuinely
        # extends its predecessor.
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        ph["obs_start"] = ph.get("shown_at_s")
        ph["obs_end"] = nxt.get("shown_at_s") if nxt else None
        if ph["obs_start"] is None:
            ph["obs_start"] = ph["start"]
        if ph["obs_end"] is None:
            # The last interval has no successor to end it, and a protocol
            # written before cue times were recorded has none at all. The
            # schedule is the fallback, and a run missing them is inconclusive
            # for that reason alone — so this fallback never backs a published
            # figure, it only keeps the synthetic paths readable.
            ph["obs_end"] = ph["end"]
    doc["phases"] = kept
    doc["dropped_phases"] = len(phases) - len(kept)
    return doc


def phase_interior(ph: dict, margin: float) -> tuple[float, float] | None:
    """The part of a phase far enough from both cues to be attributable.

    A cue is seen and acted on, not obeyed instantaneously; speech also trails
    past the cue that ends it. The margin is what keeps a late start or a long
    tail from being scored as if it belonged to the next interval — and it is
    measured from when the cue was OBSERVED, so display lateness moves the
    interval rather than spending the operator's reaction time.
    """
    lo = ph.get("obs_start", ph["start"]) + margin
    hi = ph.get("obs_end", ph["end"]) - margin
    return (lo, hi) if hi - lo > 0 else None


def classify(segs: list[dict], phases: list[dict], margin: float,
             far_text: str | None = None) -> dict:
    """Split segments by the phase containing them, and by whether the operator
    is demonstrably in them.

    Containment is strict on both ends. A segment straddling a boundary spans two
    different intentions and belongs to neither; counting it under the phase it
    starts in is how a mixture gets back into a denominator that exists to
    exclude one.

    Containment alone is not enough for the speak intervals, which is what the
    first version of this got wrong. A cue phrase read once at the top of an
    interval shows the operator spoke somewhere in it, and then every segment in
    the interval was counted as his — including the ones during a pause, which on
    speakers hold the far end and nothing else. The interval-wide label smuggled
    the mixture back in one level down.

    So each segment is asked about itself. Of the content words its own
    transcript carries, what fraction come from the passage the operator was
    reading? Reading the passage puts nearly all of them there; far-end echo puts
    nearly none, because the playback is saying something else. Precision rather
    than recall, because a three-second segment can only ever hold a fraction of
    a twenty-five-word passage, so recall is bounded low by arithmetic and would
    reject every real segment.

    A segment that fails goes to `operator_unverified`, which is reported and not
    counted in the verified class. That is deliberate and one-directional:
    echo-contaminated speech transcribes badly, which is the condition under
    study, so a failure is not evidence he was silent. It is evidence this
    segment cannot carry the claim.

    Which is also the limit of this test, and it has to be said plainly: the
    passage check reads the RAW transcript, so it selects on the contamination
    the experiment is measuring. The segments it drops are disproportionately the
    hard ones. Nothing here can fix that — it needs a near-end channel this rig
    does not have — so the class is scored anyway and reported as the other end
    of an interval by `scheduled_bounds`, rather than the retained subset being
    published as the result.
    """
    far_tokens = tokens(far_text) if far_text else set()
    out = {"operator": [], "operator_unverified": [], "control": [],
           "calibration": [], "unattributable": []}
    for seg in segs:
        placed, phase = None, None
        for ph in phases:
            span = phase_interior(ph, margin)
            if span and span[0] <= seg["start"] and seg["end"] <= span[1]:
                placed = "operator" if ph["expect"] == "operator" else ph["role"]
                phase = ph
                break
        if placed == "operator":
            want = tokens(phase["script"] or "") - far_tokens
            heard = tokens(seg.get("text", ""))
            hit = len(heard & want) / len(heard) if heard else 0.0
            seg = dict(seg, script_precision=round(hit, 2),
                       tokens_heard=len(heard))
            if len(heard) < MIN_SEGMENT_TOKENS or hit < SEGMENT_PRECISION_MIN:
                placed = "operator_unverified"
        elif placed == "calibration":
            # The fit interval is the one place the operator's voice is actively
            # harmful: `prefix` mode fits the echo path there on the premise that
            # only the far end is present, and a filter fitted on his voice learns
            # to cancel it. Silence there is an assumption everywhere else in this
            # file; here it is at least testable in one direction. A calibration
            # segment carrying a passage means he started reading before the cue,
            # and the run says so rather than fitting on it.
            want = {t for ph in phases for t in tokens(ph["script"] or "")} - far_tokens
            heard = tokens(seg.get("text", ""))
            hit = len(heard & want) / len(heard) if heard else 0.0
            seg = dict(seg, script_precision=round(hit, 2), tokens_heard=len(heard))
        out.setdefault(placed or "unattributable", []).append(seg)
    return out


def union_seconds(segs: list[dict]) -> float:
    """Distinct audio covered, not the sum of segment lengths.

    Summing is what an eight-second requirement gets satisfied by three copies of
    the same three-second span. Overlap is refused at load, so this agrees with
    the sum on any artifact that got this far — it is here because the evidence
    bar should be stated in terms of what it actually means, not in terms of what
    happens to be equivalent under the current guards.
    """
    total, cursor = 0.0, None
    for seg in sorted(segs, key=lambda s: s["start"]):
        lo, hi = seg["start"], seg["end"]
        lo = max(lo, cursor) if cursor is not None else lo
        if hi > lo:
            total += hi - lo
            cursor = hi
    return total


def conditions(rows: dict) -> tuple[str, ...]:
    """The conditions this run actually scored.

    `run_verdict` and `scheduled_bounds` both used to name raw/linear/masked
    literally, so a condition added with --condition — a real canceller's output,
    which is the whole point of the flag — appeared in the printed table and in
    neither the noise-floor check nor the bounds. A figure that no guard covers is
    worse than a missing one, because it reads as having passed them.

    The fallback is for hand-built fixtures in the self-test, which predate the
    key. It is the historical triple, so those controls keep testing what they were
    written to test.
    """
    return tuple(rows.get("conditions") or ("raw", "linear", "masked"))


def inside_repo(path: Path, repo: Path | None = None) -> bool:
    """Whether an output path lands in the working tree.

    Extracted so a control can hold it. The rule it enforces — the scores artifact
    carries what was said, and this repo is public — was learned the expensive way:
    197 lines of a household recording reached four public commits inside
    `spike/aec-bound-results.json`. A .gitignore rule only covers paths someone
    thought of, so the refusal lives in the tool.
    """
    repo = repo or Path(__file__).resolve().parent.parent
    try:
        return path.expanduser().resolve().is_relative_to(repo.resolve())
    except OSError:
        return False


def scheduled_bounds(rows: dict, threshold: float) -> dict:
    """Both readings of the speak intervals, because neither one is the answer.

    `classify` decides which segments carry the operator by reading the RAW
    microphone transcript — the contaminated signal the experiment exists to
    improve on. That makes the retained set a biased sample, and biased in the
    direction that flatters the result: the segments where echo most wrecks the
    transcript are exactly the segments where cancellation has the most to do,
    and those are the ones that fail the passage check and leave. A rate computed
    over what remains is recovery CONDITIONAL ON raw ASR already having found
    him, which is not the question.

    Correcting it needs a near-end observation channel this rig does not have — a
    close-talk mic worn by the operator, used only as labels. Short of that, the
    honest move is to stop reporting one number and report the interval it lies
    in:

      verified   — only segments whose own transcript carries the passage. The
                   optimistic end, selected as described above.
      scheduled  — every segment inside a speak interval, verified or not. The
                   pessimistic end, which treats "he read throughout the cued
                   interval" as an assumption — the same controlled-human
                   assumption the silent intervals already run on, applied
                   consistently instead of only where it helps.

    The truth is between them, and the spread is the cost of having no
    independent labels. Both are arithmetic over rows already scored, so this
    costs no extra encoding.
    """
    out = {}
    ver = rows["classes"].get("operator", {}).get("windows", [])
    unv = rows["classes"].get("operator_unverified", {}).get("windows", [])
    for cond in conditions(rows):
        def rate(ws: list[dict], cond: str = cond) -> dict | None:
            scored = [w for w in ws if w.get(cond) is not None]
            if not scored:
                return None
            return {"admitted": sum(1 for w in scored if w[cond] >= threshold),
                    "of": len(scored), "seconds": round(union_seconds(scored), 1)}
        both = rate(ver + unv)
        if both is None:
            continue
        out[cond] = {"verified": rate(ver), "scheduled": both}
    return {"conditions": out,
            "excluded_seconds": round(union_seconds(unv), 1),
            "why": "the verified subset is selected using the raw contaminated "
                   "transcript, so it is an upper bound; the scheduled set "
                   "assumes cue adherence, so it is a lower bound"}


def scored_conditions(conds: dict) -> dict:
    """The three audio conditions, without the working signals carried beside them.

    `process` returns the aligned reference and the echo estimate in the same
    dict, because both are needed downstream and both are on the microphone's
    timeline. Neither is a condition to score, and an underscore prefix alone
    would not have stopped a loop over `.items()` from embedding them.
    """
    return {k: v for k, v in conds.items() if not k.startswith("_")}


def frame_rms(x: np.ndarray, ms: float = FLOOR_FRAME_MS) -> np.ndarray:
    n = int(RATE * ms / 1000)
    k = len(x) // n
    if k < 1:
        return np.array([float(np.sqrt((x.astype(np.float64) ** 2).mean()))])
    return np.sqrt((x[:k * n].astype(np.float64).reshape(k, n) ** 2).mean(axis=1))


def run_verdict(rows: dict, protocol: dict, threshold: float) -> dict:
    """Did this take produce a result, or only the shape of one.

    A run can finish, print a table and write a manifest while carrying no
    operator segments at all, or none of the negative control — phases that ran
    past the end of a short take get dropped, and a class with no members is
    skipped rather than reported. What lands in the artifact then looks exactly
    like a measurement, and the label under which it was written ("acceptance")
    is the only thing suggesting otherwise.

    So the verdict is written down, and it has to consult everything that could
    invalidate the run rather than only the counts. An earlier version checked
    class sizes, dropped phases and the suppression figure, and ignored both
    compliance and the noise-floor ratios — so a take where not one cue was
    verified, or where an admission came from near-silence, came back "scored".
    Each of those reproduces the failure the surrounding machinery exists to
    prevent, under a label that says the opposite.

    Four things have to hold:

    * Both classes populated, measured as distinct audio rather than summed
      segment lengths. The operator class is the claim; the silent class is what
      stops the claim resting on a gate that admits everything.
    * At least one speak interval verified from content, and every scored
      operator segment carrying the passage itself. Zero verified cues means the
      protocol was not followed and the labels are intent, not observation.
    * Every cue displayed within the attribution margin of its scheduled time.
      A cue that appeared late labels audio against a boundary the operator
      never saw.
    * No admitted segment sitting at the take's own noise floor, in any scored
      condition. Such an admission is the embedding reacting to near-silence,
      and it counts in the numerator unless something removes it.

    An inconclusive run is recorded as inconclusive, with the counts that made it
    so, rather than left out of the file — an absent label reads as "not run
    yet", which is a different and less useful fact.
    """
    why = []
    for cls, what in (("operator", "the claim"),
                      ("control", "the gate's negative control")):
        members = rows["classes"].get(cls, {}).get("windows", [])
        seconds = union_seconds(members)
        if len(members) < MIN_CLASS_SEGMENTS or seconds < MIN_CLASS_SECONDS:
            why.append(
                f"{cls} ({what}): {len(members)} segments, {seconds:.1f}s of "
                f"distinct audio — needs {MIN_CLASS_SEGMENTS} and "
                f"{MIN_CLASS_SECONDS:g}s")

    c = rows.get("compliance") or {}
    if not c.get("speak_intervals_verified"):
        why.append(
            f"not one speak interval was verified from content "
            f"({c.get('speak_intervals_unverified', 0)} unverified) — the labels "
            f"are the schedule's intent, not an observation of who spoke")
    # A missing cue time is not a passing one. The earlier filter skipped the
    # Nones on its way to comparing magnitudes, so a run that recorded no cue
    # times at all satisfied "every cue displayed within the margin" vacuously —
    # it returned `scored` with an empty `why`. Unobserved is unproven: without
    # these, every label is the schedule's intent, and the interiors above fall
    # back to scheduled boundaries the operator may never have seen.
    unobserved = [ph for ph in c.get("phases", []) if ph.get("cue_late_s") is None]
    if unobserved:
        why.append(
            f"{len(unobserved)} of {len(c.get('phases', []))} cues have no "
            f"recorded display time — nothing establishes that the audio was "
            f"labelled against boundaries the operator actually saw")
    late = [ph for ph in c.get("phases", [])
            if ph.get("cue_late_s") is not None
            and abs(ph["cue_late_s"]) > protocol["cue_margin_s"]]
    if late:
        worst = max(late, key=lambda ph: abs(ph["cue_late_s"]))
        why.append(
            f"{len(late)} cue(s) appeared further than the "
            f"{protocol['cue_margin_s']:g}s margin from their scheduled time, "
            f"worst {worst['cue_late_s']:+.2f}s at {worst['start']:.0f}s — that "
            f"audio is labelled against a boundary the operator never saw")

    # Unverified segments are excluded from the claim, not fatal to it. Nobody
    # reads a passage without breathing, and a segment landing on a gap will
    # always fail — disqualifying on any of them would make every real take
    # inconclusive. What is fatal is unverified audio OUTWEIGHING verified: at
    # that point most of the speak intervals hold something unestablished, and
    # "he was reading throughout" is no longer a description of the recording.
    unverified = union_seconds(
        rows["classes"].get("operator_unverified", {}).get("windows", []))
    verified = union_seconds(rows["classes"].get("operator", {}).get("windows", []))
    if unverified > verified:
        why.append(
            f"{unverified:.1f}s inside the speak intervals does not carry the "
            f"passage against {verified:.1f}s that does — most of what was "
            f"supposed to be the operator reading is unestablished")

    # `operator_unverified` is in here because it is scored and published as the
    # pessimistic bound, so a hollow admission there reaches a reported figure
    # exactly as one in the verified class does. Excluding it from the claim is
    # not the same as excluding it from the file.
    for cls in ("operator", "operator_unverified", "control"):
        for row in rows["classes"].get(cls, {}).get("windows", []):
            for cond in conditions(rows):
                ratio = row.get(f"{cond}_rms_over_floor")
                if (row.get(cond) is not None and row[cond] >= threshold
                        and ratio is not None and ratio < FLOOR_RATIO_MIN):
                    why.append(
                        f"{cls} segment at {row['start']:.1f}s was admitted under "
                        f"{cond} at {ratio:.1f}x the noise floor — that is the "
                        f"embedding reacting to near-silence, and it is in the "
                        f"numerator")

    # A passage read inside the fit interval, which prefix mode fits on as though
    # only the far end were there. Detected rather than assumed, because this is
    # the one silence the audio can speak to: his words cannot arrive by echo.
    early = [seg for seg in rows["classes"].get("calibration", {}).get("windows", [])
             if seg.get("tokens_heard", 0) >= MIN_SEGMENT_TOKENS
             and seg.get("script_precision", 0.0) >= SEGMENT_PRECISION_MIN]
    if early:
        why.append(
            f"{len(early)} segment(s) inside the calibration phase carry a cue "
            f"passage, first at {min(s['start'] for s in early):.1f}s — the fit "
            f"interval held the operator's voice, and a filter fitted there learns "
            f"to cancel it")

    if protocol["dropped_phases"]:
        why.append(f"{protocol['dropped_phases']} scheduled phases ran past the "
                   f"end of the recording")
    if not rows.get("echo_only", {}).get("erle_db"):
        why.append("no echo-only interval long enough to measure suppression on")
    return {"verdict": "inconclusive" if why else "scored", "why": why,
            # Never "ground truth". The labels come from a human following a
            # schedule, checked against content where content allows it — and
            # that check reads the contaminated transcript, so the figure is an
            # interval rather than a number. See `scheduled_bounds`.
            "evidence": "controlled human protocol; per-segment verification "
                        "selects on the raw transcript, so results are reported "
                        "as bounds, not a point estimate"}


def floor_rms(x: np.ndarray) -> float:
    """The level of the quietest tenth of the signal, measured over frames.

    The first version of this took the 10th percentile of individual squared
    samples, and it did not measure a noise floor at all. A waveform crosses
    zero, so the low percentiles of its samples sit near zero however loud it
    is: for Gaussian noise the ratio of RMS to that "floor" is 1/sqrt(chi2(1)
    at p=0.10), about 7.96, regardless of level. Pure noise therefore cleared a
    3x guard by a factor of two and a half, and the ratios the guard was
    supposed to qualify — reported at 13 to 27 — were about 1.6 to 3.4 times
    what silence itself scores. The guard tested nothing.

    Framing first is the repair. A 25 ms frame is long enough that its RMS is a
    level rather than a sample and short enough to sit inside a pause, so the
    10th percentile over frames lands on the quiet ones. Measured the same way,
    Gaussian noise scores 1.05.
    """
    return float(np.percentile(frame_rms(x), 10))


# Words carried by any English speech, which say nothing about whose speech it
# is. Left in, one shared "the" between a cue phrase and the far end's material
# was enough to strike the phrase — and every phrase shares one.
STOPWORDS = frozenset((
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "from", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "it", "its", "this", "that", "these", "those", "as", "if", "then", "than",
    "so", "not", "no", "nor", "into", "over", "under", "about",
))


# Whisper writes numbers as digits and American spellings regardless of how the
# passage was written, so "seventeen" and "17" are the same word said once and
# "harbour" and "harbor" differ by a transcription convention rather than by
# anything the operator did. Without folding them, every number word and every
# British spelling in a passage is a guaranteed miss in every condition — measured
# on clean audio with no far end at all, that was 5 of 22 content words in the
# first passage, which is a fifth of the score gone to orthography.
#
# It depresses all conditions equally, so the comparison between them survived; the
# absolute figures did not, and they are the ones quoted. Folding is confined to the
# vocabulary of the passages this project actually uses. Extend it with the passages
# rather than reaching for a general normaliser: a wide fold invents matches, and
# this is evidence about whether words survived.
# Bumped whenever STOPWORDS, NUMBER_WORDS or SPELLINGS change. It goes in every
# result manifest, because the fold changes scores: level-45's recall moved 14.8% to
# 30.7% when it was introduced, and it moves conditions unequally — a fold only
# restores a word where the ASR emitted some variant of it, so a condition that
# dropped the word entirely gains nothing. Two numbers produced under different
# tokenizers are not comparable, and without this recorded there is no way to tell
# that they were.
TOKENIZER_VERSION = 2

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
    "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
}
SPELLINGS = {
    "harbor": "harbour", "woolen": "woollen", "cataloged": "catalogued",
    "gray": "grey", "meter": "metre", "colored": "coloured",
}


def tokens(text: str) -> set[str]:
    out = set()
    for w in "".join(c.lower() if c.isalnum() else " " for c in text).split():
        w = SPELLINGS.get(w, NUMBER_WORDS.get(w, w))
        # Digits are kept whatever their length: folding "seventeen" to "17" would
        # otherwise delete it, since the filter below exists to drop short function
        # words and a numeral is not one.
        if w.isdigit() or (len(w) > 2 and w not in STOPWORDS):
            out.add(w)
    return out


def protocol_compliance(protocol: dict, mic: np.ndarray, margin: float,
                        mic_segs: list[dict], far_text: str | None) -> dict:
    """Did the operator actually follow the cues, checked from content.

    An earlier version answered this from microphone energy, and on the only
    configuration that matters it cannot. The far end plays through the speakers
    for the whole take, so the microphone is voiced in every interval whether
    the operator spoke or not — a missed cue reads as compliant, and the control
    that "proved" the check worked used a silent recording, which is the one
    condition the experiment never runs in.

    What echo cannot fake is the operator's words. Each speak interval displays a
    passage; if the microphone transcript inside that interval carries enough of
    it, he read it there. The far end is playing different material, so its echo
    cannot produce these tokens — and where it might, the check refuses to rely
    on it: any passage the far end says enough of itself is struck from the
    evidence rather than credited.

    This answers the INTERVAL, which is a coarser question than the one that
    decides the result. Whether a given three seconds of audio holds the operator
    is settled per segment, in `classify`, against the same passage — an interval
    verified here says he read it somewhere inside, not that he was reading
    throughout it. Both are reported, and the verdict needs both: at least one
    interval verified here, and the segments it actually scores verified there.

    This is one-directional and has to stay that way. Echo-contaminated speech
    transcribes badly, which is the condition under study, so a passage that
    fails to match is NOT evidence the operator was silent. A match proves
    speech. A miss proves nothing, and is reported as unverified rather than as
    a violation.

    Silent intervals get no equivalent check — nothing can show an absence here
    — so they carry an explicit assumption, not a measurement. Both the expected
    passage and what was actually transcribed go into the artifact, so a
    borderline match is the reader's call rather than a boolean they have to
    trust. Alongside them goes the time each cue was actually displayed, because
    a cue that appeared late labels audio against a boundary nobody saw.
    """
    far_tokens = tokens(far_text) if far_text else set()
    phases, notes, verified, unverified = [], [], 0, 0
    for ph in protocol["phases"]:
        span = phase_interior(ph, margin)
        if not span:
            continue
        lo, hi = span
        heard = " ".join(s.get("text", "") for s in mic_segs
                         if s["end"] > lo and s["start"] < hi).strip()
        row = {"role": ph["role"], "expect": ph["expect"],
               "start": ph["start"], "end": ph["end"],
               # What the operator actually saw, minus what the schedule said.
               # None on a protocol written before this was recorded, which the
               # verdict treats as unproven rather than as zero.
               "cue_late_s": (round(ph["shown_at_s"] - ph["start"], 3)
                              if ph.get("shown_at_s") is not None else None),
               "level_db": round(20 * np.log10(
                   float(np.sqrt((mic[int(lo * RATE):int(hi * RATE)] ** 2).mean()))
                   + 1e-12), 1),
               "heard": heard[:200] or None}
        if ph["script"]:
            want = tokens(ph["script"])
            leaked = want & far_tokens
            # Struck only when the far end could pass the check ON ITS OWN. A
            # word or two in common is inevitable and harmless; what makes a
            # phrase unusable is the playback containing enough of it that its
            # echo alone would clear the same bar the operator has to.
            leak = len(leaked) / max(len(want), 1)
            row["script"] = ph["script"]
            row["script_in_far_end"] = sorted(leaked) or None
            row["script_far_end_overlap"] = round(leak, 2)
            if leak >= SCRIPT_OVERLAP_MIN:
                row["cue_verified"] = None
                notes.append(f"speak interval {ph['start']:.0f}-{ph['end']:.0f}s: "
                             f"the far end says {leak:.0%} of this phrase itself "
                             f"({sorted(leaked)}) — it cannot verify anything")
            else:
                hit = len(want & tokens(heard)) / max(len(want), 1)
                row["script_overlap"] = round(hit, 2)
                row["cue_verified"] = hit >= SCRIPT_OVERLAP_MIN
                if row["cue_verified"]:
                    verified += 1
                else:
                    unverified += 1
                    notes.append(
                        f"speak interval {ph['start']:.0f}-{ph['end']:.0f}s: "
                        f"{hit:.0%} of the cue phrase transcribed — unverified, "
                        f"which is not the same as silent")
        phases.append(row)
    return {"phases": phases, "notes": notes,
            "speak_intervals_verified": verified,
            "speak_intervals_unverified": unverified,
            "silence_is_assumed": True}


def control_erle(protocol: dict, conds: dict, margin: float) -> dict:
    """Suppression measured where the far end plays and the operator does not.

    This is the figure every earlier echo-return-loss number in this file wanted
    and none could have. Splitting a take by which signal happened to dominate
    put near-end speech on both sides of the split, so "suppression during far
    end" was partly the filter declining to remove a voice it was right to keep.
    The silent control intervals are far end with nothing behind it by
    construction, so the ratio measured across them is echo removal and nothing
    else.
    """
    mask = np.zeros(len(conds["raw"]), dtype=bool)
    for ph in protocol["phases"]:
        if ph["role"] != "control":
            continue
        span = phase_interior(ph, margin)
        if span:
            mask[int(span[0] * RATE):min(int(span[1] * RATE), len(mask))] = True
    # A scheduled silent interval is not the same as far-end audio playing
    # through it. Real playback has pauses between sentences, and a pause inside
    # a control interval contributes room noise to both sides of the ratio,
    # which drags a suppression figure toward zero and calls it measurement.
    # Only samples where the reference is genuinely active count.
    active = np.zeros(len(mask), dtype=bool)
    # The reference as the filter saw it: shifted onto the microphone's timeline
    # by `align`. Using the caller's own system.wav here selected far-end
    # activity up to the measured 1.7 s of startup skew away from the echo it
    # was supposed to be measuring, and reported seconds of "far-end-active"
    # audio that held no echo at all.
    env = frame_rms(conds["_aligned_ref"])
    n = int(RATE * FLOOR_FRAME_MS / 1000)
    # Measured DOWN from the reference's loud level, not up from its quiet one.
    # Up from the quiet one was the first attempt and it inverts on a reference
    # with no pauses: stationary playback has a p10 frame as loud as its p90, so
    # nothing clears a threshold set 20 dB above it and a far end that never
    # stopped read as never playing. Down from p90 handles both — speech pauses
    # fall away, continuous playback does not.
    loud = float(np.percentile(env, 90))
    live = (env > loud / 10 ** (REF_ACTIVE_DB / 20)) & (env > REF_ACTIVE_FLOOR)
    for k in np.flatnonzero(live):
        active[k * n:(k + 1) * n] = True
    mask &= active[:len(mask)]
    seconds = float(mask.sum()) / RATE
    if seconds < MIN_ECHO_ONLY_S:
        return {"seconds": round(seconds, 2), "erle_db": None,
                "why": f"under {MIN_ECHO_ONLY_S:g}s of far-end-active audio "
                       f"inside the silent intervals"}
    return {"seconds": round(seconds, 2),
            "erle_db": {cond: round(float(_erle(conds["raw"], audio, mask)), 2)
                        for cond, audio in scored_conditions(conds).items()
                        if cond != "raw"}}


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

    ok &= _ground_truth_controls()

    print("\n  all controls behaved as specified" if ok
          else "\n  SOME CONTROLS FAILED — do not trust results from this file")
    return 0 if ok else 1


def _ground_truth_controls() -> bool:
    """The artifacts that say who was talking, and the guards that read them.

    These exercise the real writers in dual_capture, not a local copy of their
    output shape. A hand-rolled fixture would keep passing after the writer
    changed, which is the failure a round-trip control exists to catch.
    """
    import tempfile

    import dual_capture as dc

    ok = True

    def check(label: str, got, want=True, shown=None) -> None:
        nonlocal ok
        good = got == want
        ok &= good
        print(f"  {label:52s} {shown if shown is not None else got!s:>13}"
              f"{'   ok' if good else '   FAILED'}")

    def refused(fn) -> str | bool:
        """The first clause of the refusal, or False if it was accepted."""
        try:
            fn()
        except SourceError as exc:
            return str(exc).split(".")[0][:40]
        return False

    def write_wav(path: Path, x: np.ndarray) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # A recording, and the artifacts a capture would write beside it.
        mic = _synth(140.0, 11, 100, 7000)
        wav = d / "mic.wav"
        write_wav(wav, mic)
        digest, samples = sha256(wav), len(mic)
        phases = dc.build_schedule()

        # 10. The far end is audible on the microphone through the calibration
        #     phase, so segments land there whatever the operator does. This is
        #     the control for a guard that USED to live here and rejected such a
        #     take as proof the operator had spoken — it cannot be, and a run
        #     that refuses this take refuses every correct recording.
        sys_wav = d / "system.wav"
        write_wav(sys_wav, _synth(140.0, 12, 100, 7000))
        sys_digest, sys_samples = sha256(sys_wav), wav_frames(sys_wav)
        speak = next(ph for ph in phases if ph["role"] == "speak")
        segs = [{"start": 3.0, "end": 9.0, "text": "far end, no operator"},
                {"start": speak["start"] + 2.0, "end": speak["start"] + 5.0,
                 "text": speak["script"]}]
        seg_p, proto_p = d / "mic-segments.json", d / "protocol.json"
        dc.write_leg_segments(seg_p, segs, samples / RATE, wav, samples, "mic")
        dc.write_protocol(proto_p, phases, wav, samples, sys_wav, sys_samples)
        loaded = load_segments(seg_p, digest=digest, samples=samples)
        check("echo in the calibration prefix is not a defect", len(loaded), 2)

        proto = load_protocol(proto_p, mic_digest=digest, mic_samples=samples,
                              sys_digest=sys_digest, sys_samples=sys_samples)
        # 11. And the schedule places those same two segments correctly: the one
        #     inside the calibration phase is not the operator, the one inside a
        #     speak interval is. Nothing in the audio distinguishes them.
        cls = classify(loaded, proto["phases"], proto["cue_margin_s"])
        check("the schedule separates them, the audio cannot",
              (len(cls["calibration"]), len(cls["operator"])), (1, 1),
              shown=f"{len(cls['calibration'])} cal, {len(cls['operator'])} op")

        # 12. A segment across a cue boundary belongs to neither interval.
        edge = classify([{"start": phases[0]["end"] - 1.5,
                          "end": phases[0]["end"] + 1.5}],
                        proto["phases"], proto["cue_margin_s"])
        check("a segment straddling a cue is unattributable",
              len(edge["unattributable"]), 1)

        # 13. The margin has to leave a scorable interval behind, or the silent
        #     control intervals yield nothing and the negative control is
        #     decorative rather than absent — which is worse, because it looks
        #     like it ran.
        ctrl = next(ph for ph in phases if ph["role"] == "control")
        lo, hi = phase_interior(ctrl, dc.CUE_MARGIN_S)
        check("a silent interval still admits a scorable segment",
              hi - lo >= 2.0, shown=f"{hi - lo:.1f}s interior")
        #     Phase lengths are settable, so the guard has to hold for lengths
        #     nobody has tried, not only for the ones shipped as defaults.
        try:
            dc.build_schedule(control_s=2 * dc.CUE_MARGIN_S + 1.0)
            refused_short = False
        except ValueError:
            refused_short = True
        check("and a shorter one is refused rather than emptied", refused_short)

        # 14. Every way the wrong file can arrive is refused, and each says why.
        merged = d / "transcript.json"
        merged.write_text(json.dumps({"turns": [{"start": 0, "end": 1}]}))
        check("a merged transcript is refused",
              bool(refused(lambda: load_segments(
                  merged, digest=digest, samples=samples))))
        bare = d / "bare.json"
        bare.write_text(json.dumps([{"start": 0, "end": 1}]))
        check("a bare list is refused",
              bool(refused(lambda: load_segments(
                  bare, digest=digest, samples=samples))))
        check("a list from another recording is refused",
              bool(refused(lambda: load_segments(
                  seg_p, digest="0" * 64, samples=samples))))
        check("a recording trimmed after the fact is refused",
              bool(refused(lambda: load_segments(
                  seg_p, digest=digest, samples=samples - 1))))
        check("the mic leg is refused where the system leg belongs",
              bool(refused(lambda: load_segments(
                  seg_p, digest=digest, samples=samples, leg="system"))))
        check("a schedule from another recording is refused",
              bool(refused(lambda: load_protocol(
                  proto_p, mic_digest="0" * 64, mic_samples=samples,
                  sys_digest=sys_digest, sys_samples=sys_samples))))
        check("a schedule with the wrong system leg is refused",
              bool(refused(lambda: load_protocol(
                  proto_p, mic_digest=digest, mic_samples=samples,
                  sys_digest="0" * 64, sys_samples=sys_samples))))
        try:
            dc.build_schedule(pairs=0)
            no_speak = False
        except ValueError:
            no_speak = True
        check("a schedule with no speak intervals is refused", no_speak)

        # 15. A take stopped early. Both cases are built the way the capture
        #     builds them — a genuinely shorter recording with its own artifact
        #     written from it — because faking the length instead trips the
        #     binding check first and the control then passes for the wrong
        #     reason. It did, on the first run of this file.
        for label, cut_s, want_refusal in (
            ("a take cut inside the calibration phase is refused",
             phases[0]["end"] - 1.0, True),
            ("phases past the end of a short take are dropped",
             phases[3]["end"] + 0.5, False),
        ):
            sub = d / f"short-{cut_s:.0f}"
            sub.mkdir()
            cut = mic[:int(cut_s * RATE)]
            write_wav(sub / "mic.wav", cut)
            write_wav(sub / "system.wav", _synth(cut_s, 12, 100, 7000))
            dc.write_protocol(sub / "protocol.json", phases,
                              sub / "mic.wav", len(cut),
                              sub / "system.wav", wav_frames(sub / "system.wav"))
            def load(s=sub, c=cut):
                return load_protocol(
                    s / "protocol.json", mic_digest=sha256(s / "mic.wav"),
                    mic_samples=len(c), sys_digest=sha256(s / "system.wav"),
                    sys_samples=wav_frames(s / "system.wav"))
            if want_refusal:
                check(label, bool(refused(load)))
            else:
                part = load()
                check(label,
                      part["dropped_phases"] > 0 and len(part["phases"]) >= 3,
                      shown=f"kept {len(part['phases'])}, "
                            f"dropped {part['dropped_phases']}")

        # 16. The noise floor. The first version of floor_rms took a percentile
        #     of squared SAMPLES, which a waveform's zero crossings drive toward
        #     zero: pure noise scored 7.96 against its own "floor" and cleared a
        #     3x guard by two and a half times. The guard tested nothing, and
        #     the 13-27x ratios it was published alongside meant nothing.
        rng = np.random.default_rng(3)
        noise = rng.standard_normal(30 * RATE) * 0.01
        old_way = float(np.sqrt((noise ** 2).mean())
                        / np.sqrt(np.percentile(noise ** 2, 10)))
        now = float(np.sqrt((noise ** 2).mean()) / floor_rms(noise))
        check("noise scores about 1x its own floor, not 8x",
              now < 1.5 < FLOOR_RATIO_MIN < old_way,
              shown=f"{now:.2f}x (was {old_way:.2f}x)")
        #     And the guard still has to pass real signal, or it trades a false
        #     negative for a false positive and reads as rigour either way.
        loud = _synth(30.0, 4, 100, 7000)
        loud[: 20 * RATE] *= 0.02                    # mostly quiet, some speech
        ratio = float(np.sqrt((loud[22 * RATE:25 * RATE] ** 2).mean())
                      / floor_rms(loud))
        check("and real speech clears the guard", ratio > FLOOR_RATIO_MIN,
              shown=f"{ratio:.1f}x floor")

        # 17. Compliance, under the condition the experiment actually runs in.
        #     The far end plays throughout, so the microphone is voiced in every
        #     interval whether the operator spoke or not. An energy check reads
        #     that as compliance; only the cue phrase separates them.
        echo_everywhere = [{"start": ph["start"] + 0.5, "end": ph["end"] - 0.5,
                            "text": "and then the quarterly numbers came back"}
                           for ph in proto["phases"] if ph["end"] > ph["start"] + 1]
        c = protocol_compliance(proto, mic, proto["cue_margin_s"],
                                echo_everywhere, None)
        check("echo in every interval verifies no speak cue",
              c["speak_intervals_verified"], 0,
              shown=f"{c['speak_intervals_verified']} verified")
        #     And the operator reading the cue is verified, in the same audio.
        spoke = echo_everywhere + [
            {"start": ph["start"] + 2.0, "end": ph["start"] + 5.0,
             "text": ph["script"]}
            for ph in proto["phases"] if ph["script"]]
        c2 = protocol_compliance(proto, mic, proto["cue_margin_s"], spoke, None)
        check("the cue phrase verifies it", c2["speak_intervals_verified"],
              sum(1 for ph in proto["phases"] if ph["script"]),
              shown=f"{c2['speak_intervals_verified']} verified")
        #     Unless the far end says it too, in which case the echo could have
        #     produced it and the phrase is struck rather than credited.
        c3 = protocol_compliance(proto, mic, proto["cue_margin_s"], spoke,
                                 " ".join(dc.SCRIPT))
        check("a phrase the far end also says is struck",
              c3["speak_intervals_verified"], 0,
              shown=f"{c3['speak_intervals_verified']} verified")

        # 18. Per-segment labels. A passage read once at the top of a speak
        #     interval used to promote every segment in it, including the ones
        #     during a pause that hold only the far end. The segment has to carry
        #     the passage itself.
        sp2 = next(ph for ph in proto["phases"]
                   if ph["role"] == "speak" and ph is not speak)
        reading = {"start": speak["start"] + 2.0, "end": speak["start"] + 5.0,
                   "text": speak["script"]}
        pausing = {"start": sp2["start"] + 2.0, "end": sp2["start"] + 5.0,
                   "text": "and then the quarterly numbers came in ahead of plan"}
        cls2 = classify([reading, pausing], proto["phases"], proto["cue_margin_s"])
        check("a segment carrying the passage is the operator",
              (len(cls2["operator"]), len(cls2["operator_unverified"])), (1, 1),
              shown=f"{len(cls2['operator'])} op, "
                    f"{len(cls2['operator_unverified'])} unverified")
        #     Including when it sits in a verified interval beside a reading one:
        #     interval-wide evidence would have promoted both.
        cls3 = classify([reading, {"start": speak["start"] + 5.5,
                                   "end": speak["start"] + 8.0,
                                   "text": "the quarterly numbers again"}],
                        proto["phases"], proto["cue_margin_s"])
        check("a pause in a verified interval is not promoted",
              len(cls3["operator"]), 1, shown=f"{len(cls3['operator'])} op")

        # 19. Distinct audio, not summed lengths — and the artifact refuses the
        #     duplicates that made the two differ. An earlier version of the
        #     fixture below used four copies of one three-second window, which
        #     certified exactly the double-counting it should have caught.
        dup = [{"start": 0.0, "end": 3.0}] * 4
        check("four copies of one window are three seconds",
              union_seconds(dup), 3.0)
        over = d / "overlap.json"
        over.write_text(json.dumps({
            "schema": "mic-segments/1", "timeline": "mic-local", "leg": "mic",
            "filtered": ["voicing"], "duration_s": 140.0,
            "audio_sha256": digest, "audio_samples": samples,
            "segments": [{"start": 0.0, "end": 3.0, "text": "a"},
                         {"start": 2.0, "end": 5.0, "text": "b"}]}))
        check("an artifact with overlapping segments is refused",
              bool(refused(lambda: load_segments(
                  over, digest=digest, samples=samples))))

        # 20. A run that produced no operator segments, no negative control, no
        #     verified cue, a late cue, or an admission at the noise floor is
        #     inconclusive and says so — it must not write a manifest that looks
        #     like a measurement.
        #     Every fixture carries observed cue times, because a run without
        #     them is now inconclusive on that ground alone. The earlier version
        #     used `phases: []`, which satisfied "every cue was observed"
        #     vacuously and so never exercised the requirement it was there for.
        def observed(*late):
            return [{"start": 35.0 + 10 * i, "cue_late_s": v}
                    for i, v in enumerate(late)]

        def rows_for(**over):
            base = {
                "classes": {
                    "operator": {"windows": [
                        {"start": t, "end": t + 3.0, "masked": 0.7,
                         "masked_rms_over_floor": 9.0} for t in (0.0, 4.0, 8.0)]},
                    "control": {"windows": [
                        {"start": t, "end": t + 3.0, "masked": 0.1,
                         "masked_rms_over_floor": 9.0} for t in (0.0, 4.0, 8.0)]}},
                "echo_only": {"erle_db": {"linear": 5.0}},
                "compliance": {"speak_intervals_verified": 5,
                               "speak_intervals_unverified": 0,
                               "phases": observed(0.03, 0.01, 0.02)},
            }
            base.update(over)
            return base

        clean = dict(proto, dropped_phases=0)
        check("a populated, verified run is scored",
              run_verdict(rows_for(), clean, 0.58)["verdict"], "scored")
        #     A breath gap does not invalidate a take; most of the interval
        #     being unaccounted for does.
        gap = rows_for()
        gap["classes"]["operator_unverified"] = {
            "windows": [{"start": 20.0, "end": 22.5}]}
        check("one unverified segment does not invalidate it",
              run_verdict(gap, clean, 0.58)["verdict"], "scored")
        mostly = rows_for()
        mostly["classes"]["operator_unverified"] = {"windows": [
            {"start": t, "end": t + 3.0} for t in (20.0, 24.0, 28.0, 32.0)]}
        check("but mostly-unverified speak intervals do",
              run_verdict(mostly, clean, 0.58)["verdict"], "inconclusive")
        no_ctrl = rows_for()
        del no_ctrl["classes"]["control"]
        check("a run with no negative control is inconclusive",
              run_verdict(no_ctrl, clean, 0.58)["verdict"], "inconclusive")
        check("and so is one with no verified speak cue",
              run_verdict(rows_for(compliance={
                  "speak_intervals_verified": 0, "speak_intervals_unverified": 5,
                  "phases": observed(0.03, 0.01)}), clean, 0.58)["verdict"],
              "inconclusive")
        check("and so is one whose cue appeared late",
              run_verdict(rows_for(compliance={
                  "speak_intervals_verified": 5, "speak_intervals_unverified": 0,
                  "phases": observed(0.03, 2.4)}),
                  clean, 0.58)["verdict"], "inconclusive")
        #     And so is one that never recorded when its cues appeared. This is
        #     the case that used to return `scored` with an empty `why`: the
        #     lateness filter skipped the Nones on its way to comparing
        #     magnitudes, so "every cue was within the margin" held vacuously.
        blind = run_verdict(rows_for(compliance={
            "speak_intervals_verified": 5, "speak_intervals_unverified": 0,
            "phases": observed(None, None)}), clean, 0.58)
        check("and so is one with no recorded cue display times",
              blind["verdict"], "inconclusive",
              shown=f"{blind['verdict']} ({len(blind['why'])} reasons)")
        hollow = rows_for()
        hollow["classes"]["operator"]["windows"][0]["masked_rms_over_floor"] = 1.1
        check("and so is one admitting a window at the noise floor",
              run_verdict(hollow, clean, 0.58)["verdict"], "inconclusive")
        check("and so is one whose phases ran off the end",
              run_verdict(rows_for(), dict(proto, dropped_phases=2),
                          0.58)["verdict"], "inconclusive")

        # 21. Suppression is only a number where the far end was actually
        #     playing, and "where" is decided on the microphone's timeline.
        quiet = {"raw": np.zeros(140 * RATE), "linear": np.zeros(140 * RATE),
                 "_aligned_ref": np.zeros(140 * RATE)}
        eo = control_erle(proto, quiet, proto["cue_margin_s"])
        check("no far-end audio yields no suppression figure",
              eo.get("erle_db"), None, shown=eo.get("why", "")[:13])
        #     A reference the caller has not aligned selects activity up to the
        #     measured 1.7s of startup skew away from the echo. control_erle now
        #     reads the aligned copy process() carries, so a shifted caller array
        #     cannot move the mask.
        far = _synth(140.0, 21, 150, 6000)
        # A sparse talker: 1.5 s on, 2.5 s off. Sparse on purpose — at a 75%
        # duty cycle a two-second shift still lands mostly on real speech, and
        # the two masks came out 1.8 dB apart, which is not a control deciding
        # anything. At this duty a shift lands in the pauses.
        gate = np.zeros(len(far))
        for k in range(0, 140, 4):
            gate[int(k * RATE):int((k + 1.5) * RATE)] = 1.0
        far *= gate
        # Suppression only where the far end plays, as a real filter behaves.
        # Comparing totals would not catch this: the gate is periodic, so a
        # shifted reference selects the same NUMBER of seconds from the wrong
        # places. What has to differ is the figure those samples produce.
        # Room noise under everything, or the pauses are digital silence and
        # contribute nothing to either side of the ratio — which is why an
        # earlier version of this control could not tell the two masks apart.
        room = _synth(140.0, 23, 100, 7000) * 0.01
        far = far + room
        quietened = np.where(gate > 0, room, far)
        base = {"raw": far, "linear": quietened, "_aligned_ref": far}
        wrong = {**base, "_aligned_ref": np.roll(far, int(2.0 * RATE))}
        # 2.0 s: half the gate period, so every selected frame lands in a pause.
        a = control_erle(proto, base, proto["cue_margin_s"])
        b = control_erle(proto, wrong, proto["cue_margin_s"])
        check("and the mask follows the aligned reference",
              a["erle_db"]["linear"] - b["erle_db"]["linear"] > 3.0,
              shown=f"{a['erle_db']['linear']:.1f} vs "
                    f"{b['erle_db']['linear']:.1f} dB")
        #     Continuous playback is active throughout, not silent throughout.
        #     Measuring up from the reference's own quietest frame said the
        #     opposite, and a stationary far end selected nothing.
        cont = {"raw": _synth(140.0, 22, 150, 6000)}
        cont["linear"] = cont["raw"] * 0.1
        cont["_aligned_ref"] = cont["raw"]
        c = control_erle(proto, cont, proto["cue_margin_s"])
        check("a far end that never pauses counts as playing",
              c["seconds"] > MIN_ECHO_ONLY_S, shown=f"{c['seconds']:.1f}s")

        # 22. Attribution runs off the cue the operator SAW. A cue displayed
        #     0.9s late passes the 1.0s margin check, and used to leave 0.1s of
        #     reaction time before the next interval's interior opened — an
        #     overrunning sentence scored as far-end-only audio in a control it
        #     had not been told to start yet.
        ctrl2 = next(ph for ph in phases
                     if ph["role"] == "control" and ph["start"] > speak["start"])
        late_p = d / "protocol-late.json"
        dc.write_protocol(
            late_p, phases, wav, samples, sys_wav, sys_samples,
            shown_at={i: (ph["start"] + 0.9 if ph is ctrl2 else ph["start"])
                      for i, ph in enumerate(phases)})
        lp = load_protocol(late_p, mic_digest=digest, mic_samples=samples,
                           sys_digest=sys_digest, sys_samples=sys_samples)
        sched = phase_interior(ctrl2, proto["cue_margin_s"])
        obs = phase_interior(
            next(ph for ph in lp["phases"] if ph["start"] == ctrl2["start"]),
            lp["cue_margin_s"])
        check("a late cue moves its interval, not the margin",
              round(obs[0] - sched[0], 2), 0.9,
              shown=f"{sched[0]:.1f} -> {obs[0]:.1f}s")
        #     Which is the whole point: audio in the reclaimed reaction time is
        #     no longer scored as the echo-only control.
        edge2 = [{"start": ctrl2["start"] + 1.0, "end": ctrl2["start"] + 1.6,
                  "text": "still finishing the passage"}]
        check("audio inside the reaction gap is not the control",
              (len(classify(edge2, proto["phases"], proto["cue_margin_s"])["control"]),
               len(classify(edge2, lp["phases"], lp["cue_margin_s"])["control"])),
              (1, 0), shown="scheduled 1, observed 0")

        # 23. Both readings of the speak intervals, because the verified subset
        #     is selected by reading the RAW contaminated transcript. The
        #     segments that fail are disproportionately the ones echo wrecked,
        #     which are the ones cancellation exists for — so publishing the
        #     retained subset alone reports recovery conditional on raw ASR
        #     having already found the operator.
        bounds = scheduled_bounds({"classes": {
            "operator": {"windows": [
                {"start": t, "end": t + 3.0, "masked": 0.7} for t in (0.0, 4.0)]},
            "operator_unverified": {"windows": [
                {"start": t, "end": t + 3.0, "masked": 0.2} for t in (8.0, 12.0)]}}},
            0.58)
        m = bounds["conditions"]["masked"]
        check("the verified subset is the upper bound",
              (m["verified"]["admitted"], m["verified"]["of"]), (2, 2),
              shown="2 of 2 admitted")
        check("the whole cued reading is the lower bound",
              (m["scheduled"]["admitted"], m["scheduled"]["of"]), (2, 4),
              shown="2 of 4 admitted")
        check("and the seconds they disagree over are named",
              bounds["excluded_seconds"], 6.0)

        # 24. A condition supplied with --condition — a real canceller's output —
        #     has to reach the guards, not just the printed table. Both the
        #     noise-floor check and the bounds named raw/linear/masked literally,
        #     so an added condition would have been reported with nothing
        #     verifying it, which reads as having passed.
        check("an added condition is one of the run's conditions",
              conditions({"conditions": ["aec3", "raw"]}), ("aec3", "raw"))
        check("and a fixture without the key keeps the historical triple",
              conditions({}), ("raw", "linear", "masked"))
        added = rows_for()
        added["conditions"] = ["aec3"]
        for w in added["classes"]["operator"]["windows"]:
            w["aec3"], w["aec3_rms_over_floor"] = 0.7, 9.0
        for w in added["classes"]["control"]["windows"]:
            w["aec3"], w["aec3_rms_over_floor"] = 0.1, 9.0
        check("a run scored on an added condition alone is scored",
              run_verdict(added, clean, 0.58)["verdict"], "scored")
        hollow_add = json.loads(json.dumps(added))
        hollow_add["classes"]["operator"]["windows"][0]["aec3_rms_over_floor"] = 1.1
        check("and a hollow admission in it is caught",
              run_verdict(hollow_add, clean, 0.58)["verdict"], "inconclusive")
        b2 = scheduled_bounds({"conditions": ["aec3"], "classes": {
            "operator": {"windows": [{"start": 0.0, "end": 3.0, "aec3": 0.7}]},
            "operator_unverified": {"windows": [{"start": 8.0, "end": 11.0,
                                                "aec3": 0.2}]}}}, 0.58)
        # 25. A passage read before the first cue. prefix mode fits the echo path
        #     on the calibration interval as though only the far end were there,
        #     so the operator's voice inside it teaches the filter to cancel him —
        #     and silence there was assumed rather than checked until a real take
        #     transcribed its first passage five seconds before the cue fired.
        cal = next(ph for ph in proto["phases"] if ph["role"] == "calibration")
        early_seg = {"start": cal["start"] + 5.0, "end": cal["start"] + 8.0,
                     "text": speak["script"]}
        cls_early = classify([early_seg], proto["phases"], proto["cue_margin_s"])
        check("reading inside the fit interval is detected",
              cls_early["calibration"][0]["script_precision"] > SEGMENT_PRECISION_MIN,
              shown=f"{cls_early['calibration'][0]['script_precision']:.2f} precision")
        jumped = rows_for()
        jumped["classes"]["calibration"] = {"windows": cls_early["calibration"]}
        check("and it makes the run inconclusive",
              run_verdict(jumped, clean, 0.58)["verdict"], "inconclusive")
        #     Far-end echo in the fit interval is the NORMAL case and must not
        #     trip it: that is what the interval is for.
        quiet_cal = classify([{"start": cal["start"] + 5.0, "end": cal["start"] + 8.0,
                               "text": "and then the quarterly numbers came in"}],
                             proto["phases"], proto["cue_margin_s"])
        fine = rows_for()
        fine["classes"]["calibration"] = {"windows": quiet_cal["calibration"]}
        check("but far-end speech there is what the interval is for",
              run_verdict(fine, clean, 0.58)["verdict"], "scored")

        # 26. The tokenizer fold. It changes published scores — level-45's recall
        #     moved 14.8% to 30.7% when it arrived — so its behaviour is pinned
        #     rather than assumed, including where it deliberately does nothing.
        check("a number word and its digit are one token",
              tokens("seventeen violet anchors") == tokens("17 violet anchors"))
        check("British and American spellings fold together",
              tokens("past the harbour") == tokens("past the harbor"))
        check("and folding does not collapse different sentences",
              tokens("past the harbour") == tokens("past the woollen harbor"), False)
        check("a folded number survives the short-word filter",
              "17" in tokens("nine and seventeen"), shown=str(sorted(tokens("seventeen"))))
        #     The fold is one-directional in effect, which is the honest limit: it
        #     restores a word only where the ASR emitted SOME variant of it. A
        #     condition that dropped the word entirely gains nothing, so the fold
        #     moves conditions unequally and cannot be treated as a constant offset.
        check("a word the ASR never emitted is still missing",
              tokens("seventeen violet anchors") - tokens("17 anchors"), {"violet"})
        #     And it must not invent matches between unrelated words, which is why
        #     it is a fixed table rather than edit distance.
        check("unrelated words do not fold",
              tokens("anchors") & tokens("anchovies"), set())
        check("the version is recorded so two tokenizers are not compared",
              isinstance(TOKENIZER_VERSION, int))

        # 27. The scores artifact carries what each segment transcribed, so it is
        #     a transcript, and this repo is public. Refused in the tool rather
        #     than left to .gitignore, which only covers paths someone thought of.
        check("an artifact path inside the repo is refused",
              inside_repo(Path(__file__).parent / "out" / "scores.json"))
        check("and one outside it is allowed",
              inside_repo(Path(tmp) / "scores.json"), False)

        check("and it is bounded like any other",
              (b2["conditions"]["aec3"]["verified"]["admitted"],
               b2["conditions"]["aec3"]["scheduled"]["of"]), (1, 2),
              shown="1 of 1 verified, 2 scheduled")

        # 28. The voiceprint gate's coupling to the bleed verdict. Four things read
        #     the same cut — the console verdict, the doubled-utterance warning,
        #     whether write_transcript clears every speaker label, and whether the
        #     gate runs at all — and the drift between them would be silent in the
        #     harmful direction: labels cleared while the gate still deletes the
        #     operator to defend them. So the cut is asserted once, through the
        #     function all four call.
        clean_b = {"peak_r": -0.9, "positive_r": 0.05, "analysed_s": 60.0}
        dirty_b = {"peak_r": 0.93, "positive_r": 0.93, "analysed_s": 60.0}
        check("a complementary pair of legs is not contaminated",
              dc.contaminated(clean_b), False)
        check("and a mic hearing the speakers is",
              dc.contaminated(dirty_b))
        check("nothing playing cannot leak, so it is not contaminated either",
              dc.contaminated(None), False)

        #     The gate must not even load the encoder on contaminated audio. The
        #     voiceprint here is a sentinel that raises if unpacked, so a control
        #     that passes proves the skip happened before any use of it.
        one_seg = [{"start": 1.0, "end": 4.0, "text": "something said"}]
        skipped_segs, skipped_rep = dc.drop_offprint(one_seg, mic, object(),
                                                     dirty_b, "mic")
        check("the gate is skipped where the labels are already gone",
              skipped_segs, one_seg, shown="unchanged")
        check("and the skip is recorded with its reason, not left to a terminal",
              (skipped_rep["applied"], bool(skipped_rep["why"])), (False, True),
              shown="not applied, reason given")
        check("and it does nothing at all with no profile supplied",
              dc.drop_offprint(one_seg, mic, None, clean_b, "mic"), (one_seg, None),
              shown="unchanged, no report")

        #     The line that actually decides what survives. Both controls above
        #     assert *unchanged*, so they cover only the two skip paths — the index
        #     map that keeps the operator had never executed in a test, and it
        #     cannot without the 153 MB install that load_encoder's own docstring
        #     says makes a test stop being run. So drop_offprint takes the encoder,
        #     and this passes the same fixture speaker_gate's controls use.
        import speaker_gate as sg

        g_rng = np.random.default_rng(11)
        g_dirs = sg._speaker_directions(g_rng, 2)
        g_embed = sg._fixture_encoder(g_dirs, within=0.038)
        g_audio, g_segs = sg._fixture_audio(sg._spans(8, 0, 1.0), g_rng)
        g_emb = [e for e in sg.embed_segments(g_audio, g_segs, g_embed) if e is not None]
        g_profile = sg.enroll(g_emb, [s["end"] - s["start"] for s in g_segs])
        # Operator, operator, intruder, operator, and one too short to judge.
        mixed_spans = [(1.0, 5.0, 0), (7.0, 11.0, 0), (13.0, 17.0, 1),
                       (19.0, 23.0, 0), (25.0, 26.0, 0)]
        mixed_audio, mixed = sg._fixture_audio(mixed_spans, g_rng)
        vp_fix = dc.Voiceprint(g_profile, 0.5,
                               {"seconds": 32.0, "encoder": "fixture",
                                "sittings": [{}, {}],
                                "operating_point": {"target_frr": 0.05}},
                               g_embed)
        kept, rep = dc.drop_offprint(mixed, mixed_audio, vp_fix, clean_b, "mic")
        #     MARKED, not removed — film-room's DP-3 applied to the one part of it
        #     that transfers. The operator is the only one who can say whether a
        #     voice near the microphone was a participant, and a filter that
        #     discarded the segment put that answer beyond reach.
        check("nothing is discarded — every segment survives the gate",
              [s["start"] for s in kept], [1.0, 7.0, 13.0, 19.0, 25.0])
        check("and the one that is not the operator is marked, with its score",
              [(s["start"], s.get("gate_score")) for s in kept if s.get("gated")],
              [(13.0, rep["rejections"][0]["score"])],
              shown="13.0s marked")
        check("the segment too short to judge is neither marked nor decided",
              any(s["start"] == 25.0 and not s.get("gated") for s in kept))
        check("marking does not mutate the caller's own segment objects",
              all("gated" not in s for s in mixed))
        #     The encoder travels in the Voiceprint, so production does not build it
        #     after the meeting. Passing it explicitly must still work, for fixtures.
        check("the encoder carried in the profile is used when none is passed",
              dc.drop_offprint(mixed, mixed_audio, vp_fix, clean_b, "mic",
                               embed=g_embed)[0] == kept)

        #     What the gate DID has to survive a closed terminal. Every count here
        #     was computed, printed and thrown away before this control existed,
        #     including the co-located-speaker alert that screens-and-states.md
        #     requires to reach the post-meeting note.
        check("the report carries what was dropped, not just what survived",
              (rep["applied"], rep["rejected"], rep["unscorable_kept"]),
              (True, 1, 1), shown="1 rejected, 1 unscorable kept")
        check("and every rejection carries its timestamp, so it can be listened to",
              [r["start"] for r in rep["rejections"]], [13.0])
        check("and its score and whether it was a close call",
              set(rep["rejections"][0]) == {"start", "end", "score", "reason"})

        #     Several states, not a boolean: a reader cannot otherwise tell "no gate
        #     was asked for" from "a gate was asked for and did not run".
        vp = dc.Voiceprint(None, 0.61,
                           {"seconds": 300.0, "encoder": "e", "sittings": [{}, {}],
                            "operating_point": {"target_frr": 0.05,
                                                "measured_frr": 0.04}}, None)
        check("an ungated capture says so",
              dc.voiceprint_provenance(None, rep), None)
        gated = dc.voiceprint_provenance(vp, rep)
        check("a gated one records the threshold it used and what it did",
              (gated["applied"], gated["threshold"], gated["rejected"]),
              (True, 0.61, 1), shown="applied at 0.61, 1 dropped")
        check("and the measured rate, not only the target that was asked for",
              (gated["target_frr"], gated["measured_frr"]), (0.05, 0.04))
        skipped = dc.voiceprint_provenance(vp, skipped_rep)
        check("and a skipped one is distinguishable from an ungated one",
              (skipped["applied"], bool(skipped["why"])), (False, True),
              shown="not applied, reason given")
        #     The sitting count comes from the enrollment list, which load_profile
        #     refuses to load without. Read from the nested operating point instead
        #     it went None on an older profile and silently dropped the over-tight
        #     warning — for exactly the profile that most needed it.
        check("the sitting count survives a profile with no operating point",
              dc.voiceprint_provenance(
                  dc.Voiceprint(None, 0.61, {"sittings": [{}, {}, {}]}, None),
                  rep)["n_sittings"], 3)

        #     And it reaches the artifact, which is where a later reader looks to
        #     find out whether the mic leg holds the operator or whoever was audible.
        gated_p = d / "transcript-gated.json"
        dc.write_transcript(gated_p, [(1.0, 4.0, "Me", "something said")], clean_b,
                            dc.voiceprint_provenance(vp, rep))
        wrote = json.loads(gated_p.read_text())
        check("the transcript carries what gated the microphone leg",
              (wrote["voiceprint"]["applied"], wrote["voiceprint"]["n_sittings"],
               wrote["voiceprint"]["rejected"]), (True, 2, 1),
              shown="applied, 2 sittings, 1 dropped")
        #     And the notes half surfaces it. A warning that stops at the JSON is the
        #     same failure one layer down from a warning that stops at the terminal.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notes"))
        import transcript as nt

        loaded_note = nt.load_capture(gated_p)
        check("the notes loader carries the gate report through",
              bool(loaded_note.gate) and loaded_note.gate["rejected"] == 1)

        #     The substrate keeps every word; the renderer decides what the model
        #     sees. Both halves have to hold, or the change from delete-to-mark
        #     either loses the record or leaks the room into the notes.
        both_p = d / "transcript-marked.json"
        dc.write_transcript(both_p, [
            (1.0, 4.0, "Me", "the part he said", False, None, None),
            (5.0, 8.0, "Me", "the part someone else said", True, 0.21,
             "below_profile"),
        ], clean_b, dc.voiceprint_provenance(vp, rep))
        marked_doc = json.loads(both_p.read_text())
        check("a gated turn stays in the artifact, with its score",
              (len(marked_doc["turns"]), marked_doc["turns"][1]["gate_score"]),
              (2, 0.21), shown="2 turns, one marked")
        check("and an ungated turn carries no gate keys at all",
              set(marked_doc["turns"][0]) == {"start", "end", "speaker", "text"})
        rendered = nt.load_capture(both_p).render()
        check("but the model is handed only what the gate accepted",
              ("the part he said" in rendered,
               "someone else" in rendered), (True, False),
              shown="kept in, gated out")
        check("and turns a co-located-speaker alert into a human warning",
              any("recurring voice" in w for w in nt.Transcript(
                  source="x", attribution="channel",
                  gate={"applied": True, "persistent_other": True,
                        "coherent_share": 0.8, "rejected_seconds": 40.0},
              ).gate_warnings))
        check("a clean gate run produces no warning to cry wolf with",
              nt.Transcript(source="x", attribution="channel",
                            gate={"applied": True, "rejected": 0}).gate_warnings, [])

    return ok


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
    p.add_argument("--protocol", action="append", metavar="NAME=FILE", default=[],
                   help="the capture's protocol.json: the cue schedule that says "
                        "which intervals the operator was asked to speak in and "
                        "which he was asked to stay silent through. Nothing in the "
                        "audio answers that — on speakers the far end is audible on "
                        "the microphone throughout — so this is the only evidence "
                        "about the talker, and prefix mode requires it. It is a "
                        "controlled human protocol, not independent labels: "
                        "adherence is assumed in the silent intervals and checked "
                        "against a contaminated transcript in the speaking ones")
    p.add_argument("--condition", action="append", metavar="NAME=TAKE:FILE", default=[],
                   help="score an already-cancelled WAV as an extra condition beside "
                        "raw/linear/masked — the output of spike/aec3/aec3_offline, or "
                        "any other canceller. This is how a real canceller gets "
                        "compared against the offline estimate on one window set and "
                        "one voiceprint, which is the only way the two numbers mean "
                        "the same thing. The file is 16 kHz mono like every other leg, "
                        "and its digest goes in the artifact: it is derived audio, so "
                        "nothing can bind it to the recording the way segments and "
                        "protocols are bound, and the digest is what makes a run "
                        "reproducible instead")
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
    p.add_argument("--out", type=Path,
                   help="write per-window scores and input digests here. It carries "
                        "what each segment transcribed — deliberately, so a borderline "
                        "passage match is the reader's judgement rather than a boolean "
                        "they have to trust — which makes it a transcript, and this "
                        "refuses to write one inside the repository")
    args = p.parse_args()

    # A transcript is the same secret as the audio it came from, and this repo is
    # public. The artifact is refused inside the working tree rather than left to a
    # .gitignore rule, because a rule only covers the paths someone thought of: 197
    # lines of a household recording reached four public commits through
    # `spike/aec-bound-results.json`, a path no rule named. The tool declining the
    # write is the only version of this that holds for paths nobody has invented yet.
    if args.out and inside_repo(args.out):
        p.error(f"--out {args.out} is inside the repository. This artifact contains "
                f"what was said. Write it somewhere outside — the recordings' own "
                f"directory is the obvious place.")

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
    seg_paths = dict(spec.partition("=")[::2] for spec in args.segments)
    proto_paths = dict(spec.partition("=")[::2] for spec in args.protocol)
    unknown = (set(seg_paths) | set(proto_paths)) - set(takes)
    if unknown:
        p.error(f"--segments/--protocol name takes that were not passed: "
                f"{', '.join(sorted(unknown))}")

    # NAME=TAKE:FILE, collected per take. Names are checked against the built-in
    # conditions here rather than at scoring time: a condition called `masked`
    # would silently replace the one `process` computes, and the table would
    # compare the offline estimate against itself.
    extra: dict[str, dict[str, Path]] = {}
    for spec in args.condition:
        cname, _, rest = spec.partition("=")
        tname, _, path = rest.partition(":")
        if not cname or not tname or not path:
            p.error(f"--condition {spec!r} is not NAME=TAKE:FILE")
        if cname in ("raw", "linear", "masked") or cname.startswith("_"):
            p.error(f"--condition {cname!r} collides with a built-in condition; "
                    f"it would replace the one this run computes")
        if tname not in takes:
            p.error(f"--condition {cname} names take {tname!r}, which was not passed")
        extra.setdefault(tname, {})[cname] = Path(path).expanduser()

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
        # Enrolment takes are exempt from both: they exist to build the profile,
        # and their rows are a sanity check rather than the measurement.
        scored_names = [n for n in takes if n not in enroll_names]
        if not scored_names:
            p.error("--fit-mode prefix has nothing to score: every --take is "
                    "also in --enroll.")
        for flag, have, why in (
            ("--segments", seg_paths,
             ("the gate consumes whole caller-supplied segments, so scoring on "
              "fixed windows would measure something the product never runs")),
            ("--protocol", proto_paths,
             ("microphone segments say what was audible, not who said it: on "
              "speakers the far end is audible on the microphone throughout, so "
              "without the cue schedule the denominator mixes the voice being "
              "recovered with the voice being cancelled")),
        ):
            missing = [n for n in scored_names if n not in have]
            if missing:
                p.error(f"--fit-mode prefix needs {flag} for "
                        f"{', '.join(missing)}: {why}.")

    # Pre-flight. Every supplied artifact is read and checked against the
    # recording it claims, and the fit boundary is checked against the schedule,
    # before the encoder loads or a single take is scored. Validating inside the
    # scoring loop instead meant a run with an invalid boundary spent minutes
    # building a profile and scoring the takes ahead of the bad one first.
    mic_digests, mic_lengths, supplied, protocols, far_texts = {}, {}, {}, {}, {}
    for name, take in takes.items():
        mic_p, sys_p = take / "mic.wav", take / "system.wav"
        for wav in (mic_p, sys_p):
            if not wav.exists():
                p.error(f"{name}: no {wav.name} in {take}")
        mic_digests[name] = sha256(mic_p)
        mic_lengths[name] = wav_frames(mic_p)
        try:
            if name in seg_paths:
                supplied[name] = load_segments(
                    Path(seg_paths[name]).expanduser(),
                    digest=mic_digests[name], samples=mic_lengths[name])
            if name in proto_paths:
                protocols[name] = load_protocol(
                    Path(proto_paths[name]).expanduser(),
                    mic_digest=mic_digests[name], mic_samples=mic_lengths[name],
                    sys_digest=sha256(sys_p), sys_samples=wav_frames(sys_p))
                # The far end's own words. A cue phrase the playback happens to
                # contain is a phrase its echo can put in the mic transcript, so
                # compliance has to know which phrases it cannot rely on. Beside
                # the protocol by construction, since dual_capture writes both.
                far_p = take / "system-segments.json"
                if not far_p.exists():
                    p.error(
                        f"{name}: --protocol needs system-segments.json beside "
                        f"protocol.json. Without the far end's transcript there "
                        f"is no way to tell a cue phrase the operator said from "
                        f"one the playback said, and the compliance check would "
                        f"credit the echo. Re-run dual_capture without "
                        f"--no-transcribe.")
                far_segs = load_segments(far_p, digest=sha256(sys_p),
                                         samples=wav_frames(sys_p), leg="system")
                far_texts[name] = " ".join(g.get("text", "") for g in far_segs)
        except SourceError as exc:
            p.error(f"{name}: {exc}")
        proto = protocols.get(name)
        if proto and args.fit_mode == "prefix":
            cal = [ph for ph in proto["phases"] if ph["role"] == "calibration"][-1]
            span = phase_interior(cal, proto["cue_margin_s"])
            if not span or not (span[0] < args.fit_before <= span[1]):
                p.error(
                    f"{name}: --fit-before {args.fit_before:g}s is not inside the "
                    f"calibration phase, whose attributable interior runs "
                    f"{span[0]:.1f}-{span[1]:.1f}s. The fit would take in audio "
                    f"the operator was never cued to be silent through.")


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
        "supplied_segments": {n: sha256(Path(v).expanduser())
                              for n, v in seg_paths.items()},
        "supplied_protocols": {n: sha256(Path(v).expanduser())
                               for n, v in proto_paths.items()},
        "max_lag_s": MAX_LAG_S, "phat_floor": PHAT_FLOOR,
        "min_fit_run": MIN_FIT_RUN, "align_margin": ALIGN_MARGIN,
        "min_fit_total": MIN_FIT_TOTAL, "dt_ratio": DT_RATIO,
        "fit_before_s": args.fit_before or None,
        "harness_sha256": sha256(Path(__file__).resolve()),
        "encoder_sha256": encoder_digest,
        "vad": {"pct": VAD_PCT, "margin_db": VAD_MARGIN_DB,
                "floor": VAD_FLOOR, "hangover_s": VAD_HANGOVER_S},
    }, "inputs": {}, "takes": {}}

    print(f"{'take':11s} {'class':19s} {'condition':10s} {'n':>4} {'min':>7} "
          f"{'mean':>7} {'max':>7} {'admitted':>10}")
    for name, take in takes.items():
        source = takes[args.reference_from] if args.reference_from else take
        mic_p, ref_p = take / "mic.wav", source / "system.wav"
        manifest["inputs"][name] = {"mic_sha256": mic_digests[name],
                                    "system_sha256": sha256(ref_p)}
        mic, ref = load_wav(mic_p), load_wav(ref_p)
        supplied_segs, protocol = supplied.get(name), protocols.get(name)
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

        # Cancelled audio from outside this program — AEC3, or anything else. It
        # joins `conds` before anything is scored, so every condition meets the
        # same window set, the same voiceprint and the same floor check. Scoring
        # it in a separate run instead is how two figures end up describing
        # different windows and get quoted as if they described the same ones.
        for cname, cpath in sorted(extra.get(name, {}).items()):
            if not cpath.exists():
                p.error(f"{name}: no {cpath} for condition {cname}")
            audio = load_wav(cpath)
            if len(audio) > len(mic):
                # Longer means it is not this take, or not this --max-seconds.
                # Trimming would align the wrong samples to every segment time.
                p.error(f"{name}: condition {cname} is {len(audio) / RATE:.2f}s "
                        f"against {len(mic) / RATE:.2f}s of microphone — that is a "
                        f"different recording, or one made before --max-seconds")
            meta.setdefault("conditions", {})[cname] = {
                "path": str(cpath), "sha256": sha256(cpath), "samples": len(audio)}
            conds[cname] = audio

        # Every condition has to cover every scored window or the comparison is
        # between different audio. A block-based canceller returns whole blocks of
        # the shorter leg, so its output is legitimately a little short; the
        # scored region shrinks to what they all cover, and says by how much.
        shortest = min(len(v) for v in scored_conditions(conds).values())
        if shortest < len(conds["raw"]):
            dropped = (len(conds["raw"]) - shortest) / RATE
            thinnest = min(scored_conditions(conds).items(), key=lambda kv: len(kv[1]))[0]
            print(f"{name:11s} scoring the first {shortest / RATE:.2f}s: "
                  f"{dropped:.2f}s dropped because condition {thinnest!r} ends "
                  f"there and every condition must cover every window")
            conds = {k: v[:shortest] if not k.startswith("_") else v
                     for k, v in conds.items()}
        limit = len(conds["raw"]) / RATE
        if supplied_segs is not None:
            segs = [s for s in supplied_segs
                    if s["end"] - s["start"] >= sg.MIN_SCORABLE_S and s["end"] <= limit]
        else:
            segs = windows(conds["raw"], args.window, args.hop)
        segs = [s for s in segs if s["start"] >= args.score_after]

        # Recorded so the verdict and the bounds iterate what was actually scored
        # rather than a hardcoded triple. Both used to name raw/linear/masked
        # literally, which meant an added condition escaped the noise-floor check
        # and the bounds table — it would have appeared in the printed rows and in
        # nothing that guards them.
        rows = {"meta": meta, "conditions": sorted(scored_conditions(conds))}
        if protocol:
            margin = protocol["cue_margin_s"]
            classes = classify(segs, protocol["phases"], margin,
                               far_texts.get(name))
            rows["compliance"] = protocol_compliance(
                protocol, conds["raw"], margin, supplied_segs or [],
                far_texts.get(name))
            rows["echo_only"] = control_erle(protocol, conds, margin)
            rows["dropped_phases"] = protocol["dropped_phases"]
            for line in rows["compliance"]["notes"]:
                print(f"{name:11s} NOTE  {line}")
            c = rows["compliance"]
            print(f"{name:11s} cue phrases transcribed in "
                  f"{c['speak_intervals_verified']} of "
                  f"{c['speak_intervals_verified'] + c['speak_intervals_unverified']} "
                  f"speak intervals; silence in the rest is assumed, not measured")
            eo = rows["echo_only"]
            if eo.get("erle_db"):
                erle = "  ".join(f"{k} {v:+.1f} dB" for k, v in eo["erle_db"].items())
                print(f"{name:11s} echo-only suppression over {eo['seconds']:.1f}s "
                      f"of far-end-active silent interval: {erle}")
            else:
                print(f"{name:11s} no echo-only suppression figure: {eo['why']}")
        else:
            classes = {"all": segs}

        rows["classes"] = {}
        for cls, members in classes.items():
            if not members or cls == "calibration":
                continue
            block = {"windows": [dict(s) for s in members]}
            for cond, audio in scored_conditions(conds).items():
                a32 = audio.astype(np.float32)
                floor = floor_rms(audio)
                scored = sg.embed_segments(a32, members, enc)
                v = np.array([sg.score(profile, e) for e in scored if e is not None])
                if not len(v):
                    # Every window came back unscorable. Say so rather than
                    # raising from inside a format string, which says nothing.
                    print(f"{name:11s} {cls:19s} {cond:10s}    0   (nothing "
                          f"reached {sg.MIN_SCORABLE_S:g}s of scorable audio)")
                    continue
                for row, e in zip(block["windows"], scored, strict=True):
                    row[cond] = None if e is None else round(float(sg.score(profile, e)), 4)
                    lo, hi = int(row["start"] * RATE), int(row["end"] * RATE)
                    # Recorded for every window, because the check it supports
                    # is one-directional: an admitted window whose residual sits
                    # at the take's own floor holds nothing, and its score is the
                    # embedding reacting to near-silence rather than to a voice.
                    row[f"{cond}_rms_over_floor"] = round(
                        float(np.sqrt((audio[lo:hi] ** 2).mean()) / (floor + 1e-12)), 1)
                hollow = sum(
                    1 for row in block["windows"]
                    if row.get(cond) is not None and row[cond] >= args.threshold
                    and row[f"{cond}_rms_over_floor"] < FLOOR_RATIO_MIN)
                warn = f"  {hollow} admitted at the noise floor" if hollow else ""
                print(f"{name:11s} {cls:19s} {cond:10s} {len(v):4d} {v.min():+7.3f} "
                      f"{v.mean():+7.3f} {v.max():+7.3f} "
                      f"{(v >= args.threshold).sum():5d}/{len(v):<4d}{warn}")
            rows["classes"][cls] = block
        if not rows["classes"]:
            print(f"{name:11s} nothing scorable at or after {args.score_after:g}s")
        if protocol:
            # After every class has been scored, because the verdict reads the
            # per-window floor ratios those passes write.
            rows["bounds"] = scheduled_bounds(rows, args.threshold)
            for cond, b in rows["bounds"]["conditions"].items():
                v, s = b["verified"], b["scheduled"]
                lo = f"{s['admitted']}/{s['of']}"
                hi = f"{v['admitted']}/{v['of']}" if v else "none verified"
                print(f"{name:11s} {cond:10s} admitted {lo} over the whole cued "
                      f"reading, {hi} over the verified subset")
            if rows["bounds"]["excluded_seconds"]:
                print(f"{name:11s} the two differ over "
                      f"{rows['bounds']['excluded_seconds']:.1f}s the raw "
                      f"transcript could not attribute — the result lies between "
                      f"them, and closing the gap needs a near-end channel")
            rows["verdict"] = run_verdict(rows, protocol, args.threshold)
            if rows["verdict"]["verdict"] != "scored":
                for why in rows["verdict"]["why"]:
                    print(f"{name:11s} INCONCLUSIVE  {why}")
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
