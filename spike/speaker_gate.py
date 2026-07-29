#!/usr/bin/env python3
"""Keep the operator's speech on the microphone leg and report what was dropped.

An open microphone records the room, not the operator. Measured on the 75-minute
capture in spike/RESULTS.md: 114 of 802 merged turns — 14.2% — were other people
talking near the laptop, transcribed cleanly and delivered to the notes labelled
as the operator. `drop_unvoiced()` in dual_capture.py cannot touch that, and
correctly so: it asks whether audio is behind a segment, and audio is. This
module asks the next question, whether that audio is the operator, which is the
same architectural move one level up.

The move is not ours. Microsoft Teams and Zoom both gate the microphone on a
voice profile stored on the device and remove what does not match, and neither
requires an enrollment ritual — Teams builds the profile from ordinary
in-meeting speech, Zoom from the first speech in a call. Enrollment here is
therefore a centroid over microphone audio the project already records, not a
setup screen.

**The threshold is not calibrated, and nothing in this repository can calibrate
it.** `gate()` takes it as a required argument with no default, because the only
defensible value is a quantile of the operator's own score distribution on the
built-in microphone, and no recording of the operator on that microphone exists
— every mic leg in this project is silence or the household. A plausible
constant here would be indistinguishable from a measured one to every later
reader, which is the failure this file is written to avoid.

The remaining input is a minute of the operator speaking at a working distance,
captured through `dual_capture.py`, in each of two or three separate sittings —
and the plural is measured, not cautious. Thresholds derived from a single
session ran too strict in all nine speaker-by-operating-point comparisons
available, by 0.006 to 0.181, which drops more of the operator than the target
asked for. `--calibrate` turns that recording into the number in one pass.

Both vendors also state the failure mode, and it is the reason this module
returns rejections rather than a filtered list. Teams alerts the user when it
detects that it is suppressing a speaker close to the microphone, because a
colleague sitting beside you is indistinguishable from interference until
somebody decides which. A gate that silently drops a real participant is worse
than the contamination it replaces: the transcript then omits speech with no
record that it did.

Run:
    python spike/speaker_gate.py --self-test
    python spike/speaker_gate.py --calibrate SEGMENTS.json AUDIO.wav \\
        --against SEGMENTS.json AUDIO.wav
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 16_000
ECAPA_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"

# ECAPA's embedding is unreliable below roughly two seconds of speech, which is
# where separability.py set its own floor. That is not a tuning constant this
# module may quietly apply as a drop rule: on the two legs of the 75-minute
# capture, segments under 2 s are 28% and 25% of all segments, carrying 12% and
# 8% of the words. Discarding an eighth of the operator's words — "yes",
# "agreed", "I'll do that", which is what short turns are — would lose exactly
# the commitments the tool exists to record. Keeping them unconditionally leaks
# the room. Neither is the gate's call to make, so they come back in their own
# bucket, counted, and the caller decides.
MIN_SCORABLE_S = 2.0

# Enrollment material is passively harvested microphone audio, so it contains
# the contamination the gate exists to remove. A plain mean has no defence
# against that: scored on how far a profile's held-out speech sits above
# everyone else's, an untrimmed centroid on the system leg fell from +0.493 to
# +0.446 as contamination went 0% to 25%, and on the mic leg from +0.340 to
# +0.295. Trimming holds both flat — +0.498 and +0.342 across the whole range.
#
# The exact fraction barely matters, which is the sign of a constant that is not
# tuned: 0.25 and 0.40 agree to within 0.002 at every contamination level
# measured, and 0.10 only falls behind once a quarter of the set is foreign.
# Trimming a clean set is not the cost it looks like, because a set assembled
# from real captures is never quite clean.
ENROLL_TRIM_FRAC = 0.25

# Below three segments a quartile is an artifact rather than a measurement, and
# quartiles decide both the enrollment trim and the borderline band's width. A
# profile that cannot say how variable the speaker is cannot say which
# rejections were close calls.
MIN_ENROLL_SEGMENTS = 3


def _unit(v: np.ndarray) -> np.ndarray:
    """Project onto the unit sphere, so every cosine is a plain dot product.

    Embedding magnitude carries recording level and duration, not identity.
    Averaging un-normalised embeddings therefore weights the profile by how loud
    and how long each segment was on top of whatever weighting was asked for.
    """
    n = float(np.linalg.norm(v))
    if n == 0:
        raise ValueError("zero-length embedding: the encoder returned nothing usable")
    return (v / n).astype(np.float64)


def _width(sims: np.ndarray) -> float:
    """A robust width for a similarity distribution: twice its upper half-IQR.

    Taken from the upper half deliberately. Every similarity distribution in
    this module has a contaminated low tail by construction — the enrollment set
    holds whatever else was in the room, and the gate's rejected set holds
    whichever of the operator's own segments fell short. A standard deviation
    reads that tail as width. The median and upper quartile do not move until
    the minority becomes a majority.

    Doubling the half-IQR lands about a third wider than a standard deviation on
    normal data. That direction is chosen: this width sets how far below the
    threshold still counts as a close call, and reporting a close call as a
    confident rejection is the error that hides a co-located speaker.
    """
    q50, q75 = np.quantile(sims, [0.5, 0.75])
    return 2 * float(q75 - q50)


def _tight_centre(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centroid of a set after its least typical quarter is dropped, and the mask.

    A plain mean is not usable as a centre for any set this module handles. Each
    of them carries a minority of the other class by construction — the
    enrollment set holds whatever else was in the room, and the gate's rejected
    set holds whichever of the operator's own segments fell short — and a
    handful of outliers pulls a mean centroid far enough to lower every other
    member's similarity to it.

    Two passes, because ranking segments by how typical they are is only
    possible once there is a provisional answer for what typical means.
    """
    provisional = _unit(vectors.mean(axis=0))
    sims = vectors @ provisional
    keep = sims >= np.quantile(sims, ENROLL_TRIM_FRAC)
    return _unit(vectors[keep].mean(axis=0)), keep


