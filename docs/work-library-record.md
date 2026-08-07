---
status: parity-direction
date: 2026-08-07
supersedes: the 2026-08-07 bounded-beta-direction record at this path (archived at archive/work-library-publication)
---

# Local Meeting Notes: build the category, locally

## The decision

Build what Granola, Wispr Flow, Circleback, Otter and Gong already ship, and run all
of it on your own Mac. Remote and cloud features come after, as a stated next phase
rather than an omission.

That reverses the previous version of this record, which drew a narrow boundary
around private capture and treated the rest of the category as out of scope. The
boundary was wrong, and the way it went wrong is the more useful finding.

**The prior record reported the build queue nearly empty while the product was a
fraction of what it was meant to be.** Both governing documents required new work to
justify itself against a ten-item feature list. That turned an incomplete list into a
fence. Three real capabilities were refused as non-goals; several more were never
written down at all. Nothing in the process was broken — the list was just short, and
nobody was checking the list against the category.

The rule now runs the other way. **A capability the category ships and this product
lacks is a gap in the definition until proven otherwise.** Work that does not map to
a row is evidence the rows are wrong.

Two commitments survive as reasons to choose this over Granola, not as limits on it:

- **A claim cites the words it came from.** An enumeration of a shipped competitor's
  interface strings found nothing that jumps from a summary line to the moment in the
  conversation it rests on. Nobody in the category does this.
- **Nothing leaves the Mac without you seeing it leave.** In phase one that is the
  default because there is no network path. In phase two it becomes a guarantee with
  a visible, refusable choice per destination.

## What it is

A macOS app that captures your microphone and the system audio as two separate
tracks, transcribes them, and writes a note — without sending anything to a server.

The destination is the full working surface of a modern notetaker: a searchable
corpus you can ask questions of, notes shaped by meeting type, action items with
owners, named speakers, folders. Most of that is not built. The definition document
lists each capability beside the competitor that ships it, so the gap is legible
rather than implied.

## Where the build actually stands

Of twenty-six capabilities in phase one: six ship today, three are partly built,
three exist as prototypes that have not passed admission, two are registered
behind the interface, and twelve are not started. Phase two adds six more, each
naming what it unblocks.

Read that as a roadmap with an honest origin, not as a progress report. It was
written by comparing this product against shipped competitors, so the twelve
unstarted rows are the point of the exercise rather than a failure inside it.

The queue is ordered by dependency and by where the value is, and it leads with the
corpus, because nothing above it works without one.

| Wave | What it delivers |
|---|---|
| 1 | The corpus: a durable store, titles, folders, filters, semantic search, then answering a question across every meeting |
| 2 | The note becomes worth reading: templates, enhanced summaries, action items, a commitment view |
| 3 | Identity: named speakers, one-click correction, and speech recognition that holds up at meeting length |
| 4 | Phase two opens with calendar |

**The store landed on 2026-08-07.** It is a SQLite index over the meeting corpus, and
your meetings do not live in it — every row is derived from files that remain the
authority, and a test deletes the database, rebuilds it from those files alone, and
demands an identical content digest.

**Meetings got names the same day.** Until then every row in the library read
`Untitled meeting`, because the only place a title could come from was a file nothing
in the product could write. A meeting is now named by the first thing said in it that
is long enough to identify it — a quotation from the transcript, not a phrase written
about it, so the words can be read back where they were said. A title you type
outranks it.

**We tested whether a small local model could pick a better sentence, and it could
not.** Competing products hand the transcript to a model and print whatever phrase it
writes back. We tried something narrower: let the model choose *which* sentence to
quote, and never let it supply words of its own. Before running it we wrote down what
would count as working — agreeing with a human's choice on 6 to 10 of ten test
meetings — so the answer could not be argued afterwards. It got 5, three times in a
row, identically. So the simple rule stands and nothing was added to the app.

Two things came out of it worth keeping. The model does beat guessing, so it is not
useless, just not good enough by the standard we set in advance. And it never once
said "no sentence here names this meeting" — not on any of thirty tries, including
the test built entirely of small talk, where it confidently picked "Yes I can hear you
perfectly well." A tool that cannot say *I don't know* is a tool you have to check.

**And on 2026-08-08 you can name one yourself.** The file holding folder names and
the titles you type could be read but never written — that was the original reason
every meeting said `Untitled meeting`, and it survived the automatic naming above,
because a title you chose is supposed to outrank one taken from the transcript and
there was no way to choose one. Now there is: name a meeting from the list, or leave
the box empty to go back to its opening line.

Deleting a meeting now also takes its name and folder with it, in that order, before
the recording itself goes. That sounds like tidying and is not. The app refuses to
trust the whole file if it mentions a meeting that no longer exists, so one leftover
name would not have cost you that meeting's title — it would have hidden every title
and folder you had set, all at once.

Folders themselves are half-built and said so rather than implied: the app knows how
to make, rename, delete and fill them, and there is no screen for it yet.

## What shipped

**Version 0.4.0, cut 2026-08-05**, signed and notarized, built at commit `331c9e9`.
Signed-release verification returned PASS.

The speaker gate ships from 0.4.0 onward. Before that, an installed copy with no
voice profile had no gate at all.

**One thing is not closed, and it is a record rather than an activity.** Installing
on another Mac has happened repeatedly — the app is distributed to a small cohort,
and a cohort member's report is what produced 0.3.1's one change. Gatekeeper,
notarization, and stapling pass on every recorded build.

