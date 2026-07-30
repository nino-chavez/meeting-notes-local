# Meeting notetakers: how they actually work, and what it takes to build one

Teardown of Circleback (desktop), Fireflies, and Granola — followed by a build
assessment against the `local-dictation` stack.

Research date: 2026-07-28. Provenance is marked per claim: **[primary]** = the
vendor's own product/API documentation or an OS/API reference; **[vendor]** =
marketing copy from a company selling the thing being described.

---

## The short version

A meeting notetaker is four layers. Only one of them is hard, and it is not the
one people assume.

| Layer | What it does | Difficulty |
|---|---|---|
| **Capture** | Get audio out of a live call | Medium — OS-specific, well-documented enough |
| **Speaker attribution** | Turn audio into *named* humans | **Hard** — this is the whole game |
| **ASR** | Audio → text | Commodity, already solved in `local-dictation` |
| **Notes + integrations** | Summary, action items, CRM/Slack push | Easy per-item, endless in aggregate |

Transcription is not the moat. Fireflies' moat is the searchable corpus plus the
CRM/ATS/Slack wiring. Circleback's and Granola's moat is bot-free capture that
does not embarrass you in a client call.

---

## Three ways to get audio out of a meeting

### 1. Meeting bot — Fireflies' default

A headless browser (or platform SDK client) joins the call as a visible
participant. Fireflies connects to Google Calendar or Outlook, detects scheduled
meetings, and dispatches a participant named "Fireflies.ai Notetaker" that
records from the moment it joins. **[vendor]**

Why anyone does this: the bot is *inside* the meeting, so it sees the platform's
participant roster and per-participant audio streams. That is where named
speaker labels come from — not from analyzing the waveform.

Costs: it is visible to everyone, some hosts must admit it from the waiting
room, and enterprise admin settings can block bots outright. **[vendor —
Recall.ai, who sells both bots and the alternative]**

### 2. Local OS capture — Circleback desktop, Granola

No bot. The app records the microphone and the computer's own audio output from
your machine.

**Circleback** captures "your microphone and computer audio directly from your
machine," optionally with the meeting window's video. Meeting detection is a
heuristic, not a calendar lookup: it fires a notification when it sees an app
start using the microphone, with auto-start after a countdown and auto-end when
mic activity stops. Works with anything you join on your computer — Zoom, Meet,
Teams, Webex, Discord, RingCentral. **[primary — Circleback support docs]**

**Granola** captures both streams and renders them as two sides of a transcript:
grey bubbles on the left for system audio (other people), green on the right for
your microphone. Transcription is *cloud*: audio is passed to a third-party
transcription provider. The audio is not stored — no recording is saved or
retrievable after the call. **[primary — Granola docs]**

Note the distinction, because the marketing in this category blurs it: *not
retained* is not *not transmitted*. Granola, Circleback, and Fireflies' bot-free
mode all send your meeting audio off the machine to be transcribed. Deleting it
afterward is a retention policy, not a locality guarantee.

**Fireflies also ships this mode** and its docs are the most honest description
of the tradeoff in the whole category — see the speaker-name section below.

### 3. First-party platform APIs — the newest path

- **Zoom RTMS** (Realtime Media Streams): WebSocket API giving live audio,
  video, transcript, and participant events. As of Jan 2026 an app's RTMS can be
  started without the host being present in the meeting. **[primary — Zoom
  developer docs/changelog]**
- **Google Meet Media API**: live RTP audio/video over WebRTC, distinct from the
  Meet REST API which only returns post-call artifacts. **[primary — Google
  developer docs]**

This path is cleanest where supported and useless where it isn't. It requires
app review, OAuth scopes, and per-platform work — which is precisely the
business Recall.ai exists to absorb.

---

## The load-bearing fact: speaker names come from the UI, not the audio

Recall.ai's Desktop Recording SDK requires three macOS permissions: Microphone,
Screen Recording, and **Accessibility** — the last one documented as needed "to
detect meeting windows and interact with them." **[primary — Recall docs]**
Accessibility is not needed to capture audio or screen. It is needed to read
another application's UI tree.

Granola confirms the same shape from the other side. Speaker tags are available
only on: Google Meet (via a **browser extension**), Zoom (macOS only), and the
iPhone app for in-person meetings. Everywhere else the transcript shows "Me" and
"Them," with the LLM "inferring speakers from contextual clues." **[primary —
Granola docs]**

