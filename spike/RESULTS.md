# Spike results — dual-leg capture

Run 2026-07-28 on macOS 26.5.2, Apple Silicon, Swift 6.3.3.
Tool: [`dual_capture.py`](./dual_capture.py). Runs of 14 s, 22 s, and 75 min.

> **Status: frozen as of 2026-07-29. These findings are directional feasibility,
> not acceptance evidence.**
>
> The offline harness answered the question it was built for: echo removal
> materially improves voiceprint recognition over part of the operating range,
> which is enough to decide that a real canceller is worth building. It cannot
> establish that speaker mode is acceptable, and further sharpening of the
> instrument will not change that — the remaining limits are structural
> (no independent near-end labels; suppression measured on an oracle-free but
> offline path), not defects to file down.
>
> Nine rounds of review hardened the wording and the guards to the point where
> the harness refuses to publish a claim it cannot support. That was worth doing
> and it is done. The next evidence has to come from the product pipeline —
> AEC3 integrated, cancellation wired through segmentation into the voice gate,
> and transcript retention measured end to end across a real operating matrix.
> Everything below stands as recorded; nothing below is a GA gate.
>
> That work has started in [`aec3/`](./aec3/README.md), which is where the
> replacement figures live. Read it instead of this file for anything about the
> real canceller.

The spike existed to answer two questions the design documents could not.
**Both are now answered** — speaker bleed destroys the Me/Them split, and clock
drift is bounded well below anything the merge cares about. Playing a real
meeting through the capture to settle the second question turned up three
findings nobody was looking for, including a crash on the seam between the two
halves of the pipeline that meant it had never worked.

---

## Answered: speaker bleed destroys the Me/Them split

Peak envelope correlation between the microphone and system legs was **+0.928**
and **+0.927** across two runs — with the acoustic component (raw lag minus the
independently measured start skew) at **−25 ms**, which is the right order for a
speaker-to-microphone path.

The transcript shows what that correlation means in practice:

```
[00:00.00] Me   The quarterly numbers came in ahead of plan.
[00:00.36] Them The quarterly numbers came in ahead of plan.
[00:07.16] Me   We should move the launch date forward by two weeks.
[00:07.20] Them We should move the launch date forward by two weeks.
```

Every utterance appears **twice**, once per leg. This is worse than degraded
output — it is inverted. A single speaker on speakers produces a transcript that
reads like two people agreeing with each other verbatim, and an LLM summarising
it has no way to know that never happened.

**This is not a tuning problem.** The mic leg is a correct recording of the room,
and the room contains the far end. Three ways out, in order of cost:

1. **Headphones** — the split is clean by construction. Zero engineering.
2. **Detect and degrade** — measure bleed at capture start and, when it is high,
   stop claiming a split: label everything as one channel rather than fabricating
   a dialogue. Cheap, honest, and the correct default.
3. **Acoustic echo cancellation** — the real fix, and the expensive one. Neither
   Core Audio taps nor WASAPI loopback provide it; it would have to be
   implemented against the tap signal as the reference.

Option 2 is now a required product behaviour, not a nice-to-have — see the
`bleed-detected` state added to `docs/screens-and-states.md`.

**Narrowed since, by [`notes/EVAL.md`](../notes/EVAL.md).** "Worse than degraded
output" is true of the *transcript* and false of the *notes*. Feeding a
summarizer the same contamination — labels dropped, every line doubled — produced
notes at full topic coverage with a correct decision list, because summarization
discards repetition on its way to compressing. So bleed costs the speaker split
and nothing else. The product should stop claiming who spoke; it should not stop
writing the note.

**What was not tested:** a real meeting with a real second human on headphones.
The far end here was `say` through the speakers, which is the *worst* case by
design. The clean case still needs a live run.

---

## Answered since: clock drift is bounded, not measured

A 75-minute capture ran on 2026-07-28 with a 57.6-minute recorded meeting playing
through the default output. Both legs recorded the full span — 4499.8 s each,
72 000 000 samples on the system leg.

| Leg | Measured | Span |
|---|---|---|
| mic | 16000.061 Hz (+4 ± 44 ppm) | 4499.58 s |
| system | 15999.996 Hz (−0 ± 44 ppm) | 4499.80 s |

Relative drift **+4 ± 63 ppm** — inside its own error bars, so there is still no
drift *value*. What the run does produce is a *bound*: ±63 ppm is under **~230 ms
of divergence per hour** (derived from the measured ppm, not printed by the run).

**What that bound does and does not buy.** Reordering in the merge depends on the
gap between adjacent turns *across the two legs*, not on how long a turn runs —
two utterances 100 ms apart swap under 100 ms of slip however long they are. The
merged 75-minute capture gives the real distribution over 416 cross-leg
transitions:

| Gap between adjacent cross-leg turns | Share |
|---|---|
| under 230 ms | **7.2%** |
| under 500 ms | 17.1% |
| under 1 s | 30.5% |
| median | 1.9 s |

So the honest claim is narrower than "drift cannot reorder turns", which is what
this document said before the distribution was measured. Typical turn spacing
clears the bound by roughly 8x, and at the *measured* +4 ppm (≈14 ms/hour) almost
nothing is at risk — but at the worst divergence the bound still permits, about
7% of cross-leg transitions are close enough to swap, and that is at the end of
an hour where the accumulated slip is largest. Drift compensation is not urgent.
It is also not provably unnecessary.

(One caveat on that 7.2%: the mic leg in this run carried hallucinations and room
noise rather than a conversational partner, so the cross-leg gaps are not those
of a real two-person meeting. It is the only two-leg distribution available until
a live headphones run happens.)

**Scope this narrowly.** The microphone and the speakers are both built-in and
plausibly share a clock domain, so a near-zero result is the *expected* one. This
settles the same-device case only. The configuration where drift actually bites —
a USB interface or a Bluetooth headset on one leg and the internal clock on the
other — remains untested, and is the case worth measuring next.

**The ~67-minute figure below was wrong, and the tool now says ~94.** The relative
uncertainty carries both legs in quadrature, so each leg has to land a factor of
√2 tighter than the target for their difference to reach it. Sizing the run from a
single leg under-states the requirement by 41% — which is how a 75-minute capture
came back advising a 67-minute one. Resolution also scales with block period, not
just run length, so halving the block size buys the same tightening as doubling
the run.

---

## Superseded: the original drift non-result

The first run reported −1231 ppm of relative drift, which would be 4.4 seconds of
divergence per hour. **That number is meaningless and was discarded.**

Sample counts are exact, but the wall-clock span is not: each endpoint is known
only to within about one block period, because a block is timestamped when the
reader thread wakes, not when the hardware produced it. Over a 22-second capture
with 200 ms blocks the uncertainty is **± ~9 000 ppm**. The measured −1231 ppm
sits well inside it. The second run measured +1148 ± 20 504 ppm — a different
sign, same conclusion.

Resolving genuine hardware drift, which lives in the tens of ppm, requires the
span to be long enough that endpoint quantisation stops dominating:

| Capture span | Uncertainty |
|---|---|
| 22 s | ± 9 259 ppm |
| 10 min | ± 333 ppm |
| 60 min | ± 56 ppm |

**~67 minutes** to resolve 50 ppm — under-stated, see the correction above. The
tool prints its own error bars and refuses to project an hourly figure when the
reading is inside them.

---

## Playing a known meeting back through the capture

