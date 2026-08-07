# Product definition — local-meeting-notes

This is the definition layer above everything else in `docs/`. It states what the
product is, names the north-star features and functions, grounds each one in the
research that earned it, and records how far each has actually been built. An agent
or a person planning work reads this file first, then descends:

1. This file — what the product is and where every feature stands.
2. [`journeys.md`](./journeys.md) — the reader, the market check, journeys J0–J6.
3. [`screens-and-states.md`](./screens-and-states.md) — the surface inventory (§A–§K).
4. [`vertical-slice.md`](./vertical-slice.md) — the implementation contract: waves,
   build order, human gates. That file, not this one, decides what gets built next;
   its **Build queue** section is the order and the status. Open proposal awaiting an
   operator decision: [`speaker-gate-slice.md`](./speaker-gate-slice.md).
5. [`backlog.md`](./backlog.md) — the decomposition layer: the parity feature set broken
   into epics and into stories with Given/When/Then criteria. It owns neither
   order nor status; it answers what a piece of work *is*, not when it happens.
6. [`teardown.md`](./teardown.md) — the mechanism research underneath all of it.

Written 2026-08-05. Statuses were verified against code on that date, not copied
from prose — and they go stale fastest of anything here. Before repeating a status,
re-verify it against `worker/main.py` (`ALPHA_OPERATIONS`),
`apps/desktop/src-tauri/tests/shell_contract.rs` (registered-command pins), and the
release runbook. This file's own claim of a status is a hypothesis, not evidence.

The app installs as **Yawn** as of 0.3.0 (2026-08-05); the brand is YAWN — Yet
Another Whisper Notetaker — delivered from `yawn-site.pages.dev`. The bundle identifier and
the repository name both remain `local-meeting-notes`, so paths, signing
identity, and doc filenames still carry the old name deliberately.

---

## What this product is

A meeting notetaker that runs entirely on the operator's Mac and is honest about
what it heard. The transcript — not the audio, not the note — is the retained
evidence. Every claim a note makes must cite the verbatim words behind it. What the
tool did not capture is shown as missing rather than papered over. Nothing leaves
the machine.

**The reader:** the operator between back-to-back calls, who will not babysit a
tool and did not open it to admire it. Derived from first principles in
`journeys.md`, then independently confirmed by the market — Granola's headline is
"The AI notepad for back-to-back meetings" (`journeys.md § What the market says`).

**The job:** recover what was decided and what was promised, weeks later, without
having taken notes by hand.

**The design order:** retrieval → commitment → capture (C → B → A,
`journeys.md § Three candidate structures`). Retrieval requirements constrain the
note's shape, the note's shape constrains what capture must preserve. Capture built
first and designed last is how a corpus becomes a junk drawer.

---

## Why these north stars and not others

Three research findings pick them (full accounts in `teardown.md` and
`journeys.md`, with per-claim provenance and fetch dates there):

1. **Local-only is a real differentiator against every commercial product.**
   Granola, Circleback, and Fireflies' bot-free mode all send meeting audio off the
   machine to a cloud transcriber; "not retained" is not "not transmitted"
   (`teardown.md`, primary sources, 2026-07-28).
2. **The corpus is where the felt value is — it is the category's headline feature
   and its paywall.** Retention caps are how Otter and Granola charge
   (`journeys.md`, fetched 2026-07-29).
3. **Two of this product's hardest problems are nobody's solved problem.** No
   product observed links a claim in a summary to the words behind it, and
   correction of AI output is undescribed across the whole category. Those are
   differentiators, not catch-up items — and they matter more here because this
   transcript is measurably partial (30.7% recall on a real speaker-gated take)
   where a cloud competitor's is not.

And one boundary the research fixed: **speaker names come from the meeting UI, not
the audio** — every competitor that shows names gets them from a bot, an extension,
or Accessibility scraping (`teardown.md`, primary). This product accepts Me/Them
from capture topology plus owner-only voice isolation, and does not chase names.

---

## Direction, decided 2026-08-07

**Build feature parity with the category — Granola, Wispr Flow, Circleback, Otter,
Gong — and be local-first where they are cloud-first. Then add remote integrations
and cloud as the next north star.**

This replaces a ten-feature list that scoped the product to capture and custody.
That list was not wrong about what it contained; it was wrong about what it left
out, and three of its non-goals were product choices being enforced as if they were
physical limits. **Overturned by operator decision, 2026-08-07.** The two that
survive are below as invariants, and they survive because they are the
differentiators rather than the fence.

The research this is built on is already in the repository and is not re-derived
here: [`teardown.md`](./teardown.md) disassembles a shipped Wispr Flow binary and
maps the three capture paths, and [`journeys.md § What the market says`](./journeys.md)
compares Granola, Circleback, Otter and Gong from their own documentation. Every
parity row below cites which of those it comes from.

