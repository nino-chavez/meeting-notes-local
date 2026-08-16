# Note-display handoff (2026-08-16)

## Bottom line

The backend generation chain is confirmed working end to end: a real meeting's
note generates, publishes, re-inspects, and commits into `meeting.json`
(`lifecycle: "ready"`, `current_note` set), and the library-rebuild
re-validation (`note.project`) that reads it back succeeds. That part is done,
tested, and pushed — see `docs/note-runtime-decision.md`'s "Operational
close-out, continued" entry for the full account of what was found and fixed
this session.

What's still broken: the note did not actually display in the app UI when the
operator looked. My own "it works" verification for that last mile was weak
and most likely wrong — see below. This has not been re-diagnosed live; it's
a lead, not a confirmed root cause.

## Why my earlier "confirmed" claim should not be trusted

I checked for the *absence* of a `"Generate note"` button and *absence* of
specific error-toast text strings in the app's accessibility tree, on a
freshly relaunched app that happened to land on the meeting's detail view. I
did not check for the *presence* of actual note content. Absence of a known
failure signature is not evidence of success — a third, silent empty state
would pass that check too. Flagging this explicitly so the next session
doesn't repeat it: any future verification of note display must confirm real
content (claim text, decision/action labels, etc.) renders, not just that
known failure text is missing.

## A concrete, untested lead

`apps/desktop/ui/main.js`'s note-detail view calls the Tauri command
`library_open_note` (`apps/desktop/src-tauri/src/main.rs:4432`), which reads
through `ApplicationState::with_preview_library`
(`apps/desktop/src-tauri/src/main.rs:824`). That helper does **not** lazily
rebuild anything — if `state.preview_library` (a `Mutex<Option<LibraryReader>>`,
starts `None` on every process launch, `main.rs:211`) is `None`, it returns
`unavailable()` immediately (`main.rs:838-840`) without ever calling
`rebuild_with_projector`.

The only thing that populates `preview_library` is the `library_snapshot`
command (`main.rs:2900`, via `library_snapshot_with` → `rebuild_with_projector`
→ `*library = Some(reader)`), which runs when the frontend loads the
meetings list ("Back to Meetings" view). If a fresh app process is
navigated (or restores window state) directly into a meeting's detail view
without the meetings-list command having run first in that process,
`library_open_note` would return `unavailable_note("")` — not an error, not a
"Generate note" prompt, just an unavailable/empty response — for a note that
is fully valid on disk.

This matches what likely happened during my last verification pass: I
relaunched the app, it restored directly onto the meeting-detail view (no
explicit "Back to Meetings" click in that fresh process before checking), and
I only checked for negative signals that an `unavailable_note` response
wouldn't necessarily produce.

**Next session, start here:**

1. Launch the app fresh and deliberately click into "Back to Meetings" (the
   list view) *first*, confirming that view loads, before opening any
   specific meeting. This is what calls `library_snapshot` and populates
   `preview_library`.
2. Then open the meeting used for this session's test run (meeting id
   `fdd59c81-30d7-480b-95d1-3753b9bad28e`, its published note is
   `notes/ac2f2583c10fb0c55e312f1a61283bd565aba1f499021cb7201e96e275a33a1c.json`
   under that meeting's directory) and check whether the note now renders.
3. If it still doesn't render even after an explicit meetings-list visit,
   the `unavailable_note` hypothesis is wrong — instrument
   `library_open_note` / `open_note` (`apps/desktop/src-tauri/src/library_reader.rs:770`)
   the same way this session instrumented the generation chain (a
   `debug_note`-style temporary log to `/tmp`, reverted before commit), and
   trace exactly what response shape reaches `main.js:874`
   (`const note = await invoke("library_open_note", ...)`).
4. Also worth checking early: whether `main.js`'s meeting-open flow calls
   `library_snapshot` (or an equivalent per-meeting refresh) itself before
   calling `library_open_note`, independent of whether the operator visited
   the list view — if it does, the lead above is wrong and the bug is
   somewhere else in the response path.

## Current repo/build state

- Working tree is clean; all code changes from this session are committed
  and pushed to `main` (commits `bf082ce`, `b045d4d`, `9baa602`, `6d1c84d`,
  `7df9b9e`).
- No temporary debug instrumentation remains in any source file.
- The release bundle at `target/release/bundle/macos/Yawn.app` was rebuilt
  and re-signed after the last code fix (the claim-length cap removal) and
  passed `codesign --verify --deep --strict` and
  `scripts/verify-release-bundle.py --signed --admission internal-alpha`
  (version 0.5.7, internal-alpha, 199 arm64-compatible Mach-O files). The app
  is not currently running.
- The test meeting (`fdd59c81-30d7-480b-95d1-3753b9bad28e`) has a fully
  valid, committed note on disk — confirmed by direct file read and by a
  standalone script replaying `note_validator.py`'s `project()`
  re-derivation against the real files, which passes. The gap is specifically
  in what the desktop UI does with that data, not in the data itself.

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
