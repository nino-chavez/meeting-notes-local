# Three protocol takes: reported observations and the missing receipt

Status: **candidate evidence from another Mac, not independently re-derived in
this checkout**.

Three `dual_capture.py --protocol` takes were run on 2026-07-31 on one machine,
in one room and seat, at one system-volume setting. Only the far-end source was
intentionally changed. The source captures remain private and are not in Git.

The reported aggregate figures are preserved below because they identify useful
next experiments. The run did not persist the bounded `aec_bound.py --out`
artifact needed to bind those figures to input, protocol, harness, and encoder
digests. This checkout therefore cannot independently reproduce or confirm the
measurements. Nothing in this note is a release or model-admission receipt.

`spike/RESULTS.md` is frozen. This note remains a standalone appendix until a
redacted receipt exists; actual real-canceller evidence belongs with
`spike/aec3/README.md`.

## What was reported

The runs used laptop speakers and the built-in microphone. Take 1 used the old
six-second control interval. Takes 2 and 3 reportedly used sixteen-second
controls and a far end that was not the operator's voice.

| take | far-end source class | pairs | control |
|---|---|---:|---:|
| 1 | single-voice screencast | 5 | 6 s |
| 2 | loudness-maximised screencast | 8 | 16 s |
| 3 | broadcast talk-show interview | 8 | 16 s |

The reported scoring command was equivalent to:

```sh
python spike/aec_bound.py \
  --take proto=<private-capture-dir> \
  --take clean=<private-headphone-capture-dir> \
  --enroll clean \
  --protocol proto=<private-capture-dir>/protocol.json \
  --segments proto=<private-capture-dir>/mic-segments.json \
  --fit-mode prefix --fit-before 34 --score-after 37
```

The operator profile for the protocol takes was reportedly enrolled from a
separate private headphone capture. No transcript text, cue response, path, or
audio from any private capture appears here.

## Reported aggregate measurements

Operator-to-echo is described as microphone level in speak intervals relative
to microphone level in silent-control intervals. `linear` and `masked` are
reported echo-only suppression over control intervals. A negative suppression
figure means the output residual was larger than the input echo for that score.

| take | tap RMS | tap peak | operator/echo at mic | linear | masked | echo-only audio |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.064 | 0.943 | +3.5 dB | +4.5 dB | +9.8 dB | 14.3 s |
| 2 | 0.138 | 1.000 | -0.9 dB | +0.7 dB | +4.3 dB | 85.4 s |
| 3 | 0.111 | 0.970 | +1.0 dB | -0.3 dB | +2.8 dB | 92.3 s |

These rows are a transcription of the other machine's report. They are not
machine-verifiable evidence until the receipt described below is produced.

## Bounded observations

### Static suppression varied across the three sources

The reported linear score ranged from +4.5 dB to -0.3 dB. Take 3 had lower tap
RMS than take 2 and also lower reported suppression, so tap RMS alone does not
order these three outcomes.

The sources changed together in loudness, spectrum, words, speaker count, and
dynamics, and each take fitted its own prefix. These runs therefore do **not**
show which source property caused the difference. They also neither validate nor
reject AEC3. The repository's executable contract is explicit that an offline
static filter is not a bound on AEC3 in either direction.

The safe consequence is narrower: the reported variation motivates testing the
actual continuously adapting AEC3 path on held-out material. It does not by
itself earn that dependency or establish product readiness.

### Playback source level was not controlled by one volume setting

Take 2 reportedly had 0.138 RMS at the tap, versus 0.064 for take 1: 2.16 times
the RMS amplitude. Its reported crest factor was 17.2 dB versus 23.4 dB, with 42
full-scale samples versus none. Those aggregates are consistent with differently
mastered sources producing materially different digital levels at the same
system-volume setting.

They do not isolate a four-decibel causal effect on operator-to-echo ratio,
because operator vocal level and the other source properties were not separately
controlled.

### No false admission was reported in this narrow control sample

Takes 2 and 3 reportedly yielded 20 and 18 control segments. At the fixed
+0.580 threshold, 0 of those 38 far-end segments were admitted as the operator;
reported mean scores were +0.090 and +0.146.

That is an observation about this tested sample, conditional on adherence to the
silent cues. The protocol cannot independently prove operator silence in a
control interval, and the two takes share one operator, profile, machine, room,
session, and threshold. This is not a false-admission rate and does not establish
that the negative control can be relied on outside the tested sample.

### Operator recovery remained inconclusive

Cue passages were reportedly detected in 4 of 5 speak intervals on take 1 and
0 of 8 on each later take. Fragments reportedly appeared in the microphone
transcript, but echo dominated the same leg used to decide whether the operator
spoke. The instrument therefore fails to label many of the segments under the
condition it is meant to study.

Those runs support an **inconclusive** operator-recovery verdict, not a low one.
Closing the gap requires a separate near-end observation channel, such as a
close microphone used only to label when the operator spoke while the built-in
microphone records the contaminated signal.

### The clean-capture score is an exploratory anomaly

A clean headphone capture reportedly scored 1 admitted segment out of 7 with a
mean of +0.507 against the +0.580 threshold. That run used the same capture for
enrollment and scoring and did not supply matched segment annotations. The
+0.864 value in `RESULTS.md` comes from a different synthetic level-sweep setup.

The figures are not like-for-like. Preserve the discrepancy as a reason to run a
held-out, matched-segment threshold-transfer test; do not use it to claim that
the production threshold fails on meetings.

## Receipt required before promotion

Repeat or re-score the takes with `aec_bound.py --out` to a private path outside
the repository. From that private artifact, derive a scrubbed public receipt
containing only:

- input audio, protocol, segment, harness, encoder, and profile digests;
- fixed command parameters and condition names;
- run verdicts, reason codes, counts, durations, and suppression aggregates;
- the exact derivation and code revision for RMS, peak, crest-factor, and
  full-scale-sample counts; and
- an explicit statement that all `text`, `heard`, `script`, local paths, and
  other speech-bearing fields were removed.

The scrubber needs its own fixture proving that sentinel transcript content and
paths cannot survive. Until that receipt is reviewed, these rows remain a useful
other-machine report rather than canonical measured evidence.

## What this changes now

- Keep the sixteen-second control as an empirically useful default, while
  preserving an inconclusive result when no complete segment lands inside it.
- Prioritize an actual AEC3 capture-path trial over more static-filter takes.
- Add a separate near-end label channel before claiming operator recovery on
  speakers.
- Treat the 0-of-38 control result and the +0.507 clean score as narrow
  observations, not population or threshold conclusions.
