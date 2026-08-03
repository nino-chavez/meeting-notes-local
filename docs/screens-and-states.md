# Screens and states — local-meeting-notes

The L5 inventory. Authored **before** any template, component, or token, per the
Blueprint finding that L4 templates cannot be derived without an L5 surface
inventory — and that patching at L1 when the missing primitive is at L4 produces
bugs that *move* from surface to surface rather than closing.

This is a native-shell app, so "route + auth state" does not apply. The
equivalent axes are **surface** and **lifecycle state**.

**This file has no clock, and that is its limit.** A state table says what a surface
can hold; it cannot say what the operator does over a week, and gaps that only appear
across time are invisible here by construction. `journeys.md` is the counterpart, and
walking it against this file is what produced surfaces I, J and K — each of which read
as complete until a journey crossed it. Read the two together or neither is finished.

---

## The product model, and the two IA rules that do not transfer

Two sibling projects in this workspace have settled IA at a scale this one has not, so
their patterns were checked against this product rather than adopted. Both of the
load-bearing ones turn out **not** to apply, and the reason is the same in each case —
which is worth more than a copied structure would have been.

**What this product is:** an ambient recorder with a reading path attached. The
menubar item (A) is the primary UI and most sessions never open a window; everything
else exists so a note can be trusted weeks later. It is not a workspace the operator
works inside, and it is not a site they navigate.

**Rejected: navigation that mirrors the work in execution order.** film-room's
`decisions/0004-console-ia-pipeline-page-bar.md` makes its nav the pipeline —
Ingest → Review → Publish → Handoff — on the reasoning that "a nav that mirrors that
order removes the translation step between 'where am I in the process' and 'where do I
click.'" That reasoning is sound and it does not reach here, because **the operator
executes no stages.** They consent once and leave; the pipeline runs unattended. A
stage-ordered nav would present a process the operator is not performing. What does
transfer is the same ADR's second finding, and it transfers intact — see below.

**Rejected: one top-level destination per job.** `website-nc`'s
`docs/IA-NAVIGATION.md` gives each of five visitor jobs its own route and states that
the homepage "does not absorb the collections." Here the jobs deliberately share
surfaces: F is the entry for retrieval (J1) *and* commitment (J2), and E is the detail
target for J1, J2 and J3 — with J4's stated minimum putting correction there too, since
it asks for gated turns to be restorable "where the note is read." Splitting those would
produce four reading surfaces over one corpus. The rule fits a site with deep parallel
collections; this is one
chronological stream, and `journeys.md` J2 already decided its case explicitly — the
commitment view is "a `filtered` view in the sense F already carries, not a new
template and not a new surface."

**Adopted intact: status is not a destination.** film-room demoted its Jobs page to an
ambient rail because "nobody's goal is 'go to Jobs'" and ambient-everywhere beats a
page. This product's equivalent is already right by accident and should be right on
purpose: capture state lives in A and C and has no page, and the gate's report is
required to reach E's `ready` state rather than living in a HUD nobody had open.
Applied as a test, it also confirms K is correctly a surface rather than a rail —
retention is a *policy the operator decides*, not a status they glance at.

**Adopted intact: art direction begins after the structure is accepted.**
`website-nc`'s IA prototype acceptance says "the prototype may use neutral styling. Art
direction is a separate decision and begins only after this structure is accepted."
`docs/prototype/build.py` harvests `DESIGN.md`'s tokens rather than free-picking a
palette, which is the safe version of the same rule — but it settles the note's
structure only. It is not art-direction acceptance, and `DIRECTION.md`'s ledger stays
empty until a product surface ships a device.

### Two tests the decisions files do not contain

The records above are the accepted outcomes. What produced them lives in the sessions,
and two operator corrections there are reusable as tests rather than as decisions. Both
are quoted as written.

**"what am i supposed to know to do vs infer cognitively?"** — asked while reviewing
film-room's ingest screen, alongside *"i dont understand the utility of the cards
beneath the form inputs like 'proxies' 'features' 'scoring' etc. what is the job to be
done on the ingest screen?"* That is the origin of the rule
`decisions/0035` later states as cards being "not the default page-composition
primitive": the cards had no job, and a card with no job costs a cold reader attention
without returning anything. **The test is cold-start: install, launch, and separate what
the surface tells you from what you are expected to work out.** It bites hardest here on
H, which is the only surface a reader meets with no prior model, and on E, where the
four claim states are new vocabulary that the surface itself has to teach.

**A surface used repeatedly needs a strip and keys, not buttons.** Reviewing film-room's
first pass: *"im mostly just hitting play then eiteh rkeep or reject but it feels
cumbersome. a comparative example in lightroom gives me a small strip then hotkeys to
pick or reject."* This product has the same shape and had not noticed: a note can carry
**83 claims**, and checking them means moving between a claim and its words over and
over. The prototype gives each claim a button, which is the cumbersome pattern at 83
repetitions. J4's correction journey compounds it — every gated turn is an
adjudication. **Neither E nor J4 has a keyboard path, and that is now a recorded gap
rather than an oversight.**

**One warning, from the redesign that got thrown away.** Asked of a
methodology-generated prototype: *"why is our current site so much better in terms of ui
and styling? just like our letsppepper and flickdaymedia designs. did we do something
different when we designed those?"* A generated surface can be visibly worse than a
directed one while every process step was followed. Harvesting real tokens instead of
picking a palette is a guard against the cluster that produces, not a guarantee of
having escaped it.

---

## What each surface must not become