**Almost everything here is Unbuilt, and that is the point of writing it down.** A
roadmap that only lists what exists is a status report. The failure to avoid is a
definition that implies coverage it does not have — in either direction.

---

## Phase 1 — local-first parity

Status vocabulary is unchanged and strict. **Shipped** = proven on real hardware or
by a real receipt. **Registered** = command, capability and UI exist with synthetic
evidence only. **Prototyped** = reviewable outside the app. **Unbuilt** = nothing
exists. **Research** = mechanism not yet chosen.

### A. Capture and identity

| # | Feature | Parity source | Status |
|---|---|---|---|
| A1 | Consent-first local two-leg capture, fresh-process recovery | own | **Shipped** |
| A2 | Operator voice isolation — guided enrollment, measured operating points | own | **Shipped 0.4.0**, unmeasured on live audio |
| A3 | **Named speakers**, not Me/Them | Wispr ships it; Granola/Otter name speakers | **Unbuilt** — was a non-goal, overturned |
| A4 | Long-form ASR: chunked streaming, VAD, timestamp stitching at meeting length | category baseline | **Partial** — dictation-shaped loop, `teardown.md § What is genuinely new` calls this a rewrite |
| A5 | Two-clock drift correction between mic and system legs | own measurement | **Shipped** as detection; correction **Unbuilt** |

**A3 is the reversal that matters.** The old non-goal said names require a bot, UI
scraping or an extension, so Me/Them was "the honest ceiling of local audio." That
is true of *sound alone* and was never the whole method. Wispr combines a calendar
roster, a directory grant, accessibility polling of the meeting window, LLM
inference over address terms, and one-click human correction propagated across the
transcript. Locally we can build the roster leg, the enrollment leg, and the
correction leg today; the meeting-window leg is Phase 2 because it needs an
accessibility grant, and the directory leg is Phase 2 because it needs OAuth.

### B. The note

| # | Feature | Parity source | Status |
|---|---|---|---|
| B1 | Operator-authored live note during the meeting | Granola's core insight | **Shipped 2026-08-06** |
| B2 | AI-enhanced note: summary, outline, highlights, open questions | Gong's one call object; Wispr's summary tab | **Prototyped** — no generator admitted |
| B3 | **Meeting-type templates** | category standard | **Unbuilt** — appears in no prior planning doc |
| B4 | **Auto-titling** | category standard | **Partly shipped 2026-08-07** — a meeting is named by its own first words. The model that would choose *which* words was measured on 2026-08-08 and refused at 5 of 10 against a registered 6–9; the category's abstractive titles remain unbuilt on purpose |
| B5 | Evidence-linked claims: every claim cites verbatim turns | **nobody does this** | **Prototyped** — the differentiator |
| B6 | Honest incompleteness: "not captured" ≠ "never said" | own | **Prototyped** |
| B7 | Correction that changes the note; restore a withheld turn, regenerate | correction is undescribed everywhere | **Registered** for restore |

### C. Commitments and handoff

| # | Feature | Parity source | Status |
|---|---|---|---|
| C1 | **Action items with owner and status — a real task list** | Wispr ships a `Todos` table with open/closed and a tasks tab | **Unbuilt** — was a non-goal, overturned |
| C2 | Commitment view across meetings | own J2 | **Unbuilt** |
| C3 | Export and share a note as a document | Wispr's docs tab | **Unbuilt**, gated on the redaction decision |

**C1 is the second reversal.** "Not a task manager" refused the checkbox on the
grounds that owning follow-through gives the operator two task systems. Three of six
colleagues surveyed asked for exactly this, and Wispr shipped it. The concern was
real and the remedy was wrong: build the task list, and let it export rather than
becoming the system of record.

### D. Retrieval and memory — the category's headline

| # | Feature | Parity source | Status |
|---|---|---|---|
| D1 | **Ask a question across every meeting, get an answer with citations** | Granola ships this on the *free* tier; Circleback's headline | **Unbuilt** — one unproven story today |
| D2 | Search: exact plus semantic, over transcript and metadata | Otter free vs Pro | **Registered** for exact |
| D3 | Filters — people, date range, keywords, titles | Gong documents all four | **Three of four shipped 2026-08-08** — folder, capture-date range and meeting-name, over the list and over search. **People is blocked on A3**: attribution is Me/Them and the contract records that named participants are absent |
| D4 | Saved searches and streams that collect future matching meetings | Gong | **Unbuilt** |
| D5 | Land on a claim, not a document | nobody does this | **Unbuilt**, needs B5 |

