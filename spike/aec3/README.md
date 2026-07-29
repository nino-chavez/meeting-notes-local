# AEC3, offline

Runs WebRTC's AEC3 over a recorded pair of legs and writes the cancelled
microphone, so a real canceller can be scored on the same table as the offline
estimate in [`../aec_bound.py`](../aec_bound.py).

This exists because the offline estimate was never the product. It was a bound —
"is a canceller worth building" — and it answered yes. `../RESULTS.md` is frozen at
that answer. Everything here is the beginning of the replacement, and it is
measurement, not acceptance.

## What it does

Follows the vendor's own `examples/run-offline.cpp`: the far end goes to
`ProcessReverseStream`, the microphone to `ProcessStream`, block by block in
capture order. That ordering is the contract — AEC3 estimates the echo path from
the reference it has already seen, so feeding it the whole far end up front, or the
near end first, measures something else.

Two deliberate departures from that example:

- **WAV at 16 kHz, not headerless PCM at 48 kHz.** That is what this project
  records and what the gate embeds. AEC3 runs natively at 16 kHz, so nothing is
  resampled and no resampler artefact enters the comparison.
- **The gain controllers are off by default**, where the example turns them on.
  This output gets compared against conditions whose levels are otherwise
  untouched; an adaptive gain would move every admitted window's level and read as
  recovery the echo canceller did not do. `--agc` and `--ns` enable them for the
  operating matrix, where the question is what the product should ship rather than
  how much echo was removed.

## Measured 2026-07-29

Ten seconds of echo-only material: the far end playing through the speakers,
nothing said in the room, recorded by
[`../../capture/aec-probe`](../../capture/aec-probe). Levels are the 90th
percentile of 25 ms frame RMS, and the reference point is a silent room recorded
on the same machine at the same volume.

| | level | suppression | vs the room floor |
|---|---|---|---|
| untreated echo | −22.8 dBFS | — | **+24.7 dB above** |
| AEC3, canceller only | −55.7 dBFS | **+32.9 dB** | 8.2 dB below |
| AEC3 + agc + ns | −60.7 dBFS | +37.9 dB | 13.2 dB below |
| macOS voice processing | −61.9 dBFS | +39.1 dB | 14.4 dB below |

AEC3 lands within about 6 dB of the platform canceller on identical audio, and
within 1.2 dB once the gain controllers are on. Both push the echo below the room
noise. The macOS row is there as a reference point only — it cannot be used, for
the reason in [`../../docs/teardown.md`](../../docs/teardown.md): it cancels audio
the enabling process rendered itself and nothing of Zoom's.

**And it discriminates.** Handed a reference unrelated to the microphone's content,
over the same interval:

| reference | removed |
|---|---|
| the audio that was actually playing | +32.3 dB |
| unrelated room noise | **+0.0 dB** |

That control is the one that matters most. A canceller that attenuated everything
would post the same suppression figure and destroy the voice the product exists to
keep. AEC3 removes what correlates with its reference and leaves the rest.

## What this does not establish

Nothing here has been through the gate or a transcript, and three of the four
conditions that decide the product are untested:

- **No double-talk.** The room was silent by design, so this measures suppression
  and says nothing about preserving the operator's voice underneath the echo. That
  is the hard case and the only one the product needs.
- **The reference is a file, not a tap.** `far.wav` is the source that was played,
  not a recording of what the device rendered. No D/A path, no clock drift between
  the legs, no start skew. The real reference is `system.wav` from a dual capture,
  which is measurably a few thousand samples adrift over two minutes.
- **No voiceprint admission and no transcript retention.** Decibels are not the
  metric the product ships on. Whether the gate admits the operator, and whether
  words survive, comes next and on the cued protocol.

## Building

AEC3 is not vendored here and there is no Homebrew formula:

```sh
git clone --depth 1 https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing.git
cd webrtc-audio-processing
meson setup build -Dprefix=$PWD/../wap-install --buildtype=release
ninja -C build install
export PKG_CONFIG_PATH=$PWD/../wap-install/lib/pkgconfig
```

Needs meson, ninja, pkg-config and abseil ≥ 20240722 (`brew install meson ninja
pkg-config abseil`). Version 2.1 packages the AudioProcessing module including
AEC3, and builds clean on arm64.

The prefix must **not** be inside the source tree on macOS. The repo ships a file
called `INSTALL`, and on a case-insensitive filesystem `install/` collides with it;
meson surfaces that as a bare `NotADirectoryError`.

Then:

```sh
make
./aec3_offline --mic mic.wav --ref system.wav --out cancelled.wav
```

## Scoring it against the offline estimate

`aec_bound.py --condition` takes the cancelled WAV as a fourth condition, so AEC3
meets the same window set, the same voiceprint and the same noise-floor check as
`raw`, `linear` and `masked`:

```sh
./aec3_offline --mic take/mic.wav --ref take/system.wav --out take/aec3.wav

python3 ../aec_bound.py --take calib=take --enroll enroll \
  --segments calib=take/mic-segments.json \
  --protocol calib=take/protocol.json \
  --condition aec3=calib:take/aec3.wav \
  --fit-mode prefix --fit-before 30
```

One run, one table. Scoring the two separately is how two figures end up
describing different windows and get quoted as though they described the same
ones. The condition's digest goes in the artifact: it is derived audio, so nothing
can bind it to the recording the way segments and protocols are bound, and the
digest is what makes the run reproducible instead.

A condition that is shorter than the microphone — which a block-based canceller
legitimately is, since it returns whole blocks of the shorter leg — shrinks the
scored region for *every* condition, and the run says by how much. Comparing a
condition over a window another condition does not cover is comparing different
audio.
