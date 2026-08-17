# Yawn product roadmap — trust before reach

Status: active product direction as of 2026-08-16.

This roadmap sequences product work. It does not claim that a listed feature is
shipped. The current product contract remains [the product brief](product-brief.md).

## The decision

Yawn should make the transcript easier to trust and correct before it expands
into broader meeting intelligence.

The current work is wiring the new local vocabulary into review, then adding
recording-quality recovery. Speaker correction now reaches generated notes in
source and in the packaged Preview bundle. Cross-meeting questions can follow
once the source record is reliable.
Cloud accounts, automatic call detection, meeting bots, and live meeting chat do
not enter the roadmap through competitor comparison alone.

## What the live apps changed

The 2026-08-16 desktop comparison checked Granola 7.478.0, Wispr Flow
1.6.447, and the installed Yawn 0.5.7 without starting a recording or changing
meeting data. It produced three decisions.

**Evidence labels.** “Observed” means the rendered desktop app was inspected
directly. “Verified in source” means the current Yawn code or product brief was
read. “Inferred” means the recommendation combines those two evidence classes;
it is product judgment, not a claim about an unobserved competitor behavior.

| Journey | Granola — observed | Wispr Flow — observed | Yawn — observed or source-verified | Yawn decision — inferred |
|---|---|---|---|---|
| Home and history | Meeting library leads; search and secondary workspace structure remain nearby | Product hub exposes history, usage, settings, and adjacent tools | Installed 0.5.7 returned from a readable transcript to an empty library; the 0.5.8 preview continuity journey passed | Keep one local meeting library and make continuity a release gate |
| Recording entry | Capture stays subordinate to the meeting and note journey | Notetaker entry is one part of a larger dictation product | Explicit consent and start action are source-verified product boundaries | Preserve explicit consent; do not add automatic call detection |
| Review attention | Generated note occupies the primary reading path; transcript and search disclose nearby | Repair and settings surfaces make learned words and retry actions visible | Summary-first note, separate personal notes, and transcript evidence are source-verified | Keep the note primary; disclose transcript, provenance, and repair at the point of doubt |
| Correction and recovery | Source context stays available beside generated material | A failed Insights view exposed one retry and recovered; dictionary entries are visible and editable | Speaker correction now preserves the transcript and records a separate local operation | Add exact repair actions, local vocabulary, and versioned retries without replacing the last usable result |
| Expansion pressure | Team spaces, templates, connectors, sharing, and chat broaden the workspace | Scores, streaks, quotas, referrals, transforms, and scratchpad broaden the product hub | Yawn is a private local meeting reviewer | Do not copy adjacent engagement, collaboration, or account architecture |

**Take Granola's meeting posture, not its workspace.** Granola keeps the note in
the main reading path and puts the transcript, transcript search, and source
context behind nearby controls. Yawn should preserve that progressive
disclosure. It should not add team spaces, connectors, sharing defaults,
calendar organization, chat, or templates to reproduce Granola's information
architecture.

**Take Wispr Flow's repair clarity, not its product hub.** A failed Insights
view exposed one **Try again** action, and the retry recovered the view. Its
dictionary also makes learned words visible and editable. Those are useful
models for Yawn's exact-repair and local-vocabulary work. Usage scores, streaks,
quotas, referrals, transforms, and a separate scratchpad solve other jobs and
stay out.

**Treat journey continuity as a release gate.** The installed Yawn identified
itself as 0.5.7 while this source declares 0.5.8. A completed transcript was
readable in the installed app, but **Back to Meetings** opened an empty library.
That observation does not prove the 0.5.8 source has the same defect. It does
prove that a packaged build must pass the complete-meeting, reopen-from-library
journey before its note or library work counts as shipped.

## The source baseline

The Yawn 0.5.8 source already provides the part many meeting tools treat as the
end goal:

- A generated note leads with an overview
- Decisions, follow-ups, ideas, and open questions are separated
- Generated claims link back to retained transcript evidence
- The full transcript remains available for verification
- Personal notes remain separate from generated claims
- Capture, transcription, and meeting storage stay on this Mac

The summary-first note is the baseline. It is not another roadmap item.

## Roadmap at a glance

| Order | Product outcome | State | Governing constraint |
|---|---|---|---|
| 0 | A completed meeting remains visible and reopens from Meetings in the packaged app | Preview passed; release package pending | A readable artifact must not disappear from its own journey |
| 1a | The reader can see who said what | Implemented in source and preview | Render the attribution already carried by each transcript turn |
| 1b | The reader can correct who said what | Implemented, tested, and packaged in Preview; rendered save-and-regenerate journey pending | Never hide uncertainty or overwrite the source transcript |
| 2 | Names and jargon stay correct across meetings | Bounded local domain and storage built; controls and transcript application queued | Vocabulary remains local, visible, editable, and bounded |
| 3 | The reader can tell whether the audio caused a bad transcript | Queued | Quality evidence stays distinct from capture-integrity evidence |
| 4 | Every recoverable problem leads to its exact repair | Current-meeting recovery presentation built; remaining destinations and retry flows queued | Recovery actions must not imply that a failed operation succeeded |
| 5 | The reader can find source passages across past meetings | Separate product decision | Search remains local, source-linked, and unavailable during capture |