Fireflies states the tradeoff outright. Recording via system audio instead of
the bot: speakers appear as *Speaker 1 / Speaker 2* instead of named
participants; named labels require the bot. No audio/video files are retained
either, and you cannot switch to the bot mid-meeting. **[primary — Fireflies KB]**

So the taxonomy of speaker attribution is:

1. **Free, from capture topology** — mic stream vs system stream gives you
   "me vs them" with zero ML. This is what Granola's green/grey bubbles are.
2. **Named, via platform** — bot in the call, or a browser extension / UI
   scraping reading the participant list and active-speaker indicator.
3. **Numbered, via diarization** — pyannote-class models clustering voice
   embeddings into Speaker 1..N. Real ML, and it still doesn't know their names
   without a mapping step.

Nobody in this category is doing (3) alone and calling it a feature. That is the
gap between a dictation tool and a notetaker.

---

## How local capture works at the OS level

None of these vendors document which macOS API they use. Circleback's support
docs say nothing about permissions or capture mechanism, and its optional
window-video recording implies ScreenCaptureKit for at least the video leg. What
follows is the OS surface any of them must be building on — not an attribution
of a specific choice to a specific product.

### macOS — Core Audio process taps

The modern path, and the one that does *not* require Screen Recording
permission. Sequence, from a working open-source implementation **[primary —
`insidegui/AudioCap`]**:

1. Declare `NSAudioCaptureUsageDescription` in Info.plist (not in the Xcode
   dropdown — type it manually). There is no public API to check or request the
   permission; it's prompted on first capture.
2. `kAudioHardwarePropertyTranslatePIDToProcessObject` — PID → `AudioObjectID`.
3. Build a `CATapDescription` for that object, keep its `uuid`.
4. `AudioHardwareCreateProcessTap` → tap object.
5. Create an aggregate device with `kAudioAggregateDeviceTapListKey` containing
   `[kAudioSubTapUIDKey: <uuid>]`, and `kAudioAggregateDeviceIsPrivateKey = true`
   so it doesn't appear system-wide.
6. `AudioHardwareCreateAggregateDevice`, read `kAudioTapPropertyFormat`, build a
   matching `AVAudioFormat`.
7. `AudioDeviceCreateIOProcIDWithBlock` for the callback; wrap the buffer list in
   an `AVAudioPCMBuffer` and write.
8. `AudioDeviceStart`, and unwind every `Create` with its `Destroy` on stop.

For **all** system audio rather than one process: pass an empty process list with
`isExclusive` set true, then feed the tap into an aggregate device. **[primary —
AudioTee]**

Version floor is muddy across sources: AudioTee says the API landed in macOS
14.2, AudioCap says 14.4. Treat **14.4** as the safe floor.

The alternative, **ScreenCaptureKit**, also yields system audio but is
screen-recording-shaped: you must configure a display/window/app target even for
audio-only, you get an unfiltered mix of every system sound including
notifications, and it asks for the scarier permission.

### Windows — WASAPI loopback

Standard, well-documented, no special permission prompt. Recall's docs note the
Desktop SDK needs no additional permissions on Windows at all. **[primary]**

### The part everyone underestimates

Neither OS gives you echo cancellation. If the user is on speakers rather than
headphones, the microphone stream contains the remote party's voice bleeding
back, which corrupts the clean "me vs them" split that the whole
two-stream design depends on. You also have to handle mid-call microphone
switching, mute-state tracking, and drift between the two streams. **[vendor —
Recall.ai, and self-serving, but technically correct]**

#### Measured 2026-07-29: correct, and for a more useful reason than stated

The claim came from a vendor selling echo cancellation, so it was worth checking
rather than repeating — especially since macOS has shipped a voice-processing path
since 10.15 (`AVAudioIONode.setVoiceProcessingEnabled`,
`kAudioUnitSubType_VoiceProcessingIO`), which Apple documents for macOS. Apple's
pages say "voice processing features" without naming the reference signal, and the
reference is the whole question: a canceller can only remove what it holds a copy
of.

`capture/aec-probe` settles it. It records the microphone over the same playback
twice, once with voice processing and once without, and compares each take against
a silent room recorded in the same mode — because voice processing also applies
noise suppression, and crediting that to the canceller would flatter it.

