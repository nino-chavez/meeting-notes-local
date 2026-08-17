# Structured meeting review handoff — 2026-08-17

## Bottom line

Yawn's trust-first meeting review roadmap is implemented through the first
privacy-safe rendered fixture journeys. The source, signed Preview package, and
separately identified Fixture package now cover speaker attribution, local
vocabulary, recording-quality guidance, bounded device context, retained-audio
playback, and source-bound transcript retry.

The fixture directly proved the read-only comparison, **Decide later**,
playback/Stop, **Keep current**, and **Use retry** paths without using a real
meeting. It also exposed one truthful-copy bug: after promoting a retry on a
meeting that never had a generated note, the success toast still says that a
previous note was cleared. Fix that copy before extending the fixture to
synthetic note and source-link states.

Nothing in this work is shipped. The Developer ID build remains unnotarized and
uninstalled. `/Applications/Yawn.app` was not changed.

## Start here

Repository:

```text
/Users/nino/Workspace/dev/apps/yawn-app
```

Current branch and last implementation/documentation commit before this handoff:

```text
agent/structured-meeting-notes
b4a534d docs(yawn): document recoverable fixture rotation
```

The commit containing this handoff and its roadmap/runbook updates is intended
to leave the main checkout clean. Verify `git status --short` before proceeding.
One unrelated linked worktree remains and must be preserved exactly as found:

```text
/Users/nino/Workspace/dev/apps/yawn-app/.worktrees/yawn-retry-discovery
```

Its state was not audited during this handoff. Do not remove, reset, rebase, or
clean it.

Read these before changing code:

1. [Product roadmap](roadmap.md)
2. [Distribution runbook](distribution-runbook.md)
3. [Product brief](product-brief.md)
4. `crates/session-core/src/bin/rendered-review-fixture.rs`
5. `apps/desktop/src-tauri/src/main.rs` around `transcript_retry_decide`

## What landed

The work is split into bounded, reviewable commits. The most recent fixture and
release-evidence sequence is:

```text
3e87475 feat(release): add local signed verification mode
644aaaf test(release): execute local signing stop gate
ad1bac3 fix(release): disclose local timestamp contact
87879d1 docs(yawn): record bounded local signing gate
867fb20 test(release): ignore comments in operation derivation
f91d332 feat(yawn): add fixture preview bundle lane
57da863 feat(yawn): add synthetic rendered-review fixture seeder
a3b237d fix(yawn): make review fixture playback-safe
58d2438 fix(yawn): align fixture quality with silent audio
ab9137b fix(yawn): align low-input fixture evidence
1a3a999 feat(yawn): add verified fixture model install
b8ebee3 fix(yawn): harden fixture model path resolution
d40562e docs(yawn): document fixture bundle review lane
e757980 docs(yawn): record rendered fixture review receipt
4e11fb3 feat(yawn): add recoverable fixture archive command
b4a534d docs(yawn): document recoverable fixture rotation
```

Earlier commits on the branch contain the speaker-correction, vocabulary,
retry, recording-device, quality, playback, and recovery work. Do not infer
their state from this summary alone; the roadmap records their current evidence
class and remaining gates.

## Evidence already established

### Source and package checks

The counts below are run-session receipts from 2026-08-17. The commands and
current source remain available, but no separate machine-readable result bundle
was committed for these counts.

- The fixture bundle is `Yawn Fixture.app` with bundle identifier
  `com.ninochavez.local-meeting-notes.fixture`.
- Its app-data root is exactly
  `/Users/nino/Library/Application Support/com.ninochavez.local-meeting-notes.fixture`.
- `npm run fixture-verify` passes against the signed local fixture bundle.
- The fixture build matrix passes 6 tests.
- The fixture binary passes 11 focused tests.
- The full session-core gate passed 456 library tests, 11 fixture-binary tests,
  17 process-fault tests, and 8 doc tests.
- The desktop UI suite passed 37 tests.
- Distribution tooling passed 19 tests.
- The unreleased local `Yawn.app` passed Developer ID and hardened-runtime
  verification for the internal-alpha admission. It was not notarized,
  packaged into a new DMG, installed, or shipped.

### Direct rendered observation

All rendered fixture content was deterministic and invented. The audio was two
eight-second silent WAV files. A verified public speech model was copied into
the fixture root only to clear the production-faithful startup gate.

Computer Use directly observed:

- Recent meetings, title search, open, Back, and reopen continuity.
- Transcript-only detail with progressive full-transcript disclosure.
- Generated-note absence and a separate personal-notes surface.
- Current-versus-candidate retry comparison.
- Silence and low-input cautions, no material clipping observation, and
  unavailable background-noise evidence.
- A bounded recording-device explanation that did not expose the device name.
- **Decide later** closing without mutation and preserving the pending retry.
- Microphone playback entering a visible active state, explicit **Stop**, and
  return to idle.
- **Keep current** closing the pending comparison, preserving the retained
  transcript, and reopening with **Retry transcript** rather than
  **Review retry**.
- **Use retry** promoting the candidate, returning to transcript-only detail,
  and exposing **Generate note** and **Retry transcript**.

The app process is closed. No Settings value or permission changed. No
recording was started. No real meeting audio or private meeting content was
used.

## Current fixture state on disk

Three exact roots now exist under the user's Application Support directory:

```text
com.ninochavez.local-meeting-notes.fixture.archive-readonly-20260817
com.ninochavez.local-meeting-notes.fixture.archive-keep-current-20260817
com.ninochavez.local-meeting-notes.fixture
```

