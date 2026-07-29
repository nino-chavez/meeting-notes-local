<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="local-meeting-notes — no bot joins the call, no audio leaves the Mac. The far end and your voice arrive as two separate streams, shown as two live level tracks from a real 14-second capture at 16 kHz.">
</p>

A meeting notetaker that captures the call from your own machine. No bot joins
the meeting, and the audio never leaves the Mac — system audio comes through a
Core Audio process tap, your microphone comes through the same path
`local-dictation` already uses, and the two arrive as separate streams.

> **Status: design definition, a capture spike, and a notes evaluation.** There
> is no app yet. What exists is a working two-leg capture — validated end to end
> over a 75-minute meeting — a local summarizer with its fabrication checked
> mechanically, the measurements both produced, and the documents deciding what
> gets built. Start with [`spike/RESULTS.md`](./spike/RESULTS.md) and
> [`notes/EVAL.md`](./notes/EVAL.md).
>
> **Usable today** for a call taken on headphones with nobody else in the room.
> Outside that, see [Limits](#limits) — an open microphone records the room into
> the transcript, and the fix is not built.

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

An off-the-shelf embedding separates the operator from his own household,
measured on five minutes of his speech through the microphone the gate would run
on. His own speech reaches +0.68 to +0.89 with nothing else playing; 197
segments of household speech in the same room on the same microphone reach
+0.577 at the very top. That gap is real but it is not yet a margin — the
strongest household segment lands 0.003 under the operating point, which is a
property of this sample and not a number to ship on. Music across the room costs
about 0.15 and still loses two segments in eight.

**Another voice is the case that breaks it, and echo removal gets most of it
back.** With the far end coming out of the laptop speakers, the gate admits 1 of
the operator's 7 speech windows — it rejects him from his own meeting. Removing
the echo takes that to 6 of 7, on audio the echo filter was never fitted to,
while the same processing leaves 197 household segments unchanged to three
decimals. It is not a full repair: the recovered windows average +0.61 against
+0.78 for the same voice with nothing playing. On a second take with the far end
roughly 7 dB louder relative to him, recovery is 0 of 8 to 1. Seven windows, one
speaker, measured offline in closed form rather than with a real canceller; the
harness and every per-window score are in
[`spike/aec_bound.py`](./spike/aec_bound.py) and
[`spike/RESULTS.md`](./spike/RESULTS.md), including two figures earlier versions
of this paragraph got wrong.

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
  <img src="./assets/readme/pipeline.svg" width="100%" alt="Capture architecture: system audio through the audiotee Core Audio tap and the microphone through sounddevice both feed dual_capture.py at 16 kHz s16le, which timestamps each block on arrival and measures drift and bleed; MLX Whisper transcribes on-GPU from locally cached weights, producing Me/Them notes as markdown on disk.">
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

**The run that matters now** — a real two-person call, on headphones. Drift has
been measured; what has never been exercised is the Me/Them split with genuine
speech arriving on *both* legs at once. Every capture so far put all the real
words on one leg.

```sh
.venv/bin/python spike/dual_capture.py --list-devices       # pick your mic
.venv/bin/python spike/dual_capture.py --seconds 3600
```

Headphones do two jobs there: they remove the bleed that duplicates every line,
and they let the same capture give the first clean read on whether the split
survives real speech.

Over-running into an empty room is harmless — bleed is measured only across the
span where system audio was actually playing.

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
| [`spike/dual_capture.py`](./spike/dual_capture.py) | The spike: two legs, drift and bleed measurement, Me/Them transcript. |
| [`notes/EVAL.md`](./notes/EVAL.md) | Whether a local model invents things, measured against human-written summaries. |
| [`notes/summarize.py`](./notes/summarize.py) | Transcript to notes, with four fabrication checks and controls for the checks. |
| [`docs/screens-and-states.md`](./docs/screens-and-states.md) | Eight surfaces, their lifecycle states, and the five templates derived from them. |
| [`DIRECTION.md`](./DIRECTION.md) | Art direction. Thesis first; the device ledger stays empty until devices ship. |
| [`DESIGN.md`](./DESIGN.md) | Tokens, visual rules, engineering rules, and the Tauri-over-SwiftUI shell decision. |
| [`docs/teardown.md`](./docs/teardown.md) | How Circleback, Fireflies and Granola actually work, and why this is built the way it is. |

The images above are drawn from real captured envelopes and follow this repo's
own `DESIGN.md` palette — including its rule that amber means live capture and
appears nowhere else.

---

## Limits

- **An open microphone records the room.** Speech from people near you is
  transcribed and labelled as yours. Headphones do not help — they cut the far
  end out of your microphone, which is a different defect. The voiceprint gate
  that fixes this is written and measured but not yet wired into the capture, so
  today: be the only person in the room, or capture the system leg alone and
  accept unattributed notes.
- **On speakers, the gate would reject you too.** The far end returning through
  the room corrupts your own voiceprint, not just your transcript. Offline echo
  removal recovers most of it, measured; nothing is built. Headphones are the
  only configuration that works today, and that is why.
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
