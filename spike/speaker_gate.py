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

**The threshold is not a constant this module may supply.** `gate()` takes it as a
required argument with no default, and `load_profile` refuses a file that does not
carry one, because the only defensible value is a quantile of the operator's own
score distribution on the microphone it will gate. A plausible constant here would
be indistinguishable from a measured one to every later reader, which is the
failure this file is written to avoid.

One sitting of that material now exists — 117 s, nine scorable segments — which is
not enough, and the shortfall is measured rather than cautious. Thresholds derived
from a single session ran too strict in all nine speaker-by-operating-point
comparisons available, by 0.006 to 0.181, which drops more of the operator than
the target asked for; `leave_one_sitting_out_scores` is what measures the
difference and it needs two. Nine scorable segments is also below the twenty a 5%
false-reject rate needs before any observation IS the fifth percentile.

So the remaining input is **at least one more sitting**, longer than a minute, plus
a recording of somebody who is not the operator for `--against`. `enforce_enrollment`
refuses a profile without both rather than leaving it to this paragraph — an
earlier version of this note said the same thing and nothing enforced it, which is
how a one-sitting profile with no negative evidence became writable.

Both vendors also state the failure mode, and it is the reason this module
returns rejections rather than a filtered list. Teams alerts the user when it
detects that it is suppressing a speaker close to the microphone, because a
colleague sitting beside you is indistinguishable from interference until
somebody decides which. A gate that silently drops a real participant is worse
than the contamination it replaces: the transcript then omits speech with no
record that it did.

Run:
    python spike/speaker_gate.py --self-test

    # One --calibrate per sitting; the plural is the measurement, not caution.
    python spike/speaker_gate.py \\
        --calibrate day1/mic-segments.json day1/mic.wav \\
        --calibrate day2/mic-segments.json day2/mic.wav \\
        --against household/mic-segments.json household/mic.wav \\
        --enroll-out ~/voiceprint.json --target-frr 0.05

Then `dual_capture.py --voiceprint ~/voiceprint.json` gates a real capture with
it. The threshold lives inside that file rather than beside it, so no caller can
substitute a plausible constant for a measured one.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The artifact readers and their refusals live in aec_bound, which retention.py
# and sweep.py already import for the same reason. It holds no echo state at
# module scope and imports this file only inside its own controls, so the
# direction is one-way in practice.
import aec_bound as ab

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


def leave_one_sitting_out_scores(
    sittings: list[tuple[list[np.ndarray], list[float]]]
) -> list[float]:
    """Score each sitting's segments against a profile built from the others.

    This is the measurement `leave_one_out_scores` cannot make, and the difference
    is not a refinement. Leaving out one *segment* still scores it against a
    centroid holding the rest of its own recording — same room, same distance,
    same microphone gain, same voice on the same day. Session bias survives
    intact, and it is the larger of the two: across three labelled speakers at
    three operating points, a single-sitting threshold sat above the honest one by
    0.006 to 0.181, while self-enrollment bias is worth a fraction of that.

    Leaving out the whole sitting is what puts real time between the profile and
    what it judges, which is the condition the gate meets in production — a
    voiceprint enrolled last week judging today's meeting.

    Needs at least two sittings; with one there is nothing to hold out, and the
    caller has to fall back and say so.
    """
    if len(sittings) < 2:
        raise ValueError(
            f"leave-one-sitting-out needs at least 2 sittings, got {len(sittings)}")
    out = []
    for i, (emb, _dur) in enumerate(sittings):
        rest = [s for j, s in enumerate(sittings) if j != i]
        rest_emb = [e for s in rest for e in s[0]]
        rest_dur = [d for s in rest for d in s[1]]
        held_out = enroll(rest_emb, rest_dur)
        out.extend(score(held_out, e) for e in emb)
    return out


def load_wav(path: Path) -> np.ndarray:
    """16 kHz mono s16le, the format both capture legs write.

    float32 rather than aec_bound's float64: ECAPA is a float32 network, and
    `torch.from_numpy` preserves dtype, so a double array reaches
    `encode_batch` as a DoubleTensor and raises inside the encoder rather than
    here. Casting at the loader keeps the whole module in the one dtype the
    embedding path accepts.
    """
    return ab.load_wav(path).astype(np.float32)


