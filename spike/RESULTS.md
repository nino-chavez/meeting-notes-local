# Spike results — dual-leg capture

Run 2026-07-28 on macOS 26.5.2, Apple Silicon, Swift 6.3.3.
Tool: [`dual_capture.py`](./dual_capture.py). Two runs, 22 s and 14 s.

The spike existed to answer two questions the design documents could not.
**One is answered and it changes the product. The other is not answered, and
this spike structurally cannot answer it.**

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

## Not answered: clock drift

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

**~67 minutes** to resolve 50 ppm. The tool now prints its own error bars and
refuses to project an hourly figure when the reading is inside them.

**To actually answer this**, run it against a real meeting:

```bash
python spike/dual_capture.py --seconds 4200 --no-transcribe
```

Until that runs, treat drift as an open risk. Do not build timestamp-stitching
logic against an assumed drift figure.

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

- The two-stream capture architecture works. The tap is stable, the format is
  right, and the seam between the Swift binary and the Python daemon is a plain
  pipe — as designed.
- **Me/Them is conditional, not free.** The design docs treated it as the thing
  you get for nothing from capture topology. That is true only on headphones. On
  speakers it produces confident fiction, which is worse than no labels.
- Drift remains the open engineering risk and needs a full-length capture before
  any stitching logic is written.
