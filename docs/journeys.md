# Journeys — local-meeting-notes

`screens-and-states.md` is an inventory: eleven surfaces and the states each can hold.
It answers *what exists*. It cannot answer *what happens*, because a journey crosses
surfaces and takes days, and nothing in a state table has a clock.

That gap is why this file exists, and it is not cosmetic. Every design decision made
so far — the thesis, the tokens, the shell, the state inventory — is structural.
Structure built without a journey produces surfaces that are individually defensible
and collectively useless: the teardown already names the outcome, "whether the corpus
is useful in six months or a junk drawer."

---

## The reader, and the trap in naming them

**Reader:** the operator between back-to-back calls, who will not babysit a tool and
did not open it to admire it.

**Job:** recover what was decided and what was promised, weeks later, without having
taken notes by hand.

**Assumed knowledge:** their own meetings and their own calendar. Nothing about
audio, models, or this repository.

**Precision locks** — these words mean one thing and are never used loosely:

| Term | Means | Never means |
|---|---|---|
| **Capture** | The recording session, both legs | The note, the file, the act of pressing a button |
| **Transcript** | Every word recovered, verbatim, with gaps | A cleaned-up or summarised version |
| **Note** | What was written *from* a transcript | The transcript itself |
| **Me / Them** | Which channel a turn arrived on | Who a person is — the audio never knows a name |

**The trap:** the reader and the author are the same person today, and designing for
the author produces a tool only the author can operate. The design reader is
therefore *the same operator six months from now, having forgotten every internal*.
That is not a hypothetical persona — it is a real and testable condition, and it is
the one film-room's own contract encodes as "usually without a technical support
person."

---

## What the market says, and what it is worth

The reader, job and journeys below were derived from first principles, from film-room,
and from this project's own measurements. That is a thin base for a persona, so this
section is the market check — and it was run *after* the derivation rather than before,
which is why the convergences below mean something.

**Provenance, stated because it bounds every claim here.** Fetched 2026-07-29 from each
vendor's own pricing and marketing pages: Granola, Circleback, Otter. Those pages are
marketing, so they are evidence of **positioning and feature vocabulary — not of
quality, and not of what the product feels like to use.** Nothing here was seen
logged in, so the actual information architecture behind a sign-up wall is unobserved.
Feature names are quoted exactly because the vocabulary is the transferable part.

### Where the market agrees with what was derived here

- **Granola's headline is "The AI notepad for back-to-back meetings"**, against the
  reader written above from scratch: "the operator between back-to-back calls". The
  same person, named the same way, independently.
- **Retrieval across the whole corpus is the category's headline feature, not a
  late-stage nicety.** Granola sells "Notes, actions and memory" and ships "AI chat
  within and across meetings" *on the free tier*; Circleback's is "Ask questions and
  get answers drawn from every conversation you've had". The C → B → A ordering chosen
  below on internal evidence is where the category has already landed.
- **History is the primary paywall in both**, which is the strongest available signal
  that the corpus is where the felt value is: Otter's free and Pro tiers cap at the
  "25 most recent" conversations, Granola's free tier at "limited meeting history".

### Where the market answers a question this project listed as open

- **The organising primitive is folders plus the calendar, not chronology and not
  counterparty.** Granola and Otter both ship "folders"; Otter adds "channels". Surface
  F's open IA question can stop being open on the primitive.
- **Retention has settled vocabulary: Granola enterprise offers "Org-wide
  auto-deletion periods".** Surface K should use the category's words rather than
  invent its own, because the operator has met them elsewhere.
- **Search scope is transcript plus metadata**, not notes alone: Otter free is "Search
  by keywords", Pro is "Advanced search by speakers, date range, and more".

### Where the whole category is weak, which is where this product can be strong

These are the findings worth the fetch. Two gaps listed below as this project's
problems turn out to be nobody's solved problem:

- **No product observed links a claim in a summary back to the words behind it.**
  Otter has "editable time codes" and a "Takeaways panel", and no mechanism connecting
  a takeaway to its transcript position. J1's trust beat is therefore a differentiator
  rather than table stakes — and it matters more here than for a cloud competitor,
  because this transcript is measurably partial where theirs is not.
