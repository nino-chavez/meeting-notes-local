# local-meeting-notes — agent guidance

Before proposing, planning, or building any feature, read
[`docs/product-definition.md`](./docs/product-definition.md). It is the definition
layer: what the product is, who the reader is, the ten north-star features with
their research grounding and build status, and the non-goals. Work that serves none
of the ten features, or crosses a non-goal, needs a dated amendment there first.

Sequencing authority stays with [`docs/vertical-slice.md`](./docs/vertical-slice.md).
Read its **Build queue** section first: that decides what gets built next, ordered by
feature, with everything buildable-without-a-human-decision at the top. The wave
table under it is the evidence history, not a work order. Surface detail lives in
[`docs/screens-and-states.md`](./docs/screens-and-states.md).

Statuses in any doc are hypotheses, not evidence. Verify against code before
repeating one: `worker/main.py` (`ALPHA_OPERATIONS`),
`apps/desktop/src-tauri/tests/shell_contract.rs` (registered-command pins), and
`docs/distribution-runbook.md` (release record).

## How to work here

**Decide and record; do not accumulate questions.** Pick the option, write the
assumption into the commit message or the doc you touched, and keep moving. Four
things genuinely need the operator: consent and retention wording, release
admission, whether a note is actually useful, and anything requiring a person to
physically operate the app. Everything else is yours to call, and cheap to override.
The build queue marks which items are which, so "is this mine or theirs" is a lookup
rather than a judgment made fresh each session.

**Every session converges.** Branch, then PR, then merge. A session that ends at
"pushed" is how this repo reached 85 branches, 44 worktrees, and two unrelated root
commits — consolidated 2026-08-07 by fast-forwarding `main` onto the app line. Work
in `<repo>/.worktrees/<branch>`, and remove the worktree after the merge; removing a
worktree does not delete its branch.

**Private meeting material never enters Git.** Audio, transcripts, note text, and
profile material stay out by design, so their absence from the repository proves
nothing about whether a run happened — the run and closure receipts live outside Git
deliberately. `spike/aec-bound-results.json` is the worked example: it is gitignored
(`.gitignore:39`), its redacted sibling `spike/aec-bound-results-redacted.json` is
what ships, and on 2026-08-07 an attempt to "restore a file missing from the trunk"
would have published the unredacted 95KB original to a public repository. Before
adding any file back, check `git check-ignore` and look for a redacted sibling.
