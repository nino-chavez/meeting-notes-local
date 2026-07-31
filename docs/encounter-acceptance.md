# Operator encounter acceptance

## Status

The input, approval contract, and interaction-only renderer now exist. An owner-only
private packet has satisfied the capture and digest-bound content prerequisites. No
meeting content, response detail, or approval packet is stored in Git. The encounter
still has **not passed**: the missing gate is a cold operator review of the rendered
interaction.

This gate approves an interaction design. It does not prove that capture,
automatic extraction, correction, deletion, startup recovery, or packaging works
in an application. The executable application skeleton remains blocked until the
encounter passes. Automatic note quality remains a separate pre-beta gate.

This repository has fresh sanitized history. That does not make meeting content
source material: no capture, transcript, review packet, or private meeting
artifact may be committed or pushed.

### Fresh-session continuation

The durable continuation point is branch `codex/product-foundation`. A new session
should read this Status section, the Cold operator checklist, and
`vertical-slice.md`'s Status before acting. It does not need the prior chat transcript.

The only input missing from this gate is the operator's cold verdict on the exact
private page already rendered: `accept`, `revise`, or `decline`. Do not regenerate the
page merely to start a new session. Do not move its content, paths, manifest, or review
details into Git or chat.

- `accept` permits recording the human-review receipt against the existing private page
  digest and then updating the public gate status. It does not approve automatic note
  quality or the application runtime.
- `revise` records UI findings without quoting private meeting content. Any interface
  change requires a new render, digest, and cold review.
- `decline` leaves application implementation blocked and preserves the reason as a
  human finding.

The colleague survey is product-research evidence in `journeys.md`; it cannot supply
this verdict. The evaluation-contribution candidate in J6 is later product research;
it is not part of the page under review or the first vertical slice.

## Why this gate uses human-curated real content

Three candidate inputs were compared:

1. **The exhaustive ES2004c classifier benchmark.** Keep it as the gate for its
   registered recall claim. It does not produce a product note, prove semantic
   support, or test an application interaction, so it is not a product-encounter
   prerequisite.
2. **Public corpus content.** It is convenient and reproducible, but it did not
   pass through the supported capture path and is not the operator's real meeting
   context.
3. **A short, consented headphone capture with operator-confirmed review items.**
   This is the smallest input that lets the operator judge the actual interaction
   with real words while keeping automatic extraction explicitly untested.

The third input is the encounter gate. The benchmark continues independently as
research. Neither can stand in for the later automatic-note canary.

## Eligibility

An encounter candidate is eligible for cold review only when all of these are
true:

1. A consented, real headphone capture was made inside the bounded CLI envelope:
   one operator at the microphone and nobody else in the room.
2. A draft small set of decisions, actions, proposals, or open questions and
   their exact retained words is stored privately as
   `encounter-review-content/1`, with `origin: review-draft`,
   `product_evidence: false`, and
   `runtime_validation: not_run`.
3. The operator explicitly confirms participant consent, the review wording,
   and its evidence links in a separate `encounter-content-approval/1` receipt
   bound to the exact review-content SHA-256.
4. The source transcript and capture-session digests reconcile, capture health
   passes, every locator resolves, and the receipt digest matches the exact
   content rendered.
5. Every populated surface visibly says that the content is operator-confirmed
   and that automatic extraction and the application runtime were not tested.
6. A separate mechanical rejected-summary specimen proves that rejected claims
   never render as a ready note. It is a state specimen, not product evidence.
7. The click-through contains the cold-start, empty, loading, startup-failure,
   review-content, summary-failed, evidence, correction-specimen, retention, and
   deletion states listed below.

Speaker-mode, failed-health, unattributed, synthetic, or unconfirmed content
cannot supply the populated side of this gate.

The operator-confirmed content is allowed only to approve interaction design. A
classifier decision, automatic claim, product `note/2`, model receipt, latency,
or runtime verdict used in a product claim must still be produced unedited by the
frozen model/runtime path.

The private input has this exact shape. The immutable capture directory retains only
its six session-receipted files. Review content and its approval live in a separate
owner-only directory, because adding either one to the capture would invalidate its
artifact receipt. The renderer takes both directories and requires 3–12 items, 1–3
source fragments per item, current passing capture health, channel attribution, and
exact digest and locator matches. The example abbreviates the item list after its
first entry.

```json
{
  "schema": "encounter-review-content/1",
  "origin": "review-draft",
  "product_evidence": false,
  "runtime_validation": "not_run",
  "source": {
    "capture_id": "<opaque id>",
    "capture_mode": "headphones",
    "transcript_file": "transcript.json",
    "transcript_sha256": "<sha256>",
    "session_file": "session.json",
    "session_sha256": "<sha256>"
  },
  "meeting": {
    "id": "<stable private id>",
    "title": "<review title>",
    "captured_at": "<timestamp>"
  },
  "items": [
    {
      "type": "decision",
      "claim": "<review wording proposed for operator confirmation>",
      "evidence": [
        {"turn": 0, "quote": "<four or more exact retained words>"}
      ]
    }
  ]
}
```

