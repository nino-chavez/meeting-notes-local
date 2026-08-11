# Real 1:1 meeting capture handoff

## What this run proves

This run supplies one short, real conversation for the interaction review. It
tests whether the command-line capture preserves both sides of a headphone call,
writes a channel-attributed transcript, and finishes with internally consistent
artifacts.

It does not test an application, automatic notes, the voiceprint gate, speaker
playback, or beta readiness. No voice profile, Ollama model, API key, or other
secret is required.

Use a three-minute portion of the meeting. Recording more private speech does not
strengthen this gate.

## Machine requirements

- Apple Silicon Mac with Metal available
- macOS 14.4 or later
- Xcode Command Line Tools with Swift 5.9 or later
- Python 3.11 or later; Python 3.13 is the measured path
- Internet access during setup for Python packages and the first Whisper model
  download, which is approximately 1.6 GB
- Enough free disk space for that model plus two WAV files and their transcript
- Headphones connected before capture and selected as the default output
- A microphone selected before capture
- Terminal permission for Microphone and System Audio Recording

An Intel Mac, virtualized Mac without Metal, speaker playback, or another person
in the operator's room is outside this test.

## Install from the clean repository

```sh
git clone git@github.com:nino-chavez/yawn-app.git
cd yawn-app

(cd capture/audiotee && swift build -c release)

python3.13 -m venv .venv
.venv/bin/python -m pip install -r spike/requirements.txt
```

Confirm the checkout and deterministic controls before opening a meeting:

```sh
test "$(git rev-list --max-parents=0 --all | sort -u)" = \
  "212a0e154895427536001fdb3d91b3e0fa0965c1"
test -z "$(git status --porcelain --untracked-files=all)"

.venv/bin/python spike/dual_capture.py --self-test
.venv/bin/python spike/verify_capture.py --self-test
.venv/bin/python spike/dual_capture.py --list-devices
```

The root check is the history boundary. It allows ordinary development commits
but refuses a checkout containing a reachable root from the retired repository.
Stop if it fails.

## Warm the cold machine before the meeting

Close applications that may produce notifications or audio. Turn on Do Not
Disturb. Connect the headphones and set the intended microphone and default
output before starting the command.

Play audio you own or may lawfully use, speak into the microphone, and run a
non-sensitive 15-second capture:

```sh
.venv/bin/python spike/dual_capture.py --seconds 15
```

The first run may prompt for Microphone and System Audio Recording access and
download the Whisper model. Grant permissions under System Settings > Privacy &
Security if the terminal does not prompt.

Do not continue until all of these are true:

- the printed microphone and default output are the devices you intended;
- both level meters move during the smoke capture;
- the final `session manifest` line says `complete`;
- the transcript reports `attribution: channel`; and
- the verifier passes for the output directory printed by the command. For this
  interaction test, it also refuses an exactly silent leg or a transcript that
  contains no channel-attributed speech from either participant.

```sh
.venv/bin/python spike/verify_capture.py --interaction-canary \
  "$HOME/Library/Application Support/local-meeting-notes/captures/<printed-directory>"
```

Delete the non-sensitive smoke directory after it passes.

## Capture the consented 1:1

1. Be the only person in the operator's room.
2. Join the remote meeting with capture off.
3. Tell the other participant that both sides will be recorded locally for this
   product test and obtain their explicit consent.
4. Record that consent was obtained before capture in a separate private note.
5. Start the three-minute capture:

```sh
.venv/bin/python spike/dual_capture.py --seconds 180
```

Omitting `--out` creates a unique owner-only directory under
`~/Library/Application Support/local-meeting-notes/captures`. Add
`--input-device '<exact name or index>'` only when the displayed default
microphone is wrong.

The terminal prints transcript text. Do not share its scrollback, pipe it to a
log, or capture it in screenshots.

## Verify and return the packet

Run the verifier against the exact directory printed when capture began:

```sh
.venv/bin/python spike/verify_capture.py --interaction-canary \
  "$HOME/Library/Application Support/local-meeting-notes/captures/<printed-directory>"
```

Stop if the verifier refuses the packet. A failed or incomplete meeting remains
private evidence, but it cannot supply the interaction review.

Return the whole capture directory through an encrypted, owner-controlled
channel that preserves file bytes and does not publish a share link. Do not add
it to Git, GitHub, an issue, a chat attachment, or routine terminal logs. The
packet contains:

- `session.json`
- `transcript.json`
- `mic.wav`
- `system.wav`
- `mic-segments.json`
- `system-segments.json`

Send this metadata separately from the packet:

- confirmation that consent preceded capture;
- confirmation that headphones were used and nobody else was in the room;
- `git rev-parse HEAD` and `git rev-parse 'HEAD^{tree}'`;
- the exact capture command;
- `sw_vers`, `python3.13 --version`, and `swift --version`; and
- the microphone and default-output names printed before capture.

The next step happens on the review machine. An agent may draft 3-12 decisions,
actions, proposals, or open questions with exact transcript locators. The
operator must confirm the wording and evidence in a separate digest-bound
approval before any private click-through is built.