| far end rendered by | suppression of the far end on the mic |
|---|---|
| another process (`say`) | **−1.1 dB** — nothing |
| the probe's own engine (`--play`) | **+34.6 dB** — pushed below the room floor |

The second row is the control that makes the first trustworthy. Voice processing
is not misconfigured and not weak: given the reference, it removes 34.6 dB and
puts the far end 9.9 dB *under* the room noise. It simply cannot see audio another
process rendered. So the vendor was right, and the sharper statement is: **macOS
gives you excellent echo cancellation for audio you render yourself, and none for
Zoom's.** AEC3 with the system tap as its reference is the only path for a
notetaker that sits beside the meeting client.

Two things worth carrying forward. Enabling voice processing naively would make
the Me/Them split *worse*, not better: it suppressed the room floor by 4.5 dB
while leaving the far end untouched, so the bleed came out relatively more
prominent. And the 34.6 dB figure is a standing architectural option — a design
where the far end is routed through our own output rather than the meeting
client's would get platform-quality cancellation for free and need no canceller of
its own. That is a much larger product decision than this spike, but it should be
decided rather than defaulted past.

---

## Can we build this?

Yes. And `local-dictation` already contains more of it than is obvious.

### What carries over unchanged

| `local-dictation` component | Reuse in a notetaker |
|---|---|
| `mlx_whisper` + `whisper-large-v3-turbo` on-GPU | ASR, unchanged |
| `sounddevice` mic capture at 16 kHz | The mic half of the two streams |
| Ollama cleanup pass with transcript-as-data prompt hardening | Summarization, same injection-resistant framing |
| launchd daemon + menubar tray driving it via `launchctl` | Identical deployment shape |
| Graceful degradation when Ollama is down | Same principle for the notes leg |
| `HF_HUB_OFFLINE` once cached | Same "nothing phones home" guarantee |

That is the capture-transcribe-clean-deliver spine already built and running.

### What is genuinely new

**1. System-audio capture (the real work).** Core Audio taps are Swift/C, not
Python. The clean seam that matches `local-dictation`'s existing shape: a small
Swift helper binary that taps system audio and emits chunked PCM on stdout,
piped into the Python daemon. AudioTee is exactly this — mono output, 200 ms
chunks, JSON metadata with a hybrid JSON/binary mode when piped. Either vendor
it or write ~300 lines of Swift against the AudioCap recipe above.

**2. Two streams that don't agree on anything.** `local-dictation` records one
mic stream via `sounddevice` at 16 kHz mono, which is exactly what Whisper wants.
A Core Audio tap hands you the aggregate device's *native* format, read from
`kAudioTapPropertyFormat` — likely 48 kHz and not necessarily mono. So before
any transcription happens you need resampling and channel downmix on the system
leg, and the two streams are driven by independent clocks that will drift apart
over an hour. This is the first bug anyone hits, and it is invisible until the
transcript's two halves stop lining up.

**3. Long-form instead of utterance-form.** Dictation is a 10-second buffer
transcribed once. A meeting is 60 minutes and needs chunked streaming ASR with
VAD and timestamp stitching. This is a rewrite of the recording loop, not a
parameter change.

**4. Speaker attribution.** Two-stream capture gives Me/Them free. Past that:
   - **pyannote 3.1** — the benchmark, pure PyTorch, ~500 MB+ of runtime, poorly
     suited to always-on background use on a laptop.
   - **sherpa-onnx** — ONNX-exported diarization, Swift bindings, but CPU-only
     (no Apple Neural Engine), so higher latency and battery cost.
   - **FluidAudio** — Swift SDK running Parakeet ASR *and* speaker diarization on
     the ANE specifically to suit background/always-on workloads. MIT/Apache
     models, actively maintained (last push 2026-07-26, 2.5k stars). This is the
     strongest option for an Apple-Silicon-native build. **[primary — repo]**

   Note that all of these give you Speaker 1..N. Mapping those to names needs
   either a calendar-attendee list plus a one-time voice enrollment, or UI
   scraping via Accessibility.

**5. Summarization at meeting length.** A 60-minute transcript blows past a small
local model's usable context. Needs chunked map-reduce, not the single cleanup
call dictation uses.