Every measurement in [`notes/EVAL.md`](../notes/EVAL.md) fed the summarizer a
transcript that arrived by some other route — a corpus file, a platform export,
or a recording decoded straight off disk. The capture path itself had never run
on real material. So a 57.6-minute meeting recording whose direct decode we
already had was played through the default output while both legs recorded.

System output was held at **volume 0** for the run. A Core Audio process tap
reads the rendered stream before hardware volume, so the tap is unaffected while
the room stays silent — verified on a 22-second probe first: tap RMS 0.099, mic
RMS 0.003, bleed −0.081. That makes a silent playback rig, and it is also the
reason muting is not a privacy control: **output volume does not protect audio
from a tap.**

### The capture path costs nothing

Transcribing the system leg alone and comparing it against the direct decode of
the same file holds the audio and the ASR model constant, leaving one variable:
the round-trip through the output device (16 kHz up to the device rate and back)
plus 200 ms block chunking.

| | units | words | mean | ≤3 words |
|---|---|---|---|---|
| direct decode | 769 | 8583 | 11.2 | 11% |
| through the capture | 691 | 8665 | 12.5 | 14% |

Across six reference commitments, the two transcripts contained **identical
counts** of the terms each commitment depends on — 3/7, 10/13, 3/6, 6/6, 10/12,
9/13 on both sides. Zero terms present in the direct decode were missing after
the capture. The resampling round-trip is not costing content.

### The handoff to the notes half had never once worked

The run crashed at its final step:

```
TypeError: Object of type float32 is not JSON serializable
```

`np.linalg.norm` returns a `float32`, so `r /= denom` in `bleed()` silently
converted every correlation back into one, and `json.dumps` refuses to encode it.
That value is `peak_r`, which `write_transcript` writes — so the capture failed to
hand anything to the notes half **on every capture where bleed was measurable at
all**, which is every real capture. Four and a half minutes of completed
transcription were discarded because the cheap step downstream of it failed.

Both halves of that are fixed: the conversion happens at the boundary in
`bleed()`, and the transcript is now written *before* the console output rather
than after it, so the expensive artifact lands first.

### A silent operator leg fabricates speech

The mic leg recorded an empty room for 75 minutes. Whisper did not return
nothing — it returned **400 turns**, against 787 real ones on the system leg. 182
of them fall after playback had ended, in pure silence. The single line
`"Thank you."` appears **92 times**, at 30-second intervals: one hallucinated
token per empty decode window. The system leg's own 17-minute silent tail did the
same thing 34 times, so this is a property of the decoder, not of one leg.

This inverts the bleed finding rather than repeating it. Bleed was the *dirty*
failure: legs correlated, split contaminated, and the capture correctly degrades
to `none`. This is the **clean** failure. Bleed measured −0.012, LOW — the state
the design tells you to aim for — so the capture keeps the labels, writes
`channel`, and hands the notes half 400 turns asserting the operator said things
they never said. The contract that looks safest is the one that fabricates.

### Fixed: gate segments on sustained voicing, not on energy

Raw energy does not separate confabulation from speech. A keyboard click clears
any peak threshold a hallucination fails, so a peak test removed 85% of the
confabulated turns only by discarding 11% of everything else — the wrong trade,
since silently dropping real speech is harder to notice than inventing it.

Sustained voicing separates them properly. Measuring what fraction of each
segment's span sits above the leg's own noise floor, across all 400 turns of that
capture:

| | median voiced fraction |
|---|---|
| the repeated confabulation | **0.01** |
| every other turn | **0.75** |

A 75x separation, wide enough that the exact cut point barely matters — which is
the sign of a feature measuring the right thing rather than a threshold tuned to
one recording. `drop_unvoiced()` keeps segments where at least 25% of the span
sits 8 dB above the leg's noise floor, with the floor estimated per leg because a
microphone in a quiet room and one beside a fan differ by more than any constant
survives. An absolute term handles what a percentile cannot: a tap on an idle
output device emits *exact* digital zero, and no multiplier lifts zero.

Re-running both legs of the 75-minute capture through it:

| | segments | `"Thank you."` | during the meeting | silent tail |
|---|---|---|---|---|
| system leg | 723 → 688 | 35 → **1** | 688 → **688** (8663 → **8663** words) | 34 → **0** |
| mic leg | 428 → 320 | 93 → **7** | 238 → 135 | 189 → 185 |

The system-leg row is the one that matters: **every fabrication in the silent
tail removed, and not one word of real meeting content touched.** A gate that
bought the first at the cost of the second would be worse than no gate.

The gate runs after transcription rather than before it. Gating first would save
the compute, but it decides what Whisper never sees, and that failure mode is
worse than the one it prevents.

Note what the mic leg's silent tail does *not* do: 185 of 189 turns survive. That
tail is not silent — it is a room with people in it, and those turns are backed by
real voiced audio. Which is the next finding, and no gate addresses it.

### Open: an open microphone records the room, not the operator

Not everything on the mic leg was hallucinated. Some of it was a real
conversation between other people in the house, transcribed cleanly and merged
into the meeting as `Me`. The voicing gate passes all of it, correctly — it asks
whether audio is behind a segment, and audio is. It never asks whether the audio
is the *meeting*.

**This is a correctness defect, not only a consent one**, and an earlier version
of this document filed it under consent alone, which was wrong. Two distinct
problems sit here:

1. **Consent.** People in the room are recorded without agreeing to it.
2. **Content.** Their speech enters the transcript labelled `Me` and reaches the
   notes as something a meeting participant said. The `channel` contract's entire
   premise is that one leg *is* the operator. A mic leg carrying other voices
   makes that premise false, exactly the way bleed does.

Bleed and room audio are the same defect approached from opposite sides, and the
capture already knows how to handle one of them: measure, and when the premise
fails, stop claiming the split. But degrading to `none` does not fix this one —
it drops the labels while leaving the foreign content in the transcript. The
pollution is in the words, not the attribution.

**Measured, because "it probably washes out" is what bleed taught us not to
assume.** Merging the gated legs over the meeting window gives 802 turns, of
which **114 turns and 966 words — 14.2% — are the room**, labelled `Me`. Running
the notes on that, against a control with the room turns removed and nothing else
changed:

- **Room content does not reach the notes.** Of 130 words the room contributed
  that the meeting never used, exactly two appear in the notes: "importance" and
  "such". No household subject matter survives compression.
- **But the notes change anyway, and deterministically.** Three repeat runs were
  byte-identical, so this is not sampling noise. With the room in: 3 action items
  and 4 decisions. With it out: 5 action items and 5 decisions, and an entirely
  different set of open questions.
- **Recall barely moves.** Hand-checked against the six reference commitments,
  the contaminated notes hit 3 and the clean notes hit 2 — and they are not the
  same 3 and 2. The contaminated run caught a commitment about a measurement plan
  that the clean run missed entirely; the clean run caught a document-sharing
  commitment in full where the contaminated run got half of it.

So the damage is not "your family's conversation appears in your meeting notes".
It is that **irrelevant input perturbs which real content survives compression**,
without changing how much of it does. On this meeting that is a wash. The
mechanism keeping it a wash is that the meeting outweighs the room ten to one in
word count — which is precisely what inverts in the case that matters: a short
or quiet meeting, an active room, or a long side conversation. One meeting, one
model, one ratio; the finding is the mechanism, not the 3-versus-2.