def load_segments(path: Path, audio_path: Path, leg: str = "mic") -> list[dict]:
    """One leg's segments, bound by digest to the recording they index.

    This delegates rather than parsing, and the reason is the whole reason it
    exists. An earlier version here accepted any bare JSON list with `start` and
    `end` keys — which is what a merged `transcript.json` also looks like once
    you stop at those two keys, and what a *different take's* segment file looks
    like too. Both load silently and every segment then points at audio it does
    not describe.

    `aec_bound.load_segments` already refuses six specific ways that can go
    wrong, each with a control behind it: a bare list, a merged transcript, the
    wrong leg's timeline, a list that has been through `drop_bled`, a digest that
    does not match the WAV, and overlapping or unordered spans. Keeping a second,
    weaker copy of that check in this file is how the two drift, and the drift is
    invisible — a permissive loader does not fail, it reports the wrong answer.

    The digest and sample count come from the WAV itself, so the caller cannot
    pass a binding that agrees with the segments but not with the audio.
    """
    return ab.load_segments(
        Path(path), digest=ab.sha256(Path(audio_path)),
        samples=_wav_samples(Path(audio_path)), leg=leg)


def _wav_samples(path: Path) -> int:
    """Frame count without decoding the file."""
    with wave.open(str(path)) as w:
        return w.getnframes()


PROFILE_SCHEMA = "voiceprint/1"

# Below this many held-out scores a quantile cannot even express the requested
# operating point: a 5% false-reject rate needs 20 observations before one of them
# IS the 5th percentile, and asking numpy for it below that returns an
# interpolation between neighbours rather than a measured rate. This is not a
# tuning constant — it is 1/target_frr, computed per request.
def min_resolvable(target_frr: float) -> int:
    return int(np.ceil(1.0 / target_frr))


# And above the resolvable floor there is still thin. Thirty is where a sample
# quantile stops moving by more than a hundredth when one observation is added or
# removed, measured on this project's own score distributions. Between the floor
# and here the number is real but soft, and the run says so rather than presenting
# it with the same confidence as a well-sampled one.
THIN_HELD_OUT = 30