def _coherent_share(kept: np.ndarray, rejected: np.ndarray) -> float | None:
    """How concentrated the dropped audio is on a consistent voice.

    Teams alerts when it detects it is suppressing a speaker near the
    microphone, and the question behind that alert is not whether the rejected
    audio is tight on average — a colleague who sounds somewhat like the
    operator and a room full of strangers can average to the same number. It is
    how much of what was dropped keeps coming back as the same person.

    So this counts: the share of rejected segments sitting at least as close to
    the rejected set's own centre as the loosest kept segment sits to the kept
    set's. The kept set is one voice by construction, which makes it the
    yardstick for what a consistent voice looks like on this microphone, in this
    room, in this recording. No constant is imported from anywhere.

    It measures concentration, not a count of speakers, and the distinction is
    not academic. Run against a labelled eight-speaker meeting it read 0.45 and
    0.46 with the rejected audio spread across seven speakers, and 0.75 where two
    dominated it.
    That is the right behaviour for what the alert is for — two colleagues
    consistently deleted from a transcript is the same defect as one — but it
    means the signal is a reason to look, not a claim about how many people were
    lost. On the controls below it reads 0.75 and 0.77 with a single voice
    dropped against 0.14 and 0.00 with three scattered.
    """
    if len(kept) < MIN_ENROLL_SEGMENTS or len(rejected) < MIN_ENROLL_SEGMENTS:
        return None
    kept_sims = kept @ _tight_centre(kept)[0]
    rejected_sims = rejected @ _tight_centre(rejected)[0]
    return float((rejected_sims >= kept_sims.min()).mean())


@dataclass(frozen=True)
class Profile:
    """An enrolled voiceprint, carrying enough to judge whether to trust it.

    `cohesion` is the profile's own self-report: the median similarity of the
    segments that built it to the centroid they built. It is the only warning
    available before any audio is gated, because a centroid built from two
    people looks exactly like one built from a single person to every caller.
    Real values, for scale: profiles enrolled per speaker on a labelled meeting
    read 0.830 to 0.844, while one enrolled over the whole multi-speaker mic leg
    of the long capture read 0.436.

    `spread` is how wide that distribution runs, and it sets the borderline
    band; the same profiles ran 0.079 to 0.123. `seconds` says how much speech
    is behind the profile, which is the quantity the vendors talk about when
    they say a passive profile improves over a couple of meetings.
    """

    centroid: np.ndarray
    n_enrolled: int
    n_excluded: int
    seconds: float
    cohesion: float
    spread: float


@dataclass(frozen=True)
class Rejection:
    """One dropped segment, with the evidence for dropping it.

    `reason` is `borderline` when the score fell within one profile spread of the
    threshold — near enough that the same voice on a worse day would have passed
    — and `below_profile` when it did not. The distinction is the whole point:
    confident rejections are the gate working, and a run full of borderline ones
    is the gate guessing.
    """

    index: int
    start: float
    end: float
    score: float
    reason: str


