# Backlog — epics, user stories, acceptance criteria

Written 2026-08-07, expanded the same day. This is the **decomposition layer**: it
breaks the parity feature set into epics, epics into stories, and stories into
acceptance criteria a person can build against and a machine can be checked against.

```
product-definition.md   what the product is, the ten features, the non-goals
vertical-slice.md       what gets built next  <- Build queue owns ORDER and STATUS
backlog.md              this file — how each feature decomposes, and what proves it
screens-and-states.md   what each surface must and must not do
journeys.md             the reader, the market, journeys J0–J6
```

**This file does not own status or order.** `vertical-slice.md § Build queue` does.
Two sequencing authorities is the exact confusion this repo already had, so every
epic carries a pointer to its queue row rather than a state of its own.

**It does not own scope either, and until 2026-08-07 it was read as if it did.** An
absent story was treated as evidence a capability was out of scope. It is not: this
file lags the definition layer on purpose, and `product-definition.md` is where the
product's shape is decided.

**On the missing PRD.** A separate PRD is deliberately not created.
`product-definition.md` already does that job — what the product is, who the reader
is, the ten features with their research grounding, and the non-goals with equal
authority. Minting a third document that also looks authoritative would add to the
confusion this layer exists to reduce. If a single artifact named "BRD/PRD" is ever
needed for an outside reader, the honest move is to concatenate these two, not to
write a new one that drifts from both.

---

## 1. Purpose and scope

v1 of the local meeting notetaker, plus the epics explicitly parked outside it.
Research candidates (J6 evaluation contribution, speaker playback/AEC) are named
where they touch a story boundary but carry no stories.

## 2. Personas

Unlike a platform product, this has essentially one user. Resist inventing more.

| Persona | Who | Appears in |
|---|---|---|
| **Operator** | The person between back-to-back calls, who will not babysit a tool and did not open it to admire it. Runs the app on their own Mac. | Every epic |
| **Far end** | The other people in the meeting. Never a user, never sees a surface, and cannot consent through the app — which is exactly why consent and retention stories exist. | E1, E2, E3 |
| **Cohort operator** | Someone handed a signed DMG for a real install. Distinguished from Operator only because they meet first run on an unprepared machine. | E10, E12 |

## 3. Story format

- Header: `US-X.Y: Title`
- Feature, journey, surface, priority (P0–P3), effort (S/M/L/XL), state
- Story statement (As a ___, I want ___, so that ___)
- **Acceptance criteria** in Given/When/Then form

Effort: **S** ≤ 3 days, **M** ≤ 2 weeks, **L** ≤ 4 weeks, **XL** > 4 weeks or needs a spike.

Four further sections appear where they carry weight:

- **Data contract** — the registered schema(s) the story reads or writes. This
  product is mostly contracts, and a story that moves bytes without naming its
  schema is under-specified.
- **Validation** — the mechanical check that proves the criteria, **by name**, or an
  explicit statement that nothing does. See § 4.
- **Refusals** — what the story must decline to do or claim. This is the local
  addition and it is load-bearing: a story here whose criteria are all happy-path is
  probably wrong.
- **Risks / open questions** — collected in § 7.

## 4. Capability validation

A story is not done because someone says so. Each carries a **Validation** line
naming the check that proves it, and the vocabulary is deliberately narrow:

| Term | Means |
|---|---|
| **Pinned** | A named test or exact-set assertion fails if the behaviour changes. Cite the test name. |
| **Exercised** | Code runs the path under synthetic input, but nothing pins the outcome against drift. |
| **Receipted** | A digest-bound receipt from a real run exists outside Git. Cite which. |
| **Unproven** | Nothing checks it. Stated rather than omitted, because an absent Validation line reads as an oversight and this reads as a fact. |

**Synthetic passes are bounded evidence.** `vertical-slice.md` says it directly:
passing tests do not advance a human gate. A story may be fully **Pinned** and still
be unproven as a product capability, because what is pinned is the code's behaviour
on fixtures, not the claim that a real meeting was captured, deleted, or usefully
summarised. Those need **Receipted**, and receipts live outside Git by design.

Check inventory as of 2026-08-07, verified by counting `#[test]` in the sources
rather than by repeating a prior claim: 269 session-core lib, 16 session-core
integration, 115 desktop lib, 33 shell-contract, 9 build-matrix, 107 Python,
42 shell JS (session-core reached 276 with the same-day corrections in US-13.2,
US-13.3, US-13.4 and US-13.7). The session-core figure was recorded as 247 earlier the same day and
was already stale; it matches what the runner reports, which is the check worth
using.

## 5. Epic catalog

**Rewritten 2026-08-07 for category parity.** The previous catalog had twelve epics
covering ten features. The north star is now 26 Phase 1 features
(`product-definition.md`), so seven epics are new and the existing twelve keep their
identifiers — renumbering would break every citation in this file and in the queue
for no gain.

**This catalog is ahead of the stories, deliberately.** The new epics carry no
stories yet. Writing 150 speculative stories in one pass produces a document nobody
trusts; the queue decides which epic gets decomposed next, and stories land when that
epic is about to be built. **An epic with no stories is not out of scope** — that
inference is what went wrong before.

| # | Epic | Features | Stories | Queue |
|---|---|---|---|---|
| E1 | Consent-first local two-leg capture | A1 | 7 | Shipped |
| E2 | Operator voice isolation | A2 | 8 | Shipped 0.4.0, unmeasured live |
| E3 | Audio lifetime and deletion | E5 | 7 | Whole-meeting deletion landed |
| E4 | Evidence-linked notes | B5 B6 | 8 | Generator unadmitted; matrix re-runnable |
| E5 | Honest incompleteness | B6 | 5 | Needs E4 |
| E6 | Correction and regeneration | B7 | 5 | Restore shipped; regeneration needs E4 |
| E7 | Exact retrieval | D2 | 6 | Registered — **search, not retrieval** |
| E8 | Commitment handoff | C2 C3 | 4 | Wave 2 item 10 |
| E9 | Preparation brief | E3 | 4 | Wave 4, with calendar |
| E10 | Shell that never lies | E4 | 9 | Signed Preview bundle exists |
| E11 | Operator-authored live note | B1 | 5 | Shipped 2026-08-06 |
| E12 | Release, distribution, admission | — | 7 | Mixed |
| **E13** | **The corpus store** | **E6 D3** | 7 | **Landed 2026-08-07**, except US-13.6 |
| **E14** | **Organisation: folders, channels, the meeting object** | **E1 E2** | 4 | **US-14.1–14.4 landed 2026-08-08**; folder rename and delete have commands and no surface; channels and E2's sibling views undecomposed |
| **E15** | **Question answering across the corpus** | **D1 D2 D3 D4 D5** | 3 | **US-15.1 landed 2026-08-08**; US-15.3 measured the same day and its store is the next build; US-15.2 blocked on A3; cross-meeting answers are Wave 1 item 6 |
| **E16** | **Note shape: templates, auto-titling, enhanced summary** | **B2 B3 B4** | 2 | **US-16.1 landed 2026-08-07**; US-16.2 measured 2026-08-08 and **closed for this model** at 5/10 against a registered 6–9; B2 B3 undecomposed until Wave 2 |
| **E17** | **Action items with owner and status** | **C1** | — | Wave 2 item 9 |
| **E18** | **Named speakers** | **A3** | — | Wave 3 items 11–12 |
| **E19** | **Long-form ASR at meeting length** | **A4 A5** | — | Wave 3 item 13 |
| **E20** | **Phase 2: calendar, directory, sync, push, workspaces** | **P1–P6** | — | Wave 4 |

**Read the dependency, not the numbering.** E13 is upstream of E14, E15, E17 and the
useful half of E7 — a corpus store is what makes organisation, cross-meeting
questions and a commitment view possible at all. That single edge is why Wave 1 leads
with it and why E7 shipped four stories of exact file search that will not survive a
real corpus.

**E7 is misnamed and the name is the finding.** It is exact search over transcripts
and metadata. The category's headline — ask a question across every conversation and
get an answer — is E15, which had no epic until today and existed as one unproven
story inside E7.

---


## 6. Epic details

### E1 — Consent-first local two-leg capture

Microphone and system audio captured as separate legs on the Operator's Mac, with the
far end told before recording starts. Shipped and proven on real hardware.

#### US-1.1: Two-leg capture with fresh-process recovery
**Feature 1 · J3 · §C · P0 · L · Shipped**

As the Operator, I want capture to survive the app dying mid-meeting, so that a crash
does not cost me the conversation.

**Acceptance criteria:**
- Given a recording is in progress, When the app process dies, Then the captured audio to that point remains on disk and is recoverable on next launch.
- Given a recovered session, When it is reopened, Then the app states the recovery happened rather than presenting the result as an unbroken recording.
- Given only one leg survived, When recovery runs, Then that leg is still bound to retention rather than orphaned.
- Given an interruption receipt that does not match the pair it claims, When recovery runs, Then the meeting is quarantined without rebinding anything.

**Data contract:** `capture-attempt/1`, `capture-session/2`, `capture-interruption/1`, `capture-ownership/1`.

**Validation:** **Pinned** — `recovery::interrupted_partial_pair_is_bound_under_its_original_private_names`, `one_leg_partial_is_still_bound_to_retention`, `mismatched_interruption_receipt_is_quarantined_without_rebinding`, `clean_promoted_pair_without_session_gets_non_product_interruption_receipt`. **Receipted** for the happy path by the real-hardware capture run recorded in `distribution-runbook.md`.

**Refusals:** never present a recovered partial capture as complete.

#### US-1.2: Consent moment before Start
**Feature 1 · J3 · §B · P0 · M · Shipped**

As the Far end, I want to be told a recording is starting, so that I am not recorded
without knowing.

**Acceptance criteria:**
- Given the Operator triggers Start, When conditions are asserted, Then the app states them explicitly and does not claim to have detected what it cannot measure.
- Given headphones and an empty room are Operator assertions, When they are recorded, Then they are stored as assertions, not as measurements.

**Refusals:** no claim of detected conditions. Manual Start and Stop only — no automatic meeting detection, which is a named non-goal for v1.

**Validation:** **Pinned** at the surface by `shell_contract::preview_navigation_spine_keeps_idle_polling_and_safe_capture_actions`. The *wording* of the consent moment is **Unproven** and is an open question — see § 7.