- **Correction is undescribed everywhere.** Nothing on Granola's marketing describes
  editing or correcting the AI output. J4 is a category gap, not a catch-up item.
- **Telling the far end is immature across the board.** Otter's "Recording disclaimer
  email" is Business-tier; Granola's equivalent is an enterprise "Org-wide notification
  that Granola is being used", marked pilot. Surface B's open decision is open in the
  market too, which means there is no convention to inherit and the legal constraint is
  the only guide.

### The one thing the market has that this project had not thought of

**Granola preps a Brief *before* the meeting** — "who's attending, what you discussed
last time, and what matters now." Every journey below starts at the meeting or after
it. That is a whole missing journey, and it is the one that converts the corpus from
something searched on demand into something that arrives when it is useful. It is added
as J0.

It also depends on a capability this product does not have: **calendar integration.**
Granola knows a meeting exists, and who is in it, before any audio. This product infers
a meeting from microphone use, which is why its own inventory has a detection surface
and no notion of a counterparty. That is a real architectural consequence of a
positioning difference, and it is not a small one — "what did we discuss last time"
requires knowing who "we" are, which no amount of audio supplies.

---

## Three candidate structures, and why the choice matters

A journey model needs a unit. The unit determines what the product optimises, so
picking it by instinct decides the product by accident. Three candidates, each
developed far enough to be compared, then tested against a capture this project
actually made.

### Candidate A — the meeting lifecycle

**Unit:** one meeting. Beats: mic use detected → consent → armed → capturing,
unwatched → a leg degrades → stop → transcribing → note ready → read → exported.

Maps cleanly onto the existing inventory: B, A, C, D, E. Every beat already has a
surface and a state. That is a strength and also the warning sign — a model that asks
for nothing new is usually describing the tool rather than the person.

**What it optimises:** never mis-capturing a meeting.
**What it is blind to:** whether anyone reads the result. Under A, "note written" is
the terminal state, so a hundred unread notes score as a hundred successes.

### Candidate B — the commitment lifecycle

**Unit:** a thing somebody agreed to do. Beats: said → transcribed → extracted as an
action item → surfaced when the operator can act → acted on or declined → closed.

**What recommends it:** this is already the project's measured metric. `notes/EVAL.md`
hand-scored commitments — 8 of 10 caught against a hosted tool's 10 — and deleting two
prompt rules took action items from three to eleven. Every notes measurement in this
repository is a commitment measurement.

**Where it fails:** a meeting also produces the reasoning behind a decision, and B
discards it. "We rejected the queue approach because retries reset status" is not a
commitment and is exactly what nobody remembers in three weeks. B also implies
task-management surfaces the tool has no business owning — the operator already has a
task system, and a notetaker that becomes a second one gets abandoned.

### Candidate C — the retrieval lifecycle

**Unit:** a question asked later. Beats: a question arises weeks on → the operator
opens the tool → locates the right meeting, or the right claim across meetings →
decides whether to trust what they find → uses it, or gives up.

**What recommends it:** it forces the decisions the inventory lists as unsettled.
Surface F's open questions — organising primitive, whether notes link, whether search
covers transcripts or only notes — are unanswerable from A or B and are *forced* by C.

**Where it fails:** it depends on capture working, so it cannot be designed in
isolation. And it is the hardest to prototype honestly, because it needs a corpus that
does not exist yet.

### The test, on a real capture

The 75-minute meeting this project recorded: 802 merged turns, 14.2% of them the room
rather than a participant, notes with 3–5 action items and 4–5 decisions.

- **Under A** the journey completed successfully. A note exists. Nothing asks whether
  it was ever opened, and it was not.
- **Under B** the interesting question is which commitments survived, and the answer
  is measured and mediocre.
- **Under C** the question is what happens three weeks later when the operator needs
  what was decided — and the answer is that nothing in the product helps, because
  retrieval is a search box over an unsettled IA.

