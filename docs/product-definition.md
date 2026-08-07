# Product definition — local-meeting-notes

This is the definition layer above everything else in `docs/`. It states what the
product is, names the north-star features and functions, grounds each one in the
research that earned it, and records how far each has actually been built. An agent
or a person planning work reads this file first, then descends:

1. This file — what the product is and where every feature stands.
2. [`journeys.md`](./journeys.md) — the reader, the market check, journeys J0–J6.
3. [`screens-and-states.md`](./screens-and-states.md) — the surface inventory (§A–§K).
4. [`vertical-slice.md`](./vertical-slice.md) — the implementation contract: waves,
   build order, human gates. That file, not this one, decides what gets built next.
   Open proposal awaiting an operator decision:
   [`speaker-gate-slice.md`](./speaker-gate-slice.md).
5. [`teardown.md`](./teardown.md) — the mechanism research underneath all of it.

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

## North-star features and functions

Status vocabulary, inherited from `journeys.md` and kept strict: **Shipped** =
proven on real hardware or by a real receipt. **Registered** = command, capability,
and UI exist in the internal-alpha build with synthetic evidence only.
**Prototyped** = reviewable outside the app, touches no real product state.
**Decided** = the design question is answered; the build follows. **Open** = nobody
has answered it yet. **Research candidate** = deliberately outside the beta.

| # | Feature | Journey | Surface | Status (verified 2026-08-06) |
|---|---|---|---|---|
| 1 | Consent-first local two-leg capture | J3 | §B §C | **Shipped** — real-hardware capture, local transcription, fresh-process recovery in the signed internal alpha |
| 2 | Operator voice isolation: guided enrollment, measured operating points, owner-only profile | J3 J5 | §I | **Registered** end to end as of 2026-08-05 — enrollment (sittings, derivation, choices, build, publication) plus the gate itself, which now runs over the microphone leg, marks non-operator turns, and records what it did in the transcript's `voiceprint` field. An installed profile the runtime cannot apply refuses the transcript rather than writing one that reads as checked; see `docs/speaker-gate-slice.md`. **Shipped in 0.4.0** (2026-08-05), the first image where an enrolled profile changes a transcript. Still unmeasured on live meeting audio: the threshold is enrolment-derived, and the app now says so on every checked transcript |
| 3 | Transcript is the retained evidence; audio has a stated lifetime | J1×J5 | §K | **Shipped** for automatic audio deletion (real `audio-deletion/1` receipt, 2026-08-02); **Registered** per-meeting audio deletion and retention overview; whole-meeting deletion and policy wording **Open** (human gate) |
| 4 | Evidence-linked notes: typed claims, each citing verbatim turns | J1 J2 | §E | **Prototyped** (`note/1` contract, claim `type` recovered, citation checker repaired); **no note generator is admitted** and `note.inspect` stays boundary-lane. Both small-model rejections were response *shape*, so neither measured comprehension. Under structure-constrained decoding the same model, prompt, and parser produced an accepted candidate on both probe fixtures at the same 181 generated tokens the rejected 2026-08-02 run recorded — one byte of that response had been invalid JSON. The registered 12-fixture matrix then ran and **failed 9 of 12** — but not on comprehension: eight failures are one behaviour, the model emitting a well-formed fragment identifier in the format of the *other* identifier the request carries, on nine fixtures but not the tenth, for reasons three checked explanations all fail to account for. The harness enforces three rules it never states and enumerates two of three identifier fields, so the decisive field is measured unfairly; both are unfixed and each needs preregistering. Human semantic adjudication is untouched; see `notes/MLX_NOTE_ADMISSION.md` |
| 5 | Honest incompleteness: "not captured" ≠ "never said", checkable proportion visible before opening | J1 | §E §F | **Prototyped**, not yet measured on a real gated capture |
| 6 | Correction that changes the note: restore a withheld turn, note goes stale, regeneration required | J4 | §E | **Registered (0.2.2)** for restoration, and reachable on a shipped image from 0.4.0 — until the gate was wired in, nothing withheld a turn, so restoration was a correct implementation of an operation that could never have an input. **Corrected 2026-08-06: it is no longer reachable from Meetings only.** The screen shown right after a recording now carries the control too, because the gate's worst failure is a colleague cut from a record that cannot be re-made and that remedy is worth less the longer it waits — the navigation was the delay. Restoring publishes a new current transcript, so that screen also rebuilds its projection in place (`refresh_current_transcript`); without it a second restore would name a digest that had moved and be refused as a changed source. Regeneration stays deliberately unregistered until a generator passes admission |
| 7 | Retrieval that enters with a question and lands on a claim | J1 | §F | **Registered** — library snapshot, search over transcripts and metadata, open-to-evidence/transcript/note; claim-level landing waits on feature 4 |
| 8 | Commitment view that hands off instead of managing tasks | J2 | §F | **Decided** — a `filtered` state on F, terminal action is export, never a checkbox; unbuilt |
| 9 | Preparation brief before the meeting | J0 | none yet | **Decided** — local read-only calendar via EventKit (`DESIGN.md § Context inputs`); unbuilt. The counterparty half — who spoke vs who was invited — stays **Open, possibly unbridgeable** *for local audio*. The clause "and the market has not bridged it either" was **falsified 2026-08-06** and is corrected here: Wispr Flow ships named speakers by combining a calendar roster, an OAuth grant reaching the org's full Workspace directory, accessibility-tree polling of Zoom and Teams for the active-speaker indicator, LLM inference over address terms, and a one-click human correction applied across the transcript. Nobody bridged it from sound; one vendor made the failure cheap to repair. See `teardown.md § Wispr Flow, disassembled` |
| 10 | A shell that never lies at menubar size: degradation is a beat, not an error | J3 | §A §C §H §J | **Shipped (0.2.2)** — tray truth table, close-to-tray, startup-failure honesty. **§H first run joined 2026-08-06** as **Registered**: six of eight states over a signed, digest-verified permission probe, deriving the step from a live measurement rather than a stored completion flag, and keeping "we could not ask" a different screen from "you said no". Neither request path has executed anywhere — running one outside the signed bundle answers about the wrong binary — so only the status read has evidence |