**6. Storage and retrieval.** Dictation is fire-and-forget into the focused text
field. A notetaker needs a durable local store (SQLite), a browsable UI, and
search. This is the largest surface-area addition and has nothing to do with
audio.

### Prior art worth reading before writing anything

- **anarlog** (`fastrepl/anarlog`, formerly Hyprnote) — MIT, 8.9k stars, pushed
  today. Local-first notetaker: on-device transcription, canonical data in local
  SQLite, Markdown export, bring-your-own LLM including Ollama and LM Studio.
  This is the closest existing thing to "what we'd build." **[primary — repo]**
- **Meetily** — MIT community edition, macOS and Windows, Whisper and Parakeet
  local ASR.
- **Recall.ai's `cliff-notetaker`** — reference Electron app; useful as an
  architecture map even though it depends on their hosted API.

---

## Constraint that shapes the design, not a footnote

Silent capture of the far end of a call is a two-party-consent problem in
roughly a dozen US states. This is why Circleback ships notify-then-click-to-record
rather than always-on, and why Fireflies' bot is deliberately visible and
announces itself. Any build should treat "the other party knows" as a product
requirement, not a compliance afterthought.

---

## Recommendation

Build the core; don't build the attribution.

The high-value, low-risk slice is a direct extension of `local-dictation`:
Core Audio tap helper → dual-stream chunked MLX Whisper → Me/Them transcript →
chunked Ollama summary → Markdown in a local SQLite store. Everything except the
Swift helper and the storage layer already exists in the repo.

That version is fully local, which is a real differentiator against the
*commercial* products — Granola and Circleback both ship audio to a cloud
transcription provider, and Fireflies' bot-free mode still uploads. It is not a
differentiator against anarlog, which got to local-first transcription and local
SQLite storage first and is MIT-licensed. The honest argument for building
rather than adopting is stack fit, not novelty: we already run MLX Whisper,
Ollama, and the launchd+menubar daemon shape, so this is an extension of
something maintained rather than a new Tauri/Rust surface to own.

Named speaker attribution is where the effort curve turns vertical, and it is
the one thing you cannot solve locally without either UI scraping or voice
enrollment. Accept Me/Them, or fork anarlog, which has already paid the
Swift/Tauri plumbing cost.

---

## Is this a Blueprint initiative?

The definition and design work is real and worth doing. The stamped initiative
is the wrong vehicle for it. Those are separate answers and the first one is
easy to lose.

### The design work this product actually has

More than a dictation tool, and the capture leg is the small part. The Swift tap
helper is ~300 lines; the decisions around it are where the product lives:

- **The consent moment** — detection fires, and something has to happen before
  recording starts. This is the highest-stakes interaction in the product (see
  the two-party-consent constraint above), and Circleback, Granola and Fireflies
  each answered it differently.
- **Transcript presentation** — Granola's grey/green Me/Them bubbles are a
  deliberate design decision that converts a capture-topology limitation into a
  legible affordance. That reframing is design work, not plumbing.
- **Notes IA** — how meetings organize, relate, and get found later. This is the
  layer that decides whether the corpus is useful in six months or a junk drawer.
- **Summary contract** — what a note is *shaped* like: templates, action items,
  what gets dropped.
- **The menubar ↔ window model** — `local-dictation` needed none of this; it
  fires and forgets into the focused field.

### Why Blueprint isn't the right vehicle for it

Blueprint genuinely does define BRD/PRD and design the prototype — Stage 1's
design-discovery sub-track (surface audit, component audit, content-type
taxonomy, auth-boundary map), Stage 2's `prototype/DESIGN.md` with the L0–L4
atomic dictionary and reference-quality grading, Stage 5's four-doc package.
That is not the objection. The objection is artifact shape, and it's visible in
the methodology's own text:

- The surface audit inventories "every route + purpose + auth state + content
  source." A menubar daemon plus a notes window has no routes and no auth tiers.
- L4 is "page archetypes the L5 inventory revealed." Native window/panel/state
  structure is not page archetypes; L0 tokens and L1 atoms partially transfer,
  L4 doesn't.
- The Stage 2 testing baseline is eslint + `tsc` + Playwright + **Lighthouse-CI
  on Vercel preview URLs** + Gitleaks, justified explicitly by "the prototype is
  a stakeholder communication tool… clicked through by VPs."