**D1 was mis-sequenced and this corrects it.** `journeys.md` records that retrieval
across the corpus is "the category's headline feature, not a late-stage nicety" and
that history is the primary paywall in both Granola and Otter — the strongest
available signal that the corpus is where the felt value is. It was decomposed as
four stories of exact search plus one unproven story for the actual headline.

### E. Organisation and surfaces

| # | Feature | Parity source | Status |
|---|---|---|---|
| E1 | Folders, and channels or workspaces | Granola and Otter both ship folders; Otter adds channels | **Shipped 2026-08-08** for folders — create, file, unfile and filter by one, from the meetings list. Renaming and deleting a folder are registered commands with no surface; channels are unbuilt |
| E2 | One meeting object with sibling views: transcript, summary, notes, tasks, docs | Gong's call page; Wispr's six tabs | **Partial** |
| E3 | Preparation brief before the meeting | Wispr's preread tab | **Unbuilt** |
| E4 | A shell that never lies at menubar size | own | **Shipped** |
| E5 | Retention with named auto-deletion periods | Granola enterprise vocabulary | **Shipped** automatic; periods **Unbuilt** |
| E6 | Local store and retrieval at corpus scale | `teardown.md` names SQLite | **Partial** — the derived SQLite index landed 2026-08-07 and is written whenever the library is opened. **Nothing reads it yet**: the app builds the full projection first, so filters are answered from memory, and the index earns a reader when US-13.6 stops the scan being the entry point |

---

## Phase 2 — the next north star: remote and cloud

Not deferred vaguely. These are the features that need a network, and each names
what it unblocks in Phase 1.

| # | Feature | Unblocks |
|---|---|---|
| P1 | Calendar integration — attendee roster, meeting detection | A3's roster leg, E3's preread |
| P2 | Directory grant for org-wide name resolution | A3 at Wispr's fidelity |
| P3 | Meeting-window reading for live active-speaker attribution | A3's third signal |
| P4 | Cloud sync and multi-device | corpus continuity |
| P5 | Push to Slack, Notion, CRM | C3 beyond a local file |
| P6 | Shared workspaces and team retrieval | E1 beyond one operator |

**Local-first is a Phase 1 default and a Phase 2 guarantee, not a prohibition.**
Every Phase 2 feature ships with the egress visible and refusable. Six of six
colleagues surveyed refused unprompted sharing and asked for control of egress —
locality is the mechanism, control is the requirement.

---

## Invariants — the two that survive

Not gates on scope. Both are the reasons to use this instead of Granola.

- **Evidence is never decoration.** A claim without a resolvable citation, or a
  "verified" state nothing checked, is the failure the category ships everywhere.
  Re-tested 2026-08-06 against a shipped Wispr binary: its meeting detail is six
  sibling tabs and a searchable transcript drawer, and an enumeration of its 411
  `hub_*` interface keys finds no key naming a jump from a claim to its source turn.
  Adjacency is not citation.
- **Nothing leaves the Mac without the operator seeing it leave.** Phase 1 has no
  network path for meeting content. Phase 2 adds paths that are visible and
  refusable per destination.

**Verification discipline is not a scope gate and is not listed as a non-goal.**
Checking a claim against source before asserting it has never blocked a feature; on
2026-08-07 it caught three wrong numbers in a published document. It stays.

---

## How planning uses this file

`vertical-slice.md` remains the implementation contract; its build queue decides
sequencing and is the operational truth. This file answers the question one level
up: **what is this product when it is finished, and how far from that is it now?**

**This file does not gate work, and the previous version of this paragraph did.** It
read: *does a proposed piece of work serve one of the ten features, without crossing
a non-goal? If it does not, either the proposal is wrong or this definition is.*
That sentence turned an incomplete feature list into a fence, and the fence held for
weeks — three parity capabilities were refused as non-goals and several more were
never written down at all, while the queue reported itself converged.

The rule now runs the other way. **A capability the category ships and this product
lacks is a gap in this file until proven otherwise, not a proposal to be justified
against it.** If work does not map to a row above, the likely fault is the row list,
and the fix is to add the row with its parity source. Amendments are still dated and
in place; they are just no longer the price of admission for building something
obvious.

---

## Provenance

Checked for this file, 2026-08-05: `teardown.md` and `journeys.md` read in full;
statuses verified mechanically against `worker/main.py` `ALPHA_OPERATIONS` /
`BOUNDARY_OPERATIONS`, the registered-command pins in
`apps/desktop/src-tauri/tests/shell_contract.rs`, and the 0.2.2 release record in
`distribution-runbook.md`. Market claims carry the original fetch dates recorded in
their source docs (2026-07-28 mechanism, 2026-07-29/31 product pages); nothing was
re-fetched, so those claims age from those dates, not from this file's. The
colleague survey remains n=2 and decides nothing.
