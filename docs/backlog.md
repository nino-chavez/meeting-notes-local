# Backlog — epics and user stories

Written 2026-08-07. This is the **decomposition layer**: it breaks the ten
north-star features into epics, and epics into stories a person can pick up and
build. It sits below the definition layer and beside the sequencing one.

```
product-definition.md   what the product is, the ten features, the non-goals
vertical-slice.md       what gets built next  <- Build queue owns ORDER and STATUS
backlog.md              this file — how each feature decomposes into work
screens-and-states.md   what each surface must and must not do
journeys.md             the reader, the market, journeys J0–J6
```

**This file does not own status or order.** `vertical-slice.md § Build queue` does.
Two sequencing authorities is the exact confusion this repo already had, so every
epic here carries a pointer to its queue row rather than a state of its own. If you
want to know what to build next, read the queue. If you want to know what a piece of
work *is*, read here.

Statuses quoted in the catalog below are copied from the queue as of 2026-08-07 and
are stale the moment the queue moves. They are convenience, not authority.

---

## 1. Purpose and scope

The scope is v1 of the local meeting notetaker, plus the two epics explicitly parked
outside it. Research candidates (J6 evaluation contribution, speaker playback/AEC)
are named where they touch a story boundary but carry no stories.

## 2. Personas

Unlike a platform product, this has essentially one user. Resist inventing more.

| Persona | Who | Appears in |
|---|---|---|
| **Operator** | The person between back-to-back calls, who will not babysit a tool and did not open it to admire it. Runs the app on their own Mac. | Every epic |
| **Far end** | The other people in the meeting. Never a user, never sees a surface, and cannot consent through the app — which is exactly why consent and retention stories exist. | E1, E2, E3 |
| **Cohort operator** | Someone handed a signed DMG for a real install. Distinguished from Operator only because they hit first run on an unprepared machine. | E10, E12 |

## 3. Story format

- Header: `US-X.Y: Title`
- Feature, journey, surface, priority (P0–P3), effort (S/M/L/XL)
- Story statement (As a ___, I want ___, so that ___)
- Acceptance criteria in Given/When/Then form

Effort: **S** ≤ 3 days, **M** ≤ 2 weeks, **L** ≤ 4 weeks, **XL** > 4 weeks or needs a spike.

Additional sections — **Evidence**, **Refusals**, **Dependencies**, **Risks** —
appear only where they carry weight. **Refusals** is this product's local addition
and is load-bearing: most stories here are as much about what the app must decline
to claim as about what it does. A story whose acceptance criteria are all happy-path
is probably wrong for this codebase.

## 4. Epic catalog

| # | Epic | Feature | Journey | Surface | Queue status (2026-08-07) |
|---|---|---|---|---|---|
| E1 | Consent-first local two-leg capture | 1 | J3 | §B §C | Shipped |
| E2 | Operator voice isolation | 2 | J3 J5 | §I | Shipped 0.4.0, unmeasured on live audio |
| E3 | Audio lifetime and deletion | 3 | J5 | §G §K | **Buildable now** (whole-meeting deletion) |
| E4 | Evidence-linked notes | 4 | J1 J2 | §E | **Buildable now** (next intervention) |
| E5 | Honest incompleteness | 5 | J1 | §E §F | Blocked on evidence (needs E4) |
| E6 | Correction and regeneration | 6 | J4 | §E | Restoration shipped; regeneration needs E4 |
| E7 | Retrieval | 7 | J1 | §F | Registered; claim-level landing needs E4 |
| E8 | Commitment handoff | 8 | J2 | §F | Blocked on a scope decision (export) |
| E9 | Preparation brief | 9 | J0 | — | Wave H, outside v1 |
| E10 | Shell that never lies | 10 | J3 | §A §C §H §J | **Buildable now** (signed preview bundle) |
| E11 | Operator-authored live note | §D amendment | J3 | §D | Shipped 2026-08-06 |
| E12 | Release, distribution, admission | cross-cutting | — | — | Mixed; closure receipt blocked on Operator |

**Read the dependency, not the numbering.** E4 is upstream of E5, E6 and E7. Nothing
in those three finishes before an admitted note generator exists, and admission is an
Operator decision. That single edge explains most of what looks like slow progress.