And a second real case decides it. On the level-45 sweep take, transcript recall was
**30.7%** — the note was built from under a third of the words. That is not an error
state; on speakers it is the normal one. **A tool whose artifact is routinely
incomplete lives or dies on whether the operator can tell what is missing and get to
the rest.** That is a retrieval and trust problem. Under A it is invisible: the note
renders, looks complete, and lies by omission.

### Chosen: design C → B → A. Build order is a separate question.

The three are not alternatives, they are a dependency order, and **the order they are
designed in decides what gets built**:

- **Design A → B → C** and retrieval inherits whatever the capture happened to
  produce. That is the junk drawer, arrived at honestly.
- **Design C → B → A** and retrieval requirements constrain the note's shape, the
  note's shape constrains what capture must preserve, and capture is built to serve
  something.

**This is a claim about design order, not build order, and conflating them would be a
real error.** Capture already exists and works; nothing here argues for rewriting it.
It argues that the next *design* question is what a note has to be to be findable and
trustworthy in six months — and that answering it will change the note format, which
capture already has everything needed to feed.

---

## The journeys

Six, ordered as designed rather than as experienced. Each names the surfaces it
crosses so the inventory can be checked against it.

### J0 — "What happened last time with this person?" (preparation)

Two minutes before a call, the operator wants what was said last time and what they
owe. Added from the market check: Granola preps a Brief before every external meeting —
"who's attending, what you discussed last time, and what matters now" — and no journey
here had a beat before the meeting started.

**This is J1 performed in advance, and that is the whole point.** The retrieval journey
requires the operator to know they have a question. J0 requires only that a meeting is
about to happen. It is the difference between a searchable archive and a tool that
appears to remember, and it is the strongest argument in this document for the corpus
being worth building at all.

Crosses nothing that exists. **It also cannot be built on this product's current
architecture, and that is the honest finding rather than a missing surface.** A brief
needs to know a meeting is coming and who will be on it. This product infers a meeting
from microphone use — after it starts — and never learns a counterparty, because the
audio does not carry names and `teardown.md` establishes that speaker names come from
the meeting UI rather than the sound.

**Resolved 2026-07-29: the tool reads the calendar, locally and read-only.** The fork
looked larger than it was, because it was framed as "a large new permission for a tool
whose pitch is that nothing leaves the machine" — and an inbound read does not move
anything off the machine. macOS supplies the calendar locally through EventKit with no
network call at all, so the pitch is untouched. `DESIGN.md § Context inputs` carries the
decision, the two findings that shaped it, and the one genuine cost: macOS offers no
read-only calendar grant, so the app holds a permission wider than the code uses.

What remains open is the *counterparty* half. A calendar says who was **invited**, which
is not who spoke, not who attended, and not who said any given sentence — and
`DESIGN.md` bars invitee names from the summarization prompt for a measured reason. So
J0's brief can say "your last call with this person" and the note still cannot say
"Brian agreed". Whether anything ever bridges that is undecided, and nothing in the
market bridges it either: `teardown.md` establishes that every product's speaker names
come from the meeting UI rather than the audio.

### J1 — "What did we decide about X?" (retrieval)

Three weeks after a call, the operator needs a decision they half remember. They do
not remember which meeting, and may not remember who was on it.

Crosses **F → E → transcript**. The beats that decide whether this works:

1. **Entering with a question, not a date.** The operator knows the *subject*, so a
   chronological list is the wrong first affordance and a search box over note text is
   the minimum.
2. **Landing on a claim, not a meeting.** What is wanted is the sentence "we agreed
   to defer the migration", not a 60-minute note to skim.
3. **Deciding whether to trust it.** The note is a compression of a partial
   transcript. So a claim must be traceable to the words behind it, and the operator
   must be able to hear that moment. **This is the beat with no surface today.**
4. **Discovering the answer is not there.** A partial transcript means "not found" is
   ambiguous between *never said* and *not captured*, and the product knows which:
   recall figures and the gate's own report are in the artifact. Presenting the two
   identically is the single most damaging thing this journey can do.