Borrowed from `website-nc`'s `docs/IA-NAVIGATION.md`, whose page-responsibility table
carries a **"Must not become"** column. It is the highest-value device in that file:
a positive spec says what to build and an anti-pattern says which plausible-looking
drift is already ruled out, and the second is what a later reader needs.

**Every cell cites a decision recorded elsewhere in this file or in `journeys.md`.** A
table of eleven invented anti-patterns would read as a mood, which is the failure the
direction contract rejects. Where nothing has been decided, the cell says so — an empty
cell is information.

**Cited by verbatim phrase, not by line number or section name.** `website-nc`'s ledger
carries a line number per device because two independent passes had inherited the same
wrong count from a shared prose source — "so the next reader counts from the file
instead of from the record." The anchor has to be checkable; a line number is not the
only way, and here it is the wrong one, because this table lives in the same file it
cites and every edit above a row would move it. A phrase greps. It also has to be
*distinctive*: writing this table by grepping its own quotes returned the table's rows
rather than the sections, which is that same failure arriving in the space of one file.

| Surface | Must not become | Grep for |
|---|---|---|
| A. Menubar item | An indicator whose `recording` and `degraded` readings look alike; or one that moves when no audio is arriving | `distinguishable at a` (§ A) · `DIRECTION.md` `No ambient motion anywhere` |
| B. Detection notification | A notice that starts capturing while it is still being read — the countdown *is* the consent window and cannot be zero — or one that re-asks after a decline in the same session | `Cancellable for its full duration` · `No re-prompt for the same session` |
| C. Recording HUD | A dialog. `tap-lost`, `device-changed` and `drift` are expected across a 60-minute capture and recording continues degraded | `Modeling them as modals is the` |
| D. Live note surface | A transcript viewer — the operator's own typing is the point — or a surface that hard-fails when ASR is unavailable | `The operator types their own notes` · `rather than hard-failing` |
| E. Note detail | A note whose claims are reordered by trust, or one that treats a missing summary as an error instead of showing the transcript | `Rendered in read order, never sorted by state` · `a first-class state, not an error` |
| F. Notes library | A task manager. A checkbox here means the tool owns follow-through and the operator has two task systems | `journeys.md` `the moment this surface offers a checkbox` |
| G. Settings | A permissions list that presents the calendar grant as ordinary, when it is the one grant the product must apologise for | `Presenting it as an ordinary permission row` |
| H. First run | A welcome graphic, or a flow that picks a retention period on the operator's behalf | `DIRECTION.md` `never a welcome card` · `no default this document may pick` |
| I. Voice enrolment | A form that asks for a threshold, or one where an overridden enrolment looks complete | `It must not ask for a number` · `must not look like` |
| J. Shell startup failure | Anything that fails before a window the operator can read | `never fail before rendering an operator-readable window` |
| K. Retention and disk | A settings toggle buried in G. It is a standing statement about material belonging to people who never agreed to anything | `Not a settings toggle buried in G` · `outranks every interface question` |

**No cell here is empty, and that is a finding rather than a relief.** Eleven surfaces
each already carried a recorded prohibition, which means the anti-patterns were being
decided all along and filed as prose next to the decision that produced them. Nothing
gathered them where a person building the surface would meet them. That is the same
failure this file's own header describes — a primitive missing at one level being
patched at another.

---

## A. Menubar item

Always present. The primary UI — most sessions never open a window.

| State | Trigger | Treatment |
|---|---|---|
| `idle` | Default | Hollow glyph. No motion. |
| `detected` | An app started using the microphone | Glyph gains outline emphasis. Still not recording. |
| `armed` | Consent given, countdown running | Countdown is legible in the glyph itself, not only in the notification. |
| `recording` | Capture running, both legs healthy | Filled glyph in the live accent. This is the only place the accent appears. |
| `degraded` | Recording, but one leg failed | Filled glyph, accent, plus a persistent mark. Never silently "recording." |
| `transcribing` | Capture ended, ASR still running | Distinct from both idle and recording. |
| `error` | Unrecoverable | Neutral error mark. Never the live accent. |

**Load-bearing rule:** `recording` and `degraded` must be distinguishable at a
glance without a click. A tool that may be listening and looks identical whether
it is or isn't is the failure this product cannot ship with.

---

## B. Detection notification — the consent moment

The highest-stakes surface in the product. Recording law and participant
expectations vary by jurisdiction and context, and this is the only surface that
stands between opening the app and recording before the operator has made the
required consent choice. The app can require that choice; it cannot provide legal
advice or infer that the room agreed.

| State | Trigger | Notes |
|---|---|---|
| `prompt` | Mic-use detected | Offers record / not this time / never for this app. |
| `countdown` | Auto-start enabled | Cancellable for its full duration. The countdown is the consent window; it cannot be zero. |
| `declined` | Dismissed or explicitly declined | Silent. No re-prompt for the same session. |
| `suppressed` | App on the never-list | No notification at all. |
| `manual` | Started from the menubar with no detection | Skips detection but not the consent affordance. |

Consent is scoped to one capture attempt. Every new Start begins unchecked; declining
the prompt, cancelling the armed countdown, completing the capture, resetting the
profile, or changing retention clears the attestation and disables Continue. Manual
Start opens this surface in the neutral/idle menubar state. It never borrows
`detected`, which belongs to the future microphone-use path.

**Design question this surface owns:** whether the far end is told. Circleback,
Granola and Fireflies each answered differently — Fireflies' bot announces
itself by existing; the bot-free products leave it to the operator. The default
here is a decision, not an oversight, and it belongs in this inventory rather
than in an implementation detail.

---

## C. Recording HUD

Visible while capturing. Small, positioned, dismissible to the menubar.

