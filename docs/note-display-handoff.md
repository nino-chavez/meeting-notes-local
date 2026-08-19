# Note-display handoff (2026-08-16)

## Bottom line

The generated note renders in the desktop UI after the meeting is dismissed
and reopened from the meetings list. This was verified live on 2026-08-16 with
meeting `fdd59c81-30d7-480b-95d1-3753b9bad28e`.

The `630` detail view showed real generated content, not just an error-free
shell. It rendered `POINT` cards containing `All right, we're good to go.` and
`I already did the recap for it.`, plus the retained source transcript. No
temporary instrumentation was needed.

The remaining issue is narrower: the capture/resume screen has no generated-
note view. The operator must choose **Back to Meetings**, which dismisses the
current meeting, before that meeting can appear in the library and its note can
be opened.

## What the live check proved

The app was already on the meetings list after the operator had dismissed the
current meeting. The first row was `630`, dated Aug 11, 2026. A coordinate
click on the row opened the meeting detail view. The detail view visibly
contained:

- the title `630` and state `Note`
- the section `Draft from transcript`
- generated cards labeled `POINT`
- exact claim text from the published note
- `Show source` controls
- the retained source transcript with matching text

The published fixture contains 61 claims, all typed `point`. `POINT` is
therefore the only generated-claim label expected in this meeting; the absence
of `DECISION` or `ACTION` cards is not a rendering failure for this fixture.

This closes the original last-mile verification gap. The check used positive
content evidence; it did not infer success from the absence of an error.

## The earlier cache hypothesis was wrong

`initialize()` calls `refreshLibrary()` at every frontend boot. That invokes
`library_snapshot`, rebuilds the reader, and stores it in `preview_library`.
The call runs alongside the initial app snapshot and permission refresh, before
the final render. A fresh process therefore does not depend on the operator
visiting the meetings list first to populate this cache.

The selected row also comes from that same library snapshot. The proposed
ordering — opening a row before any snapshot populated the reader — is not a
reachable UI path.

## What remains true about the current-meeting screen

`renderCapture()` displays the operator's note editor and the raw transcript.
It does not read or render generated claims. The library intentionally excludes
active meetings, so the current meeting cannot be opened through the library at
the same time.

On a terminal capture state, **Back to Meetings** calls `dismiss_meeting`,
clears the current meeting projection, and refreshes the library. The dismissed
meeting can then appear in the list. The live check confirmed that opening it
from there renders the generated note correctly.

Whether the capture screen should expose the finished generated note before
dismissal is a product-flow decision. It is not a failure in note generation,
storage, library opening, or detail rendering.

## Product-quality correction after the render check

The live render proved the old path, but the point-only artifact was not a
meeting summary: it made the operator review 61 selected transcript excerpts
and reconstruct the meeting themselves.

The generation path now asks the installed local model for a short overview and
typed outcomes after it selects transcript evidence. Local validation resolves
every model evidence ID back to exact transcript spans. It also rejects a
decision or action unless the cited transcript contains explicit agreement or
commitment language.

The real `630` transcript now produces three overview points, two proposals,
and one open question. It produces no decisions or actions because the retained
evidence does not support those labels. The rendered note leads with the
overview, groups the proposals under **Ideas discussed**, groups the question
under **Open questions**, and keeps source evidence one click away.

Ready meetings now expose **Regenerate note**, so an older point-only artifact
can be replaced without deleting the meeting or transcript. The operation pins
the prior note in its durable request. A failed replacement keeps that prior
note current; a passing replacement publishes atomically.

Point-only artifacts remain readable as an honest fallback. The surface says a
summary was not produced and moves those excerpts under **Review selected
excerpts** instead of presenting them as the note.

## Current repo/build state

- The structured local generation path, meeting-note UI, product brief, tests,
  and this handoff update are the current uncommitted working-tree changes.
- No temporary debug instrumentation remains in any source file.
- The app bundle at `target/release/bundle/macos/Yawn.app` was rebuilt with the
  structured generator and validator. It passes `codesign --verify --deep
  --strict` and `scripts/verify-release-bundle.py --admission internal-alpha`
  (version 0.5.7, 169 arm64-compatible Mach-O files). This is local
  internal-alpha evidence, not notarized release evidence.
- The test meeting (`fdd59c81-30d7-480b-95d1-3753b9bad28e`) now points to
  structured note `b26edd82…d25d50`. Durable operation
  `8eeadf6d-042a-419d-9392-80bcb98eeac4` records the prior note and the accepted
  replacement. A fresh `note_validator.py::project()` replay returns the six
  expected typed claims. The real frontend rendered those claim values in its
  summary-first layout with the regeneration control visible.

## Do not re-litigate

These are settled for this task and don't need re-checking unless new
evidence contradicts them:

- The MLX memory leak, the missing `candidate_first.py` staging file, the
  `note.inspect` admission gap, and the claim-length cap mismatch are all
  fixed, tested (Rust 439 tests, Python 102 tests, both green), and pushed.
- The generation chain itself — model run, note creation, re-inspection,
  meeting-record commit, and the backend's own re-validation of the
  published note — is proven working via direct file inspection and a
  standalone reproduction script, independent of the UI question above.
