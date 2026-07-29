# Spike results — dual-leg capture

Run 2026-07-28 on macOS 26.5.2, Apple Silicon, Swift 6.3.3.
Tool: [`dual_capture.py`](./dual_capture.py). Runs of 14 s, 22 s, and 75 min.

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

**Which is exactly why the missing sample is the blocker.** There is no
recording of the operator on this microphone — every mic leg in the project is
silence or the household. Proximity is the one condition that might put the
operator in a better regime than the room, it is the condition the vendor gate
depends on, and it is the one thing none of the existing audio samples. Sixty
seconds of the operator speaking at a normal working distance, captured through
`dual_capture.py`, is the entire remaining input.

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
- Separability is measured and the answer is "half". An off-the-shelf embedding
  recognises the same voice on the built-in mic at 0.243 cosine against 0.524 on
  the system tap, with real speaker structure present on both. Loudness does not
  explain the gap, so the comfortable story — the operator is close and therefore
  fine — is not available. The gate is neither ruled in nor out.
- **The one input that would settle it is sixty seconds of the operator speaking
  into the laptop microphone.** Every mic leg in this project is silence or the
  household, so the gate's positive class has never been sampled in the channel
  it would run on. No code is needed for it; `dual_capture.py --seconds 60` is
  the whole procedure.
- Still unexercised: a live two-person run on headphones. The Me/Them split has
  never seen real speech on both legs at once — every measurement so far put all
  the real words on one leg.