---

## 5. Epic details

### E1 — Consent-first local two-leg capture

Microphone and system audio captured as separate legs on the Operator's Mac, with
the far end told before recording starts. Shipped and proven on real hardware.

#### US-1.1: Two-leg capture with fresh-process recovery
**Feature 1 · J3 · §C · P0 · L · Shipped**

As the Operator, I want capture to survive the app dying mid-meeting, so that a
crash does not cost me the conversation.

**Acceptance criteria:**
- Given a recording is in progress, When the app process dies, Then the captured audio to that point remains on disk and is recoverable on next launch.
- Given a recovered session, When it is reopened, Then the app states the recovery happened rather than presenting the result as an unbroken recording.

**Refusals:** the app must never present a recovered partial capture as complete.

#### US-1.2: Consent moment before Start
**Feature 1 · J3 · §B · P0 · M · Shipped**

As the Far end, I want to be told a recording is starting, so that I am not recorded
without knowing.

**Acceptance criteria:**
- Given the Operator triggers Start, When conditions are asserted, Then the app states them explicitly and does not claim to have detected what it cannot measure.
- Given headphones and an empty room are Operator assertions, When they are recorded, Then they are stored as assertions, not as measurements.

**Refusals:** no claim of detected conditions. Manual Start and Stop only.

---

### E2 — Operator voice isolation

Guided enrolment produces an owner-only voice profile; the gate marks non-operator
turns on the microphone leg. Shipped in 0.4.0 — the first image where an enrolled
profile changes a transcript.

#### US-2.1: The gate records what it did
**Feature 2 · J3 · §I · P0 · M · Shipped 0.4.0**

As the Operator, I want every checked transcript to say what the gate did to it, so
that I never mistake a filtered transcript for a complete one.

**Acceptance criteria:**
- Given the gate runs, When a transcript is written, Then its `voiceprint` field records that the check happened and on what basis.
- Given an installed profile the runtime cannot apply, When a transcript would be written, Then the app refuses the transcript rather than writing one that reads as checked.

**Refusals:** never write a transcript that implies a check that did not happen.

#### US-2.2: Threshold measured on live meeting audio
**Feature 2 · J3 · §I · P1 · L · Blocked on Operator (real sittings)**

As the Operator, I want the gate's threshold derived from real meetings rather than
enrolment sittings, so that the recall figure means something in the field.

**Acceptance criteria:**
- Given a threshold derived only from enrolment, When a transcript is checked, Then the app states that limitation on the transcript itself. *(Already true.)*
- Given real sittings are recorded, When operating points are derived, Then the Operator selects one and the selection is recorded with its measurements.

**Dependencies:** encoder admission verdict (E12), real enrolment sittings.

---

### E3 — Audio lifetime and deletion

The transcript is the retained evidence. Audio has a stated lifetime and is removed
on it. Automatic deletion is proven by a real receipt; whole-meeting deletion is the
next build.

#### US-3.1: Automatic deletion on the stated deadline
**Feature 3 · J5 · §K · P0 · M · Shipped**

**Acceptance criteria:**
- Given the retention deadline passes, When the app next launches, Then both bound audio legs are removed and an `audio-deletion/1` receipt records it.
- Given deletion completes, When the meeting is opened, Then the transcript is present, digest-matched and readable.

**Evidence:** real receipt, 2026-08-02.

#### US-3.2: Whole-meeting deletion
**Feature 3 · J5 · §G · P0 · M · Built 2026-08-07, core and shell**

As the Operator, I want to delete a meeting entirely — audio, transcript, note and
record — so that a conversation that should not have been captured can be removed.

