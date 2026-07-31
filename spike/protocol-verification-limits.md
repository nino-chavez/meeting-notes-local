# What three incidental protocol takes report, and what they cannot establish

Status: **candidate evidence from another Mac, not independently re-derived in
this checkout**.

Three `dual_capture.py --protocol` takes were run on 2026-07-31 while bringing a
second machine up for interaction capture. They used laptop speakers, the
built-in microphone, one room, one seat, and one system-volume setting. Each
used a different far-end recording, so content, spectrum, dynamics, and digital
level changed together.

The source captures are private and are not in Git. The run also did not persist
the bounded `aec_bound.py --out` artifact that would bind aggregate results to
input, protocol, harness, and encoder digests. The observations below are
preserved because they identify useful next checks, but this checkout cannot
independently confirm their numerical values. Nothing here is a release,
voice-gate, or model-admission receipt.

These takes are not a level experiment. `sweep.py --playback` is the existing
instrument for holding one source fixed across shuffled, replicated playback
levels. They also add no direct AEC3 evidence because AEC3 was not run on them.
The separate measured case for bounded AEC3 work remains in
[`aec3/README.md`](./aec3/README.md).

## 1. No false admission was reported in this narrow control sample

With sixteen-second controls and a far end that was not the operator's voice,
the other machine reported:

| take | control segments | admitted at +0.580 | mean score |
|---|---:|---:|---:|
| 2 | 20 | 0 | +0.090 |
| 3 | 18 | 0 | +0.146 |

That is 0 reported admissions across 38 far-end segments. It is a useful
observation about this sample, conditional on the operator following the silent
cues. The protocol cannot independently prove silence in a control interval,
and both takes share one operator, profile, threshold, machine, room, and
session. This is not a false-admission rate and does not establish that the gate
will reject unrelated voices in general.

The first take could not contribute to that observation. It scored no complete
control segment, and its far end was the operator's own recorded voice, which is
not a negative control for operator identity.

## 2. Six-second controls produced no scorable segment on the first take

The first take reportedly scored 0 control segments from 5 intervals. Its
longest microphone segments were 10.0, 10.0, 9.6, and 8.2 seconds. A six-second
control leaves a four-second interior after the one-second margin at each edge,
so those segments could not fit wholly inside it.

The segmenter is not aligned to cue boundaries. Raising the default control to
sixteen seconds produced scorable controls on the next two takes, and the
duration is now configurable with `--protocol-control-s`.

Sixteen seconds is an observed useful default, not a containment guarantee. The
transcriber promises no maximum segment duration, and unaligned segments can
still straddle both margins. A take with no contained control segment must remain
inconclusive; the protocol code and self-test preserve that boundary.

## 3. Passage-based admission verification failed where echo was strongest

Cue passages were reportedly detected in 4 of 5 speak intervals on the first
take and 0 of 8 on each later take. The report says passage fragments appeared
in the microphone transcript, but the same echo-contaminated microphone leg is
used to decide whether the operator spoke. When the recognizer transcribes the
far end instead, admission-based verification loses the label it needs.

That supports an **inconclusive** operator-recovery verdict for these takes, not
a low recovery rate and not a compliance failure. A separate close microphone
used only as a near-end label would close the measurement gap.

[`retention.py`](./retention.py) is the existing word-recovery instrument. It
scores fixed passage words without depending on voiceprint admission and already
produced the separate real-AEC3 results recorded in `aec3/README.md`. It was not
run into a digest-bound receipt for these three takes, so those prior percentages
must not be silently transferred to this sample.

## 4. The clean-capture score is an exploratory anomaly

A clean headphone capture reportedly admitted 1 of 7 segments with a mean score
of +0.507 against the +0.580 threshold. That capture was used for both enrollment
and scoring and did not supply matched segment annotations. The +0.864 comparison
value in `RESULTS.md` comes from a different synthetic level-sweep construction.

Those values are not like-for-like. Preserve the discrepancy as a reason to run
a held-out, matched-segment threshold-transfer check; do not use it to claim
that the production threshold fails on meetings.

## Receipt required before promotion

Repeat or re-score the private takes with `aec_bound.py --out` to a private path
outside the repository. From that artifact, derive a scrubbed receipt containing
only:

- input audio, protocol, segment, harness, encoder, and profile digests;
- fixed command parameters and condition names;
- verdicts, reason codes, counts, durations, and aggregate scores; and
- an explicit statement that all `text`, `heard`, `script`, local paths, and
  other speech-bearing fields were removed.

The scrubber needs a fixture proving that sentinel transcript content and paths
cannot survive. Until that receipt is reviewed, this file is an honest record of
what the other machine reported, not canonical measured evidence.

## Not established here

- A playback-level response; source content and level changed together.
- An AEC3 result; AEC3 was not run on these takes.
- Operator recovery on speakers; the admission instrument lost its labels.
- A general false-admission rate; the observed sample is narrow and cue
  adherence is assumed.
- Threshold transfer from controlled enrollment to real meetings.