- Stage 2's rule 3 is "lead with the positive — savings-first, growth-positive,
  neutral plan selection," an artifact of the methodology's origin in a
  commerce CX initiative.

Roughly half the Stage 1–2 gates would resolve to N/A. Not fatal, but that is
conformance friction paid for scaffolding that returns nothing here.

### Blueprint's own audit reaches the same place

From the re-foundation research (`research/refoundation/18-final-recommendation.md`,
2026-07-23), reporting the longitudinal Film Room audit — the closest precedent,
since Film Room is also a personal tool:

> The refounded core is validated as an evidence-control kernel; a complete
> end-to-end steering method is not yet demonstrated. The native contract kept
> claims honest and revisions isolated, but **the decisive UX strategy was
> produced by a separate Steering plan while Blueprint was frozen.**

Blueprint's strength is evidence control — keeping claims honest, gating on
provenance. On the initiative most like this one, the UX strategy came from
outside it. That is the methodology's own finding, not an outside critique.

Timing reinforces it: the root is mid-refoundation under `decisions/08`, and the
recommendation explicitly says "do not publish the research schema or change
stamped defaults yet." Stamping a new initiative now buys the old stage pipeline
while the semantic core is being replaced underneath it.

### What to do instead

Do the definition work; skip the stamp. **Done 2026-07-28** — artifacts live at
`~/Workspace/dev/tools/local-meeting-notes/`:

- `docs/screens-and-states.md` — the L5 inventory: eleven surfaces, their
  lifecycle states, and the five L4 templates derived from them.
- `docs/journeys.md` — what the operator does across days, and the gaps that only
  appear when the inventory is walked against a journey rather than read.
- `DIRECTION.md` — art direction. Five-block thesis, the constraints it
  generates, and an intentionally empty device ledger.
- `DESIGN.md` — tokens + visual rules + engineering rules + the shell decision.
  Verified to parse through impeccable's own reader.

Three things from Blueprint transferred cleanly and were lifted by hand:

1. **Inventory before authoring** — the L5-before-L4 rule, restated for a native
   app: enumerate every screen and state before designing any of them. The
   documented failure mode (bugs that "move" from surface to surface because the
   missing primitive was one layer up) is stack-agnostic.
2. **Codify rules before the first screen** — a short `DESIGN.md` covering both
   visual and engineering rules, so choices aren't made ad hoc per panel.
3. **Reference-quality grading** — when deciding which competitor's UX to copy,
   classify each as Convention track ("users expect this") or Quality track
   ("this is actually good"), with evidence. Granola's Me/Them bubble treatment
   should have to earn Quality-track citation before it gets copied.

Then the spike, which answers the two things no document can: clock drift and
resampling between two independently-clocked streams, and whether Me/Them holds
up across a week of real meetings.

Blueprint becomes defensible if the answer to that second question is no — named
speakers, calendar integration, storage and a real UI is a different-sized
product with genuine open questions. `greenfield` at **Tier 0** would be the
shape then: stamped `blueprint.yml`, ADRs + research, no portal, ≤ 1 week per
the tier ladder. Same if the intent is to ship publicly the way `browse-tool`
and `local-dictation` shipped, which creates the external reader the docs
machinery is built for.

---

## Sources

- https://circleback.ai/desktop
- https://support.circleback.ai/en/articles/10460578-record-meetings-with-the-desktop-app
- https://fireflies.ai/
- https://guide.fireflies.ai/articles/6666374717-how-to-record-meetings-without-a-bot-on-the-fireflies-desktop-app
- https://docs.granola.ai/help-center/taking-notes/transcription
- https://docs.recall.ai/docs/desktop-sdk
- https://www.recall.ai/blog/how-to-build-a-desktop-recording-app
- https://www.recall.ai/blog/how-to-build-a-meeting-bot
- https://www.recall.ai/blog/how-to-get-access-to-system-audio
- https://github.com/insidegui/AudioCap
- https://stronglytyped.uk/articles/audiotee-capture-system-audio-output-macos
- https://developer.apple.com/documentation/CoreAudio/capturing-system-audio-with-core-audio-taps
- https://developers.zoom.us/docs/rtms/
- https://developers.google.com/workspace/meet/media-api/guides/overview
- https://github.com/FluidInference/FluidAudio
- https://github.com/fastrepl/anarlog
- https://meetily.ai/