**Acceptance criteria:**
- ~~a receipt in the `audio-deletion/1` shape~~ — **corrected 2026-08-07, see Risks.** Given a meeting exists, When whole-meeting deletion is authorized, Then every artifact bound to it is removed and a `meeting-deletion/1` receipt records what was removed. *(Built.)*
- Given deletion is interrupted mid-way, When the app restarts, Then reconciliation completes it, and never leaves a meeting that reads as intact but is not. *(Built.)*
- Given a meeting is active, When whole-meeting deletion is requested, Then it is refused before any mutation. *(Built — the lease is taken before storage is read at all.)*
- Given deletion completes, When the library is opened, Then the meeting is absent, not tombstoned as an empty row. *(Built at the core; the library surface is part of the open shell slice.)*
- Given the Operator has not confirmed twice, When deletion is requested, Then it does not proceed. *(Built.)* The §G control reveals a confirmation panel first, and the command turns that second click into a closed in-process `MeetingDeletionReview` the webview cannot construct — so an unconfirmed call is refused before the writer lock is taken, let alone before any removal.

**Refusals:** must not run against real meetings during development. "Exercise real
destructive actions only as Operator actions before beta admission."

**Dependencies:** borrows the wave C writer-lock authority and coordination lease
rather than re-implementing them.

**Risks — answered 2026-08-07, and the answer was no.** The `audio-deletion/1` shape
**cannot** carry this, for two independent reasons. Its receipt lives at
`meeting_dir/deletion/audio-deletion.json`, *inside* the directory whole-meeting
deletion removes, so it would destroy its own evidence and leave crash recovery
nothing to reconcile against. And a receipt listing a transcript and an operator note
under a schema named `audio-deletion/1` misdescribes what happened, which this
codebase refuses everywhere else. So `meeting-deletion/1` is a registered new schema
whose receipt lives at `<root>/deletions/<meeting_id>.json`.

`StorageRoot::create` seeds a fixed list of root children but does not enforce it as
an exact set, so the new `deletions/` child is additive: an older build reading a root
that has it is unaffected, and a newer build creates it on demand.

**What was built** (`crates/session-core/src/meeting_deletion.rs`, 11 tests): the
receipt, the three-state machine, `WholeMeetingDeletionAuthority` off the writer lock,
startup reconciliation, and a retention skip so a meeting between `staged` and
`removed` is not reported as quarantined. The ordering is the safety property —
`meeting.json` is removed **first**, because every reader reaches a meeting through
`load_meeting`, so after that transition no partially removed directory can be read as
intact.

**Shell slice, landed the same day.** `preview_delete_meeting` over a
`LibraryMeetingDeletionAccess` path, `WholeMeetingDeletionFacade`, the capability in
both windows, and the §G control.

Three separations were kept deliberately rather than collapsed, because each one is a
place where reuse would have silently widened authority:

1. **A separate handle map.** Reusing the audio-deletion handle would let a handle the
   operator obtained to free disk space destroy the retained transcript instead.
2. **A separate review token.** `MeetingDeletionReview` is a distinct type from
   `AudioDeletionReview`, so a confirmation given for the smaller act cannot satisfy
   the larger one — and the compiler enforces it.
3. **A separate capability.** `allow-preview-delete-meeting` is granted beside, not
   instead of, `allow-preview-delete-meeting-audio`.

On success the shell leaves the detail view, because a detail screen rendering a
meeting that no longer exists is the tombstone this story forbids.

**Next slice:** none for this story. Feature 3's remaining item is the policy
wording, which is the operator's.

#### Placeholders standing in for real data

Recorded here because they are invisible in the code and will otherwise be forgotten.

| Placeholder | Where | Replace with |
|---|---|---|
| Matrix re-run for the polarity gate | `notes/mlx_note_admission.py` | An actual run. `mlx_lm` is absent from `.venv`, and installing it would change the environment the committed receipts came from. The gate's logic is unit-tested; its predicted effect on the 12-fixture matrix is **unverified**, so no count may be quoted from it. |
| Synthetic meeting fixtures only | `meeting_deletion.rs` tests | A real `meeting-deletion/1` receipt. **None has ever been produced.** Passing tests are bounded evidence and do not advance the wave C human gate, so this stays unproven until an Operator runs a real deletion. |
| Placeholder staged runtime | `apps/desktop/runtime/` (gitignored, local only) | A real staged runtime via `worker/build_manifest.py`. A fresh worktree has no `apps/desktop/runtime`, so the desktop crate's `build.rs` fails on a missing resource path; a stub tree of the eight declared resources lets it compile. Any manifest-dependent assertion measured against that stub is measuring the stub. |

