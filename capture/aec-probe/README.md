# aec-probe

Records the microphone to a 16 kHz mono WAV, with or without macOS voice
processing, so the two can be compared over the same playback.

It exists to answer one question before any canceller gets built: **does macOS
remove another application's speaker output from the microphone?** If it does, a
notetaker on speakers needs no echo canceller of its own. If it does not, WebRTC
AEC3 with the system tap as reference is the only path, and that is days of work
to find out the wrong way.

## Answer

No — and the reason matters more than the answer.

| far end rendered by | suppression of the far end on the mic |
|---|---|
| another process (`say`) | **−1.1 dB** — nothing |
| this probe's own engine (`--play`) | **+34.6 dB** — pushed below the room floor |

The second row is the point. It is the positive control that makes the first row
evidence rather than a shrug: voice processing is not misconfigured and not weak.
Given a reference it removes 34.6 dB and puts the far end 9.9 dB *under* the room
noise. It simply cannot see what another process rendered.

Also measured, and load-bearing: enabling voice processing suppressed the room
floor by 4.5 dB while leaving the far end untouched, so the bleed came out
*relatively louder*. Switching it on naively would make the Me/Them split worse.

Full write-up in [`docs/teardown.md`](../../docs/teardown.md).

## Use

```bash
swift build -c release

# The comparison. Play the far end from another process for the first pair.
.build/release/aec-probe --out vp-off.wav --seconds 10
.build/release/aec-probe --out vp-on.wav  --seconds 10 --voice-processing

# The positive control: the probe renders the far end itself.
.build/release/aec-probe --out own-on.wav --seconds 10 --voice-processing --play far.wav

# A silent room in each mode, since voice processing moves the floor too.
.build/release/aec-probe --out room-off.wav --seconds 6
.build/release/aec-probe --out room-on.wav  --seconds 6 --voice-processing
```

Compare each take against the room recorded in **its own mode**. Voice processing
applies noise suppression and gain as well as cancellation, so judging a treated
take against an untreated floor credits the canceller with whatever the gain
change did.

`--diagnose` records nothing and prints the level of every input channel instead.
Enabling voice processing changes the input format — on this machine from 1
channel to 9 — and the layout is undocumented, so this is how you find the
processed microphone rather than guessing. `--channel` picks which one to write.

## What it refuses to do

Every guard here exists because the unguarded version produced a plausible wrong
answer during development, and each of those answers pointed the same way — toward
"the canceller did nothing":

- **A refused request is not a treated take.** If `setVoiceProcessingEnabled`
  throws, or the node reports the feature off afterwards, it exits rather than
  writing a file that would be compared as if it were treated.
- **A short file is a failure.** The first converter signalled `.endOfStream`
  after each buffer, which closes the stream permanently, so a ten-second take
  wrote 0.10 s. Next to a full-length take that reads as a quiet room.
- **The file is reopened before it is trusted.** `AVAudioFile` fixes up the WAV
  header's data-chunk length when it deallocates and nothing else does. Held to
  process exit it leaves 318 KB of audio that every reader sees as zero frames.
- **Many-to-one conversion needs an explicit channel map.** Without one, the
  9-channel voice-processing format converted to digital silence — RMS exactly
  zero, which beside an untreated take reads as *perfect* cancellation.
