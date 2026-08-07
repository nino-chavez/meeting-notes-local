# permission-probe

Reports this application's two capture permissions without recording anything.

It exists because first run (`docs/screens-and-states.md` § H) has to reach a
`ready` state meaning "permissions exist", and nothing in the app could measure
that. The microphone check lived inside `MeetingCaptureCLI`'s start path and the
system-audio check is the status of the tap-create call, so both were discovered
by trying to record. A first-run screen cannot record, and north-star feature 10
forbids a surface claiming a state it cannot measure.

Separate executable, not a mode on `MeetingCaptureCLI`: that CLI's argument
contract is exactly four inherited file descriptors and is frozen
(`vertical-slice.md` Wave B). `aec-probe` is the precedent in this directory —
a standalone package answering one question, writing no product record.

## The two permissions are not symmetric

| | microphone | system audio |
|---|---|---|
| status API | `AVCaptureDevice.authorizationStatus(for: .audio)` | none |
| can be checked without prompting | yes | **no** |
| how the answer is obtained | read the status | create a tap and destroy it |

macOS 14.4's Core Audio process taps report authorization through the status of
`AudioHardwareCreateProcessTap` itself. `capture/audiotee`'s tap manager learns it
exactly that way, and no query API is used anywhere in this tree. So system audio
has no check-without-asking mode.

This probe does not paper over that. `status` reports the microphone truthfully
and reports system audio as `unmeasured`, with the reason. A caller that needs the
system-audio answer must run `request-system-audio` and accept that doing so may
raise the prompt. Reporting a guess instead is the lie feature 10 exists to
prevent.

## Usage

```sh
swift build
./.build/debug/permission-probe status                 # microphone only; never prompts
./.build/debug/permission-probe request-microphone     # prompts if undetermined
./.build/debug/permission-probe request-system-audio   # creates and destroys one tap
```

One line of JSON on stdout. Exit 0 whenever the probe ran to completion —
**including when a permission is denied**, because a denial is an answer and not a
probe failure. Exit 2 means the probe could not answer.

```json
{"action":"status","microphone":"authorized","schema":"permission-probe/1",
 "system_audio":"unmeasured",
 "system_audio_detail":"run request-system-audio; creating a tap is the only check"}
```

`microphone` is one of `authorized`, `denied`, `restricted`, `not-determined`,
`unknown`. `request-microphone` also reports `prompted`, which is false when the
status was already settled — `requestAccess` returns immediately from `denied`
without showing anything, which is why a denied operator has to be sent to System
Settings rather than told to press the button again.

## What it does not do

Creating and destroying a tap reads no audio buffer, builds no aggregate device,
writes no file, and touches no product record. The binary opens no capture
directory and takes no descriptors.

**Permissions belong to the binary that asks.** Run from a terminal, this reports
the terminal's permissions, not the app's — useful for checking the probe, useless
for checking Yawn. The answer is only about the app when the probe runs from inside
the signed bundle.
