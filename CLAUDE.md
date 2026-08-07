# local-meeting-notes — agent guidance

Before proposing, planning, or building any feature, read
[`docs/product-definition.md`](./docs/product-definition.md). It is the definition
layer: what the product is, who the reader is, and the parity feature set with its
competitor sources and build status.

**It is a map of the destination, not a gate on the work.** Until 2026-08-07 this
paragraph said work serving none of the ten features "needs a dated amendment there
first," and that sentence did real damage: it turned an incomplete feature list into
a fence, three parity capabilities were refused as non-goals, several more were never
written down, and the build queue reported itself converged while the product was a
fraction of its north star.

**The rule runs the other way now.** A capability the category ships and this product
lacks is a gap in the definition until proven otherwise — not a proposal that has to
justify itself. If a piece of work does not map to a row there, the likely fault is
the row list. Add the row with its parity source and keep building. Two invariants
survive and only two: **evidence is never decoration** (a claim cites resolvable
words, which nobody in the category does), and **nothing leaves the Mac without the
operator seeing it leave**.

Do not treat verification discipline as scope gating. Checking a claim against source
before asserting it is orthogonal to how ambitious the roadmap is, and it stays.

Sequencing authority stays with [`docs/vertical-slice.md`](./docs/vertical-slice.md).
Read its **Build queue** section first, and inside it **Start here** — that names the
next build in one sentence, the work deferred on purpose, and what ending a session
cleanly means. The **Wave 1–4** tables directly under it are the work order, ordered
by feature; a struck-through row is finished, so the first row that is not struck
through is the next build. Everything further down that file — **Current milestone
plan** and below — is evidence history and contract, not a work order; read it to
learn why something is the way it is, never to learn what to do next. Surface
detail lives in
[`docs/screens-and-states.md`](./docs/screens-and-states.md), and
[`docs/backlog.md`](./docs/backlog.md) decomposes the parity feature set into epics
and stories — read it to learn what a piece of work *is*, never to learn when it
happens. Status has exactly one owner and it is the build queue. Expect the backlog
to lag the definition layer while parity is being written down; a story that does not
exist yet is not evidence that the feature is out of scope.

Each story there carries a **Validation** line naming the check that proves it:
`Pinned` (a named test fails if the behaviour changes), `Exercised` (the path runs but
nothing pins it), `Receipted` (a digest-bound receipt from a real run exists outside
Git), or `Unproven` (nothing checks it — stated, because an absent line reads as an
oversight and this reads as a fact). Before claiming a capability works, read its
Validation line; a story can be fully `Pinned` and still unproven as a product
capability, because what is pinned is behaviour on fixtures.

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

**Merging has two rules, both learned by breaking them on 2026-08-07.** Do not chain
a push straight into `gh pr merge`: GitHub computes mergeability asynchronously, and
a merge issued in the same breath fails with "Pull Request is not mergeable" for no
reason other than timing. Poll `gh pr view <n> --json mergeable` until it reads
`MERGEABLE` first. And **gate cleanup on the merge having actually landed.**

Running the delete unconditionally after a failed merge deletes the branch, closes
the PR, and leaves the work reachable only through the object store. It is
recoverable, and recovering it is pure waste. One `if` prevents it.

**Gate on content, not on ancestry.** This paragraph carried
`git merge-base --is-ancestor <sha> main` from 2026-08-07 until 2026-08-08, and that
check can never pass here: every PR in this repository lands through
`gh pr merge --squash`, which writes a *new* commit, so the branch tip is never an
ancestor of `main`. A rule that always refuses is not a safety gate — it is a rule
the next session works around, which is worse than no rule. Ask instead whether the
content arrived:

    [ -z "$(git diff main <branch>)" ] \
      && [ "$(gh pr view <n> --json state -q .state)" = MERGED ] \
      && git branch -D <branch>

An empty `git diff` says every line of the branch is in `main` however it got there
— squash, rebase or merge — and the PR state says a human-visible merge happened
rather than the branch having been empty all along. Both, because either alone
passes for a branch that never carried anything.

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

**A branch can be pinned from outside this repository, and content checks do not see
that.** The 2026-08-07 sweep deleted `codex/work-library-publication`, which held the
only copy of `work-library.publication.yml`. The Work Library portal
(`~/Workspace/dev/apps/work-library`, `sources.yml` id `local-meeting-notes`) pins that
branch by name, so its next import blocks at
`scripts/lib/blueprint-adapter.mjs:143` with `revision-mismatch`. Nothing in step 2
above could have caught it — the file was unique to the branch, but its *consumer* was
in another repo. The archive tag made it recoverable, which is the fourth step earning
its keep. The manifest now lives on `main` so the pin can follow trunk. Before deleting
a branch whose name appears in another repo's config, grep `~/Workspace/dev` for it.

**A frozen artifact must never be asserted through a live constant.** Hit three
times on 2026-08-07, each time while growing the registered fixture suite:
`mlx_note_matrix_receipt.json` (a 2026-08-05 receipt) asserted its fixture count as
`EXPECTED_FIXTURES`; a second test asserted a synthetic receipt the same way and
was correct to; and `mlx_note_id_alignment_receipt.json` asserted its row count as
`EXPECTED_FIXTURES - 2`, a proxy for "the non-abstention fixtures" that silently
became wrong. The test for a historical receipt pins the literal it was produced
with. The test for live behaviour follows the constant. Deciding which one a test
is takes a sentence and prevents a green suite from certifying a receipt against a
suite that did not produce it.

**Private meeting material never enters Git.** Audio, transcripts, note text, and
profile material stay out by design, so their absence from the repository proves
nothing about whether a run happened — the run and closure receipts live outside Git
deliberately. `spike/aec-bound-results.json` is the worked example: it is gitignored
(`.gitignore:39`), its redacted sibling `spike/aec-bound-results-redacted.json` is
what ships, and on 2026-08-07 an attempt to "restore a file missing from the trunk"
would have published the unredacted 95KB original to a public repository. Before
adding any file back, check `git check-ignore` and look for a redacted sibling.
