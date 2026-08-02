# Meeting-memory walking skeleton

This local, synthetic prototype compares three information architectures against the
same operator task and corpus:

1. Meetings first
2. Commitments first
3. Find + browse

Each direction implements the same thin journey:

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

`review-manifest.json` binds the three candidate URLs to the exact HTML, CSS, and
JavaScript under review. Its `approval` field stays `null` until the operator chooses
one candidate; mechanical checks and agent audits cannot fill it.