| State | Trigger |
|---|---|
| `running` | Both legs healthy, levels moving on both |
| `mic-only` | System-audio tap failed or was never granted |
| `system-only` | Microphone muted or unavailable |
| `tap-lost` | Tap died mid-meeting — device change, permission revoked, aggregate device torn down |
| `device-changed` | Default input or output switched mid-meeting |
| `drift` | The two streams' timestamps have diverged past threshold |
| `bleed-detected` | The microphone is hearing the speakers; the Me/Them split is not trustworthy |
| `gating-a-voice` | The voiceprint gate is repeatedly dropping one recurring voice that is not the operator |
| `stopping` | Capture ending, buffers flushing |

**`bleed-detected` is measured, not assumed** — added after the capture spike
(`spike/RESULTS.md`) found envelope correlation of **+0.93** between the two legs
when the far end plays through speakers, which makes every utterance appear twice
in the transcript, once as Me and once as Them.

That output is worse than unlabelled: it reads as two people agreeing verbatim,
and nothing downstream can tell it never happened. So this state changes
behaviour rather than showing a warning — **when bleed is high the product stops
claiming a split** and labels the session as one channel. Fabricating a dialogue
is the one failure mode a meeting record cannot have.

The current capture computes the verdict over the completed recording, restricted
to spans where system audio was active. A future live implementation may re-check
after an output-device change, but it cannot erase contamination that already
landed in the microphone leg.

**`bleed-detected` must preserve the artifact without pretending it is complete.**
The original notes test used synthetically doubled transcript lines. It showed
that a summarizer can discard duplicate text; it did not test operator speech
that never survived transcription. In the later real speaker-mode take, the raw
microphone transcript contained none of the cued operator passage and mostly
contained the far end. Offline AEC3 removed nearly all detected far-end words,
but operator-word recall remained partial and the voice gate admitted nothing.
No human notes-quality evaluation exists for that output
([`spike/aec3/README.md`](../spike/aec3/README.md)).

So this state degrades **attribution and known coverage**. The product must keep
the transcript and any best-effort note, remove the Me/Them claim, and carry a
persistent warning into the note that speaker bleed made coverage incomplete or
unknown. Do not show the result as a complete note, and do not count speaker mode
inside the supported beta envelope. If headphones or an output-device change
remove bleed, the product may re-check subsequent audio; the earlier contaminated
span must remain marked.

This is required product behavior, not current CLI evidence. The CLI records a
whole-capture bleed measurement and prints segment omissions, but it does not
persist affected-span metadata or the note warning. That provenance has to exist
before a renderer can satisfy this state.

**`gating-a-voice` exists because the gate can be right and still be wrong.**
Added when the voiceprint gate was wired into the capture
(`spike/dual_capture.py`, `drop_offprint`). The gate removes microphone speech
that is not the operator, which is what fixes the 14.2% of merged turns that were
the room — but a colleague sitting beside you is indistinguishable from
interference until somebody decides which, and only the operator can. So the gate
reports when most of what it dropped keeps coming back as *one* recurring voice,
along with roughly how many seconds of that person's speech it removed.

Microsoft Teams ships the same alert for the same reason, and it is the reason the
gate returns rejections rather than a filtered list. **A gate that silently
deletes a real participant is worse than the contamination it replaces**, because
the transcript then omits speech with no record that it did — and a note is read
by someone who was not in the room and cannot tell.

This is a state, not a modal. It changes nothing about the capture; it tells the
operator something only they can adjudicate, and it must survive to the
post-meeting note rather than living only in a HUD nobody had open. Two segments
of the design follow from that: the count belongs in `E. Note detail`'s `ready`
state as well, and the accent rule forbids colouring it — the accent means live
capture and nothing else, so this reads as neutral foreground plus text.

**`tap-lost`, `device-changed` and `drift` are states on this surface, not error
dialogs.** They are expected conditions across a 60-minute capture, and the
recording continues degraded rather than failing. Modeling them as modals is the
error that makes the tool untrustworthy in the exact moment it matters.

Two independently-clocked streams are the source of `drift`; see the teardown's
engineering notes. The HUD is where that becomes visible to the operator.

---

## D. Live note surface

Open during the meeting. The operator types their own notes while transcription
runs — the Granola insight, and the reason this isn't just a transcript viewer.

| State | Trigger |
|---|---|
| `empty` | Meeting started, nothing typed, no transcript yet |
| `typing` | Operator notes only |
| `streaming` | Transcript arriving alongside notes |
| `lagging` | ASR behind real time by more than a chunk |
| `queued` | ASR unavailable; audio buffered, transcript deferred |

`queued` inherits `local-dictation`'s existing principle: the pipeline degrades
rather than hard-failing, and the operator is told which leg is down.

---

## E. Note detail — post-meeting

| State | Trigger |
|---|---|
| `processing` | Transcript complete, summary running |
| `ready` | Summary written |
| `summary-failed` | Model unreachable or output rejected by its acceptance checks — raw transcript is shown, marked as unsummarized |
| `edited` | Operator has modified the note |
| `exported` | Written out to Markdown |

`summary-failed` is a first-class state, not an error. The transcript is the
durable artifact; the summary is an enhancement over it. A generated artifact with
`passed: false` is retained only when a research run explicitly asks for a diagnostic.
It never enters the library or note-detail surface as though it were a thin but usable
note.

**The states above are the surface's; a claim inside it has its own, and this table
was missing them.** Every state here is about whether a note *exists*. None of them
says anything about whether what it asserts can be believed, which is J1 beat 3 and
the reason `docs/journeys.md` decided the note must cite the transcript. Four
per-claim states remain the product direction established by the research
renderer:

| Claim state | Meaning |
|---|---|
| `located` | The quoted words are in the transcript, at a turn the code found. **Not** a statement that they support the claim |
| `composed` | They are not in the transcript — and it was the model's only input, so the quote was composed |
| `untestable` | Under four words, so a match would prove nothing either way |
| `unquoted` | The claim offered no evidence at all |

The current accepted product `note/2` validator authoritatively re-derives only
`located` claims. The first `note-claim-projection/1` therefore exposes only
that state. `composed`, `untestable`, and `unquoted` are not silently inferred
from stored research rows; admitting them requires the planned Wave D note-schema,
validator, interaction, and beta-admission work.

**These were `verified` and `unsupported`, and both claimed more than the check does.**
`verified` was read as "this claim checks out", including by the surface, which drew it
with a green tick — when all that was established is that the words appear at a turn.
Measured: **6 of 31 located quotes actually support their claim**, action items 0 of 8,
and one cites speech arguing the opposite of itself. `unsupported` overstated in the
other direction, laying claim to the support question while meaning only that the words
are absent from the transcript.

**Every note mixes them, which is why the state belongs to the claim and cannot be a
hover or a detail view.** Measured on three real runs — 7 located of 11 claims on a
582-turn meeting, 33 of 83 on a 1365-turn one, 4 of 15 on a third. Verified is not
rare; it runs between a quarter and two thirds. The finding is that **no note is
uniformly one thing.** All three carry at least two states and two carry three, so a
note-level statement about trust is never true, and on the longest meeting 41 claims
with composed evidence sit next to 33 with real evidence — indistinguishable unless
the state is attached to the claim that carries it.

The sharpest evidence for that is a defect rather than a measurement. One of those
runs reported **PASS while carrying four composed quotes**: the checker had misfiled
them as "no quote offered", which does not fail a run. An aggregate verdict is exactly
the shape that hides this, which is the argument for showing the state per claim
rather than summarising it.

**The treatment of those four states is decided here, and it is constrained rather than
chosen.** `docs/prototype/build.py` renders them; the reasoning belongs beside the
states themselves, not in the generator.

- `composed` takes `semantic-error`. That is `DESIGN.md`'s own escalation rule — "if a
  warning genuinely needs color, it is an error and takes `semantic-error`" — and a
  quote the model invented is the most serious thing this file reports.
- **`located` takes `semantic-info`, and `semantic-success` is deliberately unused.**
  Success is a verdict and locating a quote is not one. It first took success with a
  green tick, which told a reader the claim had passed something; four fifths of the
  time nothing had. Nothing on this surface has earned success yet, and leaving the
  token unspent is more honest than spending it on the nearest candidate.
- `untestable` and `unquoted` both take `semantic-warning`, which resolves to
  `neutral-300` with no hue. Not a compromise: an amber here would compete with the
  live-capture accent, which is the one reading the product exists to make trustworthy.
- **The accent appears nowhere on this surface.** Nothing here is live capture, so the
  rule that reserves it forbids its use even where a designer would reach for emphasis.
- Each state carries a mark and a word as well as a colour, so the two states sharing
  the neutral hue are distinguishable without it.

**The aggregate proportion is not held to the same rule, and the distinction is worth
stating.** F's row and E's header show a proportional bar whose segments are colour
only. `DIRECTION.md`'s prohibition on state carried by colour alone is grounded in
`recording` versus `degraded` at menubar size — per-item state a person must read at a
glance. A bar is an aggregate of items that each already carry their word, so it sits
outside that rule. Its label still has to name the numbers that matter, which is a
legibility requirement rather than a direction one.

**Rendered in read order, never sorted by state.** Sorting by trust would hide how
much of a note rests on composed evidence, which is the lying-by-omission failure
`journeys.md`
argues this product lives or dies on. `note/1` carries each claim's character offset
in the note so read order survives the grouping the checker needs.

---

## F. Notes library

The IA surface. Decides whether the corpus is useful in six months or a junk
drawer.

| State | Trigger |
|---|---|
| `first-run` | No valid meeting rows yet |
| `populated` | Default |
| `searching` | Query active |
| `no-results` | Query returns nothing |
| `filtered` | Narrowed by folder, UTC date range, or Recorded actions |

**Open IA decisions this surface owns.** Two of the three are now answered by the
market check in `journeys.md`, which is a weaker kind of evidence than a measurement
and a stronger kind than an opinion — it establishes what the operator has already met
elsewhere, not what is best.

- **The organising primitive: folders, and chronology as the default ordering within
  them.** Granola and Otter both ship "folders"; Otter adds "channels" for sharing.
  Neither organises by counterparty, which was the candidate this project found most
  interesting and which nothing in the market supports. Settled on the primitive.
- **Search covers the transcript and its metadata, not the notes alone.** Otter's free
  tier is "Search by keywords" and its paid tier "Advanced search by speakers, date
  range, and more". Searching notes only would find the compression and miss the words,
  which is the wrong half given how partial the transcripts here are.
- **Whether notes link to each other is still open**, and nothing observed in the
  market bears on it.

**A commitment-organised view is a state on this surface**, not a surface of its own —
see `journeys.md` J2, and the reason it stops at export rather than offering a checkbox.

---

## G. Settings

| State | Trigger |
|---|---|
| `permissions-needed` | Microphone or audio-capture permission missing |
| `permissions-partial` | One granted, one not — the common real state |
| `ready` | All grants present |
| `device-selection` | Choosing input / output to capture |
| `model-selection` | ASR and summarization model choice |

