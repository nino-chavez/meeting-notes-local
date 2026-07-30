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

Five, ordered as designed rather than as experienced. Each names the surfaces it
crosses so the inventory can be checked against it.

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

End of day or week. Crosses **F → E**, and needs an aggregation across notes that no
surface provides.

The load-bearing constraint is that this must not become a task manager. The
resolution: the tool answers *what was said*, and hands off — an export, a copy, a
link into whatever the operator already uses. Owning the closed state means owning
follow-up, and that is a different product.

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

## What the inventory is missing, checked against the journeys

Derived by walking each journey against `screens-and-states.md`, not by inspection.

| Gap | Journey | Severity |
|---|---|---|
| No retention, deletion, or disk-accounting surface | J5 | **Highest** — undesigned lifecycle for other people's voices |
| No way to overrule a gate decision | J4 | **High** — the code documents this capability as existing |
| No path from a claim in a note to the words behind it | J1 | **High** — the only defence against a confident partial note |
| "Not captured" and "never said" are indistinguishable | J1 | **High** — the artifact knows the difference and does not show it |
| No cross-meeting aggregation | J2 | Medium — the end-of-week question has no surface |
| No surface for a note that is present but inadequate | J1, J4 | Medium — `summary-failed` covers absent, not thin |
| Export/share has no redaction step | J2 | Medium — gated turns and room speech would travel |
| The far end's experience is entirely undesigned | J3 | Open decision, already flagged, legal weight |

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