#### US-1.3: Capture refuses rather than degrading silently
**Feature 1 · J3 · §C · P0 · M · Shipped**

As the Operator, I want capture to stop and say so when it cannot do what it
promised, so that I never get a file that looks complete and is not.

**Acceptance criteria:**
- Given the system-audio tap cannot be created, When Start is pressed, Then capture refuses and names the cause rather than recording one leg silently.
- Given microphone permission is denied, When Start is pressed, Then the refusal names the permission and not a generic failure.

**Data contract:** `capture-event/1`.

**Validation:** **Receipted** — the first hardware attempts failed closed on denied microphone access and are recorded in `distribution-runbook.md`. That run also exposed two release defects, which is why this story exists separately from US-1.1.

**Refusals:** never record one leg while presenting a two-leg capture.

#### US-1.4: The transcript is produced locally
**Feature 1 · J3 · — · P0 · L · Shipped**

As the Operator, I want transcription to run on my Mac, so that the meeting audio
never leaves it.

**Acceptance criteria:**
- Given a completed capture, When transcription runs, Then it uses the bundled model and makes no network call.
- Given the packaged runtime, When it is exercised, Then the regression invokes the real transcript model rather than a stub.

**Data contract:** `capture-transcript/1`, `internal-transcript-alpha/1`, `worker-command/2`, `worker-result/2`.

**Validation:** **Pinned** by the packaged-runtime regression strengthened in commit `5fe9aec`. **Receipted** by the real-hardware two-leg capture and local transcription recorded in `distribution-runbook.md`.

**Refusals:** no cloud ASR. This is the product's only true differentiator against every commercial competitor.

#### US-1.5: Operation output never enters the protocol channel
**Feature 1 · J3 · — · P0 · M · Shipped**

As a builder, I want library output isolated from the worker's JSON channel, so that
data-dependent noise cannot corrupt the protocol.

**Acceptance criteria:**
- Given an operation writes to stdout, When the worker runs, Then that output is isolated from the JSON-only protocol channel.

**Data contract:** `worker-command/2`, `worker-event/2`, `worker-result/2`.

**Validation:** **Pinned** — `note_projection::result_requires_exactly_one_terminal_newline_and_no_second_frame_bytes`. **Receipted** — this was a real field defect found on the third hardware attempt and fixed in commit `8a2359f`.

#### US-1.6: A finished transcript survives quit and relaunch
**Feature 1 · J3 · §C · P0 · M · Shipped**

**Acceptance criteria:**
- Given a completed transcript, When the app is truly quit and relaunched, Then the completed transcript screen returns.
- Given the release receipt is written, When it records the run, Then it contains no transcript text.

**Validation:** **Receipted** — observed on real hardware and recorded in `distribution-runbook.md`.

**Refusals:** no transcript text in any receipt. Receipts are content-free by design.

#### US-1.7: Capture is one operator, manually started
**Feature 1 · J3 · §C · P1 · S · Shipped (scope boundary)**

The v1 conditions, stated as a story because they bound every other capture story:
manual Start and Stop, headphones, one enrolled operator at the microphone, nobody
else in the room, local post-meeting processing.

**Refusals:** no speaker playback, live transcription, automatic meeting detection,
calendar preparation, named participants, cross-meeting search, sharing, or
product-development inference. Each is either a later epic or a named non-goal.

**Validation:** **Pinned** as a scope boundary by `build_matrix::production_rejects_every_isolated_surface_or_hybrid_field` and the command exact-sets; **Unproven** as a claim that operators actually work this way, which is a research question and not a code one.

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
- Given the threshold is enrolment-derived, When a checked transcript is shown, Then it says so.

**Data contract:** `capture-transcript/1` (`voiceprint` field), `profile-lifecycle/1`.

**Validation:** **Pinned** for the refusal path; **Unproven** on live meeting audio, which is the open item below.

**Refusals:** never write a transcript that implies a check that did not happen.

#### US-2.2: A profile has a crash-safe lifecycle
**Feature 2 · J5 · §I · P0 · L · Shipped**

As the Operator, I want my voice profile to survive a crash without becoming
ambiguous, so that the app never guesses which of two profiles is mine.

**Acceptance criteria:**
- Given a fresh install, When the lifecycle initializes, Then it builds a fixed sequence-zero baseline and reopens it after a fresh process.
- Given live profile material with no lifecycle authority, When startup runs, Then it is left untouched until the Operator explicitly chooses preserve-first migration.
- Given an unreceipted crash mid-migration, When startup runs, Then it returns to review rather than activating anything.
- Given a receipt-bound crash, When startup runs, Then it resumes safely.

**Data contract:** `profile-lifecycle/1`, `profile-lifecycle-slot/1`.

**Validation:** **Pinned** — `profile_lifecycle::initializes_zero_baseline_and_reopens_it_after_fresh_process`, `refuses_ambiguous_legacy_profile_until_migration_is_reviewed`, `explicit_migration_preserves_exact_legacy_bytes_for_later_review` (22 tests in that module).

**Refusals:** never activate preserved bytes without an explicit Operator choice.

#### US-2.3: Reset removes the profile and leaves meetings alone
**Feature 2 · J5 · §I · P0 · M · Shipped**

**Acceptance criteria:**
- Given reset is confirmed separately, When it runs, Then it writes `deleting` before swapping slots, `staged` before truncating, and `removed` once.
- Given any documented crash point, When startup runs, Then it recovers the pre-swap, post-swap, staged, or post-truncate row.
- Given an impossible staged-before-swap row, When startup runs, Then it quarantines without mutating.
- Given reset completes, When meetings are read, Then meeting storage is untouched.

**Data contract:** `profile-lifecycle/1`.

**Validation:** **Pinned** — `profile_lifecycle::reset_removes_preserved_legacy_bytes_without_opening_a_meeting`, plus the retention-side proof that profile reset leaves meeting storage intact. **Unproven** as a real destructive action: no real profile-reset receipt is claimed.

**Refusals:** reset is exposed only after a separate visible confirmation, and names that meetings remain.

#### US-2.4: Guided enrolment names every unmet requirement
**Feature 2 · J3 · §I · P0 · M · Registered**

As the Operator, I want to be told exactly what my enrolment is still missing, in the
same terms the gate enforces, so that I am not guessing why it is blocked.

**Acceptance criteria:**
- Given incomplete enrolment, When the surface renders, Then every unmet requirement is named in the term the capture gate enforces.
- Given no sitting has been recorded, When the surface renders, Then it reports `blocked` with the first enforced step rather than implying progress.

**Data contract:** `profile-choices/1`.

**Validation:** **Pinned** — `session-core::enrollment_guidance` constants are re-derived from `spike/speaker_gate.py` and pinned by test rather than copied from the screen inventory's prose.

#### US-2.5: Sitting evidence is crash-safe and content-free
**Feature 2 · J3 · §I · P0 · L · Registered**

**Acceptance criteria:**
- Given a sitting is recorded, When it is saved, Then it saves only after derivation cleanup and an absent work directory.
- Given a crash before capture, When startup runs, Then it reconciles to a labelled rehearsal.
- Given abandonment, When it is recorded, Then it labels a rehearsal and never advances enrolment.
- Given recorded evidence, When the snapshot is read, Then it refuses to evaluate without the manifest's verified encoder digest.

**Data contract:** `sitting-evidence/1`, `sitting-capture/1`, `sitting-cleanup/1`, `sitting-rehearsal/1`, `sitting-derived/1`, `sitting-segments/1`, `sitting-derivation/1`.

**Validation:** **Pinned** — 32 tests in `sitting_evidence`, including `a_sitting_saves_only_after_derivation_cleanup_and_absent_work_directory`, `crash_before_capture_reconciles_to_a_labelled_rehearsal`, `abandonment_labels_a_rehearsal_and_never_advances_enrollment`.

**Refusals:** anything deleted before derivation is labelled a rehearsal, never a sitting.

#### US-2.6: Derivation stays on the boundary lane
**Feature 2 · J3 · — · P0 · M · Registered**

**Acceptance criteria:**
- Given `sitting.derive` runs, When it produces material, Then the transcript text never leaves the worker process.
- Given the runtime's encoder is the placeholder, When the operation is invoked, Then it refuses.
- Given the packaged internal-alpha operation set, When it is compared, Then it is unchanged and cross-pinned.

**Data contract:** `sitting-derivation/1`, `worker-command/2`.

**Validation:** **Pinned** — `ALPHA_OPERATIONS` in `worker/main.py` is cross-pinned against `shell_contract.rs`; `shell_contract::preview_commands_are_named_and_preserve_the_production_command_boundary`.

#### US-2.7: Admitted derived material is verified before any durable write
**Feature 2 · J3 · — · P0 · M · Registered**

**Acceptance criteria:**
- Given the worker returns derived material, When `admit_derived_material` runs, Then it verifies capture-row raw digest, manifest encoder identity, embedding digest, and one-per-scorable-segment count before writing anything.
- Given re-admission of the same material, When it is attempted, Then it routes to cleanup retry rather than duplicating.

**Data contract:** `sitting-derived/1`, `sitting-cleanup/1`.

**Validation:** **Pinned** in `sitting_evidence`.

#### US-2.8: Threshold measured on live meeting audio
**Feature 2 · J3 · §I · P1 · L · Blocked on Operator**

As the Operator, I want the gate's threshold derived from real meetings rather than
enrolment sittings, so that the recall figure means something in the field.

**Acceptance criteria:**
- Given a threshold derived only from enrolment, When a transcript is checked, Then the app states that limitation on the transcript itself. *(Already true.)*
- Given real sittings are recorded, When operating points are derived, Then the Operator selects one and the selection is recorded with its measurements.

**Validation:** **Unproven** and unprovable without real sittings. The 30.7% recall figure in `product-definition.md` came from a real speaker-gated take and is the only field measurement this epic has.

**Dependencies:** encoder admission verdict (US-12.4), real enrolment sittings.

---

### E3 — Audio lifetime and deletion

The transcript is the retained evidence. Audio has a stated lifetime and is removed on
it. Everything here is destructive, so every story has a refusal.

#### US-3.1: Automatic deletion on the stated deadline
**Feature 3 · J5 · §K · P0 · M · Shipped**