What has never been written is the **closure receipt**: one short record covering
automatic deletion, a consented run on real hardware, and a clean transfer, all bound
to a single unchanged build. A search of the repository on 2026-08-06 found no filled
instance for any version. So the activity is done several times over and the evidence
chain is empty. Versions 0.2.2, 0.3.0, 0.3.1, and 0.4.0 each owe one, and because one
version's evidence does not carry to the next, each restarts it.

The fix is not another install. It is someone writing down a run they are already
doing.

## What the research changed

Three findings reshaped the product, and all three are measured rather than argued.

**1. Laptop speakers destroy the free speaker split.** The microphone hears the far
end of the call and duplicates their words onto your track. The app can drop the
unsafe labels. It cannot recover a trustworthy speaker history from that recording.
*What it means:* headphones are a supported-hardware boundary today. It is a boundary
on the current mechanism, not on the product — named speakers are queued work, and
the method that gets there is a roster and a correction control, not better audio.

**2. Other voices in the room change the note.** In the long measured capture,
nearby room speech entered the microphone track and changed which real action items
survived into the summary — even though the room's subject never appeared in the note
itself. *What it means:* a clean-looking note is not evidence of a clean capture.

**3. A voice profile alone is not enough.** The threshold needs both measured speech
from you and permitted speech that is not you. Echo and overlap can still reject your
own voice. *What it means:* calibration is a deliberate setup step with a visible
error cost, not a background convenience.

The note evaluation added two more. Example text inside a prompt can reappear as a
fabricated decision. Rules written to make the model cautious can delete real
actions. Both are product defects even when the note names no fake person and no fake
number.

**A fourth arrived on 2026-08-07, and it decided the current wave.** Searching the
library reads every meeting from disk. Measured against a synthetic corpus, that
costs about nine-tenths of a second at a thousand meetings and three seconds at two
thousand. But the number that mattered was not a speed: **searching for a common word
is refused outright at a single meeting**, because the reader will not return part of
an answer and call it the library. Exact search could never have answered for a word
a person would actually type, at any corpus size, and no amount of speed would have
changed it.

## What is proven, and what proven means here

Every story in the backlog carries a line naming the check that proves it, in four
terms:

- **Pinned** — a named test fails if the behaviour changes.
- **Exercised** — the path runs, but nothing pins the outcome.
- **Receipted** — a receipt from a real run exists, bound to the exact bytes.
- **Unproven** — nothing checks it, stated out loud, because an absent line reads as
  an oversight and a stated one reads as a fact.

Counted 2026-08-07, after the corpus store landed: 82 stories carry 76 validation
lines. Fifty-six name Pinned, twelve name Receipted, sixteen name Unproven, and
fourteen lines name two terms because a story can be pinned at the surface and
receipted by a release. The six stories with no line are all waiting on a decision
rather than on build work, so there is nothing yet for a check to prove.

The distinction that matters: **a story can be fully Pinned and still unproven as a
product capability.** What is pinned is behaviour on fixtures. Whether a real meeting
produced a note a person found useful is a different claim, and nothing in this
repository can settle it.

**A worked example of that gap, from the same day.** The corpus store shipped with a
test that deletes its database and rebuilds it from files, which is the right check.
The first version of that test hashed a hand-written list of columns, so a column
holding invented data — precisely what the test existed to catch — would have passed
it. A second check documented a privacy decision it could not actually observe. Both
were named correctly and covered nothing. The habit that catches this is asking what
a check reads, not what it is called.

## Evidence boundary

Measured evidence exists for capture, bleed, drift, the voice gate, echo, note
generation, and now corpus scale.

There is still no ordinary real meeting in which the operator's own recorded audio
produced a note a human judged useful. No test, waveform, token count, or generated
summary supplies that judgment.

Meeting content — audio, transcripts, note text, voice profiles — never enters the
repository by design. Its absence from Git therefore proves nothing about whether a
run happened; run and closure receipts live outside Git deliberately.

Consent wording, Apple release admission, and broader supported hardware each remain
a separate human decision, and none has been made.

## What would change this decision

- A headphone meeting whose note a person reads and calls useful. That is still the
  unmet proof, and it does not get easier as the surface grows.
- A note the person calls wrong in a way the receipts did not predict. That would
  make the receipts themselves the thing to fix.
- Discovering that a queued capability cannot be built locally at acceptable quality.
  That moves the row into phase two rather than deleting it — the failure mode this
  record exists to correct was deleting rows.

## What was checked to write this

Feature definitions, phase membership and per-capability status come from
`docs/product-definition.md`. Wave order comes from the Build queue in
`docs/vertical-slice.md`. Release state and the signing result come from
`docs/distribution-runbook.md`. The measured findings come from `spike/RESULTS.md`,
`notes/EVAL.md`, and `docs/corpus-scan-measurement.json`, all published alongside
this record.

Every count in this record was re-derived by counting the source documents on
2026-08-07 rather than by repeating an earlier figure. The previous version of this
record said seventy-five stories and twelve epics; both had moved.

Not checked: no status here was re-derived from source code today. Statuses in any
document are hypotheses until re-checked against `worker/main.py`,
`apps/desktop/src-tauri/tests/shell_contract.rs`, and the runbook.
