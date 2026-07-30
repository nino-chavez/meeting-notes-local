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

So J0 is blocked on a capability decision, not a design one: whether this tool reads the
operator's calendar. That is a genuine fork with consequences in both directions — a
calendar grant is a large new permission and a large new surface for a local-first tool
whose entire pitch is that nothing leaves the machine, and without it the product can
never do the one thing the category's leader leads with. It is recorded here undecided
rather than resolved in passing.

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

Crosses **B → A → C → D → E**, fully inventoried, and the one part already built.

Two beats worth restating as journey rather than state. **Consent** is the highest-
stakes interaction in the product and the only one with legal weight in roughly a
dozen US states. And **degradation** is a beat, not an error: a leg dies mid-meeting,
the operator is in the meeting, and the only acceptable behaviour is to keep the good
leg and be visibly honest at menubar size.

### J4 — "This note is wrong" (correction)

The gate marked a colleague's speech as not-the-operator. The operator disagrees.

**The code already promises this journey and the product cannot honour it.**
`transcript.json` keeps every gated turn with its score precisely so the decision can
be overruled, and `dual_capture.py` says so in as many words — and there is no surface
anywhere that lets anyone overrule it. A capability that exists in the substrate and
nowhere in the interface is not a feature, it is a claim.

Minimum: the gated turns are visible where the note is read, distinguishable, and
restorable — after which the note is regenerated, because a correction that does not
change the note corrects nothing.

### J5 — "How long is this keeping recordings of other people?" (retention)

**Nothing in this repository designs this, and it is the highest-stakes gap in the
product.**

Every capture writes two WAVs and a transcript of a conversation involving people who
are not the operator. There is no retention policy, no deletion surface, no disk
accounting, and no statement of any of it. The audio is the most sensitive artifact
the product creates, and its lifecycle is currently "accumulates until the disk fills."

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

**Consequences, which are real work and not corollaries.** The summary contract has to
emit citations, which changes the note format — `notes/summarize.py` currently emits
prose with no reference back into the transcript. Surface E has to render a claim and
its evidence together. And K's `audio-released` becomes a mild state rather than a
destructive one: the note keeps its evidence, and only the ability to *hear* it is
gone.

That the retrieval journey turned out to change the note format is the C → B → A
ordering doing exactly what it was chosen for.

---

## What the inventory is missing, checked against the journeys

Derived by walking each journey against `screens-and-states.md`, not by inspection.

**Status means design status, never implementation.** Nothing in this table is built.
*Specified* means a surface and its states exist in the inventory; *decided* means the
design question is answered here and the surface work follows; *open* means nobody has
answered it yet. Collapsing those three into a severity was the first version's error —
it made an undecided item read as scheduled.

| Gap | Journey | Status |
|---|---|---|
| Retention, deletion, disk accounting | J5 | **Specified** — surface K, added from this walk. Was the highest-stakes gap: an undesigned lifecycle for other people's voices |
| A claim in a note has no path to the words behind it | J1 | **Decided** — the note cites the transcript. Requires a change to the summary contract and to E, neither of which exists |
| No way to overrule a gate decision | J4 | **Open, and the code already promises it.** `transcript.json` keeps every gated turn so it can be overruled and no surface can |
| "Not captured" and "never said" look identical | J1 | **Open** — the artifact holds the recall figures and the gate's report, and shows neither |
| F has no commitment-organised view | J2 | **Decided** — a `filtered` state on F, not a new surface |
| A note that is present but inadequate | J1, J4 | **Open** — E's `summary-failed` covers absent, not thin |
| Export and share have no redaction step | J2 | **Open** — gated turns and room speech would travel with the note |
| The far end's experience | J3 | **Open**, already flagged in the inventory, and the one with legal weight. No convention to inherit — immature across the category |
| No preparation journey, and no calendar to build one on | J0 | **Blocked on a capability decision**, not a design one. Reading the operator's calendar is a large new permission for a local-first tool, and without it the product cannot do what the category leader leads with |
| No notion of a counterparty | J0, J1 | **Open** — "what did we discuss last time" needs to know who "we" are, and audio never supplies a name |

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