**Acceptance criteria:**
- Given the retention deadline passes, When the app next launches, Then both bound audio legs are removed and an `audio-deletion/1` receipt records it.
- Given deletion completes, When the meeting is opened, Then the transcript is present, digest-matched and readable.
- Given a crash at any receipt phase, When startup runs, Then the phase is recovered rather than restarted.

**Data contract:** `audio-deletion/1`, `audio-retention-policy/1`, `meeting/2`.

**Validation:** **Pinned** — `retention::manual_deletion_recovers_each_interrupted_receipt_phase` and 27 further tests. **Receipted** — a real `audio-deletion/1` `removed` receipt, SHA-256 `59a500cb…`, observed 2026-08-02.

#### US-3.2: Per-meeting audio release
**Feature 3 · J5 · §G · P0 · M · Registered**

**Acceptance criteria:**
- Given a retained meeting, When the Operator confirms twice, Then only that meeting's audio is released.
- Given the meeting is active, When release is requested, Then it defers without opening the meeting's directory.
- Given a not-yet-due deadline, When release is requested, Then it proceeds anyway and is idempotent.
- Given a nonterminal product operation on that meeting, When release is requested, Then it is refused.

**Data contract:** `audio-deletion/1`, `meeting-operation-commit/1`.

**Validation:** **Pinned** — `retention::manual_deletion_releases_an_until_manual_meeting_and_preserves_other_private_content`, `manual_deletion_defers_an_active_meeting_without_opening_its_directory`, `manual_deletion_ignores_a_not_yet_due_deadline_and_is_idempotent`; surface pinned by `shell_contract::preview_meeting_detail_requires_two_explicit_steps_for_audio_deletion`.

**Refusals:** releases audio only. It never deletes the meeting record, transcript, note, profile, or another meeting.

#### US-3.3: Whole-meeting deletion
**Feature 3 · J5 · §G · P0 · M · Built 2026-08-07**

As the Operator, I want to delete a meeting entirely, so that a conversation that
should not have been captured can be removed.

**Acceptance criteria:**
- Given a meeting exists, When deletion is authorized, Then every artifact bound to it is removed and a `meeting-deletion/1` receipt records what was removed.
- Given deletion is interrupted, When the app restarts, Then reconciliation completes it and never leaves a meeting that reads as intact but is not.
- Given a meeting is active, When deletion is requested, Then it is refused before any storage is read.
- Given deletion completes, When the library is opened, Then the meeting is absent, not tombstoned.
- Given the Operator has not confirmed twice, When deletion is requested, Then it does not proceed.

**Data contract:** `meeting-deletion/1`. Its receipt lives at `<root>/deletions/<meeting_id>.json`, **outside** the meeting, because a receipt inside the directory it removes destroys its own evidence.

**Validation:** **Pinned** — 12 tests in `meeting_deletion`, including `a_removed_meeting_leaves_nothing_behind_and_says_what_it_took`, `the_receipt_records_digests_and_never_the_bytes`, `an_active_meeting_is_refused_without_its_storage_being_touched`, `an_interrupted_removal_completes_rather_than_restarting`; surface pinned by `shell_contract::whole_meeting_deletion_is_a_separate_twice_confirmed_control`. **Unproven** as a real action — no real `meeting-deletion/1` receipt exists.

**Refusals:** must not run against real meetings during development. The confirmation token is a distinct type from the audio one, so a confirmation for the smaller act cannot satisfy the larger.

#### US-3.4: The retention overview always tells the truth
**Feature 3 · J5 · §F · P0 · M · Registered**

As the Operator, I want a standing view of what is still held, so that I do not have
to open each meeting to find out.

**Acceptance criteria:**
- Given the Meetings screen renders, When retention is shown, Then it is freshly checked rather than cached from an earlier read.
- Given a retention read fails, When the model updates, Then the failure serializes before the model changes rather than after.

**Data contract:** `audio-retention-policy/1`.

**Validation:** **Pinned** — `shell_contract::meetings_screen_carries_the_standing_retention_overview`, `retention_failure_serializes_before_changing_the_model`.

#### US-3.5: Retention policy wording
**Feature 3 · J5 · §B §G · P0 · S · Blocked on Operator**

The wording of what the app promises about retention. Two drafted options have no
encoding in `validate_start_request`, so whichever is chosen is also a build.

**Validation:** **Unproven** — this is a wording decision, not a testable behaviour, until the wording exists.

#### US-3.6: Deletion never crosses a meeting boundary
**Feature 3 · J5 · — · P0 · M · Shipped**

**Acceptance criteria:**
- Given one meeting's audio is released, When other meetings are read, Then their private content is preserved exactly.
- Given a profile reset, When meetings are read, Then meeting storage is untouched.
- Given released audio, When the transcript and note are read, Then both are intact.

**Validation:** **Pinned** — `retention::manual_deletion_releases_an_until_manual_meeting_and_preserves_other_private_content`, plus `releasing_audio_leaves_entries_the_release_was_never_told_about`.

#### US-3.7: Real destructive actions are Operator actions
**Feature 3 · J5 · — · P0 · S · Standing constraint**

**Refusals:** exercise real destructive actions only as Operator actions before beta admission. Synthetic tests do not advance the wave C human gate, whatever they prove about the code.

**Validation:** **Unproven** by construction — this is the constraint that makes the other stories' `Unproven` lines honest.

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
- Given duplicate ordinals in a projection, When it is read, Then they are preserved rather than silently merged.
- Given recursive order, unknown ids, or Unicode byte offsets, When the projection is read, Then it is refused.

**Data contract:** `note-claim-projection/1`, `note-projection-result/1`, `note-generation-request/1`, `note-generation-result/1`.

**Validation:** **Pinned** — `note_projection::shared_fixture_accepts_valid_rows_and_preserves_duplicate_ordinals`, `shared_fixture_refuses_recursive_order_duplicates_unknowns_and_unicode_byte_offsets`, `shared_fixture_maps_only_closed_refusals`.

**Refusals:** a claim without its citation, or a "verified" state nothing checked, is the failure this product exists to not ship.

#### US-4.2: Refuse a claim that inverts its evidence
**Feature 4 · J1 · — · P0 · M · Built 2026-08-07, effect unverified**

As the Operator, I want a claim that contradicts the words it cites to be refused, so
that fixing an unrelated bug does not start admitting inverted claims.

**Acceptance criteria:**
- Given cited evidence containing a polarity term, When the claim contains that term in no form, Then the claim is refused with code `claim-polarity`.
- Given evidence and claim that both carry the polarity, When the gate runs, Then the claim is unaffected.
- Given the gate is added, When the matrix re-runs, Then no fixture that was passing starts failing.

**Data contract:** `mlx-note-admission/1` (`response_contract`, claim `must_not_drop_polarity_terms`).

**Validation:** **Pinned** — six tests in `test_mlx_note_admission.py`. **Unproven** at the matrix level and currently unprovable; see US-4.8.

**Refusals:** not a model search, and not to be folded into the identifier work.

#### US-4.3: Close the identifier truncation
**Feature 4 · J1 · — · P0 · M · Blocked on US-4.8**

One characterized mechanism on three fixtures: `sf-` plus 64 hex, cut at 67
characters, with the margin receipt showing one decision losing three times at the
same step with the same runner-up token.

**Acceptance criteria:**
- Given the intervention is preregistered before it runs, When it runs, Then its prediction is recorded ahead of the result and reported against it whether or not it holds.
- Given the polarity gate is active, When the matrix re-runs, Then `negation-proposal` still refuses — on `claim-polarity` rather than `citation-locator`.

**Validation:** **Unproven** — blocked, because every intervention is defined as a matrix run.

#### US-4.4: The generator stays off the Preview critical path
**Feature 4 · J1 · §E · P0 · M · Registered**

**Acceptance criteria:**
- Given the note bridge exists, When Preview is built, Then no generator is wired into it and `note.inspect` stays boundary-lane.
- Given the production and preview configs, When they are compared, Then both exclude the unadmitted note-runtime resources.

**Data contract:** `note-bridge-command/1`, `note-bridge-event/1`, `note-runtime/1`.

**Validation:** **Pinned** — `build_matrix::production_and_preview_exclude_the_unadmitted_note_runtime_resources`, `shell_contract::product_operation_facade_registers_restoration_but_not_regeneration`.

#### US-4.5: Every response rule is advertised as well as enforced
**Feature 4 · J1 · — · P0 · M · Shipped**

As a builder, I want the parser's rules stated in the contract it advertises, so that
a candidate refused for breaking a rule it was never given is not counted as measured.

**Acceptance criteria:**
- Given `_decode_response` enforces a rule, When `response_contract` is read, Then that rule appears in it.
- Given a rule is advertised, When the parser runs, Then it is enforced.

**Validation:** **Pinned** — `test_the_mask_agrees_with_the_contract_it_claims_to_enforce`, `test_advertised_contract_nonempty_and_empty_shapes_pass_unchanged_parser`, and `test_the_polarity_rule_is_advertised_as_well_as_enforced`.

**Refusals:** a rule advertised and not enforced is the same defect facing the other way.

#### US-4.6: Bounded, fail-closed generation
**Feature 4 · J1 · — · P0 · M · Registered**

**Acceptance criteria:**
- Given a malformed, unknown-citation, timed-out, or digest-mismatched response, When it is decoded, Then the outcome is `transcript-only`.
- Given output exceeds the registered bound, When it is produced, Then it is refused rather than truncated into something parseable.

**Data contract:** `bounded-extraction-output/1` (`notes/summarize.py`, a research-lane schema rather than a session-core one).

**Validation:** **Pinned** — `test_malformed_unknown_citation_timeout_and_digest_mismatch_are_transcript_only`.

#### US-4.7: Results are readable beside their evidence
**Feature 4 · J1 · — · P0 · S · Shipped 2026-08-06, read 2026-08-07**

As the Operator, I want each generated claim laid beside the words it cites, so that
the semantic adjudication is something I can actually perform.

**Acceptance criteria:**
- Given recorded results, When the sheet is produced, Then each claim appears beside the transcript text it cites.
- Given the sheet runs, When it executes, Then it loads no model, touches no network, and changes no digest.

**Validation:** **Pinned** — `test_the_polarity_term_list_has_exactly_one_owner`. Its first reading on 2026-08-07 produced the finding behind US-4.2, which is the strongest evidence that this story was worth building.

#### US-4.8: Make the registered runtime rebuildable
**Feature 4 · — · — · P0 · M · **Buildable now***