## Delivery plan

The roadmap ships as dependent wedges, not as one large branch. The first wave
finishes the correction foundation while starting two independent foundations.
Later waves wire those foundations into the product only after their contracts
survive combined review.

```text
verified baseline
├── A. corrected transcript -> note generation
├── B. local vocabulary domain and storage contract
└── C. exact recovery presentation for current meeting warnings
        │
        └── combined integration and packaged preview gate
                ├── D. vocabulary controls and transcript application
                ├── E. capture-quality evidence and transcription retry
                └── F. narrow cross-meeting source finding decision
```

### Wave 1 — completed in parallel

| Packet | Outcome | Owned files | Must not do | Merge gate |
|---|---|---|---|---|
| A — corrected note input | Note generation consumes an immutable corrected transcript projection while source locators continue to resolve against the retained transcript | Desktop Rust correction and note-operation path | Do not rewrite the retained transcript or change the browser UI | Tests prove corrected names reach generation, source digest remains pinned, and no-correction behavior is unchanged |
| B — local vocabulary core | A bounded local domain model can add, edit, disable, delete, and deterministically project exact replacements | New session-core vocabulary module and its `lib.rs` export | Do not add UI, Tauri commands, fuzzy matching, or mutate past transcript artifacts | Tests cover restart-safe serialization, exact scope, disabled entries, deletion, ordering, and size bounds |
| C — exact recovery presentation | Existing warning and failure states map to one contextual next action without claiming success | Desktop UI view model, rendering, styles, and UI tests | Do not add backend commands, settings changes, or generic help routing | Tests cover action, unavailable-action, retrying, failure, and preservation of the last usable result |

### Wave 1 merge order

Packet B merges first because it changes only session-core. Packet A merges
second because it completes the current speaker-correction slice. Packet C
merges last because its copy must be checked against the combined backend
states. The orchestrator resolves integration edits; workers do not edit outside
their owned files to make another packet compile.

After merge, the full Rust and UI suites must pass together. A separately
identified Preview bundle must then prove this release journey: reopen a completed
meeting, inspect the original speaker label, apply a correction in a disposable
fixture, regenerate the note, follow a source link, return to Meetings, and
reopen the same meeting. The installed production app remains untouched.

### Wave 2 — integrate in dependency order

1. Expose local vocabulary through a small dedicated sheet. Keep every entry
   visible, editable, disableable, and local.
2. Apply vocabulary and explicit text corrections through the same immutable
   corrected-transcript projection used by note generation.
3. Surface stored recording-quality evidence. Then add transcription retry from
   retained audio, version comparison, and explicit keep-or-replace choice.
4. Complete the exact-repair map only after every destination exists. A button
   that opens a placeholder does not count as recovery.

### Wave 3 — make the separate product decision

Test a narrow, local source finder against real review tasks. Do not build a
general meeting assistant by default. Proceed only if quoted passages, coverage
limits, and capture-time unavailability still leave a useful product.

### Drift controls

- Every packet starts from the same verified commit in its own linked worktree
- File ownership is exclusive during a wave; widening scope returns to the orchestrator
- Shared contracts are changed once, at integration, rather than copied into each branch
- Each worker reports its commit, changed files, tests, assumptions, and unresolved gates
- The orchestrator reviews branch diffs and source, not completion claims
- A packet may be merged only when its own tests pass and its assumptions match this roadmap
- “Implemented,” “packaged,” “installed,” and “shipped” remain separate states
- No worker signs, installs, uploads, deploys, or changes `/Applications/Yawn.app`

## Current build receipt

**Directly observed on 2026-08-16.** The separately identified Yawn Preview
bundle rendered speaker labels beside transcript turns. Its **Back to Meetings**
action returned to a Recent meetings list containing the completed preview
meeting. No recording was started, and no meeting content was copied into this
roadmap.

**Verified in source.** Transcript rendering now displays the attribution
already stored on a turn and uses **Unattributed** when no claim exists. A
desktop regression test also proves that an active meeting is excluded from the
library while its lease is held and enters the library when that lease ends.

The correction increment now stores each speaker-name change as a separate,
meeting-local operation bound to the transcript digest and original source
speaker group. The latest operation changes only the rendered attribution. The
retained transcript file remains byte-for-byte unchanged, earlier corrections
remain in the local history, and choosing the source label restores the source
projection.

