# Installed desktop review protocol

**Status:** canonical for Yawn desktop review

**Owns:** the repeatable screen-by-screen review of a built Tauri app. Design
decisions remain in `DESIGN.md`; product behavior remains in
`docs/product-definition.md` and the admitted reducers.

## The rule

Review Yawn as a person uses a Mac application. A passing source check, browser
render, accessibility tree, or synthetic state does not prove native look and
feel. It also does not prove real capture, spoken VoiceOver quality, cold
comprehension, or human visual approval.

The machine-readable checklist is
`apps/desktop/ui/review/review-plan.json`. Every production `.screen` and native
Settings pane must appear there. `npm run test:ui` fails when one is omitted.

## Evidence vocabulary

Keep these dimensions separate:

- **Environment:** `source`, `browser`, or `installed-tauri`.
- **Stimulus:** `none`, `synthetic`, `retained-local`, or `live-device`.
- **Observer:** `automated`, `agent-assisted`, or `human-operator`.
- **Atomic verdict:** `pass`, `fail`, `unproven`, `blocked`,
  `not-applicable`, or `superseded`.

Do not use `partial` on an atomic row. A rollup passes only when every required
row passes. A failure can be recorded as soon as it is observed. A pass requires
evidence admissible for that exact claim.

| Claim | Minimum evidence for a pass |
|---|---|
| Static structure or state availability | Source or browser |
| Installed rendering, keyboard, focus, geometry, or window behavior | Installed Tauri |
| Real recording, degradation, stopping, file closure, or processing | Installed Tauri with live-device stimulus |
| Spoken VoiceOver order and quality | Installed Tauri, VoiceOver, human operator |
| Native look and feel | Installed Tauri plus a digest-bound human verdict |
| Cold comprehension | Unprompted human-operator task result |
| Final visual approval | Explicit human `accept` bound to the run and executable digests |

An accessibility tree can prove that a label exists. It cannot prove that the
spoken experience is understandable. A synthetic review build can prove layout,
focus, and transition presentation. It cannot prove device behavior.

## Prepare a run

From `apps/desktop/`:

```sh
npm run test:ui
cargo test -p local-meeting-notes-desktop --test shell_contract
cargo test -p local-meeting-notes-desktop
npm run build
codesign --verify --deep --strict ../../target/release/bundle/macos/Yawn.app
npm run review:prepare -- \
  --app ../../target/release/bundle/macos/Yawn.app \
  --out ../../docs/desktop-installed-app-reviews/<date>-<executable-digest-prefix>
```

Preparation records the bundle identifier, version, executable SHA-256,
signature result, Git revision, working-tree state digest, and review-plan
digest. Every check begins as `unproven`. The preparer cannot manufacture human
approval.

Private meeting screenshots stay outside Git. The run may record an opaque local
identifier and SHA-256, but never a private filesystem path. Sanitized evidence
may be committed.

## Human-style pass for every surface

1. Enter through an ordinary operator path. Do not begin only from a state picker.
2. Before clicking, record the first impression:
   - What state am I in?
   - What can I do now?
   - What is the primary action?
   - Does this look and behave like a Mac application?
   - Is anything oversized, cramped, floating, card-heavy, or web-like?
3. Exercise every visible action with the pointer.
4. Repeat the critical path with the keyboard.
5. Check focus order, visible focus, disabled behavior, Space/Return, and safe Escape.
6. Move, resize, minimize where supported, close, reopen, background, foreground,
   and verify restoration.
7. Repeat at comfortable and declared minimum geometry.
8. Repeat like-for-like in light and dark appearance.
9. Compare beside the named native pattern. Comparators inform interaction and
   density; they do not expand Yawn's product scope.
10. Record the atomic verdict immediately.

Use the order below. If a shared defect appears, stop duplicating screenshots of
the same failure. Fix the owning foundation, component, or pattern; mark affected
evidence `superseded`; rerun every mapped surface.

1. Primary shell, Library, and selected meeting.
2. Settings → Capture.
3. Consent → arming → healthy/degraded recording → stopping → processing →
   transcript handoff.
4. Menubar and window lifecycle.
5. First run and voice enrolment.
6. Ask, Actions, full transcript, failures, Help, and every remaining migration row.

## Operator verdict

Human approval is a separate receipt. It must contain:

```json
{
  "schema": "yawn-operator-verdict/1",
  "run_manifest_sha256": "...",
  "app_executable_sha256": "...",
  "reviewer": "...",
  "decided_at": "...",
  "decision": "accept | revise | decline",
  "surface_findings": []
}
```

An agent may prepare and validate this shape. It may not create `accept` for the
operator.

## Validate and rerun

```sh
npm run review:validate -- \
  ../../docs/desktop-installed-app-reviews/<run-id>/run.json
```

- Any executable SHA change invalidates installed evidence for the older binary.
- A review-plan digest change requires a new run.
- Foundation, shared-component, pattern, window, `index.html`, `main.js`,
  `styles.css`, or `native-calibration.css` changes rerun every mapped surface.
- A screen-local visual change reruns that surface in both appearances and both
  geometries.
- An interaction change reruns pointer, keyboard, focus, close/reopen, and
  restoration for the affected path.
- A copy change reruns product truth and cold comprehension.
- An accessibility change reruns the applicable assistive modes.
- Any change after operator review requires a new digest-bound operator verdict.

Historical receipts remain evidence for their exact binary. They do not close a
later run.

## Installed synthetic state lane

Rare layouts may be exercised in the separately identified, backend-free review
bundle:

```sh
npm run ui-review-build
npm run ui-review-verify
```

`Yawn UI Review.app` uses the production HTML, CSS, and native window geometry.
It starts at `index.html?review=synthetic`, forces product invocation off, carries
a persistent synthetic watermark, and has only the native start-dragging
permission. It bundles no runtime resources and registers no product commands.

Use it for installed-webview layout, focus, and presentation transitions. Never
use it to pass live capture, file closure, transcription, recovery, permission,
retained-data, or product-readiness gates. Prepare a separate digest-bound run
for this bundle; its evidence cannot be attached to a `Yawn.app` run.