An agent may draft this file. It cannot make the draft operator-confirmed by
writing a value into it. The operator's authority lives in a separate receipt:

```json
{
  "schema": "encounter-content-approval/1",
  "review_content_sha256": "<sha256 of exact review-content.json>",
  "participant_consent_before_capture": "confirmed",
  "curation": "accept",
  "reviewer": "<operator-chosen identifier>",
  "decided_at": "<timestamp>"
}
```

The renderer may verify the receipt's shape and byte binding. It cannot infer
who authored it. Only an explicit operator action may create the accepting
receipt, and any content change invalidates it.

## Private packet manifest

Create this manifest beside the private capture, outside the repository. Bind
each byte-bearing artifact by SHA-256 and record the exact renderer source and
command. Store paths as opaque local identifiers rather than copying meeting
content into the manifest.

```text
schema: operator-encounter/1

review_build:
  commit: <exact commit>
  commit tree: <git rev-parse <commit>^{tree}>
  checkout status: <empty git status --porcelain --untracked-files=all>
  docs/prototype/build.py: <sha256>
  prototype.html: <sha256>
  build command: <exact argv>
  Python executable: <resolved absolute path>
  Python version: <exact version>
  Node executable: <resolved absolute path>
  Node version: <exact version>

interaction_review_content:
  private capture id: <opaque id>
  session.json: <sha256>
  transcript.json: <sha256>
  mic.wav: <sha256>
  system.wav: <sha256>
  capture health: <embedded transcript.json field; validated under that file digest>
  voice-gate report: not_applicable
  voice-gate reason: <ungated interaction input; not beta or gate evidence>
  review-content.json: <sha256; schema encounter-review-content/1>
  origin: review-draft
  product evidence: false
  runtime validation: not_run
  content-approval.json: <sha256; schema encounter-content-approval/1>
  receipt review-content binding: <must equal review-content.json sha256>
  participant consent before capture: confirmed
  operator curation decision: accept
  rendered review-content region: <sha256>

summary_failed_control:
  private transcript id: <opaque id>
  transcript.json: <sha256>
  rejected note.json: <sha256; passed exactly false>
  rejection reasons: <canonical values>
  rendered withheld-summary region: <sha256>
  assertion: <no rejected claim or trust count rendered>

correction_specimen:
  schema: interaction-specimen/1
  product evidence: false
  source: <synthetic, non-personal fixture>
  withheld-turn state: <sha256>
  restored-transcript state: <sha256>
  stale-note state: <sha256>
  regeneration-requested state: <sha256>

mechanical_checks:
  command: <exact argv>
  output: <sha256>
  result: pass | fail

human_review:
  reviewer: <operator>
  reviewed_at: <timestamp>
  cold-start conditions: <record>
  decision: accept | revise | decline
  findings: <one result per checklist item>
```

Prepare fresh owner-only capture and review directories outside every Git repository.
The interaction-only renderer uses the existing private-output rules: absolute fresh
output, an external `0700` parent, `0600` HTML, symlink refusal, and atomic
no-overwrite publication:

```sh
python3 docs/prototype/build.py \
  --capture-dir /private/capture \
  --encounter-content /private/review/review-content.json \
  --content-approval /private/review/content-approval.json \
  --out /private/review/prototype.html \
  --node /absolute/path/to/node
```

Record that exact command and the resolved Python and Node versions in the manifest.

The correction state is deliberately a labeled specimen at this gate. Do not
enrol a voice profile or engineer a false rejection merely to populate it.
Phase 4 must later validate the real behavior on an actual gated canary before
beta.

## Mechanical prerequisites

An agent may prepare the private packet and refuse it when any check fails. It
may not approve the encounter.

- Require an otherwise clean checkout at the recorded commit. Record its Git
  tree and refuse untracked files so imported or read-at-runtime source cannot
  sit outside the packet's authority.
- Recompute every artifact digest from a fresh private staging copy.
- Refuse interaction-review mode unless the input has the exact non-product
  draft schema and a separate accepting operator receipt whose
  `review_content_sha256` matches the exact input. An agent may prepare the
  draft and verify the binding; it may not create the accepting human decision.
- Recompute the source transcript and capture-session digests, require current
  healthy channel-attributed capture artifacts, and resolve every review-item
  quote to its declared transcript turn.
- Keep interaction-review inputs structurally separate from `note/2`. Never
  synthesize a passing product note from human-curated material.
