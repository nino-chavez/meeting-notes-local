# Three protocol takes: what a static linear canceller does as the far end changes

Run 2026-07-31 on one machine, one room, one seat, one system volume, in a
single afternoon. Three `--protocol` takes, each with its own far-end source.
Written as a standalone note because it answers a question `RESULTS.md` leaves
open — whether the offline linear condition holds up on material it was not
chosen for — and should be folded into that document rather than kept apart.

The short version: **the echo-cancellation case for AEC3 is now made, and it is
made by the takes that failed.** The operator-recovery claim is not made, and
three more takes will not make it, because the instrument cannot measure it
under the condition it exists to study.

---

## What was run

`dual_capture.py --protocol`, laptop speakers, built-in microphone, the same
seat and the same system volume throughout. Only the far-end recording changed.

| | far-end source | pairs | control length |
|---|---|---|---|
| take 1 | operator's own screencast | 5 | 6 s |
| take 2 | a screencast, loudness-maximised | 8 | 16 s |
| take 3 | a broadcast talk-show interview | 8 | 16 s |

Take 1 ran before `CONTROL_S` was raised and scored no control segments at all;
that defect and its fix are described in the commit that raised it.

Scored with:

```sh
python spike/aec_bound.py \
  --take proto=<capture-dir> --take clean=<headphone-capture-dir> --enroll clean \
  --protocol proto=<capture-dir>/protocol.json \
  --segments proto=<capture-dir>/mic-segments.json \
  --fit-mode prefix --fit-before 34 --score-after 37
```

The operator profile was enrolled from a separate headphone capture — 11
segments, 81 s — so no take scores against a profile built from itself. That
capture is private meeting audio and nothing from its content appears here.

---

## The measurements

Operator-to-echo is computed at the microphone, not at the speaker: mean level
inside the speak intervals against mean level inside the control intervals,
which hold the same echo with nobody talking over it.

| | far end at the tap | operator/echo at the mic | linear | masked | echo-only audio |
|---|---|---|---|---|---|
| take 1 | rms 0.064, peak 0.943 | **+3.5 dB** | **+4.5 dB** | **+9.8 dB** | 14.3 s |
| take 2 | rms 0.138, peak 1.000 | −0.9 dB | +0.7 dB | +4.3 dB | 85.4 s |
| take 3 | rms 0.111, peak 0.970 | +1.0 dB | **−0.3 dB** | +2.8 dB | 92.3 s |

`linear` and `masked` are echo-only suppression measured across the control
intervals. A negative figure means the filter left more residual than it removed.

---

## The far end's loudness was not the operator's doing

Take 2's source is a hot master: 17.2 dB crest factor against take 1's 23.4 dB,
and 42 samples pinned at full scale where take 1 had none. Same system volume,
roughly twice the energy leaving the speakers. This is worth stating plainly
because the first reading of these numbers blamed the operator for turning the
volume up, and he had not.

It matters beyond attribution. If source mastering alone moves the operator from
3.5 dB above the echo to 0.9 dB below it, then playback level is not a setting a
product can ask the operator to manage. It is a property of whoever is on the
other end of the call and what they are playing.

---

## A static fit does not generalise, and the failure is not only about level

Take 3 was **quieter at the tap than take 2 and suppressed less** — −0.3 dB
against +0.7 dB. Level alone does not order these results.

What separates take 3 is content. A broadcast interview has several speakers,
audience laughter, music stings and abrupt dynamics; the two screencasts are one
voice at a near-constant level. A filter fit on 34 seconds of calibration and
frozen cannot follow that, and the mask built from its estimate inherits the
error.

This is the result worth carrying into an AEC3 decision. AEC3 adapts
continuously, tracks delay and drift, detects double-talk, and derives
suppression from running statistics. The offline condition has none of those,
and on the most ordinary far-end material of the three it went negative. The
question "does AEC3 earn its dependency" is answered by the material, not by
argument about the algorithm.

`RESULTS.md` already says the offline condition is not a bound on AEC3 in either
direction. These takes are consistent with that and sharpen it: the offline
condition is weakest exactly where a product needs cancellation most.

---

## The negative control works, and it is the one thing that got better

With `CONTROL_S` at 16 s and a far end that is not the operator's own voice:

| | control segments | admitted at +0.580 | mean |
|---|---|---|---|
| take 2 | 20 | **0** | +0.090 |
| take 3 | 18 | **0** | +0.146 |

Zero admissions across 38 segments of far-end-only audio. The gate does not
mistake the far end for the operator, which is the property the control exists
to establish. Take 1 could not show this at all: 0 of 5 control intervals
contained a whole segment, and its far end was the operator's own recorded
voice, which cannot serve as a negative control in any case.

---

## The operator claim cannot be closed with this instrument

Cue phrases were transcribed in 4 of 5 speak intervals on take 1, and **0 of 8**
on takes 2 and 3. Take 3 produced no attributable operator segment at all.

This is not a compliance failure. The operator read; fragments of the passages
appear in the transcript. The verification requires those passages to be
transcribed *from the microphone leg*, and that leg is dominated by echo, so the
recogniser transcribes the far end instead. Passage words surface only between
the far end's own sentences.

The mechanism fails precisely when the condition under study is present. The
existing note that echo-contaminated speech transcribes badly, so a
non-matching segment is unverified rather than silent, understates it: at
realistic levels *nearly every* segment becomes unverified, and the protocol
stops producing evidence rather than producing weak evidence.

`aec_bound` reaches the same conclusion from its own side and says so in its
output — closing the gap needs a near-end channel.

### What would close it

A third recorded channel: a close microphone on the operator, capturing him
while the built-in microphone captures the contaminated version. That supplies
ground truth about when he spoke and what he said, independent of the leg being
measured, and it is the only thing here that does. `dual_capture` takes one
`--input-device` today, so this is a capture-path change rather than a flag.

Until then, operator-recovery figures on speakers should be reported as
inconclusive rather than as low.

---

## One incidental finding, unrelated to echo

Scoring the clean headphone capture against a profile enrolled from that same
capture admitted **1 of 7 segments, mean +0.507**, against the +0.580 threshold
and the +0.864 `RESULTS.md` reports for clean operator audio.

That take has no echo in it — bleed measured `positive_r: 0.0` across 160 s. So
this is not contamination. Real-meeting audio on the built-in microphone simply
sits far below the controlled captures the threshold was calibrated on, which is
the "embedding degrades by half on the leg that needs it" result appearing in a
place nobody was looking. A threshold set on controlled material may not transfer
to meetings at all, independent of speakers, echo, or the room.

---

## What this changes

- The AEC3 integration has a measured case, and it does not depend on the
  operator claim: a static linear fit returns +4.5 dB on favourable material and
  −0.3 dB on ordinary material.
- Playback level is not an operator-managed variable. Source mastering moves it
  4 dB on its own.
- Operator recovery on speakers is unmeasured, not measured-and-poor. Saying
  otherwise would repeat the class of error this document's predecessors were
  corrected for.
- The negative control is sound and can be relied on: 0 of 38 far-end segments
  admitted as the operator.
