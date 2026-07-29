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

## Measured on a real speaker-mode take

117 seconds, built-in mic and speakers, a podcast playing as the far end while five
cued passages were read over it. The reference is the actual system tap, so this
carries the clock drift and D/A path the file-reference measurement above did not.

Echo-only suppression, over 19 s of far-end-active silent interval:

| condition | suppression |
|---|---|
| linear (offline estimate) | +3.5 dB |
| masked (offline estimate) | +7.6 dB |
| **AEC3** | **+25.3 dB** |
| **AEC3 + agc + ns** | **+29.8 dB** |

And on the voiceprint, over the segments inside the reading intervals, mean score
went **+0.064 raw → +0.386 with AEC3** — six times better, and still short of the
+0.580 gate, so nothing was admitted.

### Transcript retention, which is the number that matters

Measured by [`../retention.py`](../retention.py): the passages were fixed before the
audio existed, so how many of their content words come back is external ground
truth. `leakage` is the share of transcribed content words belonging to the far end
instead.

| condition | segments | passage recall | far-end leakage |
|---|---|---|---|
| raw microphone | 23 | **0.0%** | **80.5%** |
| AEC3 | 10 | **14.7%** (0–35%) | **0.0%** |
| AEC3 + agc + ns | 4 | 0.0% | 5.0% |

Three things fall out of that, and only the first is good news.

**Raw is not degraded, it is inverted.** Zero of the operator's words survived any
interval, and four fifths of what did transcribe belonged to the playback. The
microphone leg is a recording of the far end with a person faintly behind it. This
is the first time "speaker bleed destroys the Me/Them split" has been stated in
words recovered rather than correlation coefficients.

**AEC3 removes the wrong words completely.** Leakage 80.6% → 0.0%. Nothing of the
far end reaches the transcript. That is the whole job of the canceller and it does
it.

**But it does not yet bring the right words back.** 13.3% recall is not a usable
transcript. The echo is gone and the operator is still mostly missing, which is a
different failure from the one this project has been chasing and cannot be fixed by
cancelling harder.

The far end sat about 7 dB *louder* than the operator here — measured at −7.0 dB
signal-to-echo — which is a punishing ratio and the reason for the sweep below.

The gain controllers make retention **worse**: they take it to zero, on a sixth of
the segments, and let 5% leakage back in. They were off by default for a
level-comparison reason; that default now has a retention reason too, which is a
better one.

## The level sweep

Three takes, same seat, same passages, same reading voice — the operator's own level
held within 5 dB across all three (−39.0, −36.6, −34.3 dBFS), so the axis really is
the playback. Run by [`../sweep.py`](../sweep.py), which measures the ratio per take
from the recording's own silent and speaking intervals rather than trusting the
volume slider.

The ceiling matters more than any single row, so it is measured too: the same
passages read with **no far end at all** recover **78.9%** of their content words
(68–91% across five intervals). ASR loses a fifth of this vocabulary unaided. Every
figure below should be read against 78.9%, not against 100%.

| S/E | raw recall | AEC3 recall | raw leakage | AEC3 leakage |
|---|---|---|---|---|
| **+9.3 dB** | 41.4% | 40.2% | 30.1% | **0.0%** |
| **+1.4 dB** | **0.0%** | **30.7%** | **98.1%** | 2.0% |
| **−7.0 dB** | 1.8% | 8.0% | 66.7% | 0.0% |

**Leakage is solved, unconditionally.** 30–98% of the raw transcript's content words
belong to the far end; after AEC3 it is 0–2% at every level. The canceller does that
job completely and it does not depend on the ratio.

**Recall is rescued in the middle and untouched at the top.** At +1.4 dB the raw
transcript is a recording of the other party — 0% of the operator's words, 98%
someone else's — and AEC3 turns that into 30.7%. That is the single most valuable
number here. At +9.3 dB the raw microphone already reaches 41.4% and AEC3 gives
40.2%, which is a wash: where the echo is quiet, cancellation neither helps nor
meaningfully hurts recall, and its whole contribution is removing the other party.

**Nothing reaches the clean ceiling.** The best case is 40% against 78.9% — any
far-end presence costs about half the recoverable words, and cancellation does not
give them back. It prevents the collapse; it does not restore clean performance.

That is an envelope rather than a verdict, and it is a shippable one: **speaker mode
with AEC3 gives trustworthy attribution and a partial transcript.** Nothing of the
far end lands on the operator's leg, which is what the Me/Them split needs. Roughly
half the words are missing, which is survivable for notes and gist and is not
survivable for a verbatim record. Below about +1 dB signal-to-echo the transcript
thins fast, and that is the point to warn on.

## What this does not establish

The three gaps this section used to list — no double-talk, a file rather than a
tapped reference, no retention or admission figures — are closed by the real take
above. What replaced them is larger:

- **One axis of the matrix, one room, one microphone, one voice.** The level sweep
  ran; distance, room acoustics, a second speaker, and headphones did not. Three
  points on one axis is an envelope sketch, not an envelope.
- **Half the words are missing even at the best ratio**, and the sweep does not say
  why. It could be the microphone, the residual after cancellation, or a floor on
  what any canceller can hand an ASR. Distinguishing those decides whether speaker
  mode improves further or is done improving.
- **The gate never admitted anything.** AEC3 moved the voiceprint from +0.064 to
  +0.386 against a +0.580 threshold. Whether the remaining gap closes with a better
  level ratio or whether the threshold is wrong for cancelled audio is unmeasured,
  and picking the second answer without evidence would be tuning the ruler.
- **Nothing real-time.** Every figure here is offline, over whole recordings, with
  the entire far end available. AEC3 is a real-time algorithm being run in a batch
  and that is a fair use of it, but the product has to do this live, on a stream,
  inside a capture that cannot pause.

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
