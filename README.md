# local-meeting-notes

A meeting notetaker that keeps the audio on the machine. No bot joins the call;
system audio is captured through a Core Audio process tap and the microphone
through the same path `local-dictation` already uses, so the far end and the near
end arrive as two separate streams.

Design definition first, code second. Nothing here is a product yet — there is a
capture spike and the documents that decide what gets built.

## Where things are

| Path | What it is |
|---|---|
| [`DIRECTION.md`](./DIRECTION.md) | Art direction. Thesis first, device ledger empty until devices ship. |
| [`DESIGN.md`](./DESIGN.md) | Tokens, visual rules, engineering rules, and the Tauri-over-SwiftUI shell decision. Frontmatter verified against impeccable's reader. |
| [`docs/screens-and-states.md`](./docs/screens-and-states.md) | Eight surfaces, their lifecycle states, and the five templates derived from them. |
| [`spike/RESULTS.md`](./spike/RESULTS.md) | What the capture spike proved and, as importantly, what it could not. |
| [`docs/teardown.md`](./docs/teardown.md) | How Circleback, Fireflies and Granola actually work, and why this is built the way it is. |
| [`capture/audiotee/`](./capture/) | Vendored MIT tap binary — see [`capture/NOTICE`](./capture/NOTICE). |

## Setup

Requires macOS 14.4 or later, Xcode Command Line Tools, and Python 3.10+.

```sh
git clone <this repo> && cd local-meeting-notes

# 1. Build the tap binary (~35 s).
(cd capture/audiotee && swift build -c release)

# 2. Python environment.
python3 -m venv .venv
.venv/bin/pip install -r spike/requirements.txt
```

The first `mlx-whisper` run downloads `whisper-large-v3-turbo` (~1.6 GB) to
`~/.cache/huggingface`. To skip that entirely, run with `--no-transcribe` — the
drift and bleed measurements need only `numpy` and `sounddevice`.

**Permissions.** The terminal needs System Audio Recording permission, and
Microphone. The first run prompts for both; some terminal emulators never
prompt, in which case grant them ahead of time under System Settings → Privacy &
Security. If the tool runs but records silence, that is what happened.

## Running the capture spike

```sh
.venv/bin/python spike/dual_capture.py --seconds 60
.venv/bin/python spike/dual_capture.py                    # until Ctrl-C
.venv/bin/python spike/dual_capture.py --no-transcribe    # measure only
```

### The run that matters

Drift cannot be measured in a short capture (see below). To close that question,
run it alongside a real meeting, **on headphones**, for the full length:

```sh
.venv/bin/python spike/dual_capture.py --seconds 4200 --no-transcribe
```

Headphones matter for two reasons: they remove the bleed that otherwise
duplicates every line of transcript, and they let the same run give a first clean
read on whether the Me/Them split holds up on real speech. Drop
`--no-transcribe` if you want that transcript, and expect roughly a minute of
processing per 10 minutes of audio at the end.

Recording a meeting silently is a two-party-consent problem in about a dozen US
states. Tell the room.

## The two things worth knowing before building on this

**Me/Them is conditional.** On headphones the two-stream split separates you from
the far end for free. On speakers the microphone hears the speakers — measured
envelope correlation +0.93 — and every utterance lands in the transcript twice,
once per label. The product has to detect that and stop claiming a split rather
than fabricate a dialogue.

**Clock drift is still an open question.** A short capture cannot measure it: the
uncertainty is ±9 000 ppm over 22 seconds against a real drift of tens of ppm. It
needs roughly a 67-minute run before the number means anything, and the tool now
refuses to project an hourly figure it cannot support.
