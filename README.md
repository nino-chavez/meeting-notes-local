<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="local-meeting-notes — no bot joins the call, no audio leaves the Mac. The far end and your voice arrive as two separate streams, shown as two live level tracks from a real 14-second capture at 16 kHz.">
</p>

A meeting notetaker that captures the call from your own machine. No bot joins
the meeting, and the audio never leaves the Mac — system audio comes through a
Core Audio process tap, your microphone comes through the same path
`local-dictation` already uses, and the two arrive as separate streams.

> **Status: design definition, a capture spike, and a notes evaluation.** There
> is no app yet. What exists is a working two-leg capture — validated end to end
> over a 75-minute meeting — a voiceprint gate wired into that capture but never yet
> run on a real meeting, a local summarizer with its fabrication checked
> mechanically, the measurements the capture and the summarizer produced, and the
> documents deciding what gets built. Start with
> [`spike/RESULTS.md`](./spike/RESULTS.md) and [`notes/EVAL.md`](./notes/EVAL.md).
>
> **Usable today** for a call taken on headphones with nobody else in the room. An
> open microphone records the room into the transcript; the voiceprint gate that
> fixes that is now built and wired, needs two minutes of enrolment, and has never
> been tried on a real conversation. See [Limits](#limits).
>
> **The next run that matters** is exactly that: enrol, take one real meeting on
> headphones, and read the note. Nothing to read aloud, nothing playing in the
> background — [the commands are here](#keeping-the-room-out-of-your-half).

---

## What the spike found

<p align="center">
  <img src="./assets/readme/bleed.svg" width="100%" alt="On speakers, the two-stream split stops working. Two level tracks from one real capture: both rise during the same interval because the microphone is hearing the speakers. Peak envelope correlation +0.929, acoustic component −25 ms, consistent across three runs. The resulting transcript places the same sentence on both legs, once labelled Me and once labelled Them.">
</p>

Capturing the microphone and the system separately is supposed to give you
"me versus them" for free. It does — **on headphones, in an empty room**. Both
halves of that condition are load-bearing, and they fail for different reasons.

On speakers it does the opposite. The microphone is a correct recording of the
room, and the room contains the far end, so every sentence lands on both legs.
The transcript then reads as two people agreeing with each other word for word,
and nothing downstream can tell that it never happened. That is worse than
having no speaker labels at all.

So the product treats this as a measurement, not a caveat: correlation between
the two legs is measured over the span where system audio actually played, and
when it is high the transcript stops claiming a split rather than fabricating a
dialogue. The measurement needs the whole capture, so the verdict lands when the
recording stops — a run cannot warn you at the top that it is about to be
contaminated.

**But bleed costs the speaker labels, not the notes.** Feeding a summarizer the
same contamination — labels dropped, every line doubled, which is what a
contaminated capture actually delivers — produced notes at full topic coverage
with a correct decision list. Summarization is compression, and the first thing
compression discards is repetition. So the product stops claiming who spoke and
keeps writing the note.

**But an open microphone records the room, and that is a correctness defect —
not a manners one.** On an online call, people talking near you are transcribed,
labelled `Me`, and delivered to the notes as things a participant said. Measured
on the 75-minute capture: **14.2% of merged turns were the room.** No household
subject matter survived compression into the notes, but the notes changed anyway
and deterministically — three action items with the room in, five with it out,
and different open questions. Irrelevant input perturbs *which* real content
survives compression without changing how much does.

Teams and Zoom both solve this by gating the microphone on an enrolled voice
profile, and neither requires an enrollment ritual — the profile is built
passively from ordinary speech. Google Meet does not attempt it and says so
outright: "voices from TV or people talking won't be canceled."

**This ships a ritual anyway, and that is a deliberate divergence from the
canonical pattern.** Two explicit one-minute recordings, where the vendors ask for
none. The reason is the threshold, not the profile: a centroid can be harvested
passively, but the cut point has to be a quantile of the operator's own score
distribution, and nothing passive establishes that before the gate has already
decided what to drop. Passive enrollment is the right end state and it needs a
threshold that survives not knowing whose speech it just learned from — unbuilt,
and not something to fake with a constant.

An off-the-shelf embedding separates the operator from his own household,
measured on five minutes of his speech through the microphone the gate runs on.
His own speech reaches +0.68 to +0.89 with nothing else playing; 197
segments of household speech in the same room on the same microphone reach
+0.577 at the very top. That gap is real but it is not yet a margin — the
strongest household segment lands 0.003 under the operating point, which is a
property of this sample and not a number to ship on. Music across the room costs
about 0.15 and still loses two segments in eight.

That gate is now wired into the capture rather than sitting beside it, so a run
with `--voiceprint` filters the microphone leg as it goes. It has still never seen
a real conversation.

**Another voice is the case that breaks it, and echo removal gets most of it
back.** With the far end coming out of the laptop speakers, the gate admits 1 of
the operator's 7 voiced microphone windows — it rejects him from his own meeting.
Removing the echo takes that to 5 of 7, on audio the echo filter was fitted
before rather than on, while the same processing leaves 197 household segments
unchanged to three decimals. Voiced microphone windows, not operator-speech
windows: with the far end on the speakers the microphone is voiced either way, so
some of those seven hold no operator at all. That makes these unlabelled
outcomes — what the gate did on a window set of unknown composition — rather than
a recovery rate. An earlier version of this paragraph called them a floor on
recovery, which requires every echo-only window to be rejected, and that is not
established. Not a full repair: the recovered windows average +0.61 against
+0.78 for the same voice with nothing playing, and on a second take with the far
end roughly 7 dB louder relative to him recovery is 0 of 8 to 1. Seven windows,
one speaker, computed offline in closed form rather than by a real canceller,
and no recording in this project yet contains the far-end-only calibration
interval that would settle it properly. The harness, every per-window score, and
three figures earlier versions of this paragraph got wrong are in
[`spike/aec_bound.py`](./spike/aec_bound.py) and
[`spike/RESULTS.md`](./spike/RESULTS.md).

**Two defects in the notes half were in the prompt, not the model.** The first
was fabrication: the instructions illustrated a phrasing rule with two example
sentences, and the model reproduced both as decisions a research meeting had
reached — in a transcript where neither subject appears once. Those notes named
nobody, invented no numbers, and were read in full, so every check in place
passed them. Watching numbers is the wrong check on its own; fabricated prose
carries no digits.

The second was the opposite failure. Two rules told the model to leave out
anything it was unsure of and to prefer omitting a section to padding it — rules
written when the open question was whether a local model invents things. It does
not. It omits. Deleting those two rules is **the only change in this project
measured across two models, two domains and five meetings with no regression**;
on the longest transcript tested it took action items from three to eleven. See
[`notes/EVAL.md`](./notes/EVAL.md).

**Clock drift is bounded, not measured.** A 75-minute capture puts relative drift
at +4 ± 63 ppm — inside its own error bars, so there is still no drift *value*,
but the bound is under ~230 ms per hour. That does not close the question the way
it first appears: reordering depends on the gap between adjacent turns across the
two legs, not on turn length, and 7.2% of 416 measured cross-leg transitions sit
closer together than the bound. Drift compensation is not urgent and not provably
unnecessary. Same-device only — a USB or Bluetooth leg is where drift would
actually be expected and is untested.

---

## How it works

<p align="center">
  <img src="./assets/readme/pipeline.svg" width="100%" alt="Capture architecture: system audio through the audiotee Core Audio tap and the microphone through sounddevice both feed dual_capture.py at 16 kHz s16le, which timestamps each block on arrival, measures drift and bleed, and applies three gates — voicing, echo, voiceprint; MLX Whisper transcribes on-GPU from locally cached weights, and the result is a transcript.json that either carries Me and Them labels or declares itself unattributed.">
</p>

The tap is a small Swift binary ([audiotee](https://github.com/makeusabrew/audiotee),
MIT, vendored — see [`capture/NOTICE`](./capture/NOTICE)) that asks Core Audio
for a process tap and writes PCM to stdout. Asking it for `--sample-rate 16000`
makes it resample inside the tap, so the Python side never has to. The seam
between the two halves is an ordinary pipe: no IPC, no virtual audio driver, no
kernel extension.

Everything downstream — transcription, cleanup, storage — runs on the machine.

---

## Try it

Requires macOS 14.4+, Xcode Command Line Tools, and Python 3.10+.

```sh
git clone git@github.com:nino-chavez/local-meeting-notes.git
cd local-meeting-notes

(cd capture/audiotee && swift build -c release)     # ~35 s

python3 -m venv .venv
.venv/bin/pip install -r spike/requirements.txt
```

Capture both legs, measure drift and bleed, print a labelled transcript:

```sh
.venv/bin/python spike/dual_capture.py --seconds 60
```

`--no-transcribe` measures without transcribing, which needs only numpy and
sounddevice and skips the 1.6 GB Whisper download entirely. Plain
`dual_capture.py` runs until Ctrl-C.

That install is not small, and the cost is itemised in
[`spike/requirements.txt`](./spike/requirements.txt) rather than left as a
surprise: the voiceprint gate's two dependencies pull 36 wheels totalling 153 MB,
of which torch alone is 111 MB, and ECAPA's checkpoint adds 89 MB the first time a
profile is built. Both `--self-test` suites deliberately need neither — the encoder
is an argument rather than an import, so every control runs on numpy alone.

**The run that matters now** is an ordinary meeting on headphones with the
voiceprint gate on. Nothing to read, nothing playing in the background, no cues.
Three recordings, and you talk normally in all of them — see
[Keeping the room out of your half](#keeping-the-room-out-of-your-half) below for
the commands.

That is the run because it is the only thing this project has never done: both
halves are measured separately, and no note has ever been written from the
operator's own audio and read by a human. The cued speaker protocol below was the
run that mattered *before*; its findings are frozen as directional feasibility and
polishing it further was the wrong use of the next hour.

### Keeping the room out of your half

An open microphone records the room. On the 75-minute capture, 14.2% of merged
turns were other people talking near the laptop — transcribed cleanly and handed
to the notes as things a participant said. The voiceprint gate removes them, and it
now runs inside the capture rather than beside it.

Three recordings get you there. **You talk normally in all of them.** Nothing to
read, nothing playing in the background, no cues on screen.

**1. A minute of you talking, alone, with nothing playing.**

```sh
.venv/bin/python spike/dual_capture.py --seconds 60 --out ~/enroll-1
```

Say anything — read your inbox aloud, describe your morning. It only needs your
voice, not particular words.

**2. The same again, on a different day.**

```sh
.venv/bin/python spike/dual_capture.py --seconds 60 --out ~/enroll-2
```

Two sittings, because one is measurably worse and in the harmful direction. A
threshold from a single recording sat above the honest one in all nine comparisons
this project has, by 0.006 to 0.181 — and too high means the gate deletes *you*
from your own meeting. One recording cannot see that, because every segment in it
shares the same room, gain and day.

**3. Build the voiceprint, then take a real meeting on headphones.**

```sh
.venv/bin/python spike/speaker_gate.py \
  --calibrate ~/enroll-1/mic-segments.json ~/enroll-1/mic.wav \
  --calibrate ~/enroll-2/mic-segments.json ~/enroll-2/mic.wav \
  --enroll-out ~/voiceprint.json --target-frr 0.05

.venv/bin/python spike/dual_capture.py --seconds 3600 --voiceprint ~/voiceprint.json
```

Then hand the transcript to the notes half below and **read the note**. That is the
step, and it cannot be automated: whether a partial transcript supports usable
notes is a judgement about coverage of decisions, names and actions, and about
whether anything in it was invented. Token counts cannot answer it.

Over-running into an empty room is harmless — bleed is measured only across the
span where system audio was actually playing.

Headphones do two jobs here. They remove the bleed that duplicates every line, and
they give the first clean read on something never yet tested: whether the Me/Them
split survives genuine speech arriving on *both* legs at once. Every capture so far
put all the real words on one leg.

`--target-frr 0.05` is the operating point — the share of your own speech the
threshold may drop. It has no default, because a plausible constant reads exactly
like a measured one to anybody downstream. `--calibrate` also prints what each
operating point would admit of a *second* voice if you pass `--against` a recording
of one.

Three things are worth knowing before reading the gate's output as a result:

- **It has never run on a real meeting.** Both halves are measured separately and
  the wiring is under control, but no capture in this project has yet been through
  the gate. What it does to a real conversation is unmeasured. That is the whole
  point of the run above.
- **It stands down when bleed is high**, and says so. Above the correlation cut the
  transcript has already dropped every speaker label, so no attribution is left to
  protect — and that is the same audio where the gate performs worst, admitting 1
  of 7 voiced microphone windows. Those seven are windows of unknown composition,
  so that is an unlabelled outcome rather than a recovery rate, and either reading
  is a reason not to trust the gate there. What the skip costs is the room's words
  staying in the transcript, and [`spike/RESULTS.md`](./spike/RESULTS.md) measured
  that as a real change to the notes: 3 action items and 4 decisions with the room
  in, 5 and 5 with it out, across three byte-identical repeat runs so it is not
  sampling noise. That content cost is accepted rather than risked against deleting
  you.
- **Segments under two seconds are kept, not judged.** The embedding is unreliable
  below that, and short turns are "yes", "agreed", "I'll do that" — the
  commitments the tool exists to record. The run reports how many and how long, so
  the leak is stated rather than hidden.

Every run prints what it dropped, how much of that was a close call, and whether
the dropped speech keeps coming back as one recurring voice. That last one is the
alert Teams ships for the same reason: a gate that removes a real participant
silently is worse than the contamination it replaces, because the transcript then
omits speech with no record that it did.

### The echo experiments

Frozen. These are the commands behind [`spike/RESULTS.md`](./spike/RESULTS.md) and
[`spike/aec3/README.md`](./spike/aec3/README.md), kept so their figures are
reproducible rather than because anything here is waiting on another run. **This is
the part that involves reading passages aloud over background audio** — and it is
not the run that matters now.

A cued capture on *speakers*, which is what the echo work is scored against:

```sh
.venv/bin/python spike/dual_capture.py --list-devices        # pick your mic
.venv/bin/python spike/dual_capture.py --protocol --out ~/take
```

Start the far end playing first, sit where you would take the call, and read each
passage aloud until the cue changes. The cue displays the passage — there is
nothing to memorise, and nothing is ever played audibly, because an audible cue
would land on both legs and pollute the evidence it exists to provide. It writes
`mic.wav`, `system.wav`, `protocol.json` and both legs' segments into the output
directory. `--protocol-pairs` changes the number of speak/silence pairs from the
default five.

Scoring it needs a second, separate take to build an operator profile *inside*
`aec_bound` — distinct from the persisted voiceprint above, which is a different
artifact for a different job. It has to be a different take: the question is
whether the echo work recovers a voice the filter was not fitted on, so scoring the
enrolment audio would be marking its own homework, and `--fit-mode prefix` refuses
the run outright if every take is also an enrolment take.

```sh
.venv/bin/python spike/dual_capture.py --seconds 60 --out ~/enroll

(cd spike/aec3 && make)          # needs webrtc-audio-processing; see its README
spike/aec3/aec3_offline --mic ~/take/mic.wav --ref ~/take/system.wav \
                        --out ~/take/aec3.wav

.venv/bin/python spike/aec_bound.py \
  --take e=~/enroll --take t=~/take --enroll e \
  --segments t=~/take/mic-segments.json --protocol t=~/take/protocol.json \
  --condition aec3=t:~/take/aec3.wav --fit-mode prefix --fit-before 30
```

That reports suppression and voiceprint scores. It does **not** report whether the
words survived, which is the number that actually matters and needs a second tool —
the passages were fixed before the audio existed, so how many of their content
words come back is external ground truth:

```sh
.venv/bin/python spike/retention.py --protocol ~/take/protocol.json \
  --far ~/take/system-segments.json \
  --condition raw=~/take/mic.wav --condition aec3=~/take/aec3.wav \
  --out ~/take/retention.json
```

`--out` refuses any path inside the repository, because those rows carry what was
transcribed and this repo is public.

And [`spike/sweep.py`](./spike/sweep.py) runs the whole thing across playback
levels, measuring the ratio from each recording's own silent and speaking intervals
rather than trusting the volume slider. Its three published observations are
confounded — content, spectrum and running order all moved with level — so it grew
`--playback` (one fixed asset, restarted before every take), `--replicates` and
`--shuffle`. Nothing from it should be quoted as a level effect until that has run,
and it is not queued: it belongs on the real-time path once a canceller lives
there, not on this offline harness.

```sh
.venv/bin/python spike/sweep.py --record --playback far-end.wav \
  --levels 25,45,70 --replicates 2 --shuffle 1 --out ~/sweep
```

### Turning a transcript into notes

Needs [Ollama](https://ollama.com) and one local model. Nothing leaves the
machine here either — the transcript is the same secret as the audio.

```sh
ollama pull llama3.1
python3 notes/fetch_corpus.py                          # three real meetings
python3 notes/summarize.py notes/corpus/ES2004c.json
```

Every run prints its own checks: whether the whole transcript was read, whether
any speaker was named that the input never contained, whether any figure or any
content word is absent from the transcript. `--self-test` runs those checks
against notes with known verdicts, in both directions, so a passing check means
something.

`--strip` drops the speaker labels; `--simulate-bleed` drops them *and* doubles
every line, which is what a contaminated capture actually delivers. After a real
capture, point it at the transcript the spike writes:

```sh
python3 notes/summarize.py spike/out/transcript.json
```

That file carries its own attribution level, derived from the capture's measured
bleed — so a contaminated recording arrives as unattributed without anyone
having to remember to say so.

A run also writes `mic-segments.json`: the microphone leg alone, on its own
clock, before the bleed filter runs, carrying the recording's digest and sample
count so it cannot be read against different audio. The transcript is for
reading; that file is for anything that indexes back into `mic.wav`, because the
transcript's times belong to the merged session clock and its microphone turns
have already had the contaminated ones removed.

What neither file carries is who was speaking. "Microphone-only" names the
channel, not the talker — on speakers the far end arrives on the microphone too.
`--protocol` is the answer: it runs a two-minute cued capture and writes
`protocol.json` beside the recordings, a schedule of which intervals the operator
was asked to speak in and which to stay silent through, fixed before any audio
exists. Each speaking cue shows a passage to read aloud for the whole interval, so the
run can verify *per segment* that a given three seconds holds him — echo can make
the microphone loud, but it cannot put his words there. A run whose evidence does
not hold up records itself as inconclusive instead of as a result. The far end's
own transcript is written too, as `system-segments.json`, so a cue passage the
playback happens to say is struck from the evidence rather than credited.

This is a controlled human protocol, not ground truth, and the difference is
worth being exact about because it bounds every number the spike reports. Two
assumptions remain. In the silent intervals, nothing can demonstrate an absence,
so adherence is assumed. In the speaking intervals it is checked — but checked
against the *contaminated* microphone transcript, which is the signal the
experiment exists to improve. Segments that fail that check are
disproportionately the ones echo wrecked, which are the ones cancellation is for.
So a rate computed over only the verified segments is recovery conditional on the
raw transcript having already found him. The harness therefore reports a pair: the
verified subset as the optimistic end, and every segment inside a cued reading
interval as the pessimistic end. Closing that gap needs a near-end observation
channel — a close-talk mic worn by the operator, used only as labels — which this
rig does not have.

### Recording a specific call

Nothing to configure per platform. The tap captures the machine's audio output,
so Zoom, Meet, Teams, a browser tab, or a phone call on speaker are all identical
to it — start the capture, join the meeting, let it run. Nothing joins the call
and nothing appears in the participant list, which is exactly why the consent
note below isn't decorative.

The corollary: **everything else on the machine lands on the "them" leg** — Slack
pings, a music tab, calendar alerts. Quit the noisy apps and turn on Do Not
Disturb first. The vendored tap can scope to a process (`--include-processes
<pid>`) and the spike deliberately doesn't expose it, because it works for a
native Zoom client but not for Meet, whose audio comes from a Chrome helper whose
PID changes between sessions. A flag that works on one platform and silently
records nothing on another is worse than no flag.

**Set your audio devices before launching.** The microphone is bound when the
stream opens, and the tap follows whatever is the default *output* device — so
connecting headphones mid-capture leaves you recording the built-in mic, or
silence. Both resolved devices are printed before any audio arrives; read that
line rather than assuming. `--input-device` pins the microphone explicitly, by
index or by a substring of its name.

**Permissions.** The terminal needs Microphone and System Audio Recording. The
first run prompts for both; some terminal emulators never prompt, in which case
grant them under System Settings → Privacy & Security. If it runs but records
silence, that is what happened.

---

## What's in here

| Path | What it is |
|---|---|
| [`spike/RESULTS.md`](./spike/RESULTS.md) | What the capture spike proved, and what it structurally could not. |
| [`spike/dual_capture.py`](./spike/dual_capture.py) | The spike: two legs, drift and bleed measurement, three gates, Me/Them transcript. |
| [`spike/speaker_gate.py`](./spike/speaker_gate.py) | The voiceprint: enrolment over several sittings, and the threshold it refuses to invent. |
| [`spike/aec3/`](./spike/aec3/) | WebRTC AEC3 over recorded legs, so a real canceller meets the same table as the offline estimate. |
| [`spike/retention.py`](./spike/retention.py) | Whether the *words* survived — passage recall and far-end leakage, against passages fixed before the audio existed. |
| [`spike/sweep.py`](./spike/sweep.py) | The same across playback levels, with the level measured from the recording rather than the volume slider. |
| [`notes/EVAL.md`](./notes/EVAL.md) | Whether a local model invents things, measured against human-written summaries. |
| [`notes/summarize.py`](./notes/summarize.py) | Transcript to notes, with four fabrication checks and controls for the checks. |
| [`docs/screens-and-states.md`](./docs/screens-and-states.md) | Eight surfaces, their lifecycle states, and the five templates derived from them. |
| [`DIRECTION.md`](./DIRECTION.md) | Art direction. Thesis first; the device ledger stays empty until devices ship. |
| [`DESIGN.md`](./DESIGN.md) | Tokens, visual rules, engineering rules, and the Tauri-over-SwiftUI shell decision. |
| [`docs/teardown.md`](./docs/teardown.md) | How Circleback, Fireflies and Granola actually work, and why this is built the way it is. |

The images above are drawn from real captured envelopes and follow this repo's
own `DESIGN.md` palette — including its rule that amber means live capture and
appears nowhere else. The measured values are pinned in
[`assets/readme/envelopes.json`](./assets/readme/envelopes.json) rather than
re-measured on every run, so regenerating one diagram cannot silently redraw the
others from whatever capture happens to be in `spike/out` — which is how the
14-second caption would have come to describe a different recording.

---

## Limits

- **An open microphone records the room, and the fix has never been tried on a
  real meeting.** Speech from people near you is transcribed and labelled as
  yours. Headphones do not help — they cut the far end out of your microphone,
  which is a different defect. The voiceprint gate that fixes this is now wired
  into the capture (`--voiceprint`), but it is measured only on this project's own
  recordings of one voice and a household; what it does to an actual conversation
  is unknown. Until that run happens, treat it as untested and be the only person
  in the room.
- **The gate needs a threshold nothing in the repository can supply.** It is a
  quantile of your own score distribution, so it comes from your recordings, over
  two or more sittings, and there is deliberately no default. A single sitting
  produces a measurably over-tight one that drops more of you than you asked.
- **On speakers, the gate would reject you too**, so it stands down there rather
  than firing. The far end returning through the room corrupts your own
  voiceprint, not just your transcript — 1 of 7 voiced windows admitted with the
  far end on the speakers. Offline echo removal recovers most of it, measured; a
  real canceller now exists offline ([`spike/aec3/`](./spike/aec3/)) and is not in
  the capture path. Headphones are the only configuration that works today, and
  that is why.
- **macOS only.** Core Audio process taps are 14.4+. The Windows equivalent is
  WASAPI loopback and is not implemented.
- **Speaker labels stop at "me" and "them."** Named participants come from a bot
  in the call or from scraping the meeting UI, never from the audio alone. See
  [`docs/teardown.md`](./docs/teardown.md) for how the commercial products get
  them.
- **Recall trails a hosted notetaker.** On two real calls hand-scored against a
  published rule, these notes caught 8 of 10 commitments that Gemini caught 10 of.
  Every recall figure here rests on ten commitments across two meetings — the
  thinnest evidence in the project.
- **Muting is not a privacy control.** The tap reads the rendered stream before
  hardware volume, so a muted or zeroed output is still captured in full. Stop
  the capture; do not rely on the volume knob.
- **Recording a call silently is a two-party-consent problem** in roughly a dozen
  US states. Tell the room.

## License

MIT — see [`LICENSE`](./LICENSE). The vendored tap is separately MIT, Copyright
© 2025 Nick Payne; see [`capture/NOTICE`](./capture/NOTICE).
