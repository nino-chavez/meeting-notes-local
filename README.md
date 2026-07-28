<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="local-meeting-notes — no bot joins the call, no audio leaves the Mac. The far end and your voice arrive as two separate streams, shown as two live level tracks from a real 14-second capture at 16 kHz.">
</p>

A meeting notetaker that captures the call from your own machine. No bot joins
the meeting, and the audio never leaves the Mac — system audio comes through a
Core Audio process tap, your microphone comes through the same path
`local-dictation` already uses, and the two arrive as separate streams.

> **Status: design definition and a capture spike.** There is no app yet. What
> exists is a working two-leg capture, the measurements it produced, and the
> documents deciding what gets built. Start with
> [`spike/RESULTS.md`](./spike/RESULTS.md).

---

## What the spike found

<p align="center">
  <img src="./assets/readme/bleed.svg" width="100%" alt="On speakers, the two-stream split stops working. Two level tracks from one real capture: both rise during the same interval because the microphone is hearing the speakers. Peak envelope correlation +0.929, acoustic component −25 ms, consistent across three runs. The resulting transcript places the same sentence on both legs, once labelled Me and once labelled Them.">
</p>

Capturing the microphone and the system separately is supposed to give you
"me versus them" for free. It does — **on headphones**.

On speakers it does the opposite. The microphone is a correct recording of the
room, and the room contains the far end, so every sentence lands on both legs.
The transcript then reads as two people agreeing with each other word for word,
and nothing downstream can tell that it never happened. That is worse than
having no speaker labels at all.

So the product treats this as a measurement, not a caveat: correlation is
checked at the start of every capture, and when it is high the tool stops
claiming a split rather than fabricating a dialogue.

**Clock drift is still an open question.** A short capture cannot answer it —
sample counts are exact but each wall-clock endpoint is only known to about one
block period, so 22 seconds of audio carries ±9 000 ppm of uncertainty against a
real drift of tens of ppm. It needs roughly a 67-minute run. The tool now prints
its own error bars and refuses to project an hourly figure it cannot support.

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

**The run that matters** — alongside a real meeting, on headphones, long enough
for drift to become measurable:

```sh
.venv/bin/python spike/dual_capture.py --seconds 4200 --no-transcribe
```

Headphones do two jobs there: they remove the bleed that duplicates every line,
and they let the same capture give the first clean read on whether the Me/Them
split survives real speech.

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
| [`docs/screens-and-states.md`](./docs/screens-and-states.md) | Eight surfaces, their lifecycle states, and the five templates derived from them. |
| [`DIRECTION.md`](./DIRECTION.md) | Art direction. Thesis first; the device ledger stays empty until devices ship. |
| [`DESIGN.md`](./DESIGN.md) | Tokens, visual rules, engineering rules, and the Tauri-over-SwiftUI shell decision. |
| [`docs/teardown.md`](./docs/teardown.md) | How Circleback, Fireflies and Granola actually work, and why this is built the way it is. |

The images above are drawn from real captured envelopes and follow this repo's
own `DESIGN.md` palette — including its rule that amber means live capture and
appears nowhere else.

---

## Limits

- **macOS only.** Core Audio process taps are 14.4+. The Windows equivalent is
  WASAPI loopback and is not implemented.
- **Speaker labels stop at "me" and "them."** Named participants come from a bot
  in the call or from scraping the meeting UI, never from the audio alone. See
  [`docs/teardown.md`](./docs/teardown.md) for how the commercial products get
  them.
- **Recording a call silently is a two-party-consent problem** in roughly a dozen
  US states. Tell the room.

## License

The vendored tap is MIT, Copyright © 2025 Nick Payne — see
[`capture/NOTICE`](./capture/NOTICE). The rest of this repository has no license
declared yet, which means default copyright applies.