@dataclass(frozen=True)
class GateResult:
    """Three buckets, because two would hide a decision.

    `unscorable` is not a rejection and not a keep. Those segments are shorter
    than the embedding can judge, and folding them into either bucket would make
    a policy choice — lose the operator's short turns, or admit the room's — look
    like a measurement. The caller sees the count and the seconds and decides.

    `persistent_other` is the Teams alert: most of what was dropped keeps coming
    back as the same voice rather than being scattered, which means someone
    co-located is being deleted from the transcript and the user should be told.
    `coherent_share` carries the evidence beside the verdict, and multiplied by
    `rejected_seconds` it gives the figure a user actually needs — roughly how
    much of one person's speech this run removed. With nothing kept there is
    nothing to compare against and the flag stays down; a run that dropped every
    segment has already said something louder than this.
    """

    kept: list[int]
    rejected: list[Rejection]
    unscorable: list[int]
    scores: list[float | None]
    kept_seconds: float
    rejected_seconds: float
    unscorable_seconds: float
    coherent_share: float | None
    persistent_other: bool

    @property
    def borderline(self) -> list[Rejection]:
        return [r for r in self.rejected if r.reason == "borderline"]


def load_encoder(savedir: str | Path) -> Callable[[np.ndarray], np.ndarray]:
    """Return an `embed(audio) -> vector` over ECAPA-TDNN.

    speechbrain and torch are imported here rather than at module scope so the
    controls in `--self-test` run without either. That is not a convenience: the
    logic in this file is arithmetic over embeddings, and a test that can only
    run after a 153 MB install and an 89 MB model fetch is a test that stops
    being run.

    One segment per call. Batching would be faster and needs correct relative
    lengths alongside the padding to give the same answer; the embedding is not
    on any critical path this project has, and separability.py measured this
    audio the same way.
    """
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    encoder = EncoderClassifier.from_hparams(
        source=ECAPA_SOURCE, savedir=str(savedir), run_opts={"device": "cpu"}
    )

    def embed(audio: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            out = encoder.encode_batch(torch.from_numpy(audio).unsqueeze(0))
        return out.squeeze().cpu().numpy()

    return embed


def embed_segments(
    audio: np.ndarray, segments: list[dict], embed: Callable[[np.ndarray], np.ndarray]
) -> list[np.ndarray | None]:
    """Unit embeddings aligned to `segments`, with None where too short to judge.

    Aligned by index rather than filtered, so no caller has to maintain a second
    mapping back to the transcript. `audio` is 16 kHz mono float32 in [-1, 1),
    which is what both capture legs produce.
    """
    out: list[np.ndarray | None] = []
    for seg in segments:
        if seg["end"] - seg["start"] < MIN_SCORABLE_S:
            out.append(None)
            continue
        clip = audio[int(seg["start"] * RATE):int(seg["end"] * RATE)]
        out.append(_unit(embed(clip)))
    return out


def enroll(embeddings: list[np.ndarray], durations: list[float]) -> Profile:
    """Build a voiceprint from segments believed to be mostly the operator.

    A trimmed mean, so that one intruding voice in the harvested material cannot
    write itself into the profile.

    The segments are weighted equally, which was not the first design and is not
    the obvious one. Weighting by duration is the natural move — a ten-second
    turn ought to say more about a voice than a two-second fragment — and it was
    measured rather than assumed, against equal weights at three contamination
    levels on both legs. Equal weighting matched or beat it in all twelve
    comparisons, and weighting by uncapped duration was the worst arm
    everywhere, costing 0.020 of separation on the mic leg. Two mechanisms
    explain it: the trim already removes poor segments regardless of length, and
    Whisper's long segments are the ones most likely to span a speaker change,
    so weighting by duration weights the impurities up. `durations` is kept for
    the seconds the profile reports, which is what says whether it has enough
    material behind it, and no longer for weighting.
    """
    if len(embeddings) < MIN_ENROLL_SEGMENTS:
        raise ValueError(
            f"enrollment needs at least {MIN_ENROLL_SEGMENTS} scorable segments, "
            f"got {len(embeddings)}"
        )
    emb = np.stack([np.asarray(e, dtype=np.float64) for e in embeddings])
    dur = np.asarray(durations, dtype=np.float64)
    centroid, keep = _tight_centre(emb)
    # Cohesion describes the segments that built the profile; the width is taken
    # across every segment offered, including the trimmed ones. Measuring the
    # width post-trim understates it by around 40% — the trim has already cut the
    # low tail off the distribution being measured — and a band that narrow
    # reports close calls as confident rejections, which is the one direction
    # this module is not allowed to err in.
    cohesion = float(np.median(emb[keep] @ centroid))
    return Profile(
        centroid=centroid,
        n_enrolled=int(keep.sum()),
        n_excluded=int((~keep).sum()),
        seconds=float(dur[keep].sum()),
        cohesion=cohesion,
        spread=_width(emb @ centroid),
    )


def score(profile: Profile, embedding: np.ndarray) -> float:
    """Cosine similarity. Both sides are unit vectors, so this is a dot product."""
    return float(np.asarray(embedding, dtype=np.float64) @ profile.centroid)


def gate(
    profile: Profile,
    segments: list[dict],
    embeddings: list[np.ndarray | None],
    threshold: float,
) -> GateResult:
    """Sort segments into kept, rejected, and unjudgeable, and say why for each.

    The borderline band is one profile spread wide — the measured variability of
    the operator's own speech about their own centroid, which is the natural
    scale for "far enough below the line to be sure". Deriving it leaves the
    threshold as the only number a caller has to supply; inventing a second
    constant to describe closeness to the first would double the unfounded
    parameters rather than halve them.
    """
    kept: list[int] = []
    rejected: list[Rejection] = []
    unscorable: list[int] = []
    scores: list[float | None] = []
    kept_vectors: list[np.ndarray] = []
    rejected_vectors: list[np.ndarray] = []

    for i, (seg, emb) in enumerate(zip(segments, embeddings, strict=True)):
        if emb is None:
            unscorable.append(i)
            scores.append(None)
            continue
        s = score(profile, emb)
        scores.append(s)
        if s >= threshold:
            kept.append(i)
            kept_vectors.append(emb)
            continue
        reason = "borderline" if s >= threshold - profile.spread else "below_profile"
        rejected.append(Rejection(i, seg["start"], seg["end"], s, reason))
        rejected_vectors.append(emb)

    def seconds(indices) -> float:
        return float(sum(segments[i]["end"] - segments[i]["start"] for i in indices))

    # A majority, and nothing more precise, because nothing more precise is
    # supported: the share ran 0.75 and 0.77 with one person being dropped
    # against 0.14 and 0.00 with three, and 0.45 against 0.80 on the two ends of
    # a real labelled meeting. Every cut point between 0.2 and 0.7 gives the
    # same verdict on all of them. Erring towards firing is deliberate — a needless
    # prompt costs the user a moment, and a missed one costs them a colleague's
    # speech with no record that it went.
    share = (
        _coherent_share(np.stack(kept_vectors), np.stack(rejected_vectors))
        if kept_vectors and rejected_vectors
        else None
    )

    return GateResult(
        kept=kept,
        rejected=rejected,
        unscorable=unscorable,
        scores=scores,
        kept_seconds=seconds(kept),
        rejected_seconds=seconds(r.index for r in rejected),
        unscorable_seconds=seconds(unscorable),
        coherent_share=share,
        persistent_other=share is not None and share > 0.5,
    )


def calibrate(
    operator_scores: list[float],
    target_frr: float,
    other_scores: list[float] | None = None,
) -> dict:
    """The threshold that rejects `target_frr` of the operator's own speech.

    An operating point, not an optimum, and deliberately not the equal error
    rate. The two failures are not symmetric here: admitting the room perturbs
    which real content survives summarization, measured as a wash on one meeting
    in spike/RESULTS.md, while dropping the operator removes the answer to the
    only question this tool exists to answer. So the threshold is set on the
    operator's distribution and the admit rate is reported as its cost, rather
    than the two being balanced against each other as though they cost the same.

    The estimate is a sample quantile, so it is only as good as the sample:
    `n_operator` is returned alongside it and small values should be read as
    such, not rounded into a constant.
    """
    if not 0 < target_frr < 1:
        raise ValueError(f"target_frr must lie strictly between 0 and 1, got {target_frr}")
    op = np.asarray(operator_scores, dtype=np.float64)
    if len(op) < MIN_ENROLL_SEGMENTS:
        raise ValueError(f"too few operator scores to take a quantile: {len(op)}")
    threshold = float(np.quantile(op, target_frr))
    result = {
        "threshold": threshold,
        "target_frr": target_frr,
        "measured_frr": float((op < threshold).mean()),
        "n_operator": len(op),
        "false_admit_rate": None,
        "n_other": 0,
    }
    if other_scores is not None and len(other_scores):
        other = np.asarray(other_scores, dtype=np.float64)
        result["false_admit_rate"] = float((other >= threshold).mean())
        result["n_other"] = len(other)
    return result


def leave_one_out_scores(
    embeddings: list[np.ndarray], durations: list[float]
) -> list[float]:
    """Score each segment against a profile enrolled without it.

    A segment scores high against a centroid it helped build, and that bias runs
    in the dangerous direction — it flatters the operator's own distribution,
    which is exactly the distribution the threshold is a quantile of. Enrolling
    n times is cheap once the embeddings exist.

    It removes self-enrollment bias and no other kind. Session bias survives
    intact, and it is not small, nor is it two-sided: across three labelled
    speakers at three operating points, a threshold derived this way from a
    single sitting sat ABOVE the one derived with real time between enrollment
    and test in all nine comparisons, by 0.006 to 0.181. That direction is the
    harmful one — a threshold that strict drops more of the operator than the
    target asked for. So a calibration recording from one sitting is not
    conservative, it is systematically over-tight, and the material this is
    handed should span more than one.
    """
    out = []
    for i in range(len(embeddings)):
        rest = embeddings[:i] + embeddings[i + 1:]
        rest_dur = durations[:i] + durations[i + 1:]
        out.append(score(enroll(rest, rest_dur), embeddings[i]))
    return out


def load_wav(path: Path) -> np.ndarray:
    """16 kHz mono s16le, the format both capture legs write."""
    with wave.open(str(path)) as w:
        if w.getframerate() != RATE or w.getnchannels() != 1:
            raise SystemExit(
                f"{path}: expected {RATE} Hz mono, got {w.getframerate()} Hz "
                f"with {w.getnchannels()} channel(s)"
            )
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def load_segments(path: Path) -> list[dict]:
    """A list of `{"start": seconds, "end": seconds}`, as the capture legs emit."""
    segs = json.loads(path.read_text())
    if not isinstance(segs, list) or not all("start" in s and "end" in s for s in segs):
        raise SystemExit(f"{path}: expected a list of segments with start and end")
    return segs


# ---------------------------------------------------------------------------
# Controls
#
# Every case below states what it proves, and the sets come in pairs that have
# to behave in opposite directions — a gate that keeps everything and a gate
# that keeps nothing both pass a one-sided check.
#
# The encoder is a fixture rather than the real model, for the reason
# `load_encoder` gives, but the audio path is real: synthetic audio is built at
# a per-speaker level, sliced by `embed_segments` from segment times, and the
# fixture recovers the speaker from the samples it was handed. Slice the wrong
# span and the recovered speaker is wrong, so the arithmetic under test is not
# the only thing being exercised.
# ---------------------------------------------------------------------------

_DIM = 192  # ECAPA's output width; nothing in this file depends on the value


def _speaker_directions(rng: np.random.Generator, n: int) -> np.ndarray:
    """Speaker centres sharing a common component, as real embeddings do.

    ECAPA embeddings are not isotropic — two different speakers on the same
    channel sat at +0.21 cosine near-field and +0.10 far-field in
    spike/RESULTS.md, not at zero. Directions drawn independently would make
    every negative trivially separable and the controls would prove nothing
    about the regime this runs in.
    """
    shared = rng.standard_normal(_DIM)
    return np.stack([_unit(shared + 1.7 * rng.standard_normal(_DIM)) for _ in range(n)])


def _fixture_audio(spans: list[tuple[float, float, int]], rng) -> tuple[np.ndarray, list[dict]]:
    """Audio whose amplitude encodes which speaker holds each span."""
    total = int(max(e for _, e, _ in spans) * RATE) + RATE
    audio = np.zeros(total, dtype=np.float32)
    segments = []
    for start, end, speaker in spans:
        lo, hi = int(start * RATE), int(end * RATE)
        level = (speaker + 1) / 10.0
        audio[lo:hi] = level + 0.0005 * rng.standard_normal(hi - lo).astype(np.float32)
        segments.append({"start": start, "end": end})
    return audio, segments


def _fixture_encoder(directions: np.ndarray, within: float):
    """Recover the speaker from the clip's level, then jitter about their centre.

    The jitter is seeded from the samples, so identical audio embeds identically
    across runs and two clips of one speaker do not collapse onto one point —
    a profile with zero spread would give the borderline band zero width and
    quietly disable half of what is under test.
    """

    def embed(audio: np.ndarray) -> np.ndarray:
        k = round(float(np.abs(audio).mean()) * 10) - 1
        k = min(max(k, 0), len(directions) - 1)
        seed = int(abs(float(audio.sum())) * 1000) % (2**32)
        jitter = np.random.default_rng(seed).standard_normal(_DIM)
        return directions[k] + within * jitter

    return embed


def _spans(n: int, speaker: int, t0: float, length: float = 4.0) -> list[tuple[float, float, int]]:
    return [(t0 + i * (length + 1), t0 + i * (length + 1) + length, speaker) for i in range(n)]


def _voice_at(centroid: np.ndarray, away: np.ndarray, cosine: float) -> np.ndarray:
    """A direction sitting exactly `cosine` from `centroid`, leaning towards `away`.

    Constructed rather than blended by a hand-picked weight. The borderline band
    is one profile spread wide, which is 0.02 to 0.14 of cosine on the real
    embeddings measured for the report — narrow enough that a fixture tuned to
    land inside it by trial would break the next time any other constant moved.
    Solving for the angle instead makes the case say what it means: a voice this
    similar to the operator's.
    """
    perp = _unit(away - float(away @ centroid) * centroid)
    return _unit(cosine * centroid + (1 - cosine**2) ** 0.5 * perp)


def run_self_test() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok and detail:
            print(f"          {detail}")

    rng = np.random.default_rng(0)
    # Four voices: the operator, one nothing like them, one placed deliberately
    # close once the profile exists, and a fourth so a rejection set can be
    # spread across several people rather than one. Within-speaker variation is
    # set so the profile lands near the cohesion a real single-speaker profile
    # reached on this project's system leg, 0.88 +/- 0.03, rather than at a
    # separation no microphone offers.
    directions = _speaker_directions(rng, 4)
    embed = _fixture_encoder(directions, within=0.038)

    audio, segs = _fixture_audio(_spans(24, 0, 1.0), rng)
    emb = [e for e in embed_segments(audio, segs, embed) if e is not None]
    durations = [s["end"] - s["start"] for s in segs]
    operator = enroll(emb, durations)

    print("=== enrollment ===\n")
    check(
        "a profile built from one voice is cohesive",
        operator.cohesion > 0.8,
        f"cohesion {operator.cohesion:.3f}",
    )
    half_audio, half_segs = _fixture_audio(_spans(12, 0, 1.0) + _spans(12, 1, 70.0), rng)
    half_emb = [e for e in embed_segments(half_audio, half_segs, embed) if e is not None]
    half = enroll(half_emb, [s["end"] - s["start"] for s in half_segs])
    check(
        "a profile split between two voices is not, and says so before anything is gated",
        half.cohesion < operator.cohesion - operator.spread,
        f"two-voice {half.cohesion:.3f} vs one-voice {operator.cohesion:.3f}",
    )

    # A quarter of the enrollment set is somebody else — the level at which the
    # trim was measured to hold a profile's separation flat while an untrimmed
    # mean loses 0.047 of it on real embeddings.
    dirty_audio, dirty_segs = _fixture_audio(_spans(24, 0, 1.0) + _spans(8, 1, 130.0), rng)
    dirty_emb = [e for e in embed_segments(dirty_audio, dirty_segs, embed) if e is not None]
    dirty_dur = [s["end"] - s["start"] for s in dirty_segs]
    trimmed = enroll(dirty_emb, dirty_dur)
    plain_dirty = _unit(np.stack(dirty_emb).mean(axis=0))
    check(
        "an intruder in a quarter of the enrollment set is trimmed back out",
        score(operator, trimmed.centroid) > float(plain_dirty @ operator.centroid),
        f"trimmed {score(operator, trimmed.centroid):.4f} vs plain "
        f"{float(plain_dirty @ operator.centroid):.4f}, excluded {trimmed.n_excluded}",
    )
    # The converse is what makes the trim safe rather than merely strong: on
    # clean material it must land where the plain mean would have.
    plain_clean = _unit(np.stack(emb).mean(axis=0))
    check(
        "and trimming a clean set costs less than leaving the intruder in a dirty one",
        score(operator, plain_clean) > float(plain_dirty @ operator.centroid),
        f"clean trimmed-vs-plain {score(operator, plain_clean):.5f}, "
        f"dirty plain {float(plain_dirty @ operator.centroid):.5f}",
    )
    check(
        "enrollment below the minimum is refused rather than guessed at",
        _raises(lambda: enroll(emb[:2], durations[:2]), ValueError),
    )

    print("\n=== calibration ===\n")
    own = leave_one_out_scores(emb, durations)
    foreign_audio, foreign_segs = _fixture_audio(_spans(12, 1, 1.0), rng)
    foreign_emb = embed_segments(foreign_audio, foreign_segs, embed)
    foreign = [score(operator, e) for e in foreign_emb if e is not None]
    loose = calibrate(own, target_frr=0.25, other_scores=foreign)
    check(
        "the threshold drops the share of the operator it was asked to drop",
        abs(loose["measured_frr"] - 0.25) <= 1 / len(own),
        f"asked 0.25, measured {loose['measured_frr']:.3f} over n={len(own)}",
    )
    check(
        "and that same threshold admits none of a different voice",
        loose["false_admit_rate"] == 0.0,
        f"admit rate {loose['false_admit_rate']}",
    )
    cal = calibrate(own, target_frr=0.05, other_scores=foreign)
    check(
        "asking to drop less of the operator lowers the bar rather than raising it",
        cal["threshold"] < loose["threshold"],
        f"frr 0.05 -> {cal['threshold']:.3f}, frr 0.25 -> {loose['threshold']:.3f}",
    )
    check(
        "a target outside (0, 1) is refused rather than clamped",
        _raises(lambda: calibrate(own, target_frr=0.0), ValueError),
    )

    print("\n=== gating ===\n")
    threshold = cal["threshold"]
    held_audio, held_segs = _fixture_audio(_spans(10, 0, 1.0), rng)
    held = gate(operator, held_segs, embed_segments(held_audio, held_segs, embed), threshold)
    check(
        "speech the profile was not built from, by the enrolled voice, is kept",
        len(held.kept) >= 9,
        f"kept {len(held.kept)} of 10, rejected {len(held.rejected)}",
    )
    far = gate(operator, foreign_segs, foreign_emb, threshold)
    check(
        "a voice unlike the operator's is dropped",
        not far.kept and len(far.rejected) == 12,
        f"kept {len(far.kept)}, rejected {len(far.rejected)}",
    )

    print("\n=== reporting ===\n")
    check(
        "a voice unlike the operator's is rejected confidently",
        all(r.reason == "below_profile" for r in far.rejected),
        f"reasons {sorted({r.reason for r in far.rejected})}",
    )
    # Placed mid-band rather than by a hand-picked blend. The jitter attenuates
    # any direction's cosine by a constant factor, measured here off the foreign
    # voice's own scores rather than derived, so the case survives a change to
    # any of the geometry above it.
    attenuation = float(np.mean(foreign)) / float(directions[1] @ operator.centroid)
    directions[2] = _voice_at(
        operator.centroid, directions[1], (threshold - operator.spread / 2) / attenuation
    )
    near_audio, near_segs = _fixture_audio(_spans(12, 2, 1.0), rng)
    near = gate(operator, near_segs, embed_segments(near_audio, near_segs, embed), threshold)
    # Stated as a comparison, not a share. A voice sitting on the line produces
    # a mix — some kept, some flagged close, some clearly out — and any fixture
    # asserting a particular ratio would be asserting its own arithmetic. What
    # has to hold is the distinction itself: the near voice produces close calls
    # and the distant one produces none.
    check(
        "a voice close to the operator's is rejected as a close call, not a certainty",
        near.borderline and not far.borderline,
        f"borderline near {len(near.borderline)}/{len(near.rejected)}, "
        f"far {len(far.borderline)}/{len(far.rejected)}",
    )

    # Both alert scenes carry the operator, so the flag is decided by what the
    # rejected audio looks like and not by whether anything was kept at all.
    one_other_audio, one_other_segs = _fixture_audio(
        _spans(10, 0, 1.0) + _spans(10, 1, 60.0), rng
    )
    one_other = gate(
        operator, one_other_segs, embed_segments(one_other_audio, one_other_segs, embed), threshold
    )
    check(
        "one voice dropped repeatedly raises the co-located-speaker alert",
        one_other.persistent_other,
        f"coherent share {one_other.coherent_share:.2f} over "
        f"{len(one_other.rejected)} rejections",
    )
    crowd_spans = _spans(10, 0, 1.0) + [
        s for i, k in enumerate((1, 2, 3)) for s in _spans(4, k, 60.0 + 30 * i)
    ]
    crowd_audio, crowd_segs = _fixture_audio(crowd_spans, rng)
    crowd = gate(operator, crowd_segs, embed_segments(crowd_audio, crowd_segs, embed), threshold)
    check(
        "several different voices dropped do not",
        not crowd.persistent_other and len(crowd.rejected) >= 12,
        f"coherent share {crowd.coherent_share:.2f} over "
        f"{len(crowd.rejected)} rejections",
    )

    print("\n=== segments too short to judge ===\n")
    short_spans = [(1.0, 5.0, 0), (10.0, 11.5, 0), (20.0, 21.0, 1), (30.0, 34.0, 1)]
    short_audio, short_segs = _fixture_audio(short_spans, rng)
    short = gate(operator, short_segs, embed_segments(short_audio, short_segs, embed), threshold)
    check(
        "a segment under the embedding's floor is neither kept nor rejected",
        short.unscorable == [1, 2]
        and 1 not in short.kept
        and 2 not in {r.index for r in short.rejected},
        f"unscorable {short.unscorable}, kept {short.kept}, "
        f"rejected {[r.index for r in short.rejected]}",
    )
    check(
        "and the seconds it holds are reported rather than absorbed into either verdict",
        abs(short.unscorable_seconds - 2.5) < 1e-6,
        f"{short.unscorable_seconds:.3f}s",
    )
    check(
        "the three buckets account for every segment exactly once",
        sorted(short.kept + [r.index for r in short.rejected] + short.unscorable)
        == list(range(len(short_segs))),
    )

    outcome = (
        "all controls behaved as specified" if not failures else f"{failures} control(s) wrong"
    )
    print(f"\n  {outcome}")
    return 1 if failures else 0


def _raises(fn, exc) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


def run_calibrate(args) -> int:
    """Turn a recording of the operator into the threshold this file cannot assume.

    The operator's segments are scored leave-one-out against a profile built
    from the others, which is the distribution the threshold is a quantile of.
    `--against` supplies speech that is known not to be the operator and reports
    what each operating point would admit of it.
    """
    embed = load_encoder(args.model_dir)

    op_segs = load_segments(args.calibrate[0])
    op_audio = load_wav(args.calibrate[1])
    op_emb = [e for e in embed_segments(op_audio, op_segs, embed) if e is not None]
    op_dur = [s["end"] - s["start"] for s in op_segs if s["end"] - s["start"] >= MIN_SCORABLE_S]
    # One more than enrollment needs, because the leave-one-out pass below
    # enrols on n-1. Guarding at the enrollment minimum lets a three-segment
    # recording through and fails inside the loop instead, on the one path this
    # module exists to serve.
    if len(op_emb) <= MIN_ENROLL_SEGMENTS:
        raise SystemExit(
            f"only {len(op_emb)} segments reach {MIN_SCORABLE_S}s — at least "
            f"{MIN_ENROLL_SEGMENTS + 1} are needed to score any one of them against the rest"
        )
    profile = enroll(op_emb, op_dur)
    own = leave_one_out_scores(op_emb, op_dur)

    print("\n=== profile ===\n")
    print(f"  {profile.n_enrolled} segments, {profile.seconds:.0f}s, "
          f"{profile.n_excluded} excluded by the trim")
    print(f"  cohesion {profile.cohesion:.3f} ± {profile.spread:.3f}")
    print(f"  own scores: mean {np.mean(own):.3f}, p5 {np.percentile(own, 5):.3f} "
          f"(leave-one-out, n={len(own)})")

    other: list[float] = []
    if args.against:
        against_segs = load_segments(args.against[0])
        other = [
            score(profile, e)
            for e in embed_segments(load_wav(args.against[1]), against_segs, embed)
            if e is not None
        ]
        print(f"  other-speaker scores: mean {np.mean(other):.3f}, "
              f"p95 {np.percentile(other, 95):.3f} (n={len(other)})")

    print("\n=== operating points ===\n")
    print(f"  {'operator dropped':>16}  {'threshold':>9}  {'room admitted':>13}")
    for target in (0.01, 0.02, 0.05, 0.10, 0.20):
        c = calibrate(own, target, other or None)
        far = "—" if c["false_admit_rate"] is None else f"{c['false_admit_rate']:.1%}"
        print(f"  {target:>15.0%}  {c['threshold']:>9.3f}  {far:>13}")
    if not other:
        print("\n  no --against material, so nothing states what these thresholds cost.\n"
              "  A threshold chosen without it is a rejection rate, not a gate.")
    if len(own) < 30:
        print(f"\n  n={len(own)} is thin for a quantile — read the low targets as indicative.")
    print("\n  These scores carry no time between the profile and what it judges. On\n"
          "  labelled material that ran too strict in every comparison available, by\n"
          "  0.006 to 0.181, so a threshold from one sitting drops more of the operator\n"
          "  than its target asks. Material spanning several sittings fixes what this\n"
          "  recording cannot.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--self-test", action="store_true",
                   help="run the enrollment, gating and reporting controls")
    p.add_argument("--calibrate", nargs=2, metavar=("SEGMENTS.json", "AUDIO.wav"), type=Path,
                   help="operator speech captured on the microphone leg it will gate")
    p.add_argument("--against", nargs=2, metavar=("SEGMENTS.json", "AUDIO.wav"), type=Path,
                   help="speech known not to be the operator, to price each threshold")
    p.add_argument("--model-dir", type=Path, default=Path.home() / ".cache" / "speaker-gate",
                   help="where the ECAPA checkpoint is cached")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()
    if args.calibrate:
        return run_calibrate(args)
    p.error("nothing to do: pass --self-test or --calibrate")
    return 2


if __name__ == "__main__":
    sys.exit(main())
