# What three incidental protocol takes establish, and what they cannot

Run 2026-07-31 while bringing a second machine up to run the interaction
capture. Three `--protocol` takes, laptop speakers, built-in microphone, one
room, one seat, one system volume.

**These takes are not a level experiment and nothing here should be quoted as
one.** Each used a different far-end recording, so content, spectrum and
loudness moved together — the same confound
[`aec3/README.md`](./aec3/README.md) already identifies in the 2026-07-29 sweep
and already designed the fix for. `sweep.py --playback` holds one asset fixed
across levels, `--replicates` separates a level effect from a take effect, and
`--shuffle` breaks the order confound. That is the experiment. This is not it.

Nor do these takes bear on whether AEC3 is worth integrating. That was answered
on 2026-07-29 at +32.9 dB echo-only and +25.3 dB on a real speaker take, against
the offline linear estimate's +3.5 dB. The offline estimate was never the
product; it was a bound, and it has served its purpose.

What follows is the residue that does not depend on any of that.

---

## 1. The negative control is sound

With `CONTROL_S` at 16 s and a far end that is not the operator's own voice:

| | control segments | admitted at +0.580 | mean |
|---|---|---|---|
| take 2 | 20 | **0** | +0.090 |
| take 3 | 18 | **0** | +0.146 |

**Zero admissions across 38 segments of far-end-only audio.** The gate does not
mistake the far end for the operator, at ratios from −0.9 dB to +1.0 dB
operator-to-echo, on two unrelated far-end recordings.

This is the property the control exists to establish and it had never been shown
before: the first take scored no control segments at all, and its far end was
the operator's own recorded voice, which cannot serve as a negative control at
any interval length.

## 2. A 6 s control interval yields nothing on speakers

The first take scored 0 control segments from 5 intervals. Its longest
microphone segments ran 10.0, 10.0, 9.6 and 8.2 s; a 6 s interval leaves 4 s
after `CUE_MARGIN_S` at each edge, and a 10 s segment does not fit in 4 s.

The original reasoning — 4 s "admits two segments at speaker_gate's 2 s floor" —
assumes segmentation lands inside the cue. It does not. The far end plays
continuously, so the microphone is voiced throughout and the segmenter emits long
spans that ignore cue edges; one ran 73.5–83.5 s, covering the end of a speak
interval and the whole control after it. A control interval has to exceed the
longest segment it must *contain*, not the shortest it *could*.

Fixed by raising `CONTROL_S` to 16 s and exposing `--protocol-control-s`.

## 3. Passage verification fails exactly where it is needed

Cue phrases were transcribed in 4 of 5 speak intervals on the first take and
**0 of 8** on both later ones.

This is not a compliance failure. The operator read, and passage fragments appear
in the transcripts. Verification requires those passages transcribed *from the
microphone leg*, and echo dominates that leg, so the recogniser transcribes the
far end instead — passage words surface only in the gaps between the far end's
own sentences.

The existing note that echo-contaminated speech transcribes badly, so a
non-matching segment is unverified rather than silent, understates the effect. At
realistic ratios *nearly every* segment becomes unverified, and the protocol
stops producing evidence rather than producing weak evidence. `aec_bound` says
the same from its own side: closing the gap needs a near-end channel.

Operator-recovery figures from a contaminated microphone alone should be reported
as inconclusive rather than as low.

**`retention.py` is the instrument that does work here**, and it is already
built: passage recall measured against a schedule fixed before the audio existed
is external ground truth that does not depend on the voiceprint admitting
anything. It found 0.0% raw recall against 80.5% far-end leakage where the
admission-based view could only say "inconclusive". Any future protocol take
should be scored that way first.

---

## Incidental, unrelated to echo

Scoring a clean headphone capture against a profile enrolled from that same
capture admitted **1 of 7 segments, mean +0.507**, against the +0.580 threshold
and the +0.864 reported for clean operator audio.

That capture has no echo in it — bleed measured `positive_r: 0.0` across 160 s of
real two-sided conversation. So this is not contamination. Real-meeting audio on
the built-in microphone sits far below the controlled captures the threshold was
calibrated on, which is the "embedding degrades by half on the leg that needs it"
result appearing where nobody was looking.

A threshold set on controlled material may not transfer to meetings at all,
independent of speakers, echo or the room. Worth a designed check before the gate
ships with a fixed threshold.

---

## Not established here

- Any level response. The takes are confounded; use `sweep.py --playback`.
- Anything about AEC3, in either direction. Not run on these takes.
- Operator recovery on speakers. The instrument cannot see it.
- That the far end is rejected *in general* — 38 segments, two recordings, one
  room, one voice, one microphone.