#### US-3.3: Retention policy wording
**Feature 3 · J5 · §B §G · P0 · S · Blocked on Operator**

The wording of what the app promises about retention. Recorded here as an open item
with an Operator owner. Two drafted options currently have no encoding in
`validate_start_request`, which is a build consequence of whichever wording is chosen.

---

### E4 — Evidence-linked notes

**The load-bearing epic.** Typed claims, each citing the verbatim turns behind it. No
generator is admitted. E5, E6 and E7 all wait on this.

#### US-4.1: Typed claims that cite verbatim turns
**Feature 4 · J1 J2 · §E · P0 · L · Prototyped**

As the Operator, I want every claim in a note to point at the words that produced it,
so that I can check the note instead of trusting it.

**Acceptance criteria:**
- Given a generated note, When a claim is displayed, Then it carries a locator resolving to exact transcript bytes.
- Given a locator that does not resolve, When the note is assembled, Then the claim is refused rather than shown uncited.

**Refusals:** a claim without its citation, or a "verified" state nothing checked, is
the failure this product exists to not ship.

#### US-4.2: Refuse a claim that inverts its evidence, before closing the identifier truncation
**Feature 4 · J1 · — · P0 · M · **Buildable now***

As the Operator, I want a claim that contradicts the words it cites to be refused,
so that fixing an unrelated bug does not start admitting inverted claims.

**Acceptance criteria:**
- Given cited evidence containing a polarity term, When the claim contains that term in no form, Then the claim is refused with code `claim-polarity`.
- Given evidence and claim that both carry the polarity, When the gate runs, Then the claim is unaffected — `negation-decision` is the control and a gate that fails it is over-broad and withdrawn.
- Given the gate is added, When the matrix re-runs, Then no fixture that was passing starts failing, because the gate refuses nothing that was passing.
- Given the polarity gate is in place, When the identifier truncation is then fixed, Then the matrix improves without admitting an inverted claim.

**Why this order.** Reading the semantic-support sheet on 2026-08-07 — the first time
anyone had — found `negation-proposal` producing the claim "merge the red branch" from
the evidence "I propose that we do **not** merge the red branch". All three matrix
failures carry `citation-locator` and nothing else, so the identifier bug is the only
thing refusing it. Closing that bug alone would take the matrix from 9 of 12 to 12 of
12 while admitting a claim that asserts the opposite of its own evidence.

**Refusals:** this is not a model search, and the gate must not be folded into the
identifier work. The amendment discipline requires a rule to be registered on its own
rather than inside a change measuring something else.

**Risks:** the gate is a word-presence test. A paraphrase that carries polarity without
the listed terms — "we are keeping the red branch" — would be refused wrongly. If that
appears, the gate is too crude and the finding still stands: the harness needs *some*
polarity check, not necessarily this one.

**Evidence:** preregistered in `notes/MLX_NOTE_ADMISSION.md` § 2026-08-07, with its
prediction stated and its already-known effect on the ten recorded rows separated from
what remains unknown.

#### US-4.2b: Close the identifier truncation
**Feature 4 · J1 · — · P0 · M · Blocked on US-4.2**

One characterized mechanism on three fixtures: `sf-` plus 64 hex, cut at 67 characters.
The margin receipt shows one decision losing three times at the same step with the same
runner-up token `-t` (−1.11, −0.52, −0.31), so this is not a search.

**Acceptance criteria:**
- Given the intervention is preregistered before it runs, When it runs, Then its prediction is recorded ahead of the result and reported against it whether or not it holds.
- Given the polarity gate is already active, When the matrix re-runs, Then `negation-proposal` still refuses — on `claim-polarity` rather than `citation-locator`.
- Given the run completes, When results are recorded, Then `admits` remains false unless every registered gate passes including the human ones.

#### US-4.3: Human semantic and usefulness adjudication
**Feature 4 · J1 · §E · P0 · M · Blocked on Operator**

As the Operator, I want to read generated notes beside the evidence they cite and say
whether they are any good, so that admission rests on usefulness and not on shape.