### J2 — "Did I promise anyone anything?" (commitment)

End of day or week. Crosses **F → E**.

The load-bearing constraint is that this must not become a task manager. The tool
answers *what was said* and hands off — an export, a copy, a link into whatever the
operator already uses. Owning the closed state means owning follow-up, and that is a
different product.

**That constraint decides where this lives, and it is a filter on F rather than a
surface of its own.** An earlier version of the gap table below listed "no
cross-meeting aggregation" as a medium gap, which was wrong twice over: a journey with
no surface anywhere is not a medium gap in an inventory, it is a journey the product
cannot perform — and calling it medium made an undecided thing read as scheduled.

Decided: F gains a state where the organising primitive is the commitment rather than
the meeting, spanning a date range. It is a `filtered` view in the sense F already
carries, not a new template and not a new surface, and it is the smallest thing that
satisfies J2 without acquiring a task manager. Its detail target is still E, and its
terminal action is still export — because the moment this surface offers a checkbox,
the tool owns follow-through and the operator has two task systems.

### J3 — The meeting itself (capture)

Crosses **B → A → C → D → E**, fully inventoried. The two-leg CLI capture substrate
exists and the state choreography is reviewable in `docs/prototype/build.py`; there is
still no application that owns the journey end to end.

Two beats worth restating as journey rather than state. **Consent** is the highest-
stakes interaction in the product and the only one with legal weight in roughly a
dozen US states. And **degradation** is a beat, not an error: a leg dies mid-meeting,
the operator is in the meeting, and the only acceptable behaviour is to keep the good
leg and be visibly honest at menubar size.

### J4 — "This note is wrong" (correction)

The gate marked a colleague's speech as not-the-operator. The operator disagrees.

**The code promises this journey and the review prototype now specifies its
consequence.** `transcript.json` keeps every gated turn with its score precisely so the
decision can be overruled. The correction specimen makes a restored turn mark the note
stale and requires a separate regeneration. It is not wired to a real capture and no
application surface performs the operation yet, so this remains a product contract
rather than a feature.

Minimum: the gated turns are visible where the note is read, distinguishable, and
restorable — after which the note is regenerated, because a correction that does not
change the note corrects nothing.

### J5 — "How long is this keeping recordings of other people?" (retention)

**The lifecycle is now specified and prototyped, but not implemented; it remains the
highest-stakes application gap.**

Every capture writes two WAVs and a transcript of a conversation involving people who
are not the operator. Surface K and the interaction prototype now require a
no-default retention choice, disk accounting, per-meeting audio deletion, whole-meeting
deletion, and a separately resettable owner-only voice profile. The CLI still leaves
artifacts on disk until the operator removes them, and no application enforces the
specified lifecycle.

This outranks every interface question above, for three reasons. It is a promise the
product implicitly makes and does not keep — "the audio never leaves the Mac" says
nothing about how long it stays on it. It is the one gap where the harm lands on
people who never agreed to anything. And it is cheap to close now and expensive later,
because a retention policy adopted after a year of captures has to be applied
retroactively to material the operator has forgotten exists.

Beats: a capture ends → audio and transcript have a stated lifetime → the operator can
see what is held and how much → deletion is possible per meeting and in bulk → deleting
audio does not silently destroy the note built from it, and the note says the audio is
gone.

Voice enrollment has a deliberately shorter branch. Dedicated operator and
negative-sample raw is deleted immediately after the needed owner-only derived
material is safely stored. Failure, cancellation, abandonment, and **Discard
enrollment** delete partial raw and leave enrollment incomplete. A retained source
meeting is never copied or deleted by enrollment and keeps its existing meeting
retention. The derived profile is private to the owning macOS account and is deleted
through its own reset action. Resetting it leaves meetings alone and blocks application
capture until enrollment completes again; only the research CLI may run ungated
outside beta.

---

## Future research opportunity — meeting evidence as product input

