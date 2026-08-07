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
[`docs/screens-and-states.md`](./docs/screens-and-states.md), and
[`docs/backlog.md`](./docs/backlog.md) decomposes the ten features into twelve epics
and their stories — read it to learn what a piece of work *is*, never to learn when
it happens. Status has exactly one owner and it is the build queue.

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
commits — consolidated 2026-08-07 by fast-forwarding `main` onto the app line.

Work in `<repo>/.worktrees/<branch>`. Remove the worktree once the work has landed
**or** the session is finished with it — it does not have to be merged first, and on
2026-08-07 thirty-eight worktrees on unmerged branches were removed safely. Removing
a worktree never deletes its branch, so nothing is lost by removing it early.

Deleting a *branch* is the irreversible one, and is a separate decision. **Reconciled
2026-08-07: 85 local and 28 remote branches down to one each.** How it was done is the
part to repeat, because a reflex sweep would have destroyed real work:

1. `git cherry main <branch>` — not `--no-merged`. It matches patch IDs, so it sees
   content that landed via rebase or squash. 28 branches had zero unique commits.
2. For the rest, compare **content**: files the branch has that main lacks, and files
   where the branch is larger. Date is not a supersession test — `wave-status-refresh`
   was four days older than main and still held 645 lines against main's 307.
3. That check found genuinely stranded work, rescued in PR #8: the word-timestamp
   sidecar correction (stranded since 2026-08-02) and `notes/read_semantic_support.py`,
   the tool that lays each claim beside the evidence it cites.
4. Tag anything unique before deleting — `archive/<name>`, pushed to origin. Eleven
   exist; they make every deletion reversible and cost nothing.

Verify a rescue by content, never by exit code. A cherry-pick with a botched conflict
resolution still exits 0; the line count is the actual check.

**Private meeting material never enters Git.** Audio, transcripts, note text, and
profile material stay out by design, so their absence from the repository proves
nothing about whether a run happened — the run and closure receipts live outside Git
deliberately. `spike/aec-bound-results.json` is the worked example: it is gitignored
(`.gitignore:39`), its redacted sibling `spike/aec-bound-results-redacted.json` is
what ships, and on 2026-08-07 an attempt to "restore a file missing from the trunk"
would have published the unredacted 95KB original to a public repository. Before
adding any file back, check `git check-ignore` and look for a redacted sibling.