**Acceptance criteria:**
- Given recorded results, When the Operator reviews them, Then each claim is presented beside the transcript text it cites.
- Given the review completes, When a verdict is recorded, Then it is recorded as an Operator verdict, distinct from every mechanical gate.

**Dependencies:** `notes/read_semantic_support.py` (rescued 2026-08-07) is the
packaging that makes this reviewable at all — before it, outputs existed only as
digests and booleans inside receipts.

---

### E5 — Honest incompleteness

"Not captured" is never shown as "never said", and the Operator can see how much of a
note is checkable before opening it.

#### US-5.1: Gaps rendered as gaps
**Feature 5 · J1 · §E · P0 · M · Prototyped**

**Acceptance criteria:**
- Given the gate withheld turns, When the transcript is displayed, Then the withheld spans are visible as gaps with their cause, not silently closed.
- Given a transcript is copied, When it lands in the clipboard, Then the gaps are copied with it.

#### US-5.2: Checkable proportion before opening
**Feature 5 · J1 · §F · P1 · M · Blocked on E4**

As the Operator, I want to see what proportion of a note is checkable before I open
it, so that I know whether it is worth trusting.

**Acceptance criteria:**
- Given a note with typed claims, When the library lists it, Then the proportion of claims whose locators resolve is shown.
- Given no note has been generated, When the library lists the meeting, Then no proportion is shown — not zero, and not a placeholder.

**Risks:** the figure has nothing true to count until E4 produces claims on a real
gated capture. Building the surface earlier means building it against synthetic
input, which is how a number nobody measured ends up rendered as a fact.

---

### E6 — Correction and regeneration

Restoring a withheld turn changes the evidence, so the note built on it goes stale
and must be regenerated rather than silently kept.

#### US-6.1: Restore a withheld turn from either surface
**Feature 6 · J4 · §E · P0 · M · Registered 0.2.2, reachable 0.4.0**

**Acceptance criteria:**
- Given a withheld turn, When the Operator restores it, Then a new current transcript is published and the projection is rebuilt in place.
- Given a restoration already happened, When a second is attempted, Then it resolves against the moved digest rather than being refused as a changed source.
- Given the meeting was just recorded, When the Operator wants to restore, Then the control is on that screen too — not in the library only.

**Evidence:** the gate's worst failure is a colleague cut from a record that cannot be
re-made, and that remedy is worth less the longer it waits. Navigation was the delay.

#### US-6.2: A note whose evidence moved is marked stale
**Feature 6 · J4 · §E · P0 · M · Blocked on E4**

**Acceptance criteria:**
- Given a note cites a transcript digest, When restoration publishes a new one, Then the note is marked stale and says why.
- Given a stale note, When it is displayed, Then it is never shown as current, and regeneration is offered rather than performed silently.

---

### E7 — Retrieval

Enter with a question, land on the claim. Library, search over transcripts and
metadata, open-to-evidence.

#### US-7.1: Exact search over transcripts and metadata
**Feature 7 · J1 · §F · P0 · L · Registered**

**Acceptance criteria:**
- Given a query, When results are returned, Then each result is bound to the exact transcript bytes it matched, verified by digest and parsed-byte recheck.
- Given a result is opened, When the transcript is shown, Then the match is located in it rather than the reader being dropped at the top.

#### US-7.2: Land on a claim, not a document
**Feature 7 · J1 · §F · P1 · M · Blocked on E4**

**Acceptance criteria:**
- Given a note with typed claims, When a query matches a claim, Then the result opens at that claim with its citation resolved.

---

### E8 — Commitment handoff

A view organized by what was promised. The terminal action is export — never a
checkbox, because the moment the tool offers one it owns follow-through and the
Operator has two task systems.

#### US-8.1: `view: recorded-actions` over the library
**Feature 8 · J2 · §F · P1 · M · Blocked on a scope decision**

**Acceptance criteria:**
- Given commitments extracted into claims, When the Operator selects the commitment view, Then it is a filter over the existing library, not a separate surface.
- Given a commitment is shown, When the Operator acts on it, Then the only terminal action is export.

