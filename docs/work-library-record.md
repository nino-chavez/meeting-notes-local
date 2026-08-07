---
status: bounded-beta-direction
date: 2026-08-07
supersedes: 2026-08-02 record (same path, archived at archive/work-library-publication)
---

# Local Meeting Notes: what the beta honestly supports

## The decision

Treat this as a private, headphones-first beta. It records a meeting on your own
Mac, transcribes it there, and writes a note there. Nothing leaves the machine.

Do not present it as a general meeting recorder. Do not claim it reliably tells
speakers apart in a room, on laptop speakers, or when people talk over each other.

The next thing that would move this forward is an ordinary headphone meeting with
the voice gate on, followed by a person reading the note and saying whether it was
useful. That has not happened yet.

## What it is

A macOS app that captures the microphone and the system audio as two separate
tracks, then turns them into a note without sending anything to a server.

Three properties are the point, and each is enforced rather than promised:

- **It stays local.** No network path exists for meeting content.
- **It refuses rather than guesses.** When the two tracks bleed into each other,
  it drops speaker labels instead of inventing a plausible speaker history.
- **It keeps its receipts.** Capture integrity, timing drift between the two
  tracks, acoustic bleed, retention, and deletion each leave a record you can
  check afterward.

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
automatic deletion, a consented run on real hardware, and a clean transfer, all
bound to a single unchanged build. A search of the repository on 2026-08-06 found
no filled instance for any version. So the activity is done several times over and
the evidence chain is empty. Versions 0.2.2, 0.3.0, 0.3.1, and 0.4.0 each owe one,
and because one version's evidence does not carry to the next, each restarts it.

The fix is not another install. It is someone writing down a run they are already
doing.

## What the research changed

Three findings reshaped the product, and all three are measured rather than argued.

**1. Laptop speakers destroy the free speaker split.** The microphone hears the far
end of the call and duplicates their words onto your track. The app can drop the
unsafe labels. It cannot recover a trustworthy speaker history from that recording.
*What it means:* headphones are a supported-hardware boundary, not a suggestion.

**2. Other voices in the room change the note.** In the long measured capture,
nearby room speech entered the microphone track and changed which real action items
survived into the summary — even though the room's subject never appeared in the
note itself. *What it means:* a clean-looking note is not evidence of a clean
capture.

**3. A voice profile alone is not enough.** The threshold needs both measured
speech from you and permitted speech that is not you. Echo and overlap can still
reject your own voice. *What it means:* calibration is a deliberate setup step with
a visible error cost, not a background convenience.

The note evaluation added two more. Example text inside a prompt can reappear as a
fabricated decision. Rules written to make the model cautious can delete real
actions. Both are product defects even when the note names no fake person and no
fake number.

## Where the build stands

Ten features define the product. Three of them have work that is buildable right
now with no decision from anyone:

| Feature | Next build |
|---|---|
| Shell that never lies | A signed preview bundle, so the two permission paths can execute at all |
| Audio has a stated lifetime | Nothing — whole-meeting deletion landed 2026-08-07, core and shell |
| Evidence-linked notes | Fix the runtime pin, which currently cannot be rebuilt |

Everything else waits on one of three things: a decision only a person can make
(consent wording, release admission, whether a note was useful), evidence that does
not exist yet, or a scope boundary drawn on purpose.

That list is short, and the shortness is the finding rather than a gap in it.

**One defect is worth naming.** The note pipeline pins its runtime by a digest that
the installer writes, and that digest changes with the installer and with byte
compilation. Three environments on one machine, matching Python and matching package
versions, reproduced 9 of 9 on the wheel's own metadata and **1 of 9** on the
installer-written record. Until that pin moves, no further intervention on the note
pipeline can be verified. It is a defect in the pin, not a decision waiting on
anyone.

## What is proven, and what proven means here

Every story in the backlog carries a line naming the check that proves it, in four
terms:

- **Pinned** — a named test fails if the behaviour changes.
- **Exercised** — the path runs, but nothing pins the outcome.
- **Receipted** — a receipt from a real run exists, bound to the exact bytes.
- **Unproven** — nothing checks it. Fifteen of the seventy-five stories say this,
  out loud, because an absent line reads as an oversight and a stated one reads as
  a fact.

Counted 2026-08-07: 51 Pinned, 3 Receipted, 15 Unproven — 69 lines across 75
stories. The six with no line are all waiting on a decision rather than on build
work, so there is nothing yet for a check to prove.

The distinction that matters: **a story can be fully Pinned and still unproven as a
product capability.** What is pinned is behaviour on fixtures. Whether a real
meeting produced a note a person found useful is a different claim, and nothing in
this repository can settle it.

## Evidence boundary

Measured evidence exists for capture, bleed, drift, the voice gate, echo, and note
generation.

There is still no ordinary real meeting in which the operator's own recorded audio
produced a note a human judged useful. No test, waveform, token count, or generated
summary supplies that judgment.

Meeting content — audio, transcripts, note text, voice profiles — never enters the
repository by design. Its absence from Git therefore proves nothing about whether a
run happened; run and closure receipts live outside Git deliberately.

Consent wording, Apple release admission, and broader supported hardware each remain
a separate human decision, and none has been made.

## What would change this decision

- A headphone meeting whose note a person reads and calls useful. That widens the
  supported envelope.
- A note the person calls wrong in a way the receipts did not predict. That narrows
  it, and would make the receipts themselves the thing to fix.
- The runtime pin proving unfixable. That would end the evidence-linked-notes
  feature rather than delay it.

## What was checked to write this

Release state and the signing result come from `docs/distribution-runbook.md`. Build
order and the blocked items come from the Build queue in `docs/vertical-slice.md`,
written 2026-08-07. Feature definitions come from `docs/product-definition.md`.
Story-level proof state comes from `docs/backlog.md` — twelve epics, seventy-five
stories.

The measured findings come from `spike/RESULTS.md` and `notes/EVAL.md`, both of
which are published alongside this record.

Not checked: nothing in this record was re-derived from source code today. Statuses
in any document here are hypotheses until re-checked against `worker/main.py`,
`apps/desktop/src-tauri/tests/shell_contract.rs`, and the runbook.