**Directly observed after the correction build.** The packaged Preview transcript
rendered each speaker name as a correction control. Opening it showed the source
label, the exact number of matching turns, the unchanged-source promise, and an
explicit source-label recovery action. No correction was saved during this
rendered inspection.

**Wave 1 source and package receipt.** Three isolated worktrees started from the
same baseline and merged through disjoint file ownership. The merge added the
corrected-note input, the bounded local-vocabulary core, and contextual recovery
presentation. Cross-review caught and removed unrelated formatting edits. It
also added an incremental output bound before the vocabulary packet merged.

The corrected-note path re-derives the active correction under the same meeting
lease used for durable note replacement. The generator applies the validated
speaker-label overlay only after reading and digest-checking the retained
transcript. The generated note and its locators keep the original transcript
digest. No correction keeps the former request shape.

**Verification commands.** The session-core suite passed 428 unit tests, 17
process-fault tests, and 8 doc tests. The desktop suite passed 131 tests, the
shell contract passed 5, and the UI suite passed 22. The rebuilt packaged
runtime passed 209 worker tests. `npm run preview-build` and
`npm run preview-verify` produced and verified the separately identified
`Yawn Preview.app` bundle.

**Rendered verification boundary.** The earlier Preview observation above is
still direct evidence for speaker controls and meeting continuity. The new
bundle launched, but computer-use could not obtain an accessibility snapshot
from that process. No real correction was saved and no private note was
regenerated to manufacture a passing visual check. The source and package gates
are green; the rendered save, regenerate, source-link, Back, and reopen journey
remains a release gate.

**Remaining release gate.** The production 0.5.8 bundle has not been signed,
installed, or substituted for `/Applications/Yawn.app`. The next release must
start from a clean source tree and repeat the completed-meeting journey against
that exact installed package before these changes can be called shipped.

**Remaining slice 1b gate.** Source acceptance is complete: note generation uses
the corrected attribution while source links stay bound to the retained
transcript. Shipping still requires the non-destructive packaged journey above
to be completed with a disposable fixture or explicit human review.

## 1. Show and correct who said what

**Outcome.** The visible transcript names each known speaker. A reader can fix a
wrong or missing label once and apply the correction to every matching turn.

**Why this is first.** A useful summary can still assign a commitment to the
wrong person. Speaker uncertainty also made the earlier in-person 630 meeting
hard to review. Fixing attribution improves the transcript, the note, and every
future search result.

**Existing foundation.** Transcript turns carry an optional `speaker` value.
The copied and rendered transcript now expose it, and the visible label opens
the meeting-local correction control.

**Build sequence.** Slice 1a renders the existing attribution without changing
stored data. Slice 1b adds a durable correction operation, a corrected
projection, and note regeneration from that projection. The visible label must
land first so the correction control has an honest object to edit.

**Current state.** The durable correction operation, corrected transcript
projection, exact-group UI, reopen behavior, source-label recovery, and note
regeneration from the corrected projection are built and packaged in Preview.
The rendered save-and-regenerate release journey remains unverified.

**Scope.**

- Render `Me`, `Them`, named speakers, and `Unattributed` explicitly
- Let the reader rename one speaker and apply that name across the transcript
- Preserve the original attribution and store the correction as a separate,
  reviewable operation
- Regenerate the note from the corrected transcript projection
- Keep uncertain attribution visibly uncertain

**Done when.**

- A rendered transcript shows the same speaker information as its copied form
- One correction updates every intended turn and no unrelated turn
- Reopening the meeting preserves both the correction and the original source
- A regenerated note uses the corrected attribution and retains source links
- Tests cover named, unnamed, withheld, and incorrectly grouped turns

**Not in this slice.** General-purpose room diarization. Yawn currently requires
the operator to attest that they are the only person near the microphone. A
multi-person in-room mode needs a separate capture, consent, and evidence
decision before the product can claim it works.

## 2. Keep a local vocabulary of names and jargon

**Outcome.** The reader can teach Yawn the names, organizations, products,
acronyms, and preferred spellings that matter in their meetings.

**Scope.**

- Add, edit, disable, and delete vocabulary entries on this Mac
- Support direct replacements such as a mistaken spelling to the intended one
- Offer **Always correct this** after an explicit transcript correction
- Apply vocabulary through a deterministic corrected projection; never rewrite
  the retained source artifact silently
- Show where an entry was applied and allow the reader to undo it
- Warn when the vocabulary becomes large enough to increase overcorrection risk

**Done when.**

- A saved entry survives restart and affects the next eligible transcript
- The original transcript remains recoverable and byte-identical
- A correction cannot change text outside its declared match
- Removing an entry does not rewrite past source artifacts
- Note regeneration uses the current corrected projection and preserves evidence

**Product change required.** The product brief currently limits Settings to
audio access and model storage. Vocabulary needs either a small dedicated sheet
or an explicit amendment to that Settings boundary.