**Refusals:** no status field, no owner field, no completion state, no checkbox.
*Counterevidence acknowledged and the non-goal stands:* Wispr Flow shipped the
checkbox — a `Todos` table with open/closed status and a tasks tab — and six of six
colleagues surveyed wanted action items. None of that reaches the reason for the
non-goal, which is about owning follow-through, not about extracting commitments.

**Blocked by:** "copy/export remains disabled until the separate redaction and export
decision closes." The view is not the open part; the export is.

---

### E9 — Preparation brief

What happened last time with this person, before the meeting. **Outside v1** (wave H).
Carries no stories until an Operator scope decision moves it in, the way the §D live
note moved in on 2026-08-06.

The local half — read-only calendar through EventKit — is designed and unbuilt. The
counterparty half (who spoke vs who was invited) stays open and possibly unbridgeable
*for local audio*: nobody bridged it from sound. Wispr Flow makes the failure cheap to
repair instead, using a calendar roster, an OAuth grant into the org's directory,
accessibility-tree polling, LLM inference over address terms, and one-click human
correction. Every one of those crosses a non-goal here.

---

### E10 — Shell that never lies

At menubar size, degradation is a beat rather than an error. Tray truth table,
close-to-tray, startup-failure honesty, and a first run that never claims a permission
state it did not measure.

#### US-10.1: First run derives its step from a live measurement
**Feature 10 · J3 · §H · P0 · L · Registered 2026-08-06**

**Acceptance criteria:**
- Given first run opens, When a step is chosen, Then it is derived from a live measurement, not from a stored completion flag.
- Given a permission cannot be asked about, When the state is shown, Then "we could not ask" is a different screen from "you said no".
- Given a request path did not run, When its result is reported, Then it says unmeasured rather than unknown.

**Evidence:** `capture/permission-probe`, a signed binary digest-verified through
`app-runtime/1`. Nothing could previously measure either capture permission without
recording, so an earlier first run would have had to claim states it never measured.

#### US-10.2: Execute the two request paths in a signed bundle
**Feature 10 · J3 · §H · P0 · M · **Buildable now***

As a Cohort operator, I want first run to actually request permissions on my machine,
so that the screen is not describing a path nobody has ever taken.

**Acceptance criteria:**
- Given a signed preview bundle exists, When first run requests microphone access, Then macOS prompts and the resulting state is recorded against that bundle's identity.
- Given the system-audio request runs, When a tap is created, Then the outcome is recorded, and the microphone permission it did not ask about is reported as unmeasured.
- Given the bundle is unsigned or ad-hoc, When a request path is reached, Then it is refused.

**Refusals:** never run a request path outside the signed bundle. Doing so mutates the
calling application's TCC state and answers about the wrong binary.

**Dependencies:** the packaging lane in `distribution-runbook.md`; allow for the
signing/notarization round trip being slow enough to outlive a short timeout.

#### US-10.3: Startup failure is honest
**Feature 10 · J3 · §J · P0 · S · Shipped 0.2.2**

**Acceptance criteria:**
- Given a staged runtime whose manifest does not match, When the app starts, Then it fails closed and names the cause rather than starting degraded.

**Evidence:** this fired for real on 2026-08-06 when a staged worker predated
`permission_probe`. The lockstep is the designed behaviour, not a defect.

---

### E11 — Operator-authored live note

The Operator types their own notes during the meeting, on the recording surface.
Entered v1 by Operator decision on 2026-08-06; shipped the same day.

#### US-11.1: Type during the meeting, keep it after
**§D · J3 · §D · P0 · M · Shipped 2026-08-06**

As the Operator, I want to write my own notes while listening, so that what I chose to
write down is not lost — it is not recoverable from the recording afterwards.

**Acceptance criteria:**
- Given the Operator types during a recording, When the text is saved, Then the surface renders what storage confirmed, not what is in the textarea.
- Given saves overlap, When they are written, Then they serialize rather than dropping.
- Given Stop is pressed with an unsaved edit, When the command runs, Then the pending write flushes first and the guard is set before the flush.
- Given the note file is unreadable, When a write is attempted, Then it is refused rather than silently replacing it.
- Given the meeting is dismissed, When the Operator returns to it later, Then the note is still reachable.