**Status: research candidate, not a current product commitment.** This note app is
beginning to look like one source-specific spoke in the broader knowledge-capture and
retrieval work explored by `se-docs-frontdoor` and its successor, `docracles`.
`local-meeting-notes` would still own the narrow job it is designed for: capture a
meeting locally and preserve enough evidence to check what the note says. The broader
system would decide how that evidence relates to product work, who can approve the
relationship, and how it becomes findable later.

### Concrete case

The operator is already building a product. Its current goals, requirements,
decisions, assumptions, and open questions exist somewhere outside this app. They then
meet with a customer or user and collect feedback independently of that product work.

After the meeting note is ready, the useful question is not only "what happened?" It
is:

> What did this conversation reveal that may inform what we build next?

A useful result would identify candidate product inputs such as:

- an intent or goal the person stated directly;
- an intent, goal, or unmet need inferred from what they described;
- evidence that supports or challenges an existing product assumption;
- a possible opportunity, constraint, or change in priority; or
- no supported product implication.

Every candidate must link back to the exact meeting evidence behind it and to the
product context it may affect. It must also preserve three different claims that are
easy to collapse and dangerous to confuse:

| Layer | Example | Authority |
|---|---|---|
| **Meeting evidence** | "The customer said they reconcile this by hand every Friday." | The cited transcript turns support what was said; capture gaps remain visible. |
| **Derived intent or goal** | "They may be trying to reduce recurring reconciliation work." | A labelled inference to review, never rewritten as the customer's own words. |
| **Proposed product consequence** | "This may support prioritising automated reconciliation." | A product proposal that requires a human decision against the rest of the product evidence. |

The handoff is the opportunity. The meeting app produces evidence-preserving notes.
The wider knowledge system can turn permitted work exhaust into candidate records,
retain their provenance, route consequential inferences for review, and later answer
questions such as "which customer evidence supports this feature?" or "which user
goals conflict with the current requirement?" Neither system has to pretend that a
single meeting comment is already roadmap authority.

### What research must settle before this becomes roadmap work

1. **Product binding:** how a meeting is connected to the correct product, initiative,
   feature, requirement, or open question without guessing from vocabulary alone.
2. **Explicit versus inferred meaning:** what evidence is sufficient to call something
   a stated goal, and how weaker extrapolations are labelled and reviewed.
3. **Traceability:** whether a reviewer can move from a proposed product consequence
   to the derived intent, the cited meeting words, and the capture-quality limits.
4. **Aggregation and conflict:** how repeated signals, contradictory customers,
   recency, and product strategy affect a candidate without manufacturing consensus.
5. **Human authority:** where accept, edit, reject, and defer happen before any
   requirement, specification, backlog, or authoritative product record changes.
6. **Value:** whether the candidates find useful product evidence that a person would
   otherwise miss, without creating more review work or false implications than they
   save.

The minimum guardrail is simple: this path may propose a connection, but it cannot
make the product decision. A partial transcript is not a complete meeting record, an
inference is not a quote, one person's feedback is not consensus, and a generated
candidate does not have authority to edit the product.

---

## The one decision that resolves J1 against J5

J1's defence against a confident partial note is tracing a claim back to the words
behind it. J5 deletes audio on purpose. Written as two journeys those are a
contradiction, and noting it in both places is an acknowledgement rather than a
resolution — so it is resolved here, because one decision settles both surfaces.

**The question:** does a note carry enough evidence *inline* that the audio is only
ever a bonus? If yes, retention is cheap and J1 survives deletion. If no, J1's defence
has a fixed expiry, and what looks like a retention period is really a *trust* period —
after which every note becomes an unfalsifiable claim.

**Decided: the note cites the transcript, and the transcript is what is retained.**
Each claim in a note carries the verbatim turn or turns that produced it, with their
timestamps. Three reasons, and the third is what makes it obvious:

1. **It makes trust independent of audio.** Reading the words that produced a claim is
   the check; hearing them is confirmation of tone and identity, which matters
   sometimes and is not the load-bearing case.
