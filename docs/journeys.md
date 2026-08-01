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
quality, and not of what the product feels like to use.** Nothing in that pass was
seen logged in, so the actual information architecture behind a sign-up wall is
unobserved. Gong was added 2026-07-31 from its official product documentation rather
than its marketing pages: the [call page](https://help.gong.io/docs/intro-to-the-call-page),
[conversation library](https://help.gong.io/docs/find-conversations-and-organize-the-library),
and [transcript](https://help.gong.io/docs/view-a-call-transcript). Those pages establish
documented behavior, not usability or quality. Feature names are quoted exactly because
the vocabulary is the transferable part.

### Where the market agrees with what was derived here

- **Granola's headline is "The AI notepad for back-to-back meetings"**, against the
  reader written above from scratch: "the operator between back-to-back calls". The
  same person, named the same way, independently.
- **Retrieval across the whole corpus is the category's headline feature, not a
  late-stage nicety.** Granola sells "Notes, actions and memory" and ships "AI chat
  within and across meetings" *on the free tier*; Circleback's is "Ask questions and
  get answers drawn from every conversation you've had". The C → B → A ordering chosen
  below on internal evidence is where the category has already landed.
- **Gong puts the recording, transcript, outline, highlights, questions, comments and
  follow-up on one call object.** That supports one meeting-detail surface with several
  evidence-linked views rather than separate destinations for the transcript, summary
  and follow-up. Its coaching statistics and deal context are sales-product scope, not a
  template for this product.
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
- **Gong makes retrieval a choice of entry point.** It documents filters for people,
  accounts, exact words, trackers and call titles, plus saved searches, folders and
  streams that collect future matching calls. That validates Library as a product
  surface, but it does not decide whether this product should lead with a question,
  exact search, filters, a saved collection or recent meetings. The colleague survey
  below asks that choice directly.

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

### Colleague survey — analysis registered before reading responses

The [15-question Google Form](https://docs.google.com/forms/d/e/1FAIpQLSfZRYd2rfnzoAvCGkPIzcZVOxQOhpFUXYQo9Yj3h08M_Amq6g/viewform?usp=dialog)
opened 2026-07-31. It asks colleagues which meetings and post-meeting problems matter,
what the app should do during capture, which privacy controls and outputs are important,
how evidence should be reviewed, how an old meeting should be found, and how customer
feedback should relate to product work. It collects no email address and asks for no
confidential meeting content.

This is a convenience sample, not a market-size study. An anonymous response cannot be
deduplicated reliably or weighted by role, and a small group of colleagues cannot prove
general demand. Preserve the response count and denominator beside every result. Report
checkbox counts as selections, not as mutually exclusive preferences. Keep free-text
answers as qualitative evidence; do not turn the number of similar phrases into a false
vote.

#### Observed snapshot — n=2

Two responses exist. That sample is too small to choose a default or support a demand
claim, and the public repository deliberately does not retain respondent-level rows,
free text, timestamps, or answer combinations. The source responses remain in the Form.

At the decision level, the snapshot reinforces transcript fidelity, speaker context,
operator-controlled sharing, useful summaries, and actions with owners. It does not
resolve the during-meeting surface, retention duration, retrieval entry point, or
whether customer feedback should remain in the note or become a separately reviewed
product signal.

This changes no release gate or supported capture mode. It preserves two later
comparison tests: simple note versus live transcript during capture, and filters versus
natural-language retrieval after the corpus contains enough reviewed meetings to make
either test real. The product already retains the transcript as a first-class artifact;
the snapshot sharpens that priority without expanding beta scope.

The questions may change these product decisions:

| Survey evidence | Decision it may inform | What it cannot authorize |
|---|---|---|
| Meeting types and post-meeting problems | First pilot scenario and the primary job of the note | Expanding the supported capture envelope |
| During-meeting behavior and capture capabilities | Whether the first encounter is Start/Stop only, includes operator notes, or exposes transcript state | Claiming live transcription, speaker mode or automatic detection works |
| Audio and privacy answers | Retention choices, account and calendar defaults, and which controls must be visible | Weakening consent, local ownership, deletion or no-unprompted-sharing boundaries |
| Useful outputs | Information hierarchy of the note and which outputs deserve prototype variants | Treating every selected output as first-beta scope |
| Trust requirements | Which evidence, uncertainty and review controls must travel with generated material | Turning an inference into a quote or replacing human authority with confidence |
| Cross-meeting value and retrieval entry point | Whether Library/Ask follows the note basics, and whether it leads with a question, exact search, filters, collections or recency | Moving cross-meeting retrieval into the current beta before the corpus is trustworthy |
| Customer-feedback scenario | Whether the product-signal handoff below deserves a later prototype | Creating or changing a requirement, roadmap or backlog item automatically |
| “Never do” and open text | Prohibitions, missing jobs and language worth testing | Overriding measured defects or product safety gates |

Survey results can reorder hypotheses and decide which alternatives enter the
click-through. They cannot make a mechanical experiment pass, approve an interaction,
expand the current beta by themselves, or convert the future product-input research
below into roadmap work. Record the raw counts, the strongest counterexamples and any
change to the product brief together; do not quote only the answers that agree with the
current direction.

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

Crosses **B → A → C → D → E**, fully inventoried. The signed internal
transcript alpha owns consent, two-leg capture, post-meeting transcription, and
fresh-process transcript recovery. It does not yet own the evidence-linked note and
library end of the journey, so the beta journey is still incomplete.

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

**The lifecycle is specified and prototyped, and scheduled audio deletion is
implemented in the internal alpha. Its first real due-deletion receipt is still open;
the remaining trust actions are not implemented. This remains the highest-stakes
application gap.**

Every capture writes two WAVs and a transcript of a conversation involving people who
are not the operator. Surface K and the interaction prototype now require a
no-default retention choice, disk accounting, per-meeting audio deletion, whole-meeting
deletion, and a separately resettable owner-only voice profile. The internal alpha
persists a one-day policy and runs due deletion at startup, but the first real deletion
event is not yet a receipt and the other trust actions remain later work.

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
outside beta. The retained owner-only material includes the held-out score and
negative-source receipt needed to re-derive the selected operating point without raw
audio; it is never included in a meeting export.

Readiness is conjunctive: a valid profile, both current capture permissions, and an
explicit meeting-audio retention choice must all exist. Participant attestation then
applies to one capture attempt only. Every new Start, decline, cancellation,
completion, profile reset, or retention change clears it and disables Continue.

---

### J6 — "Can I help improve this transcript without giving away the meeting?" (evaluation contribution)

**Status: research candidate, not part of the current beta or encounter.** An operator
may want to tell the project where transcription failed or, with every participant's
informed consent, provide material for a controlled evaluation. Those are useful jobs.
They are not ordinary telemetry, and recording consent does not by itself authorize
research sharing.

Two authorities have to remain separate:

1. **Evaluate locally.** Rate a transcript, tag an error, or write the words that should
   have appeared. This changes only owner-private material on the Mac.
2. **Contribute deliberately.** Prepare a named packet for a stated evaluation, inspect
   its contents, confirm the separate sharing consent, and transfer it through one
   explicit action.

Calling both actions “send feedback” would hide the only boundary that matters: whether
meeting content leaves the computer.

#### Three candidate structures

| Candidate | What it gets right | Where it fails |
|---|---|---|
| A global “help improve transcription” control in Settings | Easy to find and cheap to implement | A blanket choice cannot authorize future meetings, other participants, or data uses the operator has not yet seen. Rejected. |
| A “send this” action beside every transcript correction | Keeps the evaluation close to the error | It makes an ordinary correction look like consent to disclose the surrounding meeting. Useful only as a local save action, not as the transfer path. |
| A meeting-scoped contribution builder plus an admin record | Binds one purpose, one meeting, one reviewed packet, and one consent receipt | Adds deliberate friction. Chosen for later prototyping because that friction is the review. |

The resulting shape is a hybrid. Surface E may eventually offer **Save private
evaluation** after a correction. Nothing is sent. A separate **Prepare research
contribution** action starts a meeting-scoped builder. A later Research & evaluation
admin view lists what is still local, what was transferred, the recipient and purpose,
the promised deletion date, and any deletion request. It is a record of governed
actions, not a global participation toggle.

#### What a contribution may contain

The operator chooses the smallest class that can answer the registered evaluation
question:

| Class | Possible contents | Default |
|---|---|---|
| Private evaluation | Model and capture versions, rating, error tags, and an optional human correction | Remains local |
| Text evaluation packet | Selected transcript spans, the human correction, and only the technical metadata needed to reproduce the error | Not prepared until selected |
| Recording evaluation packet | Selected audio spans or, only when justified, the recording legs; the reference transcript; capture metadata; and the consent receipt | Not prepared until selected |

A corrected transcript is still private meeting content even when no audio is attached.
“No recording” is not the same as “anonymous.” Redaction helps a reviewer remove
obvious names or secrets; it must not be presented as proof that the material can no
longer identify someone.

The first program should be narrower than the eventual feature: project-owned
evaluation only, no model training, no publication, no third-party sharing, and a fixed
deletion deadline stated before transfer. A meeting involving an unconsenting speaker,
an unaware person in the room, or a purpose the operator cannot explain is ineligible.
The builder fails closed rather than accepting a broad account-level attestation.

#### Required review and receipts

Before transfer, the interface must show:

- the exact files and selected time ranges;
- whether they include operator audio, participant audio, transcript text, or technical
  metadata;
- the named recipient, registered evaluation purpose, retention deadline, and prohibited
  uses;
- confirmation that every recorded participant consented to this sharing purpose, not
  only to the original meeting recording; and
- a plain statement that no material has left the Mac yet.

Transfer produces a receipt binding the packet digest, policy version, consent
attestation, recipient, purpose, time, and deletion deadline. A failed or interrupted
transfer remains visibly unsubmitted. Before transfer, Discard removes the prepared
packet. After transfer, the admin view can request deletion and retain the response;
it must also state any limit honestly. Data can be deleted from the evaluation store,
but an aggregate already reported cannot be made historically unobserved.

The first implementation should prefer an encrypted export with a separately verified
delivery channel. Built-in upload adds a remote identity, authentication, storage,
access, deletion, and incident-response system. That work is not authorized by adding
a button to this local app.

#### What the receiving side must provide

The project needs its own evaluation administration before the app can offer built-in
submission. At minimum, it must:

- register the evaluation question, accepted packet classes, permitted uses, retention
  period, and consent wording before inviting a contribution;
- quarantine each arrival until its digest and consent receipt validate, without
  treating receipt as proof that every participant understood or agreed;
- restrict and log access to the people running that evaluation;
- preserve the packet and model versions beside every score so a result can be
  reproduced without turning the recording into a general-purpose dataset;
- delete the packet and controlled copies at the promised deadline or after an accepted
  deletion request, then return a deletion receipt; and
- keep derived aggregate results separate from raw meeting content and state the
  withdrawal limit before submission.

An inbox of uploaded files is not this system. Neither is a spreadsheet recording that
someone “said yes.” Until the recipient can execute those controls, the app may prepare
an encrypted export but must not present the project as a governed upload destination.

Success is not the number of recordings collected. It is whether a submitted packet
has enough human reference material to score the registered failure, whether the
recipient can reproduce that score, whether the consent and deletion promises are
checkable, and whether the contribution teaches the product something that private
local evaluations could not.

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
answered it yet. The internal transcript alpha is an app, but it does not implement the
beta surfaces below. Collapsing those states into a severity was the first version's
error — it made an undecided item read as scheduled.

| Gap | Journey | Status |
|---|---|---|
| Retention, deletion, disk accounting | J5 | **Scheduled deletion implemented; first real receipt open; other actions prototyped** — surface K and the encounter state exact deletion consequences, including the independent voice-profile lifecycle |
| A claim in a note has no path to the words behind it | J1 | **Prototyped, repair still open** — `note/1` and surface E carry the claim-to-transcript path, while the current evidence-transport repair fails closed before a new quality result |
| No way to overrule a gate decision | J4 | **Prototyped, not wired** — the specimen restores a turn, marks the note stale, and regenerates; no app performs it on a real capture |
| "Not captured" and "never said" look identical | J1 | **Prototyped, not measured on a capture** — the specimen distinguishes a withheld turn and capture limits; QMSum has no real gate report |
| F has no commitment-organised view | J2 | **Decided** — a `filtered` state on F, not a new surface |
| A note that is present but inadequate | J1, J4 | **Decided** — a passing note's checkable proportion is shown on E and on F's rows, so a thin note is visible before it is opened. Output that fails the run's acceptance checks takes `summary-failed`; a `passed: false` research diagnostic is never rendered as a ready note |
| Export and share have no redaction step | J2 | **Open** — gated turns and room speech would travel with the note |
| The far end's experience | J3 | **Open**, already flagged in the inventory, and the one with legal weight. No convention to inherit — immature across the category |
| No preparation journey | J0 | **Decided** — local read-only calendar via EventKit, `DESIGN.md § Context inputs`. The surface for a brief is still unspecified |
| Who spoke, as opposed to who was invited | J0, J1 | **Open, and possibly unbridgeable.** A calendar gives invitees; the audio gives channels. Nothing in the market bridges it either |
| The note's own section structure was never designed | J1, J2 | **Decided** — sections are a rendering, not the model's output. See below |
| A claim's subject is not extracted | J1 | **Open** — the one thing needed to group a note by what it was about, and no measurement supports asking an 8B model for it yet |
| No governed route for transcript evaluations or consented research material | J6 | **Research candidate, deliberately outside the beta** — local evaluation, packet preparation, transfer consent, and contribution administration are separated above; no network service or upload is authorized |

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