**Refusals:** it is interpretation, never evidence. Nothing cites an operator note and
no claim resolves to one. No status, checkbox or owner field. Stored at a fixed path
and atomically swapped, so the frozen `meeting/2` contract never changes — which also
means an operator note can never make a meeting unreadable to an older build.

---

### E12 — Release, distribution and admission

Cross-cutting. Not a north-star feature, but every feature reaches the Operator
through it.

#### US-12.1: Closure receipt for one unchanged build
**Cross-cutting · P0 · S · Blocked on Operator**

As the Operator, I want the three-block closure receipt written against a build I
already have, so that the evidence chain is not empty for an activity that has
happened many times.

**Acceptance criteria:**
- Given an unchanged build, When the Operator completes a run, Then `automatic_deletion`, `consented_hardware_run` and `clean_transfer` are recorded against that one build.
- Given a version changes, When the receipt is consulted, Then it does not transfer — each version restarts it.

**Note:** this is not another transfer. Transfer has happened repeatedly; Gatekeeper,
notarization and stapling pass on every recorded build. What has never been written is
the record. Receipts live outside Git by design, so their absence in-repo proves
nothing.

#### US-12.2: Encoder admission verdict
**Cross-cutting · P0 · M · Blocked on Operator**

**Acceptance criteria:**
- Given Fbank parity, packaging and cold-load checks are recorded, When the Operator issues a verdict, Then the default runtime's encoder stops being a placeholder.
- Given no verdict, When a sitting is recorded, Then it must not be claimed saved.

**Evidence:** direction chosen 2026-08-03 — ONNX Runtime CPU preferred, PyTorch/
SpeechBrain reference and fallback. Fbank parity within 9.7 × 10⁻⁷ synthetic and
7.4 × 10⁻⁷ on registered LibriSpeech fixtures. Open: gate-classification comparison,
transferred-build Gatekeeper check, and the verdict itself.

#### US-12.3: Cold operator review
**Cross-cutting · P1 · S · Blocked on Operator**

Someone who has not seen the app uses it, before beta admission. Passing tests are
bounded evidence and do not advance a human gate.

---

## 6. Non-functional requirements

Cross-cutting; apply to every story unless a story overrides them explicitly.

**Locality.** Nothing leaves the Mac. No cloud ASR, no telemetry, no built-in upload.
This is the product's only real differentiator against every commercial competitor,
all of which send meeting audio off the machine.

**Evidence integrity.** Evidence artifacts are digest-named and bound into
`meeting.json`; a citation can only ever resolve to bytes that were verified.
Interpretation (the operator note) is stored separately at a fixed path and is cited
by nothing.

**Fail closed.** Contracts are checked exactly on both sides — `worker/main.py`
compares `set(document) != required`, Rust's `RuntimeManifest` is
`deny_unknown_fields`. Writer and readers move in one commit or the manifest fails
closed. That is the property being preserved, not a cost.

**Honesty over completeness.** Every surface must decline to claim what it did not
measure. Prefer a visible gap, an "unmeasured" state, or a refusal over a plausible
value.

**No invented content on judged surfaces.** Prototypes populate from the real corpus
or from labelled specimens carrying published measurements. Never fabricated meetings.

**Privacy of the corpus.** Audio, transcripts, note text and profile material never
enter Git. Run and closure receipts are kept outside Git deliberately.

---

## 7. Provenance

Epics derived from `product-definition.md § North-star features and functions`
(statuses verified there 2026-08-06) and `vertical-slice.md § Build queue` (written
2026-08-07). Surfaces §A–§J from `screens-and-states.md`; journeys J0–J6 from
`journeys.md`. Competitive claims carry the fetch dates recorded in `teardown.md`
(2026-07-28 mechanism, 2026-07-29/31 product pages); nothing was re-fetched for this
file.

Format follows `~/Workspace/dev/wip/bc-subscriptions/BRD.md` — story header,
Given/When/Then acceptance criteria, and the effort scale carried over. Its persona
and value-stream columns did not transfer: that product has four personas across a
platform, this one has essentially one, and the journey already does what a value
stream would.

Not written here: story-level effort for epics blocked behind E4, because sizing work
that cannot start produces numbers that decay before use.