- `archive-readonly-20260817` preserves the read-only/Decide-later/playback
  review state.
- `archive-keep-current-20260817` preserves the completed Keep-current state.
- The canonical fixture root preserves the completed Use-retry promotion state.

The archive command performs a same-parent, exclusive atomic rename under the
canonical writer lock. It never deletes, overwrites, copies, or automatically
reseeds data. Do not remove these archives as cleanup. The public speech-model
copy accounts for most of each root's size.

The directory names prove only that the roots exist. Their described states are
direct Computer Use observation receipts recorded in this handoff and the
roadmap/runbook, not facts that can be re-derived from the names alone.

## First bug to fix

The Use-retry success message is unconditional:

```text
apps/desktop/src-tauri/src/main.rs:6014
"The retry transcript is now current. Its previous note was cleared."
```

The synthetic meeting had `current_note: None`, so the second sentence claimed
an event that did not happen. The surrounding modal warning is still correct:
promoting a retry invalidates any current generated note when one exists.

Use truthful unconditional success copy, or carry an exact pre-decision
`had_current_note` fact through the response. The smaller honest fix is likely:

```text
The retry transcript is now current. Generate a new note when you're ready.
```

Verify the final wording against both cases: no previous note and a previous
note pointer that is cleared. Update exact-copy tests. Do not weaken the durable
promotion behavior to make the toast easier.

## Next build sequence

1. Fix and test the retry-promotion success message.
2. Preserve the current promoted fixture with the archive command before
   reseeding another root. Use a new absent archive label; never overwrite an
   existing archive.
3. Rebuild and verify `Yawn Fixture.app`, seed a fresh root, import the verified
   public speech model, and repeat the Use-retry rendered walk with Computer
   Use. Reopen the meeting after returning to Meetings.
4. Add a clearly synthetic, provenance-bound note fixture. It must pass the
   existing deterministic note assembler/validator and say
   `model_inference: false`; a hand-written note must not masquerade as model
   output.
5. Use that fixture to render a note card, **Show source**, speaker-correction
   save, corrected projection, regeneration request binding, and the
   post-promotion note state.
6. Add a separate exact recovery failure fixture for the recovery-toast journey.
7. Repeat the completed journeys against the exact installed production package
   only after installation/release authority is explicit.

Do not import or run the real note model for the next slice. The verified public
note model is about 8.06 GB and already exists locally, but running it adds time,
memory pressure, and a different evidence claim. A structurally valid synthetic
note can prove rendering and provenance without claiming model quality or
inference.

## Commands for the next agent

Focused checks:

```bash
cd /Users/nino/Workspace/dev/apps/yawn-app
q cargo test -p local-meeting-notes-session-core --bin rendered-review-fixture
q cargo test -p local-meeting-notes-desktop transcript_retry
q npm --prefix apps/desktop run test:ui
q python3 -m unittest tests.test_distribution_tooling
```

Fixture build and verification:

```bash
cd /Users/nino/Workspace/dev/apps/yawn-app/apps/desktop
q npm run fixture-build
q npm run fixture-verify
```

Recoverable archive syntax:

```bash
cd /Users/nino/Workspace/dev/apps/yawn-app
cargo run -p local-meeting-notes-session-core --bin rendered-review-fixture -- \
  archive \
  "/Users/nino/Library/Application Support/com.ninochavez.local-meeting-notes.fixture" \
  "/Users/nino/Library/Application Support/com.ninochavez.local-meeting-notes.fixture.archive-<new-label>"
```

The full seed and verified model-import commands are in the fixture section of
the distribution runbook. Use those canonical commands rather than reconstructing
them from memory.

## Safety and evidence boundaries

- Use the computer-use skill through `node_repl` and `@oai/sky` for every
  desktop-app action. Refresh app state after every action.
- Launch the fixture by its full built path. A local build may share identities
  with other apps.
- Do not use Computer History.
- Do not open Settings, accept microphone/system-audio permissions, start or
  stop recording, type into fields, or inspect a real meeting.
- Do not reproduce meeting titles, names, transcript text, notes, emails, or
  other private content.
- Do not touch `/Applications/Yawn.app` or existing release artifacts.
- Do not notarize, install, publish, push, or ship without explicit authority.
- Preserve dirty worktrees and unrelated changes.
- Keep evidence labels exact: source-verified, packaged, rendered fixture,
  installed production, notarized, and shipped are different states.

## Ready-to-pass continuation brief

```text
Continue Yawn from docs/structured-meeting-notes-handoff.md on branch
agent/structured-meeting-notes in
/Users/nino/Workspace/dev/apps/yawn-app.

First fix the unconditional Use-retry success toast in
apps/desktop/src-tauri/src/main.rs. The current copy says a previous note was
cleared even when the meeting had no note. Keep transcript promotion and note
invalidation semantics unchanged. Add exact-copy coverage for both note/no-note
cases or choose truthful unconditional copy.

Then preserve the current marker-bound synthetic fixture with the recoverable
archive command, rebuild and verify Yawn Fixture.app, seed a fresh fixture,
import only the verified public speech model, and repeat the Use-retry journey
with computer-use through node_repl + @oai/sky. Refresh after every action.

Do not use private meeting content, Settings, permissions, recording, Computer
History, the installed Yawn app, notarization, installation, publishing, or
shipping. Preserve .worktrees/yawn-retry-discovery and all unrelated changes.
Record direct observation separately from source inference and update the
roadmap/runbook without calling fixture evidence shipped production evidence.
```