As a builder, I want the pinned runtime to be reproducible from its own
specification, so that any registered experiment can be re-run by anyone.

**Acceptance criteria:**
- Given the pinned specification, When an environment is built from it on a clean machine, Then `local_mlx_provider` accepts it.
- Given two environments built by different installers from the same specification, When both are checked, Then both are accepted.
- Given the change lands, When request digests are compared, Then none has moved — `runtime_identity` is not an input to any request, and a moved request digest withdraws the change.

**Evidence:** three environments on one machine reproduced `METADATA` 9 of 9 and `RECORD` 1 of 9. `RECORD` is installer-written and varies with the installer and with byte-compilation. Confirmed independently 2026-08-07 on a package the original measurement never touched: `idna==3.10` under pip with and without byte-compilation gives one `METADATA` digest and two `RECORD` digests, differing by 8 `.pyc` rows.

**Validation:** **Pinned** — `test_the_registered_runtime_pins_only_wheel_shipped_files` (asserted on shape, so re-adding any installer-written file under a new key still fails), `test_dropping_record_moves_no_request_digest`, `test_a_runtime_carrying_a_record_digest_is_refused`. **Receipted** — `notes/mlx_note_matrix_receipt_wheel_pin.json`, a fresh environment built 2026-08-07 from the corrected specification, accepted (`METADATA` 3 of 3, all three `RECORD` digests different from the old pin's), with `every_fixture_ran: true` where it had been `false`. **Unproven** for the second acceptance criterion: only pip was exercised, so "accepted under two installers" is unrun — uv was the installer that reproduced none of three and is the one worth trying.

**Refusals:** do not repair `RECORD`; drop it. Pin the wheel, not the installation. A third narrowing inherits the structure of the two that failed — each varied one dimension and held the others fixed.

---

### E5 — Honest incompleteness

"Not captured" is never shown as "never said", and the Operator can see how much of a
note is checkable before opening it.

#### US-5.1: Gaps render as gaps
**Feature 5 · J1 · §E · P0 · M · Registered**

**Acceptance criteria:**
- Given the gate withheld turns, When the transcript is displayed, Then withheld spans are visible positionally with their cause, and no meeting text is invented to fill them.
- Given a transcript is copied, When it lands in the clipboard, Then the gaps are copied with it.

**Data contract:** `transcript-view/1`.

**Validation:** **Pinned** — `shell_contract::withheld_turns_render_positionally_without_meeting_text`.

#### US-5.2: Warnings keep producer order and do not stack
**Feature 5 · J1 · §E · P1 · S · Registered**

**Acceptance criteria:**
- Given multiple transcript warnings, When they render, Then there is one per paragraph and producer order is preserved.

**Validation:** **Pinned** — `shell_contract::transcript_warnings_render_one_per_paragraph_and_keep_producer_order`.

#### US-5.3: Rendered transcript text is untrusted input
**Feature 5 · J1 · §E · P0 · M · Shipped**

**Acceptance criteria:**
- Given transcript text, When it renders, Then it is treated as untrusted and the shell's CSP is restrictive and local.

**Validation:** **Pinned** — `shell_contract::bundled_shell_uses_restrictive_local_csp`, plus the shell-wide ban on `innerHTML`.

#### US-5.4: Checkable proportion before opening
**Feature 5 · J1 · §F · P1 · M · Blocked on E4**

**Acceptance criteria:**
- Given a note with typed claims, When the library lists it, Then the proportion of claims whose locators resolve is shown.
- Given no note has been generated, When the library lists the meeting, Then no proportion is shown — not zero, and not a placeholder.

**Validation:** **Unproven.** Building it earlier means building against synthetic input, which is how a number nobody measured gets rendered as a fact.

#### US-5.5: The proportion is measured on a real gated capture
**Feature 5 · J1 · — · P1 · M · Blocked on E4 and E2**

**Validation:** **Unproven** — needs both an admitted generator and a real gated capture. Named separately from US-5.4 because the surface and the measurement are different work and only one of them is blocked on the generator alone.

---

### E6 — Correction and regeneration

Restoring a withheld turn changes the evidence, so the note built on it goes stale and
must be regenerated rather than silently kept.

#### US-6.1: Restore a withheld turn
**Feature 6 · J4 · §E · P0 · M · Registered 0.2.2, reachable 0.4.0**

**Acceptance criteria:**
- Given a withheld turn, When the Operator restores it, Then a new current transcript is published and the projection is rebuilt in place.
- Given a restoration already happened, When a second is attempted, Then it resolves against the moved digest rather than being refused as a changed source.

**Data contract:** `transcript-restoration-request/1`, `transcript-restoration-result/1`, `meeting-operation-commit/1`.

**Validation:** **Pinned** — `shell_contract::product_operation_facade_registers_restoration_but_not_regeneration`, `product_operation_facade_uses_top_level_frozen_ui_arguments`.

#### US-6.2: Restoration is reachable from the screen after a recording
**Feature 6 · J4 · §C · P0 · M · Corrected 2026-08-06**

As the Operator, I want to restore a withheld turn right after the meeting, so that
the remedy is not delayed by navigation.

**Acceptance criteria:**
- Given a recording just finished, When the screen renders, Then the restore control is present there and not only in Meetings.
- Given restoration publishes a new transcript, When the screen updates, Then it rebuilds its projection in place.

**Validation:** **Pinned** — `shell_contract::the_screen_after_a_recording_can_restore_a_withheld_turn`.

**Evidence:** the gate's worst failure is a colleague cut from a record that cannot be re-made, and that remedy is worth less the longer it waits.

#### US-6.3: Regeneration stays unregistered until admission
**Feature 6 · J4 · §E · P0 · S · Deliberate absence**

**Refusals:** regeneration must not be registered as a command until a generator passes admission. A stale-note flow that regenerates from an unadmitted generator would produce a fresh note nobody may trust.

**Validation:** **Pinned** — `shell_contract::product_operation_facade_registers_restoration_but_not_regeneration` fails if regeneration is added.

#### US-6.4: A note whose evidence moved is marked stale
**Feature 6 · J4 · §E · P0 · M · Blocked on E4**

**Acceptance criteria:**
- Given a note cites a transcript digest, When restoration publishes a new one, Then the note is marked stale and says why.
- Given a stale note, When it is displayed, Then it is never shown as current, and regeneration is offered rather than performed silently.

**Validation:** **Unproven.**

#### US-6.5: A correction never invents a new record
**Feature 6 · J4 · — · P0 · M · Registered**

**Acceptance criteria:**
- Given a restoration, When it commits, Then the operation is recorded once and re-running it is idempotent.
- Given simultaneous storage mutation, When restoration runs, Then it refuses rather than interleaving.

**Validation:** **Pinned** — the independently audited restoration coordinator covers every durable phase; `meeting_coordination` refuses simultaneous mutation.

---

### E7 — Retrieval

Enter with a question, land on the claim.

#### US-7.1: A read-only library projection
**Feature 7 · J1 · §F · P0 · L · Registered**

**Acceptance criteria:**
- Given the library rebuilds, When it runs, Then it is read-only and quarantines tampered meetings rather than rendering them.
- Given an active meeting, When the snapshot is taken, Then that directory is excluded and the exclusion set is the snapshot authority.

**Data contract:** `library-metadata/1`.

**Validation:** **Pinned** — `library_read::rebuild_is_read_only_and_quarantines_tampered_meetings`, `exclusion_set_skips_active_directory_and_is_snapshot_authority` (25 tests).

#### US-7.2: Exact search over transcripts and metadata
**Feature 7 · J1 · §F · P0 · L · Registered**

**Acceptance criteria:**
- Given a query, When results return, Then each is bound to exact transcript bytes, verified by digest, path and parsed-byte recheck.
- Given a result is opened, When the transcript renders, Then it lands on the opened Unicode scalar span rather than the top.
- Given a metadata-only result, When it renders, Then it offers no transcript action.

**Validation:** **Pinned** — `shell_contract::preview_exact_search_lands_on_opened_unicode_scalar_span`, `metadata_only_search_results_have_no_transcript_action`, `preview_transcript_open_rechecks_the_bound_digest_and_path`.

#### US-7.3: Handles are opaque and single-generation
**Feature 7 · J1 · §F · P0 · M · Registered**

As a builder, I want the browser to hold no meeting identifier, so that a stale handle
cannot address storage.

**Acceptance criteria:**
- Given the shell receives a result, When it holds a reference, Then it is an opaque handle and never a path, digest or meeting id.
- Given a mutation boundary, When it is crossed, Then every retained handle is invalidated.
- Given navigation, When it refreshes, Then handle generations are response-scoped.

**Validation:** **Pinned** — `shell_contract::private_library_reader_has_no_registered_command_or_storage_authority`, `preview_library_navigation_refreshes_response_scoped_handle_generations`.

#### US-7.4: The reader loop returns where it came from
**Feature 7 · J1 · §F · P1 · M · Registered**

**Acceptance criteria:**
- Given a route is opened, When the Operator returns, Then origin, focus and scroll are preserved and start ordering stays safe.

**Validation:** **Pinned** — `shell_contract::preview_routes_preserve_origin_focus_scroll_and_safe_start_ordering`.

#### US-7.5: Land on a claim, not a document
**Feature 7 · J1 · §F · P1 · M · Blocked on E4**

**Validation:** **Unproven.**

#### US-7.6: Retrieval answers a question weeks later
**Feature 7 · J1 · §F · P0 · L · Unproven as an outcome**

The job, stated as a story so the epic is not mistaken for its mechanism: recover what
was decided and what was promised, weeks later, without having taken notes by hand.

**Validation:** **Unproven.** No count of search results or claims stands in for this. Whether the Operator finds what they needed is the outcome, and it has not been measured. See § 8 on why no count may occupy that position.

---

### E8 — Commitment handoff

A view organized by what was promised. The terminal action is export — never a
checkbox, because the moment the tool offers one it owns follow-through.

#### US-8.1: `view: recorded-actions` over the library
**Feature 8 · J2 · §F · P1 · M · Blocked on a scope decision**

**Acceptance criteria:**
- Given commitments extracted into claims, When the Operator selects the commitment view, Then it is a filter over the existing library, not a separate surface.
- Given a commitment is shown, When the Operator acts on it, Then the only terminal action is export.

**Refusals:** no status field, no owner field, no completion state, no checkbox.

**Blocked by:** "copy/export remains disabled until the separate redaction and export decision closes." The view is not the open part; the export is.

#### US-8.2: The redaction and export decision
**Feature 8 · J2 · — · P0 · S · Blocked on Operator**

What may leave the machine, in what form, with what redaction. Everything in E8 waits
on it, and so does any future sharing story.

**Validation:** **Unproven** — a decision, not a behaviour.

#### US-8.3: Commitments are extracted, not managed
**Feature 8 · J2 · §F · P1 · S · Decided**

**Refusals:** *Counterevidence acknowledged and the non-goal stands.* Wispr Flow shipped the checkbox — a `Todos` table with open/closed status, a tasks tab, a `meetingId` key — and six of six colleagues surveyed wanted action items in the note. None of that reaches the reason for the non-goal, which is about owning follow-through, not about extracting commitments.

#### US-8.4: Export carries its evidence
**Feature 8 · J2 · §F · P1 · M · Blocked on US-8.2**

**Acceptance criteria:**
- Given a commitment is exported, When it lands elsewhere, Then it carries the verbatim evidence it cites, because a commitment without its words is the category's standard failure.

**Validation:** **Unproven.**

---

### E9 — Preparation brief

What happened last time with this person, before the meeting. **Outside v1** (wave H).
These stories exist so the epic is specified rather than empty, and none may be built
until an Operator scope decision moves it in, the way the §D live note moved in on
2026-08-06.

#### US-9.1: Local read-only calendar
**Feature 9 · J0 · — · P1 · M · Outside v1**

**Acceptance criteria:**
- Given EventKit access, When the brief is built, Then it is read-only and no calendar data leaves the Mac.

**Refusals:** the slice's own conditions list excludes "calendar preparation" outright, and §H first run deliberately omits `offer-calendar` because it crosses the envelope.

#### US-9.2: The counterparty half stays open
**Feature 9 · J0 · — · P2 · XL · Open, possibly unbridgeable**

Who spoke versus who was invited. Open for *local audio*: nobody bridged it from
sound. The clause "and the market has not bridged it either" was falsified
2026-08-06 — Wispr Flow ships named speakers by combining a calendar roster, an OAuth
grant into the org's directory, accessibility-tree polling of Zoom and Teams, LLM
inference over address terms, and one-click human correction.

**Refusals:** every one of those paths crosses a non-goal here.

#### US-9.3: A brief that is wrong is worse than none
**Feature 9 · J0 · — · P1 · M · Outside v1**

**Acceptance criteria:**
- Given the brief cannot establish who attended, When it renders, Then it says so rather than showing the invitee list as if it were the attendee list.

**Validation:** **Unproven.**

#### US-9.4: Moving E9 into v1 is a dated amendment
**Feature 9 · — · — · P0 · S · Process**

**Acceptance criteria:**
- Given a decision to build E9, When it is taken, Then it is recorded as a dated amendment in `product-definition.md` first, because the work serves a feature currently outside scope.

---

### E10 — Shell that never lies

At menubar size, degradation is a beat rather than an error.

#### US-10.1: The tray tells the truth
**Feature 10 · J3 · §A · P0 · M · Shipped 0.2.2**

**Acceptance criteria:**
- Given any capture state, When the tray renders, Then it matches the truth table and close-to-tray does not imply the app stopped.

**Validation:** **Pinned** at the surface; **Receipted** by the 0.2.2 release record.

#### US-10.2: Startup failure is honest
**Feature 10 · J3 · §J · P0 · S · Shipped 0.2.2**

**Acceptance criteria:**
- Given a staged runtime whose manifest does not match, When the app starts, Then it fails closed and names the cause rather than starting degraded.
- Given the shell loads, When it renders, Then it shows a safe state before the runtime preflight completes.

**Data contract:** `app-runtime/1`.

**Validation:** **Pinned** — `shell_contract::shell_renders_safe_state_before_runtime_preflight`. **Receipted** — this fired for real on 2026-08-06 when a staged worker predated `permission_probe`; the lockstep is the designed behaviour, not a defect.

#### US-10.3: First run derives its step from a live measurement
**Feature 10 · J3 · §H · P0 · L · Registered 2026-08-06**

**Acceptance criteria:**
- Given first run opens, When a step is chosen, Then it is derived from a live measurement, not a stored completion flag.
- Given a permission cannot be asked about, When the state is shown, Then "we could not ask" is a different screen from "you said no".
- Given a request path did not run, When its result is reported, Then it says unmeasured rather than unknown.
- Given any panel, When it is shown, Then it can be left.

**Data contract:** `permission-probe/1`, `app-runtime/1`.

**Validation:** **Pinned** — `shell_contract::first_run_claims_its_route_and_every_panel_can_be_left`.

**Refusals:** first run may not claim a permission state it cannot measure.

#### US-10.4: The probe is a digest-verified child
**Feature 10 · J3 · — · P0 · M · Registered**

**Acceptance criteria:**
- Given the app executes the probe, When it is spawned, Then it is digest-verified from `app-runtime/1` like every other executed child.
- Given the manifest's required set changes, When writer or reader disagree, Then it fails closed.

**Data contract:** `app-runtime/1` (`permission_probe` resource).

**Validation:** **Pinned** — `worker/main.py` compares `set(document) != required` and Rust's `RuntimeManifest` is `deny_unknown_fields`, so writer and both readers move in one commit or the manifest fails closed.

#### US-10.5: Execute the two request paths in a signed bundle
**Feature 10 · J3 · §H · P0 · M · **Buildable now***

As a Cohort operator, I want first run to actually request permissions on my machine,
so that the screen is not describing a path nobody has taken.

**Acceptance criteria:**
- Given a signed preview bundle, When first run requests microphone access, Then macOS prompts and the state is recorded against that bundle's identity.
- Given the system-audio request runs, When a tap is created, Then the outcome is recorded, and the microphone permission it did not ask about is reported as unmeasured.
- Given an unsigned or ad-hoc bundle, When a request path is reached, Then it is refused.

**Validation:** **Unproven** — neither request path has executed anywhere.

**Refusals:** never run a request path outside the signed bundle; it mutates the calling application's TCC state and answers about the wrong binary.

**Dependencies:** `worker/build_runtime.sh` stages the runtime — pinned CPython 3.12.13, whisper-large-v3-turbo at a pinned revision, and two Swift helpers. Only the `build-alpha-encoder` lane needs the ECAPA ONNX.

#### US-10.6: The shipped shell may invoke only what it is granted
**Feature 10 · J3 · — · P0 · M · Shipped 0.2.1**

**Acceptance criteria:**
- Given the shell invokes a command, When the build runs, Then the window capability grants it or the build fails.
- Given the main window, When its capability is read, Then it names every command and grants no generic capability.

**Validation:** **Pinned** — `shell_contract::shipped_shell_is_permitted_every_command_it_invokes`, `main_window_has_only_named_commands_and_no_generic_capability`, `preview_window_is_a_separate_capture_shell_with_narrow_product_commands`.

**Evidence:** the 0.2.0 cohort DMG gated its record entry and search on a dev-only preview lane flag, so neither was reachable on any machine while the mechanical suite stayed green. This pin exists because of that.

#### US-10.7: Exactly one build lane at a time
**Feature 10 · — · — · P0 · M · Shipped**

**Acceptance criteria:**
- Given surface features, When the build runs, Then exactly one lane is selected.
- Given each lane's config, When it is validated, Then it rejects every field belonging to another lane.

**Validation:** **Pinned** — all 9 `build_matrix` tests.

**Risks:** `gen/schemas` flips wholesale between lanes. The committed form is `main-window`, so production must be the last build before committing — a trap that has no pin and is recorded in `CLAUDE.md` instead.

#### US-10.8: Navigation is persistent and content-free
**Feature 10 · J3 · §A · P1 · M · Registered**

**Acceptance criteria:**
- Given navigation renders, When library entries appear, Then they are content-free.
- Given generated buttons, When they render, Then each binds its own activation.

**Validation:** **Pinned** — `shell_contract::preview_shell_keeps_navigation_persistent_and_library_navigation_content_free`, `generated_preview_library_buttons_bind_their_own_activation`.

#### US-10.9: One instance, and it starts before anything else
**Feature 10 · — · — · P0 · S · Shipped**

**Validation:** **Pinned** — `shell_contract::single_instance_is_the_first_plugin_and_precedes_app_setup`.

---

### E11 — Operator-authored live note

The Operator types their own notes during the meeting. Entered v1 by Operator decision
on 2026-08-06; shipped the same day.

#### US-11.1: Type during the meeting, keep it after
**§D · J3 · §D · P0 · M · Shipped 2026-08-06**

As the Operator, I want to write my own notes while listening, so that what I chose to
write down is not lost — it is not recoverable from the recording afterwards.

**Acceptance criteria:**
- Given the Operator types, When the text is saved, Then the surface renders what storage confirmed, not what is in the textarea.
- Given the meeting is dismissed, When the Operator returns later, Then the note is still reachable.

**Data contract:** `operator-note/1`. A fixed-path file, atomically swapped; the frozen `meeting/2` contract is untouched, so an operator note can never make a meeting unreadable to an older build.

**Validation:** **Pinned** — `operator_note::a_note_round_trips_and_replaces_in_place`, `shell_contract::the_live_note_is_the_operators_alone_and_says_what_it_cannot_do`.

**Refusals:** interpretation, never evidence. Nothing cites it and no claim resolves to it. No status, checkbox or owner field.

#### US-11.2: Overlapping saves serialize
**§D · J3 · §D · P0 · S · Shipped**

**Acceptance criteria:**
- Given saves overlap, When they are written, Then they serialize rather than dropping.
- Given Stop is pressed with an unsaved edit, When the command runs, Then the pending write flushes first and the guard is set before the flush.

**Validation:** **Pinned** — the shell's write-queue tests.

#### US-11.3: Unreadable is not the same as empty
**§D · J3 · §D · P0 · S · Shipped**

**Acceptance criteria:**
- Given the note file is unreadable, When a write is attempted, Then it is refused rather than silently replacing it.
- Given a meeting with no note, When it is read, Then it reads empty and not unreadable.

**Validation:** **Pinned** — `operator_note::a_meeting_with_no_note_reads_empty_and_not_unreadable`, `an_unreadable_note_is_not_silently_replaced`.

**Refusals:** "could not be read" and "nothing written" lead a reader to opposite conclusions and must never collapse.

#### US-11.4: The note is bounded
**§D · J3 · §D · P1 · S · Shipped**

**Acceptance criteria:**
- Given a note past the ceiling, When it is written, Then it is refused rather than truncated.

**Validation:** **Pinned** — `operator_note::a_note_past_the_ceiling_is_refused_rather_than_truncated`.

#### US-11.5: Retention follows the transcript
**§D · J5 · §D · P0 · S · Decided**

Text the Operator wrote is kept as long as the transcript is kept, and is not subject
to the audio deletion period. It *is* removed by whole-meeting deletion (US-3.3).

**Validation:** **Pinned** — `meeting_deletion::a_removed_meeting_leaves_nothing_behind_and_says_what_it_took` names `operator-note.json`.

---

### E12 — Release, distribution and admission

Cross-cutting. Not a north-star feature, but every feature reaches the Operator
through it.

#### US-12.1: The bundle is signed, notarized and stapled
**Cross-cutting · P0 · M · Shipped**

**Acceptance criteria:**
- Given a release build, When it is verified, Then Gatekeeper, notarization and stapling all pass.
- Given the enclosing app, When it is signed, Then it is signed last, because signing the executable standalone first makes it seal the surrounding bundle.

**Validation:** **Pinned** — `shell_contract` asserts the signing order and the audio-input entitlement. **Receipted** — passes on every recorded build.

#### US-12.2: Every executed child is digest-verified
**Cross-cutting · P0 · M · Shipped**

**Acceptance criteria:**
- Given the app spawns a child, When it does, Then that child is digest-verified from `app-runtime/1` first.

**Data contract:** `app-runtime/1`.

**Validation:** **Pinned** — exact-set on both sides.

#### US-12.3: The closure receipt
**Cross-cutting · P0 · S · Blocked on Operator**

**Acceptance criteria:**
- Given an unchanged build, When the Operator completes a run, Then `automatic_deletion`, `consented_hardware_run` and `clean_transfer` are recorded against that one build.
- Given a version changes, When the receipt is consulted, Then it does not transfer — each version restarts it.

**Validation:** **Unproven.** A repository search on 2026-08-06 found no filled instance. Not another transfer: the activity has happened repeatedly and only the record is missing.

#### US-12.4: Encoder admission verdict
**Cross-cutting · P0 · M · Blocked on Operator**

**Acceptance criteria:**
- Given Fbank parity, packaging and cold-load checks are recorded, When the Operator issues a verdict, Then the default runtime's encoder stops being a placeholder.
- Given no verdict, When a sitting is recorded, Then it must not be claimed saved.

**Evidence:** direction chosen 2026-08-03 — ONNX Runtime CPU preferred. Fbank parity within 9.7 × 10⁻⁷ synthetic and 7.4 × 10⁻⁷ on registered LibriSpeech fixtures. Open: gate-classification comparison, transferred-build Gatekeeper check, and the verdict.

#### US-12.5: Cold operator review
**Cross-cutting · P1 · S · Blocked on Operator**

Someone who has not seen the app uses it, before beta admission.

**Validation:** **Unproven** by construction. Passing tests are bounded evidence and do not advance a human gate.

#### US-12.6: Distribution reaches a real machine
**Cross-cutting · P1 · M · Shipped**

**Acceptance criteria:**
- Given a cohort DMG, When it is distributed through R2, Then it installs by drag and passes Gatekeeper on the receiving machine.

**Validation:** **Receipted** — the 0.2.0 install produced a real cohort-operator report, which is what produced 0.3.1's one change.

#### US-12.7: Private meeting material never enters Git
**Cross-cutting · P0 · S · Standing constraint**

**Refusals:** audio, transcripts, note text and profile material stay out by design. Their absence from the repository proves nothing about whether a run happened.

**Validation:** **Pinned** — `.gitignore` plus the redacted-sibling convention. `spike/aec-bound-results.json` is the worked example: gitignored, with `aec-bound-results-redacted.json` shipping in its place.

---

### E13 — The corpus store

A place the corpus can be asked questions, without any file stopping being the
answer.

**Decomposed 2026-08-07, when the queue reached it.** The catalog's rule is that new
epics carry no stories until they are about to be built; this is the first one to
arrive. Seven stories, of which six landed the same day.

#### US-13.1: Measure the scan before replacing it
**Feature E6 · — · — · P0 · S · Landed 2026-08-07**

As the Builder, I want the file-scan library measured at corpus scale, so that
replacing it is a response to a number rather than to a preference.

**Acceptance criteria:**
- Given a synthetic corpus of N meetings, When the scan is timed, Then cold rebuild and warm query latency are recorded for several N.
- Given the benchmark runs, When it writes its corpus, Then every byte is generated from a counter and no real meeting is read.

**Data contract:** `corpus-scan-bench/1`.

**Refusals:** the benchmark must not be pointed at a live storage root. It creates the corpus it measures and deletes the previous one.

**Validation:** **Receipted** — `docs/corpus-scan-measurement.json`, six runs on an M3 Max, checked in because it contains no private material.

**Evidence:** `vertical-slice.md` deferred any index "until a measured corpus exceeds the bounded scan envelope" and named a synthetic no-private-text benchmark as what would settle it. Nobody had run one. The number that actually decided it was not a latency at all — a common word is refused at one meeting.

#### US-13.2: A derived index that cannot become an authority
**Feature E6 · J1 · §F · P0 · L · Landed 2026-08-07**

As the Operator, I want a queryable store over my meetings, so that the library
answers questions the scan cannot, without a database becoming the place my
meetings live.

**Acceptance criteria:**
- Given a validated projection, When the index syncs, Then one row exists per accepted meeting and one row per retained turn.
- Given a populated index, When the database file is deleted, Then rebuilding from the files alone produces the same content digest.
- Given a sync fails partway, When it aborts, Then the previous contents remain intact.

**Data contract:** `corpus-index/1`.

**Refusals:** no column may hold anything the canonical files did not produce. The index reaches its data only through `LibraryRow::derived`, so it cannot become a second parser of private bytes, and claims are deliberately excluded because they come from an out-of-process projector rather than from a file.

**Validation:** **Pinned** — `corpus_index::tests::rebuild_from_files_equals_the_live_index` deletes the database and requires digest equality; `a_column_no_file_produced_breaks_the_rebuild_digest` proves that test can actually see a write-only column; `a_synced_index_holds_one_row_per_validated_meeting`; `a_removed_meeting_leaves_no_turn_behind`; `an_older_schema_is_dropped_and_re_derived_rather_than_read`.

**Correction, same day.** The first version of `fingerprint()` named its columns and counted to eleven, so a column added by a later migration would never have reached the digest — the rebuild test would have passed with exactly the write-only field it exists to catch. It now uses `SELECT *` driven by `column_count()`, and `a_column_no_file_produced_breaks_the_rebuild_digest` adds a column and requires the digest to move. A pin is only as wide as what it reads.

#### US-13.3: The store answers where the scan refuses
**Feature D3 · J1 · §F · P0 · M · Landed 2026-08-07**

As the Operator, I want to filter my meetings by folder, date and state, so that a
corpus stays navigable once it is larger than a screen.

**Acceptance criteria:**
- Given a filter, When it is applied, Then results come back ordered newest-first and matching the scan's order.
- Given more matches than a page, When a page is returned, Then the total and the returned count are separate numbers.
- Given a query the scan refuses with `library-capacity-exceeded`, When the same corpus is filtered, Then a count comes back.

**Refusals:** a page must never be presentable as the whole answer. The scan's rule — never expose a prefix as a library — survives as two fields rather than as a refusal.

**Validation:** **Pinned** — `corpus_index::tests::a_filter_answers_where_the_scan_refuses` asserts the scan refuses and the filter answers on the same corpus; `list_order_matches_the_scans_order` compares against `LibraryProjection::rows()` itself, on a fixture with two meetings sharing a timestamp so the tiebreak is exercised; `lifecycle_round_trips_through_its_canonical_name`.

#### US-13.4: The database is as private as the files
**Feature E6 · — · — · P0 · M · Landed 2026-08-07**

**Acceptance criteria:**
- Given the index is opened, When SQLite creates the file, Then its mode is narrowed to 0600 before anything is written into it.
- Given a database whose mode has widened, When it is opened, Then the open is refused.
- Given a completed write, When the library directory is listed, Then every file in it is 0600 and no journal sidecar remains.

**Refusals:** SQLite opens a path, so none of `storage.rs`'s descriptor-bound guards apply to it. Those checks are re-implemented at the boundary rather than assumed. Error values are content-free: a SQLite error string can carry a column value, and the column values here are transcript text.

**Validation:** **Pinned** — `corpus_index::tests::every_file_the_index_leaves_behind_is_private`, `a_group_readable_database_is_refused_rather_than_opened`, `the_journal_mode_is_read_back_rather_than_assumed`, `a_deleted_meetings_words_do_not_survive_in_the_database_file`.

**Evidence:** WAL was rejected for this reason. Its `-wal` and `-shm` sidecars would hold transcript bytes under permissions SQLite chooses; rollback journalling leaves one file at rest. `secure_delete` is on so a deleted meeting's pages are overwritten rather than left legible in free space, which is how audio is already treated here.

**Correction, same day.** Both halves of that paragraph were prose with nothing behind them. A file listing cannot detect WAL — SQLite removes the sidecars on a clean close, so the one-file assertion passes either way — and `journal_mode` is the pragma where a set can silently not take. It is now read back and the open refuses on anything but `delete`. The `secure_delete` claim is checked the only way it can be: write a distinctive word, remove the meeting, re-sync, and grep the raw database bytes for it.

#### US-13.5: An index carries its own provenance and refuses a future it cannot read
**Feature E6 · — · — · P1 · S · Landed 2026-08-07**

**Acceptance criteria:**
- Given a fresh index, When it is created, Then the schema name and the SQLite build that wrote it are recorded in the file.
- Given a file written by a newer schema, When an older build opens it, Then the open is refused rather than reading columns whose meaning changed.

**Validation:** **Pinned** — `corpus_index::tests::the_index_records_the_sqlite_build_that_wrote_it`, `a_newer_schema_refuses_instead_of_reading_columns_it_does_not_know`.

#### US-13.7: The index is built where the library is read
**Feature E6 · J1 · §F · P0 · S · Landed 2026-08-07**

As the Operator, I want the store to exist on my disk without doing anything to
create it, so that the corpus features have something to read the first time I
open the library.

**Acceptance criteria:**
- Given the library is opened or invalidated, When the projection is rebuilt, Then the index is synced beside it.
- Given the corpus has not changed since the last sync, When the path runs again, Then nothing is written.
- Given the index cannot be opened or written, When the library is read, Then the library behaves exactly as it did before the index existed.

**Refusals:** a cache failure must never reach the operator or degrade a read. Every error from the sync is dropped at the call site, and no diagnostic is emitted, because the only content distinguishing those failures is private.

**Validation:** **Pinned** — `main::tests::preview_reader_commands_preserve_app_snapshot_and_storage_bytes` now asserts that no canonical byte changes across a read and that `library/corpus.sqlite3` is the *only* path that moved; `corpus_index::tests::an_unchanged_corpus_syncs_once_and_then_skips`; `a_direct_replace_clears_the_recorded_corpus_digest`.

**Evidence:** without this the module had no non-test caller, so `Landed` would have described code nobody ran. Skipping an unchanged corpus is what makes a sync affordable on a path walked every time the library opens: one hash over the projection's row identities and one `SELECT`, no write. It is not incremental sync — one changed meeting still replaces the whole index, and US-13.6 carries that.

**Contract amended here, deliberately.** The read path used to be pinned as "no byte in the storage root changes." It is now "no canonical byte changes, and the derived cache is the only thing that moved" — narrower where it must be and stricter everywhere else, since a read path writing anything other than the index still fails the test.

#### US-13.6: The launch scan stops being paid twice
**Feature E6 · J1 · §F · P0 · M · Next**

As the Operator, I want the library to open without re-reading every meeting, so
that launch does not get slower every month I use the product.

**Acceptance criteria:**
- Given an index whose rows match the files, When the app launches, Then unchanged meetings are not re-validated.
- Given a meeting whose canonical record changed, When sync runs, Then that meeting alone is re-derived.
- Given the files and the index disagree, When they are reconciled, Then the files win and the index row is discarded.

**Refusals:** incremental sync must not skip a meeting on any signal weaker than its canonical digest. A directory mtime is not a change signal.

**Validation:** **Unproven** — not built. It needs a per-meeting entry point into `library_read`, which is an audited module; doing that in the same change that introduced a C dependency and a new storage surface would make the audit result unattributable. The store landed first deliberately, and the launch scan still runs in full.

---

### E16 — Note shape: auto-titling, templates, enhanced summary

What a meeting is called, and what its note looks like.

**Partly decomposed 2026-08-07, when the queue reached auto-titling.** Only the
titling stories are written. B2 and B3 — templates and the enhanced summary — stay
undecomposed until the queue reaches Wave 2, per the catalog's rule.

#### US-16.1: A meeting is named by what was said in it
**Feature B4 · J1 · §F · P0 · M · Landed 2026-08-07**

As the Operator, I want each meeting in my library to carry a name I can tell apart
from the others, so that a corpus is something I can navigate rather than a column
of identical rows.

**Acceptance criteria:**
- Given a meeting with a transcript and no operator title, When the library is read, Then the row is named by the first thing said in it that is at least six words.
- Given a meeting with an operator title, When the library is read, Then the operator's title is used and the derived one is not.
- Given a meeting with neither, When the library is read, Then the row sends no label and is named by its capture time.
- Given a derived name, When it is displayed, Then it is marked as something said in the meeting rather than a title somebody wrote.
- Given a withheld microphone turn, When a name is derived, Then that turn is never its source, whether or not any other turn qualifies.

**Data contract:** none — nothing is stored. A derived title is recomputed from the
validated turns on every read.

**Refusals:** a derived title must be a contiguous span of a canonical transcript
turn. It is not composed, paraphrased, or summarised, and no model writes it. It is
also not a search field: every span it can return is already indexed as part of the
turn it came from, so indexing it again would return the same words twice under two
hit kinds.

**Validation:** **Pinned** — `meeting_title::tests` (11 cases, including
`a_title_is_always_a_contiguous_span_of_the_turn_it_came_from` and
`a_withheld_turn_is_never_a_title_even_when_it_is_the_only_candidate`);
`library_read::tests::a_derived_title_is_the_first_long_enough_visible_turn_and_is_never_a_search_field`;
`library_reader::tests::a_row_is_named_by_the_operator_then_by_its_own_first_words_then_by_nothing`.

**Evidence:** every row read `Untitled meeting` — all of them, at once. The operator
title is read from `library/metadata.json`, and `library_metadata.rs` states in its
first line that it "deliberately has no writer", so the fallback was the only
reachable branch. `vertical-slice.md` had already specified generated labels twice
and neither sentence had an implementation behind it.

**Two things it is not.** It is not the category's auto-titling: Granola, Otter and
Circleback print a phrase a model composed, and no rule here will ever produce
"Q3 pricing". And the six-word threshold is a guess at a distribution nobody has
measured — it is the arbitrary number in the module, it changes no contract, and the
operator is its falsifier.

#### US-16.2: A local model chooses the turn
**Feature B4 · J1 · §F · P1 · L · Measured 2026-08-08, not built**

As the Operator, I want the phrase that names a meeting to be the one that actually
identifies it, so that a title is worth reading rather than merely present.

**Acceptance criteria:**
- Given a transcript, When the model runs, Then it returns one offered turn number and no free text.
- Given a returned turn, When a title is made, Then US-16.1's cleaning and ceiling produce it, so the title is a span of that turn.
- Given a gated turn, When candidates are offered, Then it is absent from the offered set, not marked within it.
- Given the model is unavailable, refuses, or exceeds its budget, When a name is needed, Then US-16.1's rule produces it and nothing reports a failure to the operator.

**Refusals:** the model's output is untrusted and it is not the title. It names a
turn; it never supplies words. A turn number outside the offered set is discarded,
not displayed with a caveat.

**Validation:** **Receipted, and the receipt says no.** `notes/MLX_TITLE_SELECTION.md`
registered a two-sided prediction of 6–9 of 10 before the run; three cold runs
returned **5 of 10**, byte-identical. The registered consequence stands: the
selection path is closed for `Qwen2.5-1.5B-Instruct-4bit`. Receipts are committed
and pinned by `TitleReceiptTests`.

**Do not build the Rust seam.** It has no caller and no measurement supporting one,
which is exactly what the probe was run to find out before the seam was written.

**Two findings worth carrying to any next candidate.** 5 of 10 beats every baseline
that reads nothing — the shipped rule scores 1, the best position rule 3, random an
expected 2.28 — so the model is doing something and the honest reading is *between
random and useful*. And separately: **it never abstained**, on any of 30 calls,
including the fixture where nothing said identifies a meeting. A selection model
that cannot abstain cannot be asked whether a meeting has a subject at all.

**Evidence:** the build queue names auto-titling "the cheapest possible test that the
store and a local model are wired together end to end", and this half is the local
model. MLX already ships in the internal-alpha lane for ASR, so `mlx-lm` and a pinned
small model would have been an incremental dependency rather than a new framework.
The probe cost no dependency at all: it ran in a disposable environment against a
model already in the local cache, and answered the question before anything was
added to the product. `MLX_NOTE_ADMISSION.md`'s gate table ends at "no admission
without a recorded human decision" — a builder can register, measure and pin this,
and cannot admit it. That gate was never reached.

---

### E14 — Organisation: folders, channels, the meeting object

Somewhere to put a meeting, and a name the operator chose.

**Partly decomposed 2026-08-08, when the queue reached folders.** Three stories
landed; the folder surface is written and not built. Channels (Otter's) and E2's
sibling views stay undecomposed until the queue reaches them.

#### US-14.1: The organization record gains a writer
**Feature E1 · J1 · §F · P0 · L · Landed 2026-08-08**

As the Operator, I want to name a meeting and put it in a folder, so that a corpus
is something I organise rather than something I scroll.

**Acceptance criteria:**
- Given a record at revision N, When a mutation carries `expected_revision` N, Then it applies and the revision becomes N+1.
- Given a mutation carrying any other revision, When it is submitted, Then it is refused and the current revision is reported.
- Given a mutation that changes nothing, When it is submitted, Then nothing is written and the revision does not move.
- Given a folder is deleted, When the record is replaced, Then every meeting naming it is unfiled in that same replacement.
- Given a malformed record, When any mutation is submitted, Then it is refused and the bytes are left exactly as they were.
- Given a name with a control character, slash or line separator, When it is submitted, Then it is refused rather than stripped.
- Given a name with surrounding whitespace or a decomposed character, When it is submitted, Then it is trimmed and composed rather than refused.

**Data contract:** `library-metadata/1`, unchanged. The writer produces the shape
the reader already enforced; it does not extend it.

**Refusals:** the writer refuses a row for a meeting it cannot see. `library_read`
grants the whole record authority only while every row targets a safely projected
meeting, so one row for a meeting that is not there does not lose one title — it
makes every title and folder unavailable at once.

**Validation:** **Pinned** — 20 tests in `library_metadata::tests`, including
`a_semantic_no_op_writes_nothing_and_keeps_the_revision`,
`a_malformed_record_is_refused_and_left_exactly_as_it_was`,
`the_writer_refuses_a_row_the_reader_would_quarantine`, and
`every_mutation_is_parsed_back_through_the_readers_own_validator`.

**Evidence:** the module opened with "this module deliberately has no writer" from
the day it was written, and that sentence was load-bearing — it is why every row
read `Untitled meeting`. Auto-titling covered the symptom on 2026-08-07 with a
derived label and shipped a three-way precedence whose top branch could never fire.

**The writer proves it agrees with the reader on every call.** Each mutation is
serialized, parsed back through this module's own deserializer, and run through the
same `validate` the reader uses, before a byte is replaced. A draft the reader would
quarantine is an internal error, refused without writing.

#### US-14.2: Deleting a meeting takes its organization row with it
**Feature E1 · J1 · §F · P0 · S · Landed 2026-08-08**

As the Operator, I want deleting one meeting to leave the rest of my library alone,
so that removing a recording does not cost me every folder and title I set.

**Acceptance criteria:**
- Given a meeting with a title and a folder, When it is deleted, Then its row is removed before its `meeting.json` is.
- Given other meetings with titles, When one meeting is deleted, Then their titles and folders remain readable.
- Given a crash between the row removal and the staged transition, When reconciliation runs, Then the deletion completes and the record stays valid.

**Refusals:** a row that cannot be removed is fatal to the deletion rather than
skipped. Continuing would quarantine the whole record — every other meeting's title
— rather than losing this one's.

**Validation:** **Pinned** —
`meeting_deletion::tests::deleting_a_meeting_takes_its_organization_row_and_leaves_the_rest_intact`
and `a_deletion_interrupted_after_the_row_is_removed_completes_on_reconcile`.

**Evidence:** `vertical-slice.md` stated this in advance — "leaving title or folder
text behind is not successful whole-meeting deletion" — and until the writer existed
there was no row to leave behind, so the clause had nothing to bind. It became live
and load-bearing on the same day the writer did.

#### US-14.3: Naming a meeting from the shell
**Feature E1 · J1 · §F · P0 · M · Landed 2026-08-08**

As the Operator, I want to type a name for a meeting in the app, so that the title I
chose is the one I see.

**Acceptance criteria:**
- Given a meeting row, When the operator names it, Then the row shows that name and no longer marks it as an opening line.
- Given an empty answer, When it is submitted, Then the operator's title is cleared and the derived one returns.
- Given the record could not be read, When rows are shown, Then renaming is withheld rather than attempted against an unknown revision.
- Given the record moved since the snapshot, When a rename is submitted, Then it is refused, the operator is told, and the rows reload.

**Validation:** **Pinned** for the boundary and the wiring —
`library_organization::tests` on the response shape, and the shell-contract greps on
the revision guard, the command name, and the empty-answer clause. **Unproven** as a
product capability: nobody has renamed a meeting in the running app.

**Evidence:** this closes the branch `label_for` opened on 2026-08-07. Until now
`labelSource === "operator"` was a case the shell handled and could never receive.

#### US-14.4: A folder surface
**Feature E1 · J1 · §F · P1 · M · Landed 2026-08-08**

As the Operator, I want to make folders and file meetings into them, so that a
hundred meetings are navigable.

**Acceptance criteria:**
- Given folders exist, When the library is shown, Then meetings can be narrowed to one folder or to those in none.
- Given a meeting row, When the operator picks a folder for it, Then it moves without the meeting being opened.
- Given a folder the filter names is deleted elsewhere, When the list is rebuilt, Then the filter drops it rather than showing an empty list with no explanation.

**Validation:** **Pinned** for the boundary and the wiring —
`library_reader::tests::unfiled_wins_over_a_folder_id_because_the_two_contradict`,
`a_filtered_snapshot_states_how_many_it_is_hiding`, and shell-contract greps on the
create and assign invocations. **Unproven** as a product capability: nobody has
filed a meeting in the running app.

**Still without a surface:** renaming and deleting a folder. Both are registered
commands, granted in both capability files, and reachable only from a future
surface. Deleting one in particular wants a confirmation this list does not have.

#### US-15.1: Narrowing the library
**Feature D3 · J1 · §F · P0 · M · Landed 2026-08-08**

As the Operator, I want to narrow my meetings to a folder, a stretch of time, or a
name, so that finding one is not scrolling.

**Acceptance criteria:**
- Given a filter, When the list is shown, Then it states how many meetings it is showing and how many are retained.
- Given a filter that matches nothing, When the list is shown, Then it says so in words that cannot be read as an empty library.
- Given a capture-date range, When it is applied, Then both ends are inclusive.
- Given two folders with the same name, When one is filtered to, Then only its own meetings appear.
- Given a filter, When a search runs, Then it answers only from the meetings the filter admits, and what counts as a match inside one is unchanged.

**Refusals:** the name filter is not a transcript search. Search already covers
transcript text and returns spans; this narrows a list of meetings, and quietly
searching everything would return meetings whose names do not contain what was
typed.

**Validation:** **Pinned** — `library_read::tests` on folder identity, inclusive
range, and the normalization agreement; `library_reader::tests` on the counts and
the argument mapping.

**One rule, one owner.** The name filter runs through `normalized_matches`, the
same transform search uses. `search-normalization/1` pins Unicode 17.0.0, three
crate checksums and a Rust commit for `char::to_lowercase`; a filter with its own
lowercase-and-contains would disagree with search on composed `é` and expanding
`İ`, and `the_title_filter_normalizes_the_same_way_search_does` is the check that
they do not.

**Applied in memory, deliberately.** The corpus index carries the same folder and
capture-time columns and could answer these in SQL. It would buy nothing today: the
app builds the full projection before anything else happens, so the rows are already
in hand. The index earns its read path when US-13.6 stops the scan being the entry
point — and until then it is written on every library open and read by nothing,
which is stated here rather than left for someone to discover.

#### US-15.3: Semantic retrieval, measured before it is built
**Feature D2 · J1 · §F · P0 · M · Measured 2026-08-08, store not built**

As the Operator, I want to find a meeting by describing it, so that forgetting the
exact words somebody used does not lose it.

**Acceptance criteria:**
- Given a question whose words appear in no meeting, When retrieval runs, Then the meeting a person meant is ranked first.
- Given a question exact search already answers, When retrieval runs, Then it is not worse.
- Given the same corpus and question, When retrieval runs again from a fresh process, Then the ranking and the margins are identical.

**Validation:** **Receipted** — `notes/SEMANTIC_RETRIEVAL.md` registered a
two-sided prediction of 8–10 of 10 before any download; three cold runs returned
10 of 10 overall and 5 of 5 on the questions exact search cannot answer, with
byte-identical receipts. `ReceiptTests` pins the numbers as literals and
`the_semantic_probe_fixtures_describe_what_exact_search_actually_does` asserts the
baseline against `library_read::search` itself.

**The margins are the finding, not the score.** Three of the five hard questions
were decided by less than 0.04 cosine — one by 0.013 — on a corpus of ten
meetings. That justifies building the store and says nothing about a thousand
meetings. The next measurement here is distractor density.

**Not built:** the vector column, the MLX forward pass, and any surface. The
probe used the Apache-2.0 reference implementation because `mlx-embeddings` is
GPL-3.0 and this repository is MIT — so the shipping path is a forward pass
written here, checkable against the committed receipts.

**Evidence:** the fixtures were hardened mid-registration. A word-overlap ranker
with no model in it initially scored 8 of 10 and 3 of 5 on the hard half, because
two transcripts contained words the fixture claimed were absent. Both were
removed and a test now fails if any non-semantic strategy answers a hard question.

#### US-15.2: Filtering by person
**Feature D3 · J1 · §F · P1 · M · Blocked on A3**

As the Operator, I want to narrow my meetings to the people in them.

**Validation:** **Unproven** — not built, and not buildable here. Attribution is
`channel` (Me/Them) or `none`, and the contract states that named participants,
inferred counterparties, tags and generated subjects are absent. This needs E18 /
Wave 3 item 11, named speakers. The meetings surface says so where the filters are,
rather than leaving a person to conclude the control is missing.


---

## 7. Open questions

Equivalent to a BRD's open-questions register. Each blocks at least one story.

| # | Question | Blocks | Owner |
|---|---|---|---|
| Q1 | What exactly does the app promise about retention, in the consent moment and in Settings? Two drafted options have no encoding in `validate_start_request`. | US-3.5, US-1.2 wording | Operator |
| Q2 | What may leave the machine, in what form, with what redaction? | All of E8 | Operator |
| Q3 | Is the encoder admitted? | US-12.4, US-2.8, and the sitting recorder | Operator |
| Q4 | Are the generated notes semantically supported and useful? | E4 admission, and E5–E7 behind it | Operator |
| Q5 | Does E9 come into v1? | All of E9 | Operator |
| Q6 | How should the runtime be pinned so registered experiments are reproducible? | US-4.8 and every intervention after it | Builder — buildable now |
| Q7 | Should claim *type* be checked against the cue? The model emits only ACTION and DECISION across ten rows and never PROPOSAL, and two fixtures pass every gate while mistyping the claim. The cue is a heuristic, not ground truth, so a naive gate would be wrong. | Nothing yet; recorded so it is not lost | Builder |

## 8. Success measures, and one rule about them

Most of this product's outcomes are **not yet measured**, and that is stated rather
than filled with proxies.

**No count occupies the result position.** A number that names what the work achieved
must be an outcome the Operator owns — not a tally of what the system produced. Claims
generated, fixtures passing, meetings captured and tests green are operating
diagnostics. Labelled as such, they belong below the outcome; promoted above it, they
become the target, and a system rewarded for producing claims will produce claims.

| Outcome | Owned by | State |
|---|---|---|
| The Operator recovers what was decided, weeks later, without having taken notes | E7, E4 | **Not yet measured** |
| A colleague cut from the record can be restored before it matters | E6, E2 | **Not yet measured**; the remedy exists |
| The Operator trusts a note enough to act on it without re-reading the transcript | E4 | **Not yet measured** — this is Q4 |
| Nothing left the machine | E1, E12 | Held by construction, and pinned |
| The transcript that was kept is the transcript that was produced | E1, E3 | Pinned by digest, and receipted once |

Diagnostics, recorded as diagnostics: 553 mechanical checks across six suites;
12 of 12 fixtures reach the matrix, 9 passing every registered gate as of the last
runnable measurement on 2026-08-06.

## 9. Provenance

Epics derived from `product-definition.md § North-star features and functions`
(statuses verified there 2026-08-06) and `vertical-slice.md § Build queue`. Surfaces
§A–§J from `screens-and-states.md`; journeys J0–J6 from `journeys.md`. Competitive
claims carry the fetch dates recorded in `teardown.md`; nothing was re-fetched here.

Every check named in a **Validation** line was read out of the source on 2026-08-07,
not copied from a prior document. Contract names were enumerated from
`crates/session-core/src/` and `apps/desktop/src-tauri/src/`: 41 product-facing
schemas of 95 in the repository. One cited schema,
`bounded-extraction-output/1`, lives in the research lane (`notes/summarize.py`) and
is labelled as such where it appears, because a research-lane contract and a
session-core one carry different weight.

Format follows `~/Workspace/dev/wip/bc-subscriptions/BRD.md` — story header,
Given/When/Then, and the effort scale. Its persona and value-stream columns did not
transfer: that product has four personas across a platform, this one has essentially
one, and the journey already does what a value stream would. **Validation** and
**Refusals** are local additions with no counterpart there.