`permissions-partial` is the state that actually occurs and the one most likely
to be skipped in design. macOS attributes prompts to the launching binary, and
under launchd there is no hosting terminal — `local-dictation`'s README already
documents this trap.

**Calendar is a third grant, and it is the only one the product must apologise for.**
Microphone and audio-capture grants match what the app does with them. Calendar does
not: macOS offers no read-only option, so reading the operator's schedule means holding
a grant that also permits editing and deleting it (`DESIGN.md § Context inputs`). This
surface has to say that in the operator's words — the app reads and never writes, macOS
has no narrower grant to ask for, and declining costs the pre-meeting brief and nothing
else. Presenting it as an ordinary permission row alongside the other two would be the
dishonest option, because the other two are not over-privileged and this one is.

It is also the only grant that is genuinely optional. Capture without a microphone is
not a degraded product, it is no product; capture without a calendar loses J0 and
nothing else.

**Research contribution must not become a Settings opt-in.** `journeys.md` J6 compares
the plausible structures and rejects a global “help improve transcription” control.
Settings may later link to a Research & evaluation admin record, but sharing authority
belongs to one reviewed meeting packet, one stated purpose, and one separate consent
receipt. A durable account preference cannot supply any of those.

---

## H. First run

| State |
|---|
| `welcome` |
| `request-microphone` |
| `request-audio-capture` |
| `choose-retention` — the auto-deletion period, which has no default (see K) |
| `enrol-voice` — supported meeting capture remains blocked until I reaches `enrolled` |
| `ready` — permissions, retention, and a measured voice profile all exist |
| `offer-calendar` — optional, and asked only after `ready` for that reason |
| `denied-recovery` — deep-link to the right System Settings pane |

**Two of these are asks rather than requests, and the ordering says which.** Microphone
and audio-capture are prerequisites — decline either and there is no product. Calendar is
optional and over-privileged by the platform's own design, so it comes after the app is
already usable, where declining it is visibly cheap. Retention is a choice the operator
has to make because this document refuses to pick a default for how long other people's
voices are kept.

The permissions do not make the product ready by themselves. First run orders the
requirements as permissions → meeting-audio retention → voice enrolment. The dedicated
recordings made by enrolment are not meetings and do not inherit the meeting-retention
choice: each raw artifact is deleted as soon as the needed owner-only derived material
is safely stored. The manual meeting-capture control is enabled only by the conjunction
of a valid profile, both current permissions, and an explicitly selected retention
period. Reviewing a panel or satisfying only one requirement cannot make it appear
ready.

---

## I. Voice enrolment

Added 2026-07-29, when the voiceprint gate landed in the capture
(`spike/speaker_gate.py`, `spike/dual_capture.py`) and no surface owned its contract.
The inventory and review prototype now do. The Preview enforces the separately
confirmed reset branch. The shared lifecycle now implements crash-recoverable
`writing`, `ready`, and `active` publication. Its strict-loader bridge binds the
canonical worker verdict to the exact descriptor-reopened candidate digest and keeps
candidate cleanup separately retryable. The shortfall calculation this surface is
for now exists as `session-core::enrollment_guidance`: a deterministic, content-free
evaluation that reports `blocked`, `resume-after-gap`, `second-sitting-review`,
`needs-other-voice`, `choosing-operating-point`, or `refused` over accumulated
evidence, and names each unmet requirement in the enforced term rather than as a
share. Its constants are re-derived from `spike/speaker_gate.py` and pinned by test,
because § I's prose is a restatement of that contract and not the contract. Preview's
voice panel now renders that evaluation and separates the two lifecycle facts it
previously collapsed: an active enrolled profile no longer inherits the
preserved-legacy copy promising that Preview will not activate what it found.

**Three things this does not do, and none of them are close.** No dedicated sitting
is recorded, so the evidence set is empty and the honest evaluation is `blocked` with
the first enforced step. `choosing-operating-point` and `ready-to-build` need measured
choices from the operator's own calibration and an explicit selection with no default,
neither of which an agent may supply. No enrolment command is exposed to Preview, and
the Preview capability still grants no enrolment or profile-activation permission.
Clearing every requirement named here is not admission: the canonical loader refuses
again, through `worker/adapters.py`'s `profile_inspect`, before any candidate reaches
the lifecycle.

**A sitting is saved only when its derived voice material exists, and the deletion
order is the reason.** `first-sitting-saved` promises the dedicated raw recording is
already gone *because* the owner-only derived material is safely stored. That derived
material is the ECAPA embeddings, their encoder checkpoint identity, and the
provenance a later profile build re-verifies — `save_profile` takes a centroid and
held-out/negative scores, all embedding-derived, so raw audio deleted before
embeddings exist leaves nothing a profile can be built from. Whisper segment
durations survive such a deletion and can gate the structural floors above; they
cannot enrol. Until derivation completes, a recording is **raw-retained** under an
explicit temporary state and counts toward nothing; the evaluator reports it as
app-side pending work, never as the operator's next errand. A capture deleted before
derivation is a rehearsal, not evidence. Derived material spanning two encoder
checkpoints is refused outright — cosines between embedding spaces are not
comparable, the same fact behind the `stale` state below.