2. **The layers have wildly different costs.** An hour of two-leg 16 kHz audio is
   roughly 230 MB; its transcript is tens of kilobytes. Retaining the cheap layer
   indefinitely and expiring the expensive one is available precisely because the
   evidence lives in the cheap one.
3. **A partial transcript makes citation more necessary, not less.** At 30% recall the
   note's claims rest on a third of the words, and a citation is what lets the operator
   see *which* third. A note that says "we agreed to defer" over an unquoted gap is the
   failure mode; the same note quoting the two turns it compressed is honest about its
   own basis.

**Consequences, which became real work rather than corollaries.** `note/1` artifacts
now carry each claim's quoted evidence and a locally derived transcript location, and
the review prototype renders the claim and words together. The current
evidence-transport repair still fails closed before it can produce a new supported
artifact, so the contract is visible without being mistaken for a quality result.
K's `audio-released` is now specified as a mild state: the note keeps its transcript
evidence, and only the ability to *hear* or retranscribe the source audio is gone.

That the retrieval journey turned out to change the note format is the C → B → A
ordering doing exactly what it was chosen for.

---

## What the inventory is missing, checked against the journeys

Derived by walking each journey against `screens-and-states.md`, not by inspection.

**Status names the strongest evidence available, never a shipped implementation.**
*Specified* means a surface and its states exist in the inventory; *prototyped* means
the transition is reviewable but does not touch real product state; *decided* means the
design question is answered here and the surface work follows; *open* means nobody has
answered it yet. There is still no app. Collapsing those into a severity was the first
version's error — it made an undecided item read as scheduled.

| Gap | Journey | Status |
|---|---|---|
| Retention, deletion, disk accounting | J5 | **Prototyped, not implemented** — surface K and the encounter state exact deletion consequences, including the independent voice-profile lifecycle |
| A claim in a note has no path to the words behind it | J1 | **Prototyped, repair still open** — `note/1` and surface E carry the claim-to-transcript path, while the current evidence-transport repair fails closed before a new quality result |
| No way to overrule a gate decision | J4 | **Prototyped, not wired** — the specimen restores a turn, marks the note stale, and regenerates; no app performs it on a real capture |
| "Not captured" and "never said" look identical | J1 | **Prototyped, not measured on a capture** — the specimen distinguishes a withheld turn and capture limits; QMSum has no real gate report |
| F has no commitment-organised view | J2 | **Decided** — a `filtered` state on F, not a new surface |
| A note that is present but inadequate | J1, J4 | **Decided** — a note's checkable proportion is shown on E and on F's rows, so a thin note is visible before it is opened. `summary-failed` still covers only absent |
| Export and share have no redaction step | J2 | **Open** — gated turns and room speech would travel with the note |
| The far end's experience | J3 | **Open**, already flagged in the inventory, and the one with legal weight. No convention to inherit — immature across the category |
| No preparation journey | J0 | **Decided** — local read-only calendar via EventKit, `DESIGN.md § Context inputs`. The surface for a brief is still unspecified |
| Who spoke, as opposed to who was invited | J0, J1 | **Open, and possibly unbridgeable.** A calendar gives invitees; the audio gives channels. Nothing in the market bridges it either |
| The note's own section structure was never designed | J1, J2 | **Decided** — sections are a rendering, not the model's output. See below |
| A claim's subject is not extracted | J1 | **Open** — the one thing needed to group a note by what it was about, and no measurement supports asking an 8B model for it yet |

**The note has four sections and no document chose them.** `notes/summarize.py` emits
Summary, Decisions, Action items and Open questions. That list appears in no design
record — not here, not in `DESIGN.md`, not in `screens-and-states.md`, not in
`notes/EVAL.md`. It arrived with the first notes commit (`e542232`) and has been the
note's shape ever since, through a citation contract and a prototype built to settle
"the note format".

The prototype rendered it faithfully, which is the problem. This file argued that
designing C → B → A would let retrieval requirements constrain the note's shape; the
citation layer *was* constrained that way, and the sections underneath it were inherited
whole and never asked to justify themselves. Decisions plausibly serves J1 and Action
items plausibly serves J2 — plausibly is the word doing the work, and it is the word
this file rejects everywhere else.

