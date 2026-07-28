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
| [`capture/audiotee/`](./capture/) | Vendored MIT tap binary — see [`capture/NOTICE`](./capture/NOTICE). |

Background research on how the commercial products work is at
`~/Workspace/dev/wip/meeting-notetaker-teardown.md`.

## Running the capture spike

Build the tap binary once:

```sh
(cd capture/audiotee && swift build -c release)
```

Then capture both legs, measure clock drift and speaker bleed, and print a
Me/Them transcript:

```sh
python spike/dual_capture.py --seconds 60
python spike/dual_capture.py                     # until Ctrl-C
python spike/dual_capture.py --no-transcribe     # capture and measure only
```

Dependencies are in [`spike/requirements.txt`](./spike/requirements.txt); it runs
as-is under `local-dictation`'s venv, which already has the Whisper weights
cached.

macOS 14.4 or later, and the terminal needs System Audio Recording permission.
The first run prompts; some terminal emulators do not, in which case grant it
ahead of time in System Settings.

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