The store enforcing this order exists: `session-core::sitting_evidence` keeps raw
bytes only in a per-sitting work directory, holds durable write-once evidence rows
(identity, capture digest, content-free segment timings, embeddings bound to
encoder and `.onnx` artifact identity), and deletes raw audio only under a
digest-bound `deleting → staged → removed` receipt copied in shape from
`audio-deletion/1`. A sitting reports saved only with a terminal receipt and an
absent work directory; a cleanup interrupted anywhere resumes at startup; a
recording interrupted before its capture row becomes a durable rehearsal label,
never silent loss. Preview reads the store under the app-data writer lock and
evaluates it against the runtime manifest's encoder digest — with recorded
evidence and no verified encoder identity it refuses (`needs-attention`) rather
than guessing. The store's derivation seam accepts only synthetic fixtures until
the preferred ONNX encoder passes both admission checks.

**The packaged runtime cannot derive that material today, and the chosen encoder
is a preferred candidate, not an admitted one.** `worker/build_runtime.sh`
records `encoder-unavailable.identity` — a text placeholder — as its encoder, and its
digest is what `profile.inspect` hands `load_profile` as the expected fingerprint, so
every real ECAPA profile is refused in the packaged app. The same boundary blocks
meeting-time gating: `dual_capture.load_voiceprint` builds the encoder *before the
microphone opens*. The packaging direction was decided on 2026-08-03 from the
measured spike (`spike/encoder-packaging/RESULTS.md`): voice isolation stays in the
first beta, served by ONNX Runtime CPU execution with the converted ECAPA model
pinned by its own `.onnx` digest and a torch-free feature front end;
PyTorch/SpeechBrain remains only the reference implementation and packaging
fallback. Two mandatory checks stand between preferred and admitted — a registered
Fbank-parity comparison whose score/classification agreement decides, and the
release-lane packaging proof against the actual signed bundle — and until both
pass, every surface says *preferred ONNX candidate*, and no real sitting may be
claimed saved. CLI-only enrolment is not a middle path: a profile enrolled outside
the app still needs the in-app encoder to score anything.

Recorded here rather than improvised at implementation time, because this file
opens with the reason: patching at L1 when the missing primitive is at L4 produces
bugs that *move* from surface to surface instead of closing.

| State | Trigger | Notes |
|---|---|---|
| `blocked` | No valid profile loaded | Supported meeting capture is disabled. Existing meetings remain readable. |
| `first-sitting-saved` | Owner-only derived material safely stored | The dedicated raw, transcript, segment list, and partial work are already deleted. |
| `resume-after-gap` | One sitting held | Names the enforced ≥1 hour gap and says different days are ideal; it does not invent elapsed time. |
| `second-sitting-review` | Second sitting processed | Shows observed counts, gap, held-out speech, and any refusal before asking for negative material. |
| `needs-other-voice` | Operator material sufficient, no negative sample | Offers public-domain or licensed playback, or a person who knowingly consents to make a calibration recording. |
| `choosing-operating-point` | Measured choices exist | Two or three ordered choices, actual costs, no default; controls remain disabled before measurements load. |
| `ready-to-build` | One measured row explicitly selected | The selected row is visible; no profile exists yet. |
| `building-profile` | Build transition started | Start remains blocked until owner-only persistence succeeds. Failure deletes partial output. |
| `enrolled` | A new profile is safely persisted | Carries provenance, both measured rates, build time, and encoder identity, then enters the valid-profile condition. |
| `returning-valid-profile` | A persisted profile passes every load check | Distinct from `blocked`; it supplies the profile prerequisite but does not bypass current permissions or retention. |
| `discard-confirm` | The operator abandons incomplete enrolment | Deletes dedicated raw, partial derived work, and partial profile state; source meetings and any previous valid profile remain. |
| `incomplete-cleaned` | Extraction/build failure, cancellation, or abandonment | Partial raw is deleted and enrolment remains incomplete. |
| `reset-confirm` | The operator asks to delete the valid profile | Names exactly what goes and what remains. |
| `reset` | Profile removed | Meetings remain and application capture is blocked until enrolment completes again. Only the research CLI may run ungated outside beta. |
| `stale` | The encoder changed under the profile | Cosines between two embedding spaces are not comparable, so the threshold means nothing. `load_profile` already refuses this; the surface has to explain it. |
| `experimental` | Built past the contract | Visually distinct from `enrolled`. Nothing a capture gated by it does is a measured result. |

**The supported beta uses deliberate calibration, despite the category's passive
pattern.** Teams and Zoom build profiles from ordinary in-meeting speech and neither
ships a setup ritual; `docs/teardown.md` records that. This product cannot use an
ordinary first meeting to bootstrap the same path while also claiming that meeting was
gated. The initial profile therefore uses dedicated operator sittings and dedicated
negative material. Passive updating remains the desired later state, after a valid
profile already exists and can keep the input boundary honest.

**The load-bearing rule is that `accumulating` states the shortfall in the terms
the code enforces, not as a progress bar.** `enforce_enrollment` refuses for four
specific reasons, and a percentage cannot express any of them:

- fewer than two sittings,
- sittings less than one hour apart — exactly one hour passes; different days are
  ideal — including two pieces of one recording, which reads as satisfied and is not,
- fewer held-out segments than a candidate target can express
  (`ceil(1 / target)`),
- fewer than 60 scorable seconds or 20 scorable segments from allowed speech that is
  not the operator,
- a repeated negative recording identified by the same canonical audio digest.

A bar at "80%" tells the operator to keep going. "Return at least one hour after the
first sitting — ideally another day — then supply a permitted negative sample" tells
them what to do. The second is the whole job of this surface. A negative sample is not
permission to harvest someone else's speech: it is public-domain or appropriately
licensed playback, or a deliberate recording made by a person who consented to that
use. The minute is the registered speech floor. Twenty segments is a product
judgement, separate from duration, that prevents one long passage from posing as a
distribution and permits a 5% false-admission observation. Neither is a statistical
guarantee.