The correction is borrowed from the operator's own, made when a redesign stayed anchored
to the site it was replacing: *"you are too grounded in what we already have and i can't
trust you are building a net new design."*

### Three candidate note structures, tested against the notes on disk

Not to be confused with the three candidate *journey* structures above, which chose the
unit this whole file is organised by. That question was "what is a journey about"; this
one is "what shape is a note", and it is downstream of the answer — C → B → A was chosen
precisely so retrieval would get to constrain the note.

**The evidence first, because it decides the comparison.** The current structure
produces 11, 15 and 55 items on the three real meetings, against a human reference that
segments the same meetings into **5, 7 and 5 subjects**. Two separate problems hid in the
longest, and they had to be told apart before any structure could be judged:

- **Duplication, since fixed.** The merge pass was repeating itself — 160 extracted items
  consolidating into 83 of which 14 were exact repeats, on the chunked path only.
  `dedupe_items` strips and counts them, and a re-run under the revised citation prompt
  produced 55 items with zero repeats, so the prompt turned out to fix the cause too.
  Full account in `notes/EVAL.md`.
- **55 is still an order of magnitude above 5**, so the count was never only an artifact.
  And the problem was wider than the section names: only **6 of 31 located quotes
  supported the claim they were attached to**, action items 0 of 8. A fourth section for
  what was *raised and not agreed* took that to **17 of 42 (40%)**, and `Proposed` is now
  the best-supported kind in the note at 5 of 7 — the model was finding hedged speech all
  along and had nowhere honest to file it. `notes/EVAL.md` has the account, including a
  `verified` state that told readers a claim had passed a check nothing performed, and
  three separate parser blind spots that reported real citations as absent.

**Candidate A — keep type-first sections.** Summary, Decisions, Action items, Open
questions, as the model emits them. Serves J2 directly: Action items *is* the answer.
Costs nothing to keep, and the DECISION/ACTION/QUESTION vocabulary already exists in the
extraction pass and is measured. **Where it fails:** the item count grows with meeting
length, so at 55 the note cannot be read in one pass — and a subject's information is
scattered across all three sections, which is exactly J1's entry. "What did we decide
about disk storage" means scanning three lists.

**Candidate B — subject-first, types nested underneath.** A handful of subjects, each
carrying its decisions, commitments and open questions. Serves J1 directly and stays
readable at any length, because the top level holds steady while claims-per-subject
grows — which is what the human reference's stable 5–7 demonstrates is achievable.
**Where it fails:** it needs the model to segment by subject, a harder task than
labelling an item, on a model this project has already measured as unreliable at
following a citation format. Nothing supports the assumption that it can.

**Candidate C — typed claims, sections as a rendering.** The model extracts claims and
labels each one; no pass decides the note's structure. Grouping is chosen by whatever
reads the note. **Where it fails:** a flat list is not a reading surface on its own, so
something downstream must choose a grouping — this does not remove that decision, it
moves it.

**Chosen: C.** Three reasons, and the third is what makes it obvious.

1. **It is the project's own stated principle, unapplied.** film-room's DP-4 — "analysis
   is the substrate; outputs are renderers" — is cited elsewhere in this repository. A
   note whose section headings *are* its data model is the opposite: the substrate
   shaped by one renderer's needs.
2. **It costs no model capability.** A and C ask the model for exactly the same thing.
   B asks for something unmeasured.
3. **The information already existed and was being thrown away.** The extraction pass
   labels every item DECISION, ACTION or QUESTION. The consolidator turns that into a
   markdown heading, and by the time a `note/1` artifact exists the label survives only
   as *which section a claim happens to sit under* — so any surface wanting to group by
   kind had to re-parse the note and become a second authority on what a section means.
   Recovering it is not new machinery; it is stopping a discard.

