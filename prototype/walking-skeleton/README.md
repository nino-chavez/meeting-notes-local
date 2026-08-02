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
JavaScript under review. Its `compositionApproval` field stays `null` until the
operator approves the default view and shared navigation hierarchy; mechanical checks
and agent audits cannot fill it.