**`choosing-operating-point` is the one screen in the product that presents a
trade-off rather than a reading**, which makes it the exception to the thesis and the
reason it is its own state. `speaker_gate.operating_point_choices` keeps only targets
the held-out sample can resolve and that carry both the measured operator-speech drop
rate and negative-speech admission rate. Duplicate cost pairs collapse. It requires at
least two distinct choices; with more than three it presents the loosest, deterministic
lower median, and strictest. Both costs are concrete and asymmetric — dropping the
operator removes the answer to the only question this tool exists to answer, while
admitting the room perturbs which real content survives compression.

**It must not ask for a number, and that resolves a contradiction between two things
this project decided separately.** `speaker_gate.py` deliberately gives `--target-frr`
no default, because a plausible constant would read exactly like a measured one to
every later reader — correct for a CLI whose user is reading the source.
`journeys.md` states the reader assumes nothing about audio or models. A screen that
asks for a false-reject rate satisfies the first and violates the second, and both
were written as binding.

The resolution keeps the choice and drops the vocabulary: **two or three ordered named
options, each carrying both actual costs measured from the operator's calibration**.
"Preserve more of my speech" comes first, a measured middle point appears when three
survive, and "keep more other voices out" comes last. Before measurements load, the
prototype radios stay disabled. Its populated rates come from a deterministic
non-personal score fixture and are labelled as such; they are not claims about the
reviewer. The CLI first reports without writing, then requires an explicit rerun with
one displayed target. No point is selected by default.

Selection is not enrollment. A checked measured row enters `ready-to-build`; a build
transition follows; only a separate owner-only persistence-success transition enters
`enrolled`. The returning-profile fixture is an independent load path and cannot be
reached from the new-enrollment choice screen.

**The profile carries a private, re-derivable operating-point receipt.**
`save_profile` accepts evidence plus the selected target, not a caller-supplied
threshold or operating-point object. The owner-only receipt records the contract and
target-set versions, held-out operator and negative score arrays with counts and
digests, negative source manifests, deterministic offered choices and digest, and the
selected row. Thresholds are observed order statistics (`higher`), so every offered
threshold is one input score. `load_profile` recomputes the table and selected row;
an arbitrary 7% target or edited threshold is refused as production.

**The profile and its source recordings have separate lifecycles.** The profile is
app-private to the owning macOS account, is never included in a meeting export, and can
be reset independently. After each dedicated operator or negative recording yields the
needed owner-only derived material safely, its raw, transcript, segments, and working
files are deleted immediately. Failure, cancellation, abandonment, and **Discard
enrolment** delete partial dedicated raw and derived work and leave enrolment
incomplete. A retained source meeting is never copied or deleted by enrolment and keeps
its chosen meeting policy. Reset deletes the profile, threshold, and enrolment
provenance; it does not delete any meeting. The application then blocks capture until
reenrolment. Only the research CLI may run ungated outside beta.

**`experimental` must not look like `enrolled`.** The override exists so a
measurement can be taken with material that does not meet the contract, and its only
value is that the weakening stays visible downstream. Two surfaces already carry
that marker — the capture's console output and `transcript.json` — and a settings
panel that renders it identically to a real profile silently removes it from the one
place a person looks.

**No accent here, including while recording.** This surface records audio, so the
temptation is to reach for the live indicator. `DIRECTION.md` reserves the accent for
capture that is running, and enrolment recording *is* capture — so the accent is
correct on the menubar item (state A `recording`) and wrong as decoration on this
panel. The panel shows a level meter, which is a reading, and no other motion.

---

## J. Shell startup failure

Not a surface anyone designs for and the one most likely to be the operator's first
encounter. Three runtimes sit in this process tree — a Swift tap, a Python ASR
daemon, and the Rust/TS shell (`DESIGN.md § Shell decision`) — and any of them can be
missing on a machine that has never run the CLI.

| State | Trigger |
|---|---|
| `runtime-missing` | The Swift sidecar, Python, or the ASR weights are absent |
| `service-timeout` | A child process started and never reported ready |
| `diagnostic-written` | The failure is recorded locally, with its path shown |
| `retry` | Ordered recovery, one action at a time |
| `reinstall` | Recovery beyond what the app can do for itself |

**The rule is: never fail before rendering an operator-readable window.** Stop
partial child work, preserve any captured audio, write a local diagnostic, and give
ordered recovery. Taken from film-room's component catalog, where it is backed by
package-level fault injection naming each runtime path
(`~/Workspace/dev/wip/film-room/docs/design-system/component-state-catalog.md`) —
a project one stage further along than this one, which found that a three-runtime
desktop app fails in exactly this way and that a silent failure is indistinguishable
from a corrupt install.

The stake is higher here than there. A failure during capture is a failure during a
meeting that cannot be re-run, so preserving the audio outranks reporting the error
cleanly: a diagnostic with no recording is worse than a recording with no diagnostic.

---

## Rendered transcript text is untrusted input

Not a surface, a rule that binds several of them. Every note, transcript and
participant name rendered into the webview is a string this app did not author — it
came out of an ASR model listening to whoever was on the call. film-room reached the
same conclusion for filenames and local database strings and states it as "treat
every file/database/API string as untrusted", using text nodes where possible and a
single shared escape boundary otherwise.

Here the input is less trusted still, because a person on a call can choose what to
say. Text nodes and `textContent` are the default; anything that cannot use them
passes through one escape boundary; CSP permits only the shipped scripts. This is
recorded in the inventory rather than left to implementation because "render the
transcript" appears on four surfaces (C, D, E, F) and a boundary applied on three of
them is not a boundary.