**What shipped:** `note/1` claims carry `type`, recovered from the heading each sits
under, with an unrecognised heading keeping its own words rather than being forced into
one of the three. E can now group by kind, filter to commitments for J2, or read in
order for J1, with no further model call. The markdown keeps its three sections, because
that is now one rendering among several rather than the structure.

**What did not, and why it is the honest boundary.** Grouping by *subject* is what would
make a 55-claim note readable, and nothing extracts a subject. Candidate B's risk does
not disappear by being deferred — it becomes a measurement someone has to run. Recorded
as its own open gap above rather than folded into this decision.

---

## What to prototype, and what a prototype cannot settle

film-room's Decision 0047 records the operator opening a shell with placeholder
interiors and reasonably mistaking one for a broken folder chooser. Its conclusion is
that a shell fixture cannot serve as an operator encounter. The inference here — which
is this project's and not that decision's — is that a prototype is the right tool for
a *design question* and the wrong one for judging the product.

**Worth prototyping, because these are design questions:** J1's retrieval path, since
the organising primitive, the search scope, and the claim-to-audio path are all
unsettled and all cross-surface; and the note format itself, since J1 and J2 both
depend on its shape and it is currently whatever the summarizer emits.

**Prototype as static HTML** — the same shape film-room used before its Tauri
candidate. It can settle IA, hierarchy, and the note's shape against a real corpus.

**It cannot settle** whether the notes are any good, which needs the dogfood run;
whether retrieval works, which needs a corpus of more than one meeting; or anything
about capture, which is not in it.

**A prototype needs real content or it settles nothing.** This project has one real
75-minute capture and three QMSum meetings, which is enough to populate a library view
honestly and not enough to test search. Populating it with invented meetings would
make every IA judgement worthless, and the operator's own recorded objection — "so
where is the content I use for reviewing with 630?" — is what that failure looks like
from the outside.

### Built: `docs/prototype/build.py`

A generator rather than a page, because the populated page is derived from QMSum and
`.gitignore` already keeps that corpus out of a public repo. It reads `note/1`
artifacts and renders J1's retrieval path against them.

**What it settled.** A claim's evidence state belongs to the claim, always visible,
never a hover — because on real runs no note is uniformly one thing. Verified ran 7 of
11, 33 of 83 and 4 of 15 across the three meetings, so it is neither rare nor
reliable; every note carries at least two states, and on the longest, 41 claims with
composed evidence sit beside 33 with real evidence. A note-level trust mark would be
false on all three. Claims render in read order rather than sorted by trust. And the
claim → words path needs no audio, so K's `audio-released` costs confirmation of tone
and not the check itself.

**What building it caught, which is the reason to build it.** The prototype needed
every claim state populated from real runs, and populating them is what exposed that
the citation checker was wrong on most real output. Two regexes decided independently
whether a claim was cited; the model collapsed the quote onto the claim's own line on
two of three meetings; the first regex missed it, the second matched the whole line,
and 41 located quotes reported as "no quote offered" — a bucket that does not fail a
run. One of those runs therefore reported PASS with four composed quotes in it. Reading
the notes as a *reader* would is what surfaced it; no check was going to, because every
fixture used the layout the contract asks for.

**What building it changed.** Two things the walk had not predicted. A located
claim's *locator* is a promise a reader cannot check by looking — a button that
scrolls to the wrong turn still moves the page and still highlights a turn, and the
operator reads speech that did not produce the claim, which manufactures confidence
rather than merely failing. It is asserted at build time now, with both a wrong-index
and an out-of-range control. And a note artifact has to record which *transform*
produced its turn indices: `strip` preserves positions and `simulate_bleed` does not,
so the safe case would have concealed the unsafe one until someone rendered a bleed
run.

**What it could not populate, and says so in place.** J1 beat 4's honesty banner — the
corpus is full-recall reference text, so no gate ran and there is no recall figure;
it is rendered as a labelled specimen carrying this project's own published
measurements instead of an invented meeting. Chronological ordering, because corpus
meetings have no date. And search, deliberately: no box is drawn, since one that
ranked three results would look settled while resting on nothing.
