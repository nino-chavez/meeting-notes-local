---
status: bounded-beta-direction
date: 2026-08-02
---

# Local Meeting Notes: the supported beta boundary

## Decision

Treat Local Meeting Notes as a private, headphones-first beta with deliberate
voice calibration and explicit capture-health evidence. Do not present it as a
general meeting recorder or claim that it reliably separates speakers in rooms,
on laptop speakers, or during overlapping speech.

The next evidence-bearing action is an ordinary headphone meeting with the
voice gate enabled, followed by a human reading the resulting note.

## What the current system does

The repository contains a local macOS capture and note pipeline that:

- records microphone and system audio separately;
- measures capture integrity, drift, and acoustic bleed;
- can remove speaker attribution when the split is unsafe;
- applies a calibrated voice gate to the microphone leg;
- transcribes and writes notes locally; and
- preserves provenance, failure, retention, and recovery state.

Passing mechanics establish that the files and evidence reconcile. They do not
establish that a meeting note is useful.

## What the measurements changed

The research found three product-shaping failures:

1. **Laptop speakers destroy the free speaker split.** The microphone hears the
   far end and duplicates dialogue across both legs. The system can drop unsafe
   labels, but it cannot recover a trustworthy speaker history from that capture.
2. **Other voices in the room change the note.** In the measured long capture,
   nearby room speech entered the microphone transcript and changed which real
   actions survived summarization even when the room's subject matter did not
   appear in the final note.
3. **A voice profile is not enough by itself.** The operator-specific threshold
   needs measured positive and permitted negative speech. Echo and overlap can
   still reject the operator's own speech, so the supported envelope remains
   headphones-first.

The notes evaluation also found that prompt examples can become fabricated
decisions and that over-cautious omission rules can remove useful actions. Both
are product defects even when the model names no fake person or number.

## Supported beta encounter

Before a supported meeting, the operator must:

1. complete two separated voice sittings;
2. provide a permitted negative speech sample;
3. choose from measured operating points with both error costs visible;
4. run a short canary and reconcile the capture, transcript, and gate evidence;
5. use headphones for the meeting; and
6. read the resulting note before treating it as useful.

The application must fail closed when capture or profile provenance does not
match. It must not silently guess who spoke.

## Evidence boundary

The repository contains measured capture, bleed, drift, voice-gate, echo, and
note-generation evidence. It still has no ordinary real meeting in which the
operator's own captured audio produced a note that a human judged useful.

No agent, unit test, waveform, token count, or generated summary can supply
that judgment. Consent, Apple signing, beta release, and broader supported
hardware remain separate human decisions.

## Next decision

Authorize only the bounded headphone beta encounter. Broaden the supported
envelope after real meetings establish useful notes, acceptable voice-gate loss,
recovery, retention, and operator burden.