## 3. Explain recording quality and allow a safe retry

**Outcome.** When a transcript looks wrong, the reader can determine whether the
recording was silent, clipped, noisy, incomplete, or captured from the wrong
microphone before blaming the speech or note model.

**Existing foundation.** Capture already persists integrity evidence, and the
recorder resolves the microphone device before capture. The current transcript
projection reads but does not expose the stored `capture_health` object.

**Scope.**

- Show the microphone selected for the recording
- Surface silence, clipping, low input, dropouts, and material background noise
  as separate observations
- Let the reader play retained audio while the retention period allows it
- Retry transcription from the unchanged recording
- Compare the retry with the current transcript before replacing the active
  projection
- Keep every retry versioned and source-bound

**Done when.**

- Each quality message names the observed condition and the next useful action
- Integrity evidence and quality guidance remain separate fields and labels
- Retrying transcription cannot alter or delete the recording
- The reader can keep the current transcript when the retry is worse
- If retained audio is gone, the interface says that the meeting cannot be
  retranscribed

## 4. Route each problem to its exact repair

**Outcome.** A warning or failed state ends with one action that opens the place
where the reader can fix it.

Examples:

- Wrong microphone → open audio access and device guidance
- Misspelled name → open the local vocabulary
- Wrong speaker → open speaker correction for that turn
- Incomplete transcript → listen to retained audio and retry transcription
- Weak generated note → regenerate without discarding the current note first

This is an in-app routing contract, not an email campaign. A generic help page
does not satisfy the outcome when Yawn already knows the failing meeting and
operation.

**Done when.** Every recoverable warning has one primary action, lands at the
correct meeting or control, and preserves the failed artifact until the repair
succeeds.

## 5. Find source passages across meetings

**Outcome.** The reader can ask a narrow question such as “Where did we discuss
the launch date?” and receive quoted passages linked to the meetings that contain
them.

**Existing foundation.** A local corpus-question command and source-handle path
already exist in the desktop backend. The command is deliberately not registered
in the shipped interface.

**Decision gate.** The product brief excludes chat over every meeting from the
current reset. Before this work starts, decide whether the reader needs a narrow
source-finding tool or a broader assistant. The narrow tool is the default
proposal because it preserves Yawn's evidence-first shape.

**Required boundaries.**

- Search and answer generation stay on this Mac
- Every answer quotes and links to retained source passages
- Coverage gaps are stated instead of hidden
- Search remains unavailable during capture when it would compete with the
  transcription worker
- No email, calendar, Slack, or web context is added through this slice

**Not yet.** Live “What did I miss?” summaries. The current worker boundary makes
capture the priority, and a live summary would add an uncapped interpretation
path while the source is still being recorded.

## Ideas this roadmap does not adopt

The Wispr Flow emails also promoted writing styles, reusable dictation snippets,
spoken list formatting, automatic call detection, connected services, and AI
tool integrations. Those ideas solve different jobs or cross Yawn's current
privacy and consent boundaries.

They stay out unless a later product decision supplies a Yawn-specific user
need, a local authority model, and evidence that the added complexity improves
the private meeting-note job.

## Invariants across every slice

- Original recordings and transcripts are never silently rewritten
- Corrected and generated material remains distinguishable from source evidence
- A failed retry never replaces the last usable result
- Capture, transcription, corrections, vocabulary, and notes remain local
- Recording still begins through an explicit consent and start action
- UI copy states what happened, what is uncertain, and what the reader can do
- A feature is not marked shipped until it is rendered and verified in the
  packaged desktop app

## Evidence behind the direction

Two Wispr Flow emails received on 2026-08-08 and 2026-08-10 introduced the
comparison. Their useful product ideas were checked against the linked public
material and Yawn's current source. Private email contents are not copied into
this repository.

- [Why transcription quality fluctuates](https://wisprflow.ai/post/transcription-quality)
  describes microphone changes, background noise, input volume, audio review,
  transcription retry, transcript feedback, and dictionary overcorrection.
- [Wispr Flow Notetaker](https://wisprflow.ai/notetaker) presents named speakers,
  one-step relabeling, topic-organized summaries, source-linked questions, and
  live catch-up as its product direction.
- [Yawn's product brief](product-brief.md) owns the local storage, consent,
  evidence, note, and interface boundaries this roadmap preserves.
- The current desktop sources own the implementation facts:
  [`main.js`](../apps/desktop/ui/main.js),
  [`view-model.mjs`](../apps/desktop/ui/view-model.mjs),
  [`main.rs`](../apps/desktop/src-tauri/src/main.rs), and
  [`capture_health.py`](../apps/desktop/runtime/spike/capture_health.py).

External URLs were resolved and checked against the cited claims on 2026-08-16.