The dependency to keep in view: features 4, 5, 6, and 7 converge on the same
artifact. The admitted note generator is the single biggest unlock in the table —
it turns restoration into regeneration, search results into claims, and the
proportion figure into something a real capture produces. It is also gated on
human semantic adjudication (`vertical-slice.md` wave D), so no amount of
autonomous work closes it alone.

---

## What this product must not become

Non-goals with the same authority as the features. Each earned its place in the
research; violating one needs an amendment here first, not a quiet exception.

- **Not a task manager.** The moment a commitment view offers a checkbox, the tool
  owns follow-through and the operator has two task systems (`journeys.md` J2).
  Export and hand off, always. *Counterevidence recorded 2026-08-06, and the non-goal
  stands.* Wispr Flow shipped the checkbox — a `Todos` table with an open/closed
  status, a tasks tab, a `meetingId` key — and "tracking action items" is one of the
  four frustrations its own onboarding offers. Three of six colleagues surveyed named
  capturing actions and owners as a job, and all six wanted action items in the note.
  None of that reaches the reason for the non-goal, which is about *owning
  follow-through*, not about extracting commitments.
- **Not a named-speaker product.** Names would require a bot, UI scraping, or an
  extension — every path the teardown rejected. Me/Them plus operator isolation is
  the honest ceiling of local audio. *Confirmed 2026-08-06 by disassembling the
  newest entrant:* Wispr Flow's speaker naming runs through a helper bundle
  identified as `…accessibility-mac-app`, carrying `AXUIElementCopyAttributeValue`
  and per-platform `ZoomSpeakerStrategy` / `TeamsSpeakerStrategy` classes that poll
  the meeting window's active-speaker indicator. That is UI scraping, exactly as the
  teardown predicted. The enumeration above is incomplete — it omits the cloud
  directory grant and the LLM address-term inference Wispr also uses — and its
  conclusion is unchanged and better supported.
- **Nothing leaves the Mac.** No cloud ASR, no telemetry, no built-in upload. J6
  (evaluation contribution) stays a research candidate, export-first, with consent
  machinery specified before any transfer path exists. *Note for messaging, not for
  the boundary (2026-08-06):* six of six colleagues surveyed refused unprompted
  sharing and one named local-only processing. What they asked for is control of
  egress; locality is the mechanism that guarantees it. The boundary does not move —
  the way it is described should lead with the guarantee. For contrast, Wispr Flow's
  own copy states its notetaker "requires" cloud sync to process transcriptions, and
  gates the retention control behind it.
- **No invented content on judged surfaces.** Prototypes populate from the real
  corpus or labelled specimens carrying published measurements — never fabricated
  meetings (`journeys.md § What to prototype`).
- **The note's evidence is never decoration.** A claim without its citation, or a
  "verified" state nothing checked, is the failure the category ships everywhere;
  it is the one thing this product exists to not do.

---

## How planning uses this file

`vertical-slice.md` remains the implementation contract; its waves and human gates
decide sequencing, and its Status section is the operational truth. This file
answers the question one level up: *does a proposed piece of work serve one of the
ten features for the named reader, without crossing a non-goal?* If it does not,
either the proposal is wrong or this definition is — and the fix is a dated
amendment here, in place, the way `screens-and-states.md` amends.

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