- Refuse a failed artifact if any rejected claim, claim-derived count, or
  ready-note trust treatment renders. Neutral meeting metadata, model timing,
  capture warnings, the retained transcript, canonical failure reasons, and
  recovery actions may remain.
- Require the correction specimen to be visibly non-product and non-personal.
  Its restore action must create a new transcript view, mark the old note stale,
  and keep regeneration separate. It supplies no voice-gate or persistence
  evidence.
- Verify that the interaction distinguishes the two deletion consequences:
  - **Delete audio:** the note, transcript, evidence, and meeting record remain;
    playback, retranscription, and tone checks do not.
  - **Delete meeting:** that meeting's note, transcript, evidence, audio, and
    retention record go; the voice profile and other meetings remain.
- Save the rendered-page digest and the prototype's automated state/wiring
  check output with the manifest.
- Keep `python3 docs/prototype/build.py --self-test --node <absolute path>`
  passing. When the interaction-only route is added, extend the controls to
  prove both exact schemas, missing/mismatched/declined receipt refusal, evidence
  locators, visible non-product labels, privacy modes, symlink refusal,
  no-overwrite publication, interruption cleanup, and outside-Git guard.
  Synthetic controls cannot supply real content, a product note, or encounter
  approval.

These checks establish artifact consistency and interaction wiring. They do not
establish human authority, automatic note usefulness, understandable language,
successful deletion, or recovery on a real installed application.

## Required encounter states

The review build must let the operator reach each state from the encounter
itself. A reviewer-only state picker may remain available, but it cannot be the
only route.

| State | What the encounter must make clear |
|---|---|
| Cold start | Nothing is recording; setup status and the next available action are unambiguous |
| Empty library | No meetings and no audio held is different from a loading failure |
| Consent | Capture cannot begin until the operator makes the per-attempt attestation |
| Recording / degraded | Which legs are healthy, what is still being preserved, and how to stop |
| Transcribing / summarizing | The retained artifact, current work, and safe recovery if processing stops |
| Startup failure | Runtime missing or service timeout, diagnostic location, capture consequence, retry, then reinstall |
| Review content | Human-curated real meeting content, evidence access, capture limits, and a visible statement that automatic extraction was not tested |
| Summary failed | Transcript retained, note withheld, canonical reason, and retry without rejected claims |
| Evidence | Exact retained words, source location, and the fact that a locator is not a support verdict |
| Correction specimen | A visibly synthetic withheld-turn example, intentional restore, stale note, then separate regeneration; no claim that the gate or persistence works |
| Retention | Chosen no-default policy, disk use, audio-only deletion, and whole-meeting deletion |

The current renderer covers this choreography, including empty-library,
artifact-specific processing recovery, and ordered shell-startup recovery
routes. Its private-input mode consumes the exact `encounter-review-content/1` and
digest-bound `encounter-content-approval/1` schemas, and an eligible owner-only packet
has populated the page awaiting cold review. Its correction, retention, deletion, and
processing behaviors remain specimens. Cross-meeting search remains outside the
supported beta and outside this gate.

## Cold operator checklist

Start at the opening screen without an agent walkthrough or a list of expected
controls. Record a separate answer and finding for each question.

1. Can the operator tell that nothing is recording, what setup is incomplete,
   and what action is available?
2. Can they tell what the human-curated review content says, what its limits are,
   and that it is not an automatic note or a claim that capture was perfect?
3. Can they move from a claim to the exact retained words and understand that a
   locator is not a support verdict?
4. In the failed-summary state, can they tell that the transcript survived, why
   no note is shown, and what retry will do?
5. From the clearly labeled correction specimen, can they inspect the reason
   and score, restore it intentionally, see the old note become stale, and
   understand that regeneration is a separate action without mistaking the
   specimen for runtime evidence?
6. Before confirming deletion, can they accurately state what survives
   audio-only deletion and what survives whole-meeting deletion?
7. Can they distinguish an empty library, transcription in progress, and
   summary generation in progress?
8. From a runtime-missing or service-timeout screen, can they find the
   diagnostic, understand whether capture survived, and follow retry or
   reinstall in the right order?
9. Is the encounter understandable and safe enough to approve as an
   interaction?
10. Separately, is this content representative enough to judge the interaction?

The last two answers are independent. A mechanically correct encounter can
still be rejected. Whether an automatically generated note is useful is judged
later on the product canary and does not inherit this approval.

## Approval receipt

Approval is an explicit operator action over the exact private manifest and
rendered-page digest. A chat acknowledgment, successful build, automated check,
or agent-authored review is not approval.

Record `accept`, `revise`, or `decline`. A revision creates a new build and
digest; approval does not carry across it.