---

## What a review of this app may be built from

film-room served a shell with placeholder interiors for an operator review, and the
operator "reasonably mistook the Ingest placeholder for a non-working folder
chooser" — recorded in its Decision 0047, which concluded that "a shell fixture
cannot serve as the next operator encounter."

So the build order here is **one working surface at a time over real data**, not a
shell with empty rooms. A placeholder does not read as unfinished; it reads as
broken, and it spends the operator's review on a question the team already knew the
answer to. The first thing worth showing is the menubar item over a real capture that
produces a real note — narrow, and true end to end.

---

## K. Retention and disk

Added 2026-07-29, from walking `journeys.md`'s J5 against this file and finding
nothing. Every capture writes two WAVs and a transcript of a conversation involving
people who are not the operator, and until this surface existed their lifecycle was
"accumulates until the disk fills."

| State | Trigger | Notes |
|---|---|---|
| `holding` | Default | What is kept, how much of it, and until when. Not a settings toggle buried in G — a standing statement. |
| `nearing-limit` | Held audio passes the operator's own ceiling | Names the consequence and the choice, before anything is deleted. |
| `expiring` | Material is inside its stated lifetime but close to the end | Deletion is never a surprise; the operator sees it coming. |
| `deleting` | Bulk or per-meeting removal running | Interruptible, and says what is already gone. |
| `audio-released` | The audio is deleted, the note is not | A first-class state on the note, not a broken one. |
| `nothing-held` | No captures, or all audio released | Names why it is empty rather than rendering blank. |

**`audio-released` is the state that makes this surface honest.** Deleting audio must
not silently destroy the note or transcript built from it, and the note must say the
audio is gone. The retained transcript still lets a claim resolve to the words behind
it. What disappears is the stronger recovery path: listening to the recording,
checking the transcription against it, or transcribing it again with a better model.
The state must name both what survived and what cannot be recovered. The owner-only
voice profile is separate and remains until the operator resets it. Deleting the whole
meeting removes that meeting's note, transcript, claim evidence, both WAV files, and
retention record; it still does not delete the voice profile or any other meeting.

**Why this outranks every interface question in this file.** It is a promise the
product implicitly makes and does not keep: "the audio never leaves the Mac" says
nothing about how long it stays on it. It is the only gap where the harm lands on
people who never agreed to anything — the far end and anyone in the room. And it is
cheap now and expensive later, because a policy adopted after a year of captures has
to be applied retroactively to material the operator has forgotten exists.

**The retention period is the operator's choice and has no default this document may
pick.** The same reasoning as the voiceprint threshold: a plausible constant would be
indistinguishable from a considered one to every later reader. First run asks, and the
answer is stated here rather than assumed.

This period governs source meetings, including any retained meeting later used to
rebuild a voice profile. It does not govern dedicated enrolment recordings: dedicated
operator and negative-sample raw is deleted immediately after the needed owner-only
derived material is safely stored. Failure, cancellation, or abandonment deletes
partial raw and leaves enrolment incomplete. That shorter lifecycle is stated before
either recording starts.

**The vocabulary is the category's, not this project's.** Granola's enterprise tier
offers "Org-wide auto-deletion periods" (`journeys.md`, market check), so this surface
says *auto-deletion period* rather than inventing a term for a thing the operator has
already met. Worth noting what that also reveals: retention is the primary paywall in
both products observed — Otter caps free and Pro at the "25 most recent" conversations,
Granola's free tier at "limited meeting history". The current CLI leaves its local
artifacts until the operator removes them; the beta must not turn that implementation
default into a retention policy. The same mechanism that competitors monetise is a cost
this product absorbs, which is the honest reason a period has to be chosen rather than
defaulted to forever.

---

## L4 templates derived from the above

Five, and no more until an L5 state demands a sixth:

1. **Shell chrome** — window frame, sidebar, title treatment. Used by D, E, F, G, I,
   J, K.
2. **List–detail** — F to E.
3. **Transient overlay** — B and C. Positioned, non-modal, dismissible.
4. **Form** — G, `choosing-operating-point` in I, and the retention period in K.
5. **Sequence** — H, and only H.

**J and K were checked against this list rather than left unmapped**, because an
unmapped surface is where a sixth template gets invented at implementation time.
Neither needs one. K is a standing status panel in the chrome plus a form for the
period and a destructive confirmation for deletion — and destructive confirmation is a
component with its own required states, not a template.

**J carries a constraint no other surface has, and it is a property of the template
rather than the surface.** Shell chrome is available to J — the Rust/TS shell must be
running to render any window at all, which is the whole premise of "never fail before
rendering an operator-readable window." But J occurs precisely when the sidecars are
missing, so **the chrome must render with zero dependency on the Swift tap, the Python
daemon, or the ASR weights.** A sidebar that lists notes, a title that names the last
meeting, or a level meter would each turn the one surface that exists to report a
broken install into a second broken thing. Any chrome element that reaches for a
sidecar has to degrade to nothing, not to an error.

**Surface I does not demand a sixth template, and that was checked rather than
assumed.** The instinct is to call enrolment a Sequence like first run, and it is
not: a Sequence is a series of steps taken in one sitting, and enrolment's central
constraint is that it *cannot* be — two sittings must be at least one hour apart and
different days are ideal. So `accumulating` is a status panel in the shell chrome that
persists across days, not a step in a flow, and the only genuinely form-shaped state
is choosing the operating point. Modelling enrolment as a wizard would encode exactly
the shortcut the enrolment contract refuses.

The menubar item (A) is not a template. It is a single glyph with seven states
and is specified directly.
