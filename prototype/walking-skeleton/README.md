# Meeting-memory walking skeleton

This local, synthetic prototype compares three possible default opening views inside
one information architecture, against the same operator task and corpus:

1. Meetings
2. Recorded promises
3. Find

All three capabilities remain in the product. The review question is which view opens
first, what receives first-class navigation, and how the operator moves among them.
Each starting view implements the same thin journey:

`find a decision → inspect its typed claim → open exact transcript words → review a withheld turn → restore it → see the note become stale → regenerate → return to the preserved retrieval context`

The light app header is the proposed persistent product navigation: **Find**,
**Meetings**, and **Promises** remain reachable from every product view. The dark bar is
reviewer-only: it changes which of those views opens by default. Switching product
views preserves corrected transcript state, regenerated note state, and the resulting
meeting and promise updates.

Find opened by default as an evidence-ranked hypothesis, not an arbitrary favorite.
Existing market research treats corpus retrieval as core value; the registered
colleague snapshot (`n=3`) favors a question-shaped entry 2:1 over filters and scores
cited cross-meeting value 5, 4, and 5. Meetings and Recorded promises remain in the
composition. This prototype uses exact synthetic search and does not claim the later
conversational-search capability.

The operator accepted that composition on 2026-08-02 at exact commit
`689fcda396c073d21d69d8feb3cfb6031bec0596`: Find opens by default,
Find/Meetings/Promises remain persistent product navigation, and all three converge on
the shared meeting, note, transcript, evidence, correction, and regeneration surfaces.
The accepted artifact and its file digests are preserved in `review-manifest.json`.

The navigation corpus stayed frozen through the review so every starting view faced
the same task and evidence states. The active flesh-out now holds that accepted
hierarchy constant and uses a synthetic sales/discovery meeting—the first scenario
selected by 3/3 respondents—to compare note content and evidence treatment.

The first content slice is now runnable. It adds a synthetic discovery call organized
as concise summary, decisions, actions and owners, open questions, risks and blockers,
and customer needs. Each typed claim has exact-word navigation; the note distinguishes
stated from inferred wording and labels its summary as derived. The content review is
still pending: this fixture does not prove automatic extraction, semantic support, or
operator usefulness.

The next runnable slice adds manual capture without making status a destination.
**Start meeting** opens a per-attempt consent overlay above the current view. Once the
synthetic recording starts, healthy or degraded channel state lives in the persistent
header and a dismissible HUD while Find, Meetings, and Promises remain usable beneath
it. Stop moves through local-transcription status and rejoins either the discovery note
or the existing partial-transcript specimen when a simulated channel interruption was
not recovered. This path uses no hardware, permissions, audio, model, or product data;
its interaction review is pending.

The first trust-controls slice keeps **Settings** outside the accepted primary
navigation and makes readiness explicit in one place. A returning-profile fixture
shows the ready state; the first-run path requires both capture permissions and a
no-default audio auto-deletion choice before it reaches the voice-profile boundary.
Reset is a separate two-step action that leaves meetings, transcripts, notes,
retained meeting audio, and the chosen retention period intact while making Start
unavailable. The joined enrolment slice then walks two operator sittings separated by
a measured gap, permitted comparison speech, an unselected measured-policy trade-off,
private build/persistence, discard, and return to ready. Its displayed rates come from
the repository's fixed non-personal score fixture. No macOS permission, profile,
audio, model, or product record is inspected or changed.

It is a design instrument, not a second application runtime. It does not read or write
Preview data, record audio, invoke a model, or prove note usefulness or semantic
support. The synthetic corpus is frozen as of May 9, 2026 so relative retention states
do not drift with the real clock.

Run from the repository root:

```bash
python3 -m http.server 4173 --directory prototype/walking-skeleton
```

Then open `http://127.0.0.1:4173` at a 960×900 viewport. The outer page never scrolls;
long meeting and transcript content scrolls inside its reading pane.

`review-manifest.json` binds the three starting-view URLs to the exact HTML, CSS, and
JavaScript under review. Its `compositionApproval` preserves the operator's explicit
decision and the exact artifact digests it covered. Later content changes do not widen
that approval: mechanical checks and agent audits still cannot approve automatic-note
quality, installed behavior, beta admission, or release.