def _finite(name: str, value, lo: float | None = None, hi: float | None = None) -> float:
    """A float that is actually a number, in range, or a refusal naming the field.

    NaN is the case this exists for and it is not hypothetical: a NaN threshold
    round-tripped through `save_profile` and `load_profile` unchallenged, and every
    comparison `score >= nan` is False — so the gate rejects every scorable segment
    while keeping the ones too short to judge. The transcript comes out holding
    only the sub-two-second turns, no error is raised, and the printed count of
    what was dropped is the only evidence anything went wrong.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise SystemExit(f"{name} is {value!r}, which is not a number") from None
    if not np.isfinite(v):
        raise SystemExit(
            f"{name} is {v}, which is not a finite number. Every comparison against "
            f"it would be False, so the gate would silently reject all judgeable "
            f"speech and keep only what it cannot judge.")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise SystemExit(f"{name} is {v}, outside the valid range [{lo}, {hi}]")
    return v


def encoder_fingerprint(savedir: str | Path | None = None) -> str | None:
    """A digest of the embedding weights, not the name of the recipe that fetched them.

    `ECAPA_SOURCE` is a Hugging Face repo id, and a repo id is a moving target: the
    same string resolved to different weights would produce a different embedding
    space and silently invalidate every threshold derived under the old one. The
    cosine would still be a number, the gate would still run, and nothing would
    say the profile no longer describes what the encoder emits.

    Only `embedding_model.ckpt` is hashed. The recipe also fetches a VoxCeleb
    classification head this module never calls, and including a file that cannot
    affect an embedding would make the fingerprint change for reasons that do not
    matter. Returns None when the checkpoint has not been fetched yet, which is not
    an error — a profile can be built by a caller supplying its own encoder.
    """
    d = Path(savedir) if savedir else Path.home() / ".cache" / "speaker-gate"
    ckpt = d / "embedding_model.ckpt"
    if not ckpt.exists():
        return None
    # resolve(): the cache stores symlinks into the Hugging Face hub, and hashing a
    # symlink's own bytes would fingerprint the path rather than the weights.
    return ab.sha256(ckpt.resolve())


def runtime_versions() -> dict:
    """The library versions behind an embedding, for a reader who has to reproduce it.

    Imported defensively rather than at module scope, for the reason
    `load_encoder` gives: the controls in `--self-test` run on numpy alone, and a
    provenance helper that drags in 153 MB would make them stop running.
    """
    out = {}
    for mod in ("torch", "speechbrain", "numpy"):
        try:
            out[mod] = __import__(mod).__version__
        except (ImportError, AttributeError):
            out[mod] = None
    return out


def save_profile(path: Path, profile: Profile, threshold: float, *,
                 operating_point: dict, sittings: list[dict],
                 encoder: str = ECAPA_SOURCE) -> None:
    """Persist a voiceprint with the threshold and what produced both.

    The threshold travels **inside** the file, not beside it. Every other
    arrangement lets a caller supply its own number, and this module's entire
    position is that a plausible constant is indistinguishable from a measured
    one to every later reader. A profile whose threshold is a property of the file
    cannot be gated on an invented one.

    `sittings` is the enrollment provenance, and it is required rather than
    optional because of what it makes visible. A threshold derived from a single
    sitting sat ABOVE the multi-sitting one in all nine comparisons available, by
    0.006 to 0.181 — it drops more of the operator than its target asked for. That
    bias is in the harmful direction and it is invisible in the number itself, so
    the count of independent sittings has to be carried with it and stated at
    every use. Optional provenance would be absent exactly when it mattered.
    """
    if not sittings:
        raise ValueError(
            "a profile with no recorded enrollment material cannot state how many "
            "sittings produced it, and a single-sitting threshold is measurably "
            "over-tight — see leave_one_out_scores")
    # Validated on the way OUT as well as in. A profile that cannot be used is
    # better refused where it is produced, beside the material that explains why,
    # than at the start of a meeting an hour later.
    _finite("threshold", threshold, -1.0, 1.0)
    _finite("cohesion", profile.cohesion, -1.0, 1.0)
    _finite("spread", profile.spread, 0.0, 2.0)
    if not np.all(np.isfinite(profile.centroid)):
        raise ValueError("the centroid holds non-finite values")

    doc = {
        "schema": PROFILE_SCHEMA,
        "encoder": encoder,
        "encoder_fingerprint": encoder_fingerprint(),
        "versions": runtime_versions(),
        "centroid": profile.centroid.tolist(),
        "n_enrolled": profile.n_enrolled,
        "n_excluded": profile.n_excluded,
        "seconds": round(profile.seconds, 2),
        "cohesion": round(profile.cohesion, 4),
        "spread": round(profile.spread, 4),
        "threshold": threshold,
        "operating_point": operating_point,
        "sittings": sittings,
    }
    # Owner-only, and written through a temporary file in the same directory so an
    # interrupted write cannot leave a half-parsed profile where a whole one was.
    # A voiceprint is biometric: it is not a secret the way a password is, but it
    # identifies a person and it does not need to be world-readable to work.
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def load_profile(path: Path) -> tuple[Profile, float, dict]:
    """Read a saved voiceprint, its threshold, and the manifest behind them.

    Refuses rather than defaults on every missing field. A gate that falls back to
    a built-in threshold when the file does not carry one is the failure this
    module was written to prevent, arriving through the loader instead of through
    the caller.
    """
    doc = json.loads(Path(path).read_text())
    if doc.get("schema") != PROFILE_SCHEMA:
        raise SystemExit(f"{path}: expected schema {PROFILE_SCHEMA}, "
                         f"got {doc.get('schema')!r}")
    if doc.get("encoder") != ECAPA_SOURCE:
        raise SystemExit(
            f"{path} was enrolled with {doc.get('encoder')!r} but this build uses "
            f"{ECAPA_SOURCE!r}. Cosines between two embedding spaces are not "
            f"comparable, so the threshold means nothing here. Re-enroll.")
    for field in ("centroid", "threshold", "cohesion", "spread", "sittings"):
        if doc.get(field) is None:
            raise SystemExit(f"{path}: no {field}. This is not a usable profile.")
    centroid = np.asarray(doc["centroid"], dtype=np.float64)
    if not centroid.size or not np.all(np.isfinite(centroid)):
        raise SystemExit(f"{path}: the centroid is empty or holds non-finite values, "
                         f"so every score against it is meaningless.")
    profile = Profile(
        centroid=_unit(centroid),
        n_enrolled=int(doc["n_enrolled"]),
        n_excluded=int(doc["n_excluded"]),
        seconds=_finite(f"{path}: seconds", doc["seconds"], 0.0),
        cohesion=_finite(f"{path}: cohesion", doc["cohesion"], -1.0, 1.0),
        spread=_finite(f"{path}: spread", doc["spread"], 0.0, 2.0),
    )
    # A cosine threshold outside [-1, 1] can never be met or never be missed, and
    # NaN is met by nothing at all — see _finite.
    threshold = _finite(f"{path}: threshold", doc["threshold"], -1.0, 1.0)
    # Recorded so the transcript can say which profile gated it. Computed here
    # rather than stored inside, because a digest of a file cannot live in it.
    doc["_profile_sha256"] = ab.sha256(Path(path))
    return profile, threshold, doc


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

    print("\n=== sittings ===\n")
    # Two sittings of the same voice, each with its own small shared offset — one
    # room, one gain setting, one day's worth of whatever a voice does. That
    # offset is exactly what leaving out a single segment cannot see, because the
    # rest of its own sitting carries it too.
    def sitting(direction: np.ndarray, offset: np.ndarray, n: int) -> tuple[list, list]:
        vecs = [_unit(direction + 0.03 * offset + 0.02 * rng.standard_normal(_DIM))
                for _ in range(n)]
        return vecs, [4.0] * n

    session_a = _unit(rng.standard_normal(_DIM))
    session_b = _unit(rng.standard_normal(_DIM))
    sit_a = sitting(directions[0], session_a, 10)
    sit_b = sitting(directions[0], session_b, 10)
    pooled_emb = sit_a[0] + sit_b[0]
    pooled_dur = sit_a[1] + sit_b[1]
    loo = leave_one_out_scores(pooled_emb, pooled_dur)
    loso = leave_one_sitting_out_scores([sit_a, sit_b])
    check(
        "holding out the whole sitting scores lower than holding out one segment, "
        "which is the session bias a single-sitting threshold cannot see",
        float(np.mean(loso)) < float(np.mean(loo)),
        f"leave-one-sitting-out {np.mean(loso):.3f} vs "
        f"leave-one-out {np.mean(loo):.3f}",
    )
    check(
        "so a threshold from one sitting sits ABOVE the honest one — the harmful "
        "direction, dropping more of the operator than its target asked",
        calibrate(loo, 0.05)["threshold"] > calibrate(loso, 0.05)["threshold"],
        f"single-sitting {calibrate(loo, 0.05)['threshold']:.3f} vs "
        f"multi-sitting {calibrate(loso, 0.05)['threshold']:.3f}",
    )
    check(
        "one sitting cannot be held out at all, and says so rather than "
        "silently falling back to the weaker measurement",
        _raises(lambda: leave_one_sitting_out_scores([sit_a]), ValueError),
    )
    check(
        "every segment is scored exactly once across the held-out sittings",
        len(loso) == len(pooled_emb),
        f"{len(loso)} scores for {len(pooled_emb)} segments",
    )

    print("\n=== the profile file ===\n")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        pp = Path(tmp) / "voiceprint.json"
        point = {"threshold": 0.61, "target_frr": 0.05, "n_sittings": 2}
        save_profile(pp, operator, 0.61, operating_point=point,
                     sittings=[{"audio": "a.wav"}, {"audio": "b.wav"}])
        back, thresh, doc = load_profile(pp)
        check(
            "a profile round-trips through the file with its centroid intact",
            float(back.centroid @ operator.centroid) > 1 - 1e-9,
            f"cosine to itself {float(back.centroid @ operator.centroid):.9f}",
        )
        check(
            "the threshold travels inside the file, so no caller supplies its own",
            abs(thresh - 0.61) < 1e-9 and doc["operating_point"]["n_sittings"] == 2,
            f"threshold {thresh}",
        )
        check(
            "and the spread comes back too — without it every rejection reads as "
            "confident and no close call can be reported",
            abs(back.spread - operator.spread) < 1e-4,
            f"{back.spread:.4f} vs {operator.spread:.4f}",
        )
        check(
            "enrollment provenance is required, because a profile that cannot say "
            "how many sittings built it hides the one bias that matters",
            _raises(lambda: save_profile(pp, operator, 0.61, operating_point=point,
                                         sittings=[]), ValueError),
        )

        wrong_space = json.loads(pp.read_text())
        wrong_space["encoder"] = "some/other-model"
        (Path(tmp) / "other.json").write_text(json.dumps(wrong_space))
        check(
            "a profile from another embedding space is refused — its cosines are "
            "not comparable, so its threshold means nothing here",
            _raises(lambda: load_profile(Path(tmp) / "other.json"), SystemExit),
        )

        no_thresh = json.loads(pp.read_text())
        del no_thresh["threshold"]
        (Path(tmp) / "bare.json").write_text(json.dumps(no_thresh))
        check(
            "a profile with no threshold is refused rather than defaulted — a "
            "built-in fallback is the exact failure this module exists to prevent",
            _raises(lambda: load_profile(Path(tmp) / "bare.json"), SystemExit),
        )
        check(
            "and it is written owner-only, because a centroid identifies a person",
            pp.stat().st_mode & 0o077 == 0,
            f"mode {pp.stat().st_mode & 0o777:o}",
        )

        # A NaN threshold is met by nothing: `score >= nan` is False for every
        # segment, so the gate rejects all judgeable speech and keeps only what it
        # cannot judge — a transcript of sub-two-second turns, with no error. It
        # round-tripped through both functions unchallenged before these two.
        check(
            "a NaN threshold is refused on the way out",
            _raises(lambda: save_profile(pp, operator, float("nan"),
                                        operating_point=point,
                                        sittings=[{}, {}]), SystemExit),
        )
        for bad, label in ((float("nan"), "NaN"), (2.0, "above +1"),
                           (-3.0, "below -1")):
            broken = json.loads(pp.read_text())
            broken["threshold"] = bad
            bp = Path(tmp) / f"bad-{label.replace(' ', '-')}.json"
            bp.write_text(json.dumps(broken))
            check(
                f"and a threshold {label} is refused on the way in",
                _raises(lambda p=bp: load_profile(p), SystemExit),
            )
        hollow_centroid = json.loads(pp.read_text())
        hollow_centroid["centroid"] = [float("nan")] * _DIM
        hc = Path(tmp) / "nan-centroid.json"
        hc.write_text(json.dumps(hollow_centroid))
        check(
            "a centroid of NaNs is refused, not normalised into one",
            _raises(lambda: load_profile(hc), SystemExit),
        )
        check(
            "the profile's own digest travels with it, so a transcript can say "
            "which voiceprint gated it",
            len(load_profile(pp)[2]["_profile_sha256"]) == 64,
        )

    print("\n=== the enrolment contract ===\n")
    # Each of these wrote a production profile before the contract existed.
    def sitting_at(name: str, stamp: str | None) -> dict:
        return {"audio_sha256": name, "audio": f"/tmp/{name}.wav",
                "captured_at": stamp}

    two_ok = [sitting_at("aaa", "2026-07-20T09:00:00+0000"),
              sitting_at("bbb", "2026-07-22T14:00:00+0000")]
    plenty = [0.8] * 40
    other_ok = [0.2, 0.3]
    check(
        "material that meets the contract is accepted",
        not _raises(lambda: enforce_enrollment(two_ok, plenty, other_ok, 0.05, False),
                    SystemExit),
    )
    check(
        "the same recording passed twice is one sitting, not two — digests, not paths",
        _raises(lambda: enforce_enrollment(
            [sitting_at("aaa", "2026-07-20T09:00:00+0000"),
             sitting_at("aaa", "2026-07-20T09:00:00+0000")],
            plenty, other_ok, 0.05, False), SystemExit),
    )
    check(
        "one sitting is refused",
        _raises(lambda: enforce_enrollment(
            [sitting_at("aaa", "2026-07-20T09:00:00+0000")], plenty,
            other_ok, 0.05, False), SystemExit),
    )
    # The case that defeated the digest test: slice one recording and every chunk
    # has different bytes, a different digest, and the same capture window.
    chunks = [sitting_at("chunk-a", "2026-07-20T09:00:00+0000"),
              sitting_at("chunk-b", "2026-07-20T09:00:00+0000")]
    check(
        "two CHUNKS of one recording are refused, though their digests differ — "
        "distinct bytes were never evidence of a distinct sitting",
        _raises(lambda: enforce_enrollment(chunks, plenty, other_ok, 0.05, False),
                SystemExit),
    )
    check(
        "and so are two takes from the same half-hour, which is the same thing "
        "with extra steps",
        _raises(lambda: enforce_enrollment(
            [sitting_at("aaa", "2026-07-20T09:00:00+0000"),
             sitting_at("bbb", "2026-07-20T09:25:00+0000")],
            plenty, other_ok, 0.05, False), SystemExit),
    )
    check(
        "material with no capture time is refused rather than assumed separate",
        _raises(lambda: enforce_enrollment(
            [sitting_at("aaa", None), sitting_at("bbb", None)],
            plenty, other_ok, 0.05, False), SystemExit),
    )
    check(
        "an unparseable capture time is refused rather than ignored",
        _raises(lambda: enforce_enrollment(
            [sitting_at("aaa", "last Tuesday"), sitting_at("bbb", "later")],
            plenty, other_ok, 0.05, False), SystemExit),
    )
    check(
        "order does not matter — the gap is between sorted neighbours",
        not _raises(lambda: enforce_enrollment(
            [sitting_at("bbb", "2026-07-22T14:00:00+0000"),
             sitting_at("aaa", "2026-07-20T09:00:00+0000")],
            plenty, other_ok, 0.05, False), SystemExit),
    )
    check(
        "no negative-speaker material is refused — that is a rejection rate, not a gate",
        _raises(lambda: enforce_enrollment(two_ok, plenty, [], 0.05, False),
                SystemExit),
    )
    check(
        "too few held-out scores to express the target is refused",
        _raises(lambda: enforce_enrollment(two_ok, [0.8] * 19, other_ok, 0.05, False),
                SystemExit),
        f"19 scores against the {min_resolvable(0.05)} a 5% target needs",
    )
    check(
        "and the floor tracks the target rather than being a constant",
        (min_resolvable(0.05), min_resolvable(0.20), min_resolvable(0.01))
        == (20, 5, 100),
    )
    check(
        "a looser target makes the same thin sample sufficient",
        not _raises(lambda: enforce_enrollment(two_ok, [0.8] * 19, other_ok, 0.20,
                                              False), SystemExit),
    )
    check(
        "--experimental writes it anyway, which is what keeps the override visible",
        not _raises(lambda: enforce_enrollment(
            [sitting_at("aaa", None)], [0.8] * 4, [], 0.05, True), SystemExit),
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


def _embed_pair(pair: list[Path], embed, leg: str = "mic") -> tuple[list, list, dict]:
    """Embed one (segments, audio) recording and return its provenance with it."""
    seg_p, wav_p = Path(pair[0]), Path(pair[1])
    segs = load_segments(seg_p, wav_p, leg)
    emb = [e for e in embed_segments(load_wav(wav_p), segs, embed) if e is not None]
    dur = [s["end"] - s["start"] for s in segs if s["end"] - s["start"] >= MIN_SCORABLE_S]
    return emb, dur, {
        "segments": str(seg_p), "audio": str(wav_p),
        "audio_sha256": ab.sha256(wav_p), "audio_samples": _wav_samples(wav_p),
        "captured_at": json.loads(seg_p.read_text()).get("captured_at"),
        "scorable_segments": len(emb), "scorable_seconds": round(sum(dur), 1),
    }


def run_calibrate(args) -> int:
    """Turn recordings of the operator into the threshold this file cannot assume.

    Repeatable, because one sitting is not enough and the file says why: a
    threshold from a single recording sat above the honest one in all nine
    comparisons available, which drops more of the operator than its target asks.
    With two or more sittings the operator's distribution is measured
    leave-one-*sitting*-out, so the profile judging each segment has real time
    between it and the material it was built from — the condition production
    meets. With one, it falls back to leave-one-segment-out and says the number
    carries a bias in the harmful direction.

    `--against` supplies speech known not to be the operator and prices each
    operating point in what it would admit of it.
    """
    embed = load_encoder(args.model_dir)

    sittings, manifest = [], []
    for pair in args.calibrate:
        emb, dur, prov = _embed_pair(pair, embed)
        # One more than enrollment needs: a leave-one-out pass enrols on n-1, so
        # guarding at the enrollment minimum lets a three-segment recording
        # through and fails inside the loop instead, on the one path this module
        # exists to serve.
        if len(emb) <= MIN_ENROLL_SEGMENTS:
            raise SystemExit(
                f"{pair[1]}: only {len(emb)} segments reach {MIN_SCORABLE_S}s — at "
                f"least {MIN_ENROLL_SEGMENTS + 1} are needed to score any one of "
                f"them against the rest")
        sittings.append((emb, dur))
        manifest.append(prov)

    op_emb = [e for s in sittings for e in s[0]]
    op_dur = [d for s in sittings for d in s[1]]
    profile = enroll(op_emb, op_dur)

    multi = len(sittings) >= 2
    own = (leave_one_sitting_out_scores(sittings) if multi
           else leave_one_out_scores(op_emb, op_dur))
    held = "leave-one-sitting-out" if multi else "leave-one-out, single sitting"

    print("\n=== profile ===\n")
    print(f"  {profile.n_enrolled} segments, {profile.seconds:.0f}s, "
          f"{profile.n_excluded} excluded by the trim")
    print(f"  {len(sittings)} sitting(s): "
          f"{', '.join(str(p['scorable_segments']) for p in manifest)} scorable segments")
    print(f"  cohesion {profile.cohesion:.3f} ± {profile.spread:.3f}")
    print(f"  own scores: mean {np.mean(own):.3f}, p5 {np.percentile(own, 5):.3f} "
          f"({held}, n={len(own)})")

    other: list[float] = []
    for pair in args.against or []:
        seg_p, wav_p = Path(pair[0]), Path(pair[1])
        other.extend(
            score(profile, e)
            for e in embed_segments(load_wav(wav_p),
                                    load_segments(seg_p, wav_p), embed)
            if e is not None)
    if other:
        print(f"  other-speaker scores: mean {np.mean(other):.3f}, "
              f"p95 {np.percentile(other, 95):.3f} (n={len(other)})")

    print("\n=== operating points ===\n")
    print(f"  {'operator dropped':>16}  {'threshold':>9}  {'room admitted':>13}")
    points = {}
    for target in (0.01, 0.02, 0.05, 0.10, 0.20):
        c = calibrate(own, target, other or None)
        points[target] = c
        far = "—" if c["false_admit_rate"] is None else f"{c['false_admit_rate']:.1%}"
        print(f"  {target:>15.0%}  {c['threshold']:>9.3f}  {far:>13}")
    if not other:
        print("\n  no --against material, so nothing states what these thresholds cost.\n"
              "  A threshold chosen without it is a rejection rate, not a gate.")
    if len(own) < 30:
        print(f"\n  n={len(own)} is thin for a quantile — read the low targets as indicative.")
    if not multi:
        print("\n  ONE SITTING. These scores carry no time between the profile and what\n"
              "  it judges. On labelled material that ran too strict in every comparison\n"
              "  available, by 0.006 to 0.181, so this threshold drops more of the\n"
              "  operator than its target asks. Record another sitting and pass a second\n"
              "  --calibrate pair.")

    if args.enroll_out:
        if args.target_frr is None:
            raise SystemExit(
                "--enroll-out needs --target-frr: the file carries one threshold, and "
                "which operating point it is has to be a choice on the record rather "
                "than a default this module picked.")
        _finite("--target-frr", args.target_frr, 0.0, 1.0)
        enforce_enrollment(manifest, own, other, args.target_frr, args.experimental)
        chosen = calibrate(own, args.target_frr, other or None)
        chosen["held_out"] = held
        chosen["n_sittings"] = len(sittings)
        chosen["experimental"] = bool(args.experimental)
        save_profile(args.enroll_out, profile, chosen["threshold"],
                     operating_point=chosen, sittings=manifest)
        mark = "  EXPERIMENTAL — " if args.experimental else "  "
        print(f"\n{mark}wrote {args.enroll_out} — threshold "
              f"{chosen['threshold']:.3f} at {args.target_frr:.0%} operator-dropped, "
              f"{len(sittings)} sitting(s), {len(own)} held-out scores")
    return 0


# A judgement, and labelled as one rather than dressed up as a measurement. The
# evidence that single-sitting thresholds run over-tight came from labelled corpora
# with real time between enrolment and test; it puts no number on how much time is
# enough. An hour is the smallest gap where "a different sitting" is plausibly true
# of a room, a seating position, a gain setting and a voice. A different day is
# better and is what the README asks for.
MIN_SITTING_GAP_S = 3600


def _sitting_problems(manifest: list[dict]) -> list[str]:
    """Whether these recordings are really from separate sittings.

    Distinct audio digests were the original test and they are not sufficient:
    slicing one recording into chunks produces distinct digests for every chunk
    while carrying none of the session-to-session variation the plural exists for —
    same room, same gain, same position, same voice, same minute. The check passed
    and the profile was worse than one honest sitting, because a threshold measured
    leave-one-*sitting*-out across fabricated sittings claims cross-session evidence
    it does not have.

    A capture window is the fact that separates the two cases, so `write_leg_segments`
    records one and this reads it. Chunks of one recording share it.

    Material with no `captured_at` predates that field and cannot be checked either
    way. It is refused rather than assumed good, because the failure it would hide —
    a threshold that deletes the operator from his own meeting — is worse than the
    inconvenience of re-recording. `--experimental` accepts it and marks the profile.
    """
    import datetime as dt

    stamps = []
    for m in manifest:
        raw = m.get("captured_at")
        if not raw:
            return [(f"{m['audio']} does not record when it was captured, so nothing "
                     f"establishes it as a separate sitting from the others. "
                     f"Recordings made before that field existed cannot be checked; "
                     f"re-record, or pass --experimental.")]
        try:
            stamps.append((dt.datetime.fromisoformat(raw), m))
        except ValueError:
            return [(f"{m['audio']} records captured_at {raw!r}, which is not a "
                     f"timestamp this can compare.")]

    stamps.sort(key=lambda s: s[0])
    out = []
    for (t1, m1), (t2, m2) in pairwise(stamps):
        gap = (t2 - t1).total_seconds()
        if gap < MIN_SITTING_GAP_S:
            out.append(
                f"{Path(m1['audio']).name} and {Path(m2['audio']).name} were captured "
                f"{gap / 60:.0f} minutes apart"
                + (" — the same capture window, so these are pieces of one recording "
                   "rather than two sittings" if gap == 0 else "")
                + f". Separate sittings means at least {MIN_SITTING_GAP_S // 3600}h "
                  f"apart, and a different day is what the measured bias is about.")
    return out


def enforce_enrollment(manifest: list[dict], own: list[float],
                       other: list[float], target_frr: float,
                       experimental: bool) -> None:
    """Refuse to write a profile the material cannot support.

    Everything below was documented as required and enforced by nothing, which is
    the gap between a README and a contract. Each of these produced a profile that
    looked exactly like a good one:

      * **One sitting.** Measurably over-tight, in the direction that deletes the
        operator, and the file recorded `n_sittings: 1` where nothing read it.
      * **The same recording passed twice.** Counted as two sittings and reported as
        two. Caught by this project's own smoke test doing precisely that by
        accident — two `--calibrate` pairs pointing at one file, printed as
        "2 sitting(s)", with none of the session diversity that plural is for. Audio
        digests, not paths: a copy under another name is the same sitting.
      * **No negative-speaker material.** `--calibrate` already prints that a
        threshold without it "is a rejection rate, not a gate", then wrote one.
      * **Too few held-out scores to express the operating point.** A 5% target
        needs 20 observations before any of them is the 5th percentile.

    `--experimental` allows all of it and is recorded in the profile, so a run
    gated by one says so rather than reading as a measured configuration. That is
    the point of an override: not to weaken the rule, but to keep the weakening
    visible downstream.
    """
    digests = {m["audio_sha256"] for m in manifest}
    problems = []
    if len(digests) < 2:
        problems.append(
            f"{len(manifest)} --calibrate pair(s) but only {len(digests)} distinct "
            f"recording(s). A threshold needs material from separate sittings; the "
            f"same audio twice carries none of the session variation that is for."
            + (" The two pairs point at the same file."
               if len(manifest) > 1 else ""))
    problems.extend(_sitting_problems(manifest))
    floor = min_resolvable(target_frr)
    if len(own) < floor:
        problems.append(
            f"{len(own)} held-out scores cannot express a {target_frr:.0%} "
            f"false-reject rate — that needs at least {floor}, or the quantile is an "
            f"interpolation between neighbours rather than a measured rate. Record "
            f"longer sittings or ask for a looser target.")
    if not other:
        problems.append(
            "no --against material, so nothing states what this threshold admits of "
            "a voice that is not the operator. That is a rejection rate, not a gate.")
    if problems and not experimental:
        raise SystemExit(
            "\n  refusing to write this profile:\n"
            + "".join(f"\n    - {p}" for p in problems)
            + "\n\n  Pass --experimental to write it anyway. The profile will record "
              "that it is experimental and every capture gated by it will say so.")
    if problems:
        # Named, not waved through. An override that prints nothing is
        # indistinguishable from material that met the contract.
        print("\n  EXPERIMENTAL — written past the contract on:"
              + "".join(f"\n    - {p}" for p in problems))
    # Only where the floor was actually cleared. Under an override the sample can be
    # below the floor, and "clears the 20 needed" printed over 4 scores is worse
    # than silence — it reports a passed check that failed.
    if floor <= len(own) < THIN_HELD_OUT:
        print(f"\n  THIN: {len(own)} held-out scores clears the {floor} needed to "
              f"express {target_frr:.0%}, but a sample quantile is still soft below "
              f"{THIN_HELD_OUT}. The threshold is real; treat its third decimal as "
              f"noise.")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--self-test", action="store_true",
                   help="run the enrollment, gating and reporting controls")
    p.add_argument("--calibrate", nargs=2, metavar=("SEGMENTS.json", "AUDIO.wav"),
                   type=Path, action="append",
                   help="operator speech captured on the microphone leg it will "
                        "gate. Repeat for each sitting — one sitting yields a "
                        "measurably over-tight threshold")
    p.add_argument("--against", nargs=2, metavar=("SEGMENTS.json", "AUDIO.wav"),
                   type=Path, action="append",
                   help="speech known not to be the operator, to price each "
                        "threshold. Repeatable")
    p.add_argument("--enroll-out", type=Path,
                   help="write the voiceprint and its threshold here, for "
                        "dual_capture.py --voiceprint. Cannot be inside the "
                        "repository: a centroid identifies a person")
    p.add_argument("--target-frr", type=float,
                   help="the operating point to persist: the fraction of the "
                        "operator's own speech the threshold may drop. Required "
                        "with --enroll-out, and deliberately has no default")
    p.add_argument("--experimental", action="store_true",
                   help="write a profile the material does not support — one "
                        "sitting, duplicate audio, no --against, or too few scores "
                        "for the target. Recorded in the profile, and every capture "
                        "gated by it says so")
    p.add_argument("--model-dir", type=Path, default=Path.home() / ".cache" / "speaker-gate",
                   help="where the ECAPA checkpoint is cached")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()
    if args.enroll_out and ab.inside_repo(args.enroll_out):
        # The same refusal the transcript artifacts carry, for a stronger reason.
        # A transcript is a record of what was said; a centroid is a measurement of
        # who was speaking, usable to recognise the same voice in other audio. This
        # repository is public, and 197 lines of household speech reached it once
        # already — closed in the tool then, and closed in the tool here, because
        # .gitignore only covers the paths somebody thought of in advance.
        p.error(f"--enroll-out {args.enroll_out} is inside the repository. A "
                f"voiceprint identifies a person. Write it to your home directory.")
    if args.calibrate:
        return run_calibrate(args)
    p.error("nothing to do: pass --self-test or --calibrate")
    return 2


if __name__ == "__main__":
    sys.exit(main())