**The fix is speaker verification on the mic leg.** Enroll the operator's voice
once; keep the segments that match. It is the same architectural move as the
voicing gate, one level up — that gate asks "is this audio?", this one asks "is
this the operator?" — and it is an off-the-shelf capability (compact speaker
embeddings, running locally) rather than a research problem. It costs a model
dependency this project does not yet have, which is the real decision to make.

Worth noting what a system-leg-only capture at `none` looks like, because it
scored *best* of everything measured in [`notes/EVAL.md`](../notes/EVAL.md): it
is a good degraded mode and a bad product. It loses the operator's own speech,
which is why the mic leg exists at all — an online meeting's system audio
contains everyone except the person holding the microphone, so the notes come
back without a single thing *you* committed to. For a tool whose question is
"what did I agree to", that is not a reduced scope; it is the wrong answer
delivered confidently.

**So this is not an off-ramp.** Degrading to system-only is what the capture does
when it detects it cannot honour the split — a correctness behaviour, already
built. It is not the shape of the product, and the gate below is not optional
work that a smaller release could skip.

### The canonical pattern agrees, and it does not require an enrollment ritual

Speaker verification was named above as *our* fix before checking whether the
category had already settled the question. It has. Read at the vendors' own
documentation rather than from search summaries:

- **Microsoft Teams — voice isolation.** "Relies on the voice profile, stored on
  the user's local device, to remove any sounds or voices during a call or
  meeting that don't match the profile."
  ([admin doc](https://learn.microsoft.com/en-us/microsoftteams/voice-isolation))
- **Zoom — personalized audio isolation.** A voiceprint "generated automatically
  when you first speak in a meeting", "stored locally on the user's device until
  they delete it", with an optional read-aloud script to reinforce it.
  ([support KB0074698](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0074698))
- **Google Meet — noise cancellation.** Does *not* attempt it, and says so:
  "Voices from TV or people talking won't be canceled."
  ([support 9919960](https://support.google.com/meet/answer/9919960))

Two independent implementations landed on target-speaker extraction gated by an
enrolled voice profile; the third ships only non-speech denoising and documents
the gap. That is a canonical pattern, and it removes the question of whether the
approach is sound. What remains is only whether a local embedding model is worth
the dependency.

**The enrollment cost is smaller than this document assumed.** "Enroll the
operator's voice once" implied a setup screen. Neither vendor requires one.
Teams' `PassiveVoiceEnrollment` builds the profile "via their in-meeting speech"
and "typically takes a couple of meetings"; Zoom's automatic voiceprint is
generated from the first speech in a meeting with no user action at all. Applied
here, that means the profile is a centroid over embeddings of mic audio this
project *already records* — a background job over prior captures, not a feature
with a surface. The `single_source` runs are ideal enrollment material: one
speaker, known identity, minutes of it.

**Both vendors also state the failure mode, which we should copy rather than
rediscover.** Teams alerts when it detects that it is suppressing a speaker close
to the microphone and offers to disable isolation for that meeting — because a
colleague sitting next to you is indistinguishable from interference until you
decide which one they are. A verification gate that silently drops a co-located
participant is a worse defect than the contamination it replaces, since the
transcript then omits speech with no record that it did. Whatever we build
reports its rejections.

**Zoom names the headset as the substitute for a voiceprint**, not as a general
requirement: without a voiceprint recording the feature "works best with headset
microphones." That is the same trade this project faces, stated by a vendor that
measured it.

### What headphones actually fix here, and what they do not

These are two defects, not one, and headphones address only the first:

| | far end into the mic (bleed) | the room into the mic |
|---|---|---|
| symptom | their speech labelled `Me`, duplicated | strangers' speech labelled `Me` |
| headphones | **fix it** — no acoustic path | no effect |
| industry fix | acoustic echo cancellation | enrolled voiceprint |
| our state | measured, degrade-only | measured, unfixed |

For bleed we already hold something an echo canceller has to estimate: the
process tap **is** the far-end reference signal, clean, with the lag measured.
`bleed()` computes that cross-correlation today at whole-capture scale. A
per-segment version — drop mic segments that correlate with the tap at the known
lag — is a zero-dependency option that has not been priced against pulling in
AEC, and should be before either is chosen.

Apple's Voice Processing I/O is the obvious alternative and is **not** a flag we
can set: the mic leg is `sd.InputStream` (`dual_capture.py:218`), so it runs
through PortAudio, not through a voice-processing audio unit. Adopting it means
rewriting that leg in Core Audio. Note also that Apple documents its Voice
Isolation mic mode only as filtering "background sounds"
([Mac Help](https://support.apple.com/guide/mac-help/use-mic-modes-on-your-mac-mchle82b42f0/mac));
it does not claim to remove other people's speech, and we have not tested
whether it does.

### Answered: the gate works, and the operator sample changed three conclusions

Five 60–75 s captures of the operator on the built-in microphone, in the room the
household negatives were recorded in. This is the positive class that never
existed before, and it is what turns the threshold from a guess into a number.

**The gate separates cleanly.** Enrolled on unscripted speech, scored against the
197 household segments from the long capture:

| class | n | min | mean | max |
|---|---|---|---|---|
| operator, quiet room (leave-one-out) | 10 | +0.743 | +0.838 | +0.880 |
| operator, reading aloud | 14 | +0.431 | +0.648 | +0.749 |
| operator, music playing in the room | 11 | +0.533 | +0.632 | +0.737 |
| the household | 197 | −0.145 | +0.039 | +0.575 |

The worst quiet segment sits above the best household segment. **The earlier
"half strength" figure measured the harder problem** — room against room, every
speaker far-field. Operator against room, in the right channel, is roughly a
twentyfold margin.

**A read script transfers, which removes a subsystem from the build.** Enrolled
on phonetically-balanced sentences, unscripted speech scores +0.755 mean —
higher than the read take's own held-out scores. So a sixty-second setup step is
sufficient and the passive multi-meeting enrollment Teams ships is not required
here. Enrolling on unscripted speech is still better (complete separation rather
than one overlapping segment), so asking for both is the ideal; the cheap path
works.

**A threshold calibrated in a quiet room deletes the operator.** The obvious
rule — reject 2% of the operator's own speech — gives +0.749 on clean audio, and
that threshold discards *every* segment recorded with music playing:

| threshold | quiet | read aloud | with room music | household admitted |
|---|---|---|---|---|
| +0.749 | 90% | 7% | **0%** | 0.0% |
| +0.650 | 100% | 64% | 36% | 0.0% |
| **+0.580** | 100% | 79% | **91%** | **0.0%** |
| +0.530 | 100% | 86% | 100% | 1.0% |

**+0.580 is the operating point.** Ambient noise moves the embedding about as far
as changing speaking style does, so any enrollment flow that captures one clean
sample and calibrates from it builds this failure in. Enrollment has to span
conditions.

**Playing a recording of the operator is not the operator, and the gate is right
to say so.** The same voice through a speaker, room and microphone scores +0.36
to +0.56 against a profile that scores the live voice at +0.84 — a 0.3–0.5 drop
from channel alone. Audio of you playing in the room is not you participating in
a meeting, and a gate that accepted it would be the defect.

### Open: overlapping speech defeats the voiceprint, and no threshold fixes it

The case every real call contains — the operator talking *while* the far end
plays through speakers — is the one configuration the gate cannot handle. On a
capture with both live at once, 2 of 15 segments survived. Those fifteen are
voiced *microphone* segments, and with the far end on the speakers the
microphone is voiced whether or not the operator is talking, so some of them
hold no operator at all — an unlabelled outcome rather than a retention rate.
The table below does not have that problem: it mixes the far end
into the operator's own clean segments at known ratios, so every segment in it
is his by construction.

The mechanism is not a badly-set threshold. Mixing the actual far end into the
operator's own clean segments at known ratios:

| far end level | operator's mean score | kept at +0.580 |
|---|---|---|
| none | +0.864 | 100% |
| 0.25x | +0.711 | 80% |
| 0.50x | +0.476 | 30% |
| 0.75x | +0.361 | 10% |
| **1.00x** | **+0.266** | **0%** |

At equal loudness the operator's own voice scores +0.266, against +0.039 for a
stranger. The embedding is a blend, and it is genuinely no longer his — so
lowering the threshold to catch it would admit the household as well, since the
household's best segment is +0.575.

**This is a missing pipeline stage, not a tuning problem.** The project has bleed
*detection* — `drop_bled` discards segments that ARE the far end — and voiceprint
*gating*, which needs clean speech. It has no *cancellation*, and cancellation is
what turns a mixture back into clean speech. Teams and Zoom run echo cancellation
BEFORE voice isolation for exactly this reason; the order is not incidental.
Detection can only discard a contaminated segment. Cancellation recovers it.

The reference signal is already there and already time-aligned — the tap is the
far end exactly, with the lag measured — so the missing piece is the adaptive
filter, not the information it needs.

**Until that exists, the honest statement is narrower than "the gate works":** on
headphones there is no acoustic path, no mixture, and the gate separates as
measured above. On speakers, every moment the operator talks over the far end is
lost from the notes. That is what headphones now buy — not the room problem,
which the voiceprint solves, but the overlap problem, which it cannot.

### Corrections to the section above, from an external review

An independent review of the commit that first published these numbers found
four overstatements and three defects. The defects are fixed in the same change
as this note. The overstatements are corrected here rather than quietly edited,
because the original claims were pushed to a public repository.

**The quoted false-rejection rates were targets, not measurements.** `calibrate`
takes a *target* FRR and returns both the threshold and the `measured_frr` it
actually achieves; the table above quoted the target. With ten operator scores a
sample quantile cannot resolve 2% — every target at or below 10% lands on the
same place in the order statistics, and the measured rejection is **10%**, not
2%. The module was honest and the write-up was not.

**+0.580 is 0.005 above the strongest household segment.** That is not a margin,
it is a coincidence of this sample, and it was reported as an operating point
with the thinness relegated to a clause. Nothing should ship on it. It stands as
an experiment result.

**"Removes a subsystem from the build" was too strong.** Fourteen read segments
from one speaker support "a scripted seed is worth trying", not "passive
enrollment is unnecessary" — particularly when the same measurement concludes
that calibration must span conditions, which is an argument *for* continuing
adaptation, not against it.

**"Twentyfold margin" is not a meaningful way to report cosine separation.**
Ratios of cosine similarities have no operational meaning. The claim that
survives is held-out FAR/FRR, and at the sample sizes here (10 quiet, 14 read,
11 with music, one operator, one household, one day) even that is an estimate
with wide bars. Every conclusion above is single-subject.

**The recordings and the analysis harness are not retained in the repository.**
The audio is the operator's own voice and a household, so it cannot be committed,
but that leaves these numbers unreproducible from a clone — a real gap, and the
same reproducibility standard this project applies to its own claims.

### Three capture defects the review found, now fixed

**The bleed verdict condemned clean captures.** Attribution degraded on
`abs(peak_r) > 0.5`, while the code immediately above it explained that a
negative peak is turn-taking rather than an acoustic path. Two perfectly
complementary streams — one leg loud exactly when the other is silent, which is
what a *good* headphones capture looks like — give `peak_r = -0.994` and were
being stripped of every speaker label they had legitimately earned. All four
sites now test `positive_r`, and the reproduction confirms the reversal.

**A split sample corrupted everything after it.** The tap pipe reader discarded
an odd trailing byte. Pipes do not guarantee sample-aligned reads, and dropping
one byte shifts every subsequent sample by one, pairing each low byte with the
next high byte so the remainder of the capture decodes as noise. The byte is now
carried into the next read; verified across deliberately odd splits.

**Driver dropouts were discarded.** The microphone callback ignored
sounddevice's `status`, which is the hardware reporting that samples were lost —
the one event that leaves a leg's sample count looking healthy while its timeline
has a hole. Dropouts are now recorded with their offset and reported.

### What the review changes about the echo canceller

The previous section said the missing piece was "the adaptive filter, not the
information it needs". Both halves of that were wrong.

**The reference is not time-aligned yet.** The tap's Core Audio callback receives
a hardware timestamp and discards it; the Python side timestamps *pipe arrival*
instead, and the microphone callback ignored its `time_info` entirely. That is
adequate for merging a transcript, where the tolerance is a syllable. Echo
cancellation needs ordered frames near the hardware boundary, and the measured
start skew on these captures ran to 1.7 s.

**And an adaptive filter is not an echo canceller.** Production AEC needs delay
estimation, path-change handling, double-talk protection, residual-echo
estimation and suppression. WebRTC's AEC3 has all of them and is BSD-licensed.
Writing an NLMS filter here would be exactly the custom shape the workspace's
canonical-pattern-first rule exists to prevent — the vendor implementation is the
baseline, and this project has no disqualifier to name against it.

Apple's Voice Processing I/O is not the shortcut it appears to be either: it
requires both the input and output nodes to participate, and this application
does not own the conferencing app's playback.

So the next step is a feasibility spike, not production work: preserve hardware
timestamps and callback discontinuities, emit framed 10 ms streams, and run AEC3
offline against retained paired fixtures before changing any architecture. Judge
it on downstream outcomes — operator words retained, household false admits,
residual echo — not on filter convergence.

### Answered: echo removal recovers the operator on audio the filter never saw

That spike ran, and it did not need AEC3, WebRTC, or a line of Swift. The
question a real integration answers is "can *this* implementation do it"; the one
worth asking first is "is there anything here to recover", and that has a closed
form. The harness is [`aec_bound.py`](./aec_bound.py) — ten controls, every
parameter a named constant — and
[`aec-bound-results.json`](./aec-bound-results.json) holds all five experiments
below with per-window scores and SHA-256 digests of every recording and segment
list, so a figure here can be checked rather than taken.

**What is computed.** `linear` subtracts a least-squares FIR echo estimate.
`masked` then applies a Wiener-style time-frequency gain built from that same
estimate.

**What it is not.** An earlier version of this section called the mask an oracle
and the linear stage an upper bound on AEC3. Both were wrong. An oracle mask
needs the true isolated echo; this one is built from an *estimate* and inherits
its errors. And a static fit is no ceiling over AEC3, which adapts continuously,
tracks delay and drift, detects double-talk, and derives suppression from
statistics this harness never computes — on a moving path it can win outright.

#### The recordings cannot support a double-talk-free fit, and saying so cost the headline

The right way to fit an echo path is on audio where the far end plays and the
operator does not, because a filter fit during double-talk can reduce the
residual by cancelling *him*. The previous version of this document claimed
exactly that fit, and reported 3 of 16 windows admitted rising to 10.

The selector behind it failed open. When no double-talk-free stretch survived, it
returned every far-end-active stretch instead — the whole of the double-talk it
exists to exclude — and labelled the result double-talk-free. Made to fail
closed, it refuses both recordings:

| take | double-talk-free audio found | verdict |
|---|---|---|
| overlap | 0.00 s in 0 runs | refused |
| bleed | 1.02 s in 2 runs | refused, under the 4 s floor |

The takes do contain 8.4 s and 13.1 s of *echo-dominant frames* — frames where
the residual after a first-pass fit falls at least 6 dB below the estimated
echo. That is a classifier's judgement about audio in which the operator is
known to have been talking throughout, not an observation of him being silent,
and this document earlier described it as the latter. Those frames also arrive
scattered: the selector needs 400 ms consecutively and 4 s in total, and gets
neither. **The 10-of-16 figure is withdrawn**, along with the sentence calling
the fit double-talk-free.

#### What the material does support: held out in time

Fit on the first thirty seconds, then score only windows beginning at or after
thirty seconds — audio the filter never saw:

| take | raw | linear | masked | admitted |
|---|---|---|---|---|
| **overlap** | +0.326 | +0.535 | +0.615 | **1/7 → 5/7** |
| bleed | +0.101 | +0.152 | +0.442 | 0/8 → 1/8 |

**These are unlabelled outcomes, not measures of operator recall, and not
floors on it either.** The window selector takes voiced spans of the microphone,
and with the far end coming out of the speakers the microphone is voiced whether
or not the operator is talking. An unknown number of these fourteen windows hold
the far end alone.

An earlier version of this paragraph called the ratios a floor on recall, on the
reasoning that an echo-only window can only ever count as a miss. That is wrong,
and the paragraph conceded as much two sentences later without noticing the
contradiction: an echo-only window can be *admitted*, and then it enters the
numerator as well as the denominator. A floor requires every echo-only window to
be rejected, which is exactly what is not established. What these numbers report
is what the gate did on a window set of unknown composition. Nothing more.

The obvious way that could inflate was checked and does not settle it. After the
mask an echo-only window becomes near-silence, and a speaker embedding of
near-silence can score anywhere, so every window admitted after cancellation but
not before was measured against its take's own noise floor. The first version of
that check was itself broken — it estimated the floor from a percentile of
squared *samples*, which a waveform's zero crossings drag toward zero, so pure
noise scored 7.96 against its own "floor" and cleared the 3x guard by two and a
half times. Recomputed over 25 ms frames, where noise scores 1.05, the admitted
windows run **3.7 to 8.3 times the floor** rather than the 13 to 27 first
published. The recomputation weakened the evidence and it is stated at its new
strength. What survives is narrow: those windows are not empty. Whether what
fills them is the operator or residual echo, this cannot say — which is why the
recording protocol below had to change.

Seven windows. It was six of seven until the alignment leak below was closed —
estimating the delay over the whole take let audio after the boundary influence
the shift the fit was built on, and one window did not survive taking that away.
That is the honest size of the strongest claim available here,
and the claim is narrower than it first reads: **recovery generalised to later
audio.** Holding the waveform out stops the filter fitting the samples it is
scored on. It does not stop a fitted filter and mask from suppressing the
operator's voice in audio they never saw — components correlated with the
reference get removed wherever they occur. The room-noise control below, losing
two windows of fourteen against a reference unrelated to it, is that effect
measured directly. On the same take fit in-sample over the whole minute the
figure is 3/16 → 12/16, the optimistic reading, reported alongside rather than
instead — and an unlabelled outcome in the same way as the held-out figure
above, which matters more here because this is the number a skimmer quotes.

The bleed take does not recover under any fit — 0 of 8, or 1 with the mask,
over the same window set of unknown composition. Two
things differ between the takes and only one is usually named: the far end sits
about 7 dB louder relative to the operator, *and* the operator carries about
10 dB less low-frequency energy, consistent with being further from the
microphone. **Level ratio is a hypothesis about where recovery stops, not a
rule**, and a controlled sweep — same seat, same posture, volume varied
deliberately — is what would turn it into something the product could warn on.

#### The controls

Every clean take ran through the identical chain against the bleed take's system
audio as a borrowed reference: a loud, entirely unrelated signal, and every
chance to carve the operator out of a recording that never contained an echo.

| take | raw | linear | masked | admitted |
|---|---|---|---|---|
| free | +0.777 | +0.771 | +0.774 | 8/8 → 8/8 |
| read | +0.619 | +0.599 | +0.605 | 4/5 → 4/5 |
| roomnoise | +0.597 | +0.595 | +0.596 | **9/14 → 7/14** |
| household (197 segments) | +0.037 | +0.037 | +0.037 | 0/197 → 0/197 |

The household segments — other people, same microphone, same room — are the only
figures here measured on the segmentation the pipeline actually produces, and
they do not move at all. But the room-noise take loses two windows of fourteen on
a mean shift of 0.002: its windows cluster right at the operating point, so a
change far too small to see in a mean still moves a count. **The chain is not
free where there is nothing to cancel**, and any deployment has to carry that
cost against the recovery.

#### The dB metrics point the wrong way

Recomputed through the corrected harness rather than carried over from the
scratch script that preceded it:

| | overlap (recovers) | bleed (does not) |
|---|---|---|
| suppression, echo-dominant frames | 10.5 dB | 9.6 dB |
| suppression, double-talk | **1.4 dB** | **3.4 dB** |
| echo above the microphone's noise floor, same frames | 12.1 dB | 16.1 dB |
| residual above that floor | 1.7 dB | 6.5 dB |
| band-averaged coherence, best band | 6.5 dB | 6.4 dB |
| level dependence, loud vs quiet quartile | −2.9 dB | −1.9 dB |

The take that recovers has *less* double-talk suppression than the take that
does not. Judging this work on ERLE — which the previous plan proposed — would
have ranked the two backwards and retired a mechanism that works. A speaker
embedding cares which time-frequency cells are corrupted, not how much energy
left the signal.

The residual on overlap sits 1.7 dB above the microphone's own noise floor on
the frames the classifier calls echo-dominant. That is suggestive and not more:
those frames are selected *because* their residual is low relative to the
estimated echo, so a low residual there is partly the selection rule restating
itself, and the operator was talking throughout. Read it as "on the frames where
this filter did best, it ran out of echo to remove", not as "the far end plays
alone there" or "the linear filter is close to finished" — both of which this
document asserted and neither of which follows. The coherence figure is **not** a
ceiling either, though an earlier version of
this table called it one and concluded that no longer filter could do better:
the measured suppression of 10.5 and 9.6 dB is already above it, which is the
arithmetic refuting the label. Averaging coherence across a band before taking
the log is not the per-bin bound, and the frames it is measured on are selected
by the same residual-to-echo test that selects the ERLE frames. It describes how
linearly related the two legs are and supports no conclusion about filter
length. Level dependence of −2 to −3 dB is small enough that macOS speaker
processing downstream of the tap is not the obstacle it might have been.

#### What this does not say

It does not say AEC3 clears the bar, and it is not an upper bound that would let
AEC3 be dismissed. It says there is enough recoverable signal to justify one
bounded integration. Seven held-out windows, two takes, one speaker, one room,
one microphone — and a windowing that is *not* the gate's contract, since
`speaker_gate.py` embeds whole caller-supplied segments rather than fixed
windows.

#### The recording that would settle it

**The missing input is a stretch of the far end playing while the operator says
nothing** — what a real canceller adapts on, and what not one of these five
takes contains. Every limit above follows from its absence.

It has to be the *opening of the take that is then scored*, not a separate
recording. A standalone silent take contains no operator speech to measure
recovery on, the harness holds no way to carry a filter from one take to
another, and standing up between recordings changes the acoustic path that the
filter exists to model — which would put the calibration and the measurement in
different rooms, in effect.

The protocol runs itself. `dual_capture.py --protocol` shows timed cues in the
terminal and writes the schedule beside the recordings:

```sh
python3 spike/dual_capture.py --protocol --out ~/enroll-calibrated
```

Start the far end playing first, sit where you would actually take the call, set
the volume you would actually use, and then change nothing for the ~2 minutes the
capture runs. The cues say only when to talk:

1. **35 s: say nothing** while the far end plays. This is the fit interval.
2. **Then five pairs**, ten seconds reading aloud over the same playback and six
   seconds silent while it keeps playing. Each talking cue shows a passage —
   read it continuously until the cue changes, starting again from the top if you
   reach the end. Reading rather than talking is what lets the run verify, per
   segment, that a given three seconds of audio holds you.

The silent intervals are not padding. They are the far end with nothing behind
it, which makes them the negative control for the gate — audio that must *not* be
admitted as the operator in any condition — and the first echo-only audio in this
project, which is what an honest suppression figure needs and what none of the
earlier ones had.

Then:

```sh
python3 spike/aec_bound.py --label acceptance \
  --enroll read,free --take read=... --take free=... \
  --take calib=~/enroll-calibrated \
  --segments calib=~/enroll-calibrated/mic-segments.json \
  --protocol calib=~/enroll-calibrated/protocol.json \
  --fit-mode prefix --fit-before 30 --score-after 34 \
  --out spike/aec-bound-results.json
```

Three things in that command are the point.

**The fit stops at 28 s and scoring starts at 32 s**, leaving four seconds
neither is allowed to touch. Identical boundaries would put the filter's last
fitted sample next to the first scored one, and a two-second guard is cheaper
than arguing about whether that matters. The harness refuses a prefix run whose
scoring reaches back into its own fit, rather than letting an invalid result be
reported as a held-out one.

**Alignment is estimated from the prefix too**, not from the whole take. It used
not to be, which let audio after the boundary influence the delay the fit was
built from — a quieter version of the leak the fit spans exist to close.

**`--segments` is required in this mode**, and points at `mic-segments.json` —
not at `transcript.json`, which cannot do this job in three separate ways. The
transcript holds both legs, and clears every speaker label whenever bleed is
detected, so operator and far-end turns are indistinguishable in it. Its times
are on the merged session clock rather than the microphone's, off by a startup
skew that has reached 1.7 s, so slicing `mic.wav` with them selects the wrong
audio. And its microphone turns have already been through `drop_bled`, which
removes precisely the contaminated operator speech an echo experiment exists to
recover. `dual_capture.py` now writes `mic-segments.json` before the merge and
before that filter: microphone only, microphone clock, voicing filtering and
nothing else, with a schema marker the harness checks rather than trusts.

That also matters because everything else in this document is measured on fixed
three-second windows, which are a control for comparing takes and are *not* what
the gate consumes — `speaker_gate.py` embeds whole segments its caller hands it.
An acceptance run scored on fixed windows would measure something the product
never does. They stay available as a secondary diagnostic by omitting the flag.

**`--protocol` is required in this mode too, and it is the part that took two
attempts to get right.** An earlier version of this section checked the
calibration phase by refusing any run whose microphone segments began before
`--fit-before` — reasoning that a segment there meant the operator had spoken.
That check was unsound, and it would have rejected every correct recording. On
speakers the far end reaches the microphone and transcribes there, which is the
entire premise of `drop_bled`; a silent operator and a talking one both produce
microphone segments throughout the calibration phase. Its absence would not have
proved silence either.

The same mistake, one level up, was the denominator. "Microphone-only" names the
channel, not the talker. Between the operator's phrases the microphone still
carries the far end, so a list of voiced microphone intervals is a mixture of the
voice being recovered and the voice being cancelled. Every echo figure in this
document was scored against exactly that mixture. The controls are not affected
in the same way: the quiet takes have no far end to leak, the household rate
counts admissions of segments that are deliberately *not* the operator, and the
synthetic level sweep mixes into his own clean audio, so what it scores is his
by construction.

Nothing in the audio fixes this, so the labels come from outside it. The cue
schedule is decided before any audio exists and written to `protocol.json`, bound
to `mic.wav` by digest and sample count. A keypress mark would have been simpler
and is the wrong shape: it is the operator attesting afterwards to what he did,
which is the class of evidence this project keeps refusing. A schedule fixed in
advance cannot be fitted to the result.

**Compliance is checked from content, because energy cannot check it.** The
first version of this asked whether each speak interval contained voiced
microphone audio. On the only configuration that matters it always does — the far
end plays throughout — so a missed cue read as compliant, and the control that
"proved" the check worked used a silent recording, the one condition the
experiment never runs in.

What echo cannot fake is the operator's words. Each speak cue displays a
twenty-five-word passage to read continuously, and **each segment is judged on
its own transcript**: of the content words in it, how many come from the passage?
Reading puts nearly all of them there; far-end echo puts nearly none, because the
playback is saying something else.

Judging the segment rather than the interval is the second version of this. The
first showed a short phrase once at the top of a ten-second interval, which
established that the operator spoke *somewhere* in it — and then every segment in
the interval was counted as his, including the ones during a pause, which on
speakers hold the far end and nothing else. "Then keep talking" was carrying the
weight, and it is an assumption. The interval-wide label smuggled the mixture
back in one level down from where it was removed.

Precision, not recall: a three-second segment can only hold a fraction of a
twenty-five-word passage, so requiring most of the passage would reject every
real segment by arithmetic. What is asked is how much of what the segment *does*
say comes from the passage.

Segments that fail go to `operator_unverified` — reported, and not treated as
violations. Nobody reads a passage without breathing, so a segment landing on a
gap will always fail; what makes a run inconclusive is unverified audio
*outweighing* verified, at which point most of what was supposed to be reading is
unestablished.

This runs one way only. Echo-contaminated speech transcribes badly — that is the
condition under study — so a segment that fails to match is **not** evidence of
silence. And the silent intervals have no equivalent check at all, because
nothing can demonstrate an absence there. That they were silent is an assumption
the artifact states as one, which is why the verdict calls the whole thing a
controlled human protocol and never ground truth.

**And it selects on the contaminated signal, which bounds every figure below.**
The passage check reads the raw microphone transcript — the thing cancellation
exists to improve. The segments it drops are therefore not a random sample: they
are disproportionately the ones echo wrecked, which are exactly the ones where a
canceller has the most to do. A rate computed over the survivors is recovery
*conditional on the raw transcript having already found the operator*, which is
not the question the table claims to answer.

Nothing in this rig can fix that. It needs a near-end observation channel — a
close-talk mic worn by the operator, feeding labels and nothing else — which
would make the labels independent of the signal under test. Short of that, the
honest move is to stop reporting one number and report the interval it lies in.
The harness now scores `operator_unverified` too and prints a pair per condition:

* **verified subset** — segments whose own transcript carries the passage. The
  optimistic end, selected as described above.
* **whole cued reading** — every segment inside a speak interval, verified or
  not. The pessimistic end, which assumes the operator read throughout the
  interval he was cued to read through. That is the same controlled-human
  assumption the silent intervals already run on, applied consistently rather
  than only where it flatters the result.

The truth is between them and the spread is the price of having no independent
labels, so the run also prints how many seconds the two disagree over. A single
figure quoted from either end alone is a misreading of what was measured.

The far end's own transcript is checked too, and any passage the playback says
enough of itself is struck from the evidence rather than credited to him.

The harness then scores three groups separately: segments wholly inside a speak
interval, segments wholly inside a silent one, and segments straddling a cue,
which belong to neither and are reported apart rather than assigned. One second
is trimmed from each end of every interval, because a cue is seen and acted on
rather than obeyed instantly. Compliance is reported, not enforced — a speak
interval the operator stayed quiet through reaches the artifact saying so.

That second is trimmed from the moment the cue was **observed**, not from the
moment it was scheduled. Trimming from the schedule let display lateness spend the
operator's reaction time instead of moving the interval: a control cue 0.9 s late
passes a 1.0 s margin check and leaves 0.1 s to stop talking before the echo-only
window opens, so an overrunning sentence scores as far-end-only audio in a control
the operator had not been told to start. Both edges move with the observation,
because what ends an interval is the next cue appearing rather than the clock — an
instruction stands until it is replaced, so a late successor genuinely extends its
predecessor. This propagates: the compliance check and the suppression measurement
read the same interiors.

**A run that cannot support a conclusion records itself as inconclusive.** Four
things have to hold, and an earlier version checked only the first: both classes
populated (three segments and eight seconds each, measured as *distinct* audio —
summing lengths let three copies of one three-second span satisfy an eight-second
bar, and overlapping segment lists are now refused at load); at least one speak
interval verified from content, because zero verified cues means the labels are
the schedule's intent rather than an observation; every cue carrying a recorded
display time *and* falling within the attribution margin of its scheduled time;
and no admitted segment sitting at the take's own noise floor, which was
previously a console warning that left the admission in the numerator regardless.
Phases that ran past the end of a short take put the run in that state too.

The display-time requirement has two halves because the first version only had
the second, and it held vacuously. The lateness filter skipped over the missing
timestamps on its way to comparing magnitudes, so a run that recorded no cue
times at all satisfied "every cue displayed within the margin" trivially and
returned `scored` with nothing in its list of reasons. Unobserved is not
compliant; it is unproven, and without those times the interiors above fall back
to boundaries the operator may never have seen. It still writes its manifest, with the counts that made it
inconclusive; a missing label reads as "not run yet", which is a different fact.

Suppression on the silent intervals is only reported where the far end was
**actually playing**, and "where" is decided on the microphone's timeline. Real
playback pauses between sentences, and a pause inside a silent interval
contributes room noise to both sides of the ratio, which drags the figure toward
zero and calls it a measurement. A frame counts as playing when it is within
20 dB of the reference's loud level — measured *down* from that rather than up
from its quietest frame, because a far end that never pauses has a quietest frame
as loud as its loudest and the up-from-quiet version read continuous playback as
silence. Four seconds of it have to exist, or the run says there is no figure
rather than printing one.

The reference it reads is the *aligned* one. `align` shifts a private copy onto
the microphone's timeline, and selecting far-end activity from the caller's own
`system.wav` picked samples up to the measured 1.7 s of startup skew away from
the echo being measured — reporting seconds of "far-end-active" audio that
contained no echo at all. Digests prove two files are the same file; they say
nothing about the two clocks agreeing.

This is also the exact fixture AEC3 should be handed first, since it gives a real
canceller the single-talk interval it converges on.
### Measured: the embedding degrades by half on the leg that needs it

Before deciding whether a speaker-embedding dependency is worth carrying, the
question is whether one would even work on this microphone. Ran
`speechbrain/spkrec-ecapa-voxceleb` over both legs of the 75-minute capture.

**The segments have no speaker labels, so the positive class was manufactured
without any: the two halves of a single utterance are the same speaker by
construction** — same person, same channel, same session, same distance from the
microphone. Half-versus-half within a segment is a guaranteed positive; the same
comparison across segments is a mixture. Both sides use equal-length audio,
because embedding similarity climbs with duration and would otherwise flatter
the positives.

Two controls, neither of which the first version had, and both of which changed
the result:

- **A duration cap.** Whisper emits segments up to 30 s, and a 30-second span of
  conversation is not one speaker. Splitting those manufactures negatives
  labelled as positives. Restricted to 3-12 s.
- **A control leg.** The same code over the system tap — near-field meeting
  audio. Without it there is no way to tell a hard acoustic condition from a
  broken harness, and the mic number alone cannot distinguish them.

| leg | speech RMS | same speaker | arbitrary pair | gap | silhouette |
|---|---|---|---|---|---|
| system tap (near-field) | 0.110 | 0.524 | 0.211 | **+0.313** | 0.397 |
| built-in mic (the room) | 0.010 | 0.243 | 0.096 | **+0.148** | 0.227 |

The control passes, so the instrument is sound. **On far-field room audio the
same voice is recognised at less than half the confidence, and the margin over
an arbitrary pair is 47% of the near-field margin.** That is the honest state:
not dead, not comfortable.

**Speaker structure is present even so.** People hold the floor for many ASR
segments in a row, so if clusters track speakers, consecutive segments should
land in the same cluster more often than cluster sizes predict. They do, on both
legs — 1.9x chance on the mic, 1.7x on the system tap. This uses timing only, so
it is independent of the embeddings it is checking. Individually weak embeddings
still carry a speaker signal that survives aggregation, which is what an
enrolment centroid does.

**Loudness is not the explanation, and that kills the convenient hypothesis.**
The mic leg is 21 dB quieter, so the obvious story is that the operator sits
close to the laptop and lands in a better regime than the room. Split-half
consistency by loudness quartile refuses it:

| quartile | system RMS / score | mic RMS / score |
|---|---|---|
| quietest | 0.082 → 0.487 | 0.0054 → 0.229 |
| lower | 0.101 → 0.576 | 0.0069 → 0.257 |
| upper | 0.113 → 0.572 | 0.0081 → 0.252 |
| loudest | 0.135 → 0.466 | 0.0135 → 0.237 |

Flat on both legs. Within a channel, a segment 2.5x louder embeds no better.
Whatever the mic leg loses, it is not gain — reverberation, distance, or the
microphone's own front end are all still live, and this measurement does not
separate them. Note the limit precisely: **RMS conflates how loudly someone
spoke with how close they were**, so this rules out level as the driver without
ruling out proximity.

**Which is exactly why the missing sample is the blocker.** Proximity is the one
condition that might put the operator in a better regime than the room, it is the
condition the vendor gate depends on, and it is the one thing none of the audio
behind this section samples. Sixty seconds of the operator speaking at a normal
working distance, captured through `dual_capture.py`, is the entire remaining
input.

> **Updated 2026-07-29, and this paragraph's premise no longer holds.** When this
> was written there was no recording of the operator on this microphone at all.
> One now exists — 117 s, nine scorable segments — so the sentence "every mic leg
> in the project is silence or the household", which this paragraph used to carry,
> was true when frozen and is false now. The frozen banner at the top of this file
> covers the *echo findings*; it does not license a stale claim about what exists.
> The gap is now narrower and specific: one sitting rather than none, still short
> of the two `leave_one_sitting_out_scores` needs and of the twenty held-out scores
> a 5% false-reject rate can express. `speaker_gate.enforce_enrollment` refuses a
> profile until both are met.

**This measured the harder problem than the gate has to solve, in two ways, and
the numbers above should not be read as the gate's expected accuracy.**

*It measured room against room.* Every segment here is far-field: people at
conversational distance from a laptop that is not pointed at them. The gate's
actual job is operator against room, and the operator is the near-field case on
that same microphone — a metre away, speaking toward it. The control leg shows
what near-field buys, 0.524 against 0.243. Where the operator's own segments land
between those is unknown because no recording of them exists, and the
loudness-quartile result specifically does not answer it: within-channel volume
predicted nothing, but the 21 dB *between*-channel difference came with a large
quality difference, so distance and channel remain live where gain does not.

*It measured clustering, not verification.* Silhouette and cluster structure ask
whether every speaker can be told apart from every other. The gate asks one
binary question against one enrolled identity — keep, or drop. That is a strictly
easier problem, and it is the one Teams and Zoom ship.

So the honest summary is narrower than it first reads: an off-the-shelf embedding
finds real speaker structure in far-field room audio at roughly half the strength
it manages near-field, which bounds the *pessimistic* case. The gate's own case
is untested and has reason to be better. What settles it is the operator sample,
not more analysis of this recording.

---

## Two defects found while preparing the long run

Both were in the spike itself, surfaced by walking through what a 70-minute
capture on a second machine would actually do. Both are fixed.

**Bleed was measured over the whole capture, so over-running diluted it.** The
correlation ran across every frame, including stretches where nothing was playing
on the system leg. Silence there cannot demonstrate bleed in either direction —
no audio is playing, so none can leak — but it still adds microphone noise to the
denominator and drags the result toward zero. Measured by appending synthetic
empty-room audio to a real capture:

| Empty room appended | Before fix | After fix |
|---|---|---|
| none | +0.927 | +0.889 |
| 5 min | +0.916 | +0.889 |
| 20 min | +0.875 | +0.889 |
| 40 min | +0.826 | +0.889 |

This failed in the dangerous direction: a contaminated capture reads as *cleaner*
than it is, so the Me/Them split gets trusted when it shouldn't be. Since
`--seconds 4200` is sized for the drift measurement rather than the meeting,
over-running into an empty room is the expected case, not an edge case. Bleed is
now measured across the system leg's active span only, and the report states how
much of the capture that covered.

(The two "after" columns differ from the two "before" columns at zero tail
because the numbers come from different recordings — the point is the decay
across each column, not the absolute value.)

**The microphone was bound silently.** `sd.InputStream` took no `device=`
argument, so it grabbed whatever macOS had as default input at the moment the
stream opened, and never said which. Connect headphones after launch and you
record the built-in mic, or silence — and you find out 70 minutes later, on a run
that is expensive to repeat. There is now `--input-device` and `--list-devices`,
and both resolved devices are printed before any audio arrives. The output device
is printed too, since the tap follows the default output rather than the input.

---

## Incidental findings

**Start skew is variable and not small.** First-block arrival differed by
−357 ms on run 1 and +5 ms on run 2. Whatever aligns the legs cannot assume a
fixed offset measured once; it has to be measured per capture. The correlation
lag and the independently measured skew agreed on run 1 (−380 ms vs −357 ms),
which is a useful cross-check that both measurements are sound.

**The tap resamples, so Python never has to.** `audiotee --sample-rate 16000`
emits 16 kHz mono `s16le` directly, converting from the device's native 48 kHz
inside the tap. Half of the "resampling and channel reconciliation" work named in
the teardown is handled by the capture binary. Note the documented side effect:
requesting any sample rate also drops bit depth from 32-bit float to 16-bit int.
For ASR that is fine.

**Permissions were not the obstacle.** A bare SwiftPM binary with no bundle and
no `Info.plist` captured system audio without a prompt, because the host terminal
already held the grant. This will not hold for a launchd-managed daemon —
`local-dictation`'s README already documents macOS attributing TCC prompts to the
`.venv` python binary under launchd. Expect to solve this again at packaging time.

**Transcription is not a bottleneck.** MLX Whisper `large-v3-turbo` transcribed
both legs of a 22-second capture in 6.1 s, and both legs of a 14-second capture
in 2.2 s.

---

## What this means for the build

- The two-stream capture architecture works, now demonstrated over 75 minutes
  rather than 22 seconds. The tap is stable, survives the audio source exiting,
  and costs nothing in transcribed content.
- **Me/Them is conditional, not free** — and it fails in *both* directions. On
  speakers, bleed makes the split confident fiction. On a clean capture with a
  quiet operator, silence makes it confident fiction. The design docs treated the
  split as the thing you get for nothing from capture topology; it is the thing
  that needs the most defending.
- Drift on same-device capture is bounded under ~230 ms/hour, roughly 8x inside
  typical cross-leg turn spacing — but not inside the closest 7% of it, so this
  demotes drift from open risk to known quantity rather than closing it.
  Mixed-clock hardware (USB, Bluetooth) is still unmeasured and is where drift
  would actually be expected.
- Fabricated turns are gated out, validated at zero cost to real content. What
  remains on the mic leg is genuine room audio — a correctness defect as well as
  a consent one, since it enters the transcript labelled `Me`. An earlier version
  of this list called it "a consent question rather than an engineering one",
  which was wrong in the same way the section above was.
- **Headphones are not the fix for that, and are not a permanent requirement for
  bleed either.** They cut the acoustic path from the far end to the mic and do
  nothing about the room. Both defects have a known industry answer — echo
  cancellation for one, an enrolled voiceprint for the other — and neither is
  implemented here yet, which is the only reason headphones are load-bearing
  today.
- **Echo removal recovers the operator on one take and almost none on the
  other.** Fit offline on the first thirty seconds and scored only on audio it
  never saw: 1 admitted window of 7 becomes 5 where the far end sits
  below the operator, and 0 of 8 becomes 1 where it sits ~7 dB above. Those are
  voiced *microphone* windows and not all of them hold the operator, so each
  ratio is what the gate did on a window set of unknown composition — not a
  recovery rate, and not a floor on one either. Enough to
  justify one bounded AEC3 integration; not enough to design a warning around,
  since the two takes differ in operator distance as well as level.
- **No take in this project contains four seconds of the far end playing while
  the operator is silent**, which is what a real canceller adapts on. That
  single missing input is why the fit has to be held out in time rather than by
  regime. `dual_capture.py --protocol` now records it, cueing the operator
  through a calibration phase and then alternating speak and silent intervals —
  which also supplies the one thing no recording can: which intervals held his
  voice, decided before the audio existed rather than inferred from it after.
- Separability is measured and the answer is "half". An off-the-shelf embedding
  recognises the same voice on the built-in mic at 0.243 cosine against 0.524 on
  the system tap, with real speaker structure present on both. Loudness does not
  explain the gap, so the comfortable story — the operator is close and therefore
  fine — is not available. The gate is neither ruled in nor out.
- **That input was collected**: five sixty-second takes — read, spontaneous, far
  end on the speakers, off-device music, and the operator talking over the far
  end. They are what turned the gate's threshold from a guess into a number, and
  what every echo-cancellation figure above is measured on. They also carry the
  project's sharpest remaining limit: one speaker, one room, one microphone.
- Still unexercised: a live two-person run on headphones. The Me/Them split has
  never seen real speech on both legs at once — every measurement so far put all
  the real words on one leg.
