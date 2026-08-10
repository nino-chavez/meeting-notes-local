# DS-4 desktop design-system verification receipt

**Date:** 2026-08-09

**Scope:** production Library and selected meeting, native Settings → Capture, and consent through transcript handoff

**Outcome:** the integrated system is buildable, the automated contracts pass, and the current signed bundle was relaunched and exercised in its Tauri windows. Human and platform-assistive gates remain open below.

**Current standing:** historical DS-4 receipt. It does not close the current visual
approval gate. New installed passes use
[`desktop-installed-app-review.md`](desktop-installed-app-review.md) and live under
`docs/desktop-installed-app-reviews/`, bound to the exact executable and review-plan
digests.

Latest digest-bound product run: `2026-08-09-531ec638-layout`, executable
SHA-256 `531ec6389e5492e0460576a36e1dfaa4df0a241d25a6454bb551155c95008bbf`.
It covers the configurable Automatic/Focus/Library slice, the Meetings root,
and direct retained-transcript handoff. Its final installed smoke reached the
retained Meetings root and selected Transcript directly. macOS locked before the
final Desktop Behavior Settings rerun, so the broader Settings, Light/Dark, and
minimum-geometry observations remain bound to the superseded `74160b48` binary
and do not close gates for `531ec638`. All 110 rows remain formally unproven where
the installed walk did not cover every required state or human gate. The validated
machine-readable receipt is
`docs/desktop-installed-app-reviews/2026-08-09-531ec638-layout/run.json`.

Latest backend-free installed state run: `2026-08-09-ui-review-7515dc15`.

## What was in the historical DS-4 bundle

- App: `target/release/bundle/macos/Yawn.app`
- Bundle identifier: `com.ninochavez.local-meeting-notes`
- Version: `0.5.1`
- Executable SHA-256: `e6c0eebca1c02d58e8c52510c43b586903ab030123f2b336f5ebaedac6af69af`
- Executable size: `15,066,400` bytes
- Signature: local ad-hoc signature; `codesign --verify --deep --strict` passes

This is a local verification bundle. It is not a notarized or distribution-signed release.

## Installed-window evidence

The integrated Tauri app opened its real retained Library data and selected the retained meeting's Transcript tab. The accessibility tree exposed the main navigation, meeting list, five meeting tabs, source-of-record copy, and the retained-transcript action.

Command–Comma opened `Capture — Yawn Settings` as a separate 720×560 window. Its accessibility tree exposed seven tabs and one complete Capture pane. The pane reported measured permission truth without asking for access. Both device selectors remained disabled and named the implemented system defaults.

Keyboard evidence in that installed Settings window:

- End selected and focused About
- Home returned to Capture
- Right selected and focused Privacy
- the native close button returned focus to the main Yawn window
- Command–Comma reopened Settings on the remembered About pane
- zoom and minimize were unavailable; native close remained available

The first installed pass found two production-only layout defects: the retained-meeting list inherited a horizontal strip breakpoint, and a long title squeezed the locality label. The final CSS correction restores a vertical list, removes horizontal overflow from the product rail, and stacks the locality label under the title. The current signed bundle was then quit, relaunched, and captured again. Its real meeting list rendered vertically without horizontal scrollbars, and the locality label stayed below the long title.

The current bundle also reopened Settings on the remembered About pane. Keyboard focus then moved to Capture with a visible blue ring. The 720×560 Capture window retained its measured permission copy and disabled device controls after the rebuild.

DS-2 separately proved the isolated native Settings reference in both appearances, at 720×560, including App-menu entry, Command–Comma, focus, close, reopen, and pane restoration.

The current integrated bundle was then clamped to the declared 720×560 primary-window minimum and captured like-for-like in macOS Light and Dark appearances. The same installed process opened Capture Settings at its fixed 720×560 geometry in both appearances. The primary action, local meeting list, selected Transcript tab, locality label, Settings entry, permission truth, and disabled device controls remained present. No page-level horizontal scrollbar appeared. macOS was returned to its original Dark appearance after the check.

Pre-correction native captures retained for comparison:

- [Primary window — Light, 720×560](desktop-design-system-verification/installed-main-720x560-light.jpg)
- [Primary window — Dark, 720×560](desktop-design-system-verification/installed-main-720x560-dark.jpg)
- [Capture Settings — Light, 720×560](desktop-design-system-verification/installed-settings-720x560-light.jpg)
- [Capture Settings — Dark, 720×560](desktop-design-system-verification/installed-settings-720x560-dark.jpg)

### Operator correction: window movement and native fit

The operator rejected the first integrated primary window after using it. The window resized but would not move, and the screen still read as a styled web dashboard rather than a Mac application. That direct evidence reopens the human Comparison gate even though the earlier automated appearance and geometry checks remain valid.

The movement defect was mechanical: the overlay header declared a Tauri drag region, but the main-window capability did not grant the narrow `core:window:allow-start-dragging` permission. The corrected bundle grants that permission and uses the deep drag-region contract so noninteractive title-bar content participates while toolbar buttons remain clickable.

The same correction removes the inner rounded web-window frame, makes the three panes fill the native window, restores desktop-scale record type, tightens sidebar and list density, neutralizes dark chrome, and replaces the dashed transcript card with a quiet content-unavailable treatment. Product behavior and the selected Mac Split composition are unchanged.

- [Operator-rejected primary window](desktop-design-system-verification/operator-rejected-main-dark.jpg)
- [Corrected installed primary window](desktop-design-system-verification/installed-main-native-correction-dark.jpg)

The rebuilt, ad-hoc-signed bundle passed a Computer Use drag action on the corrected title bar and remained interactive with the retained Transcript selected. This is implementation evidence, not human approval of the corrected visual result.

Because this correction changes shared appearance tokens, record scale, and primary-window geometry, the earlier installed Light/Dark and exact-minimum captures no longer close those rows for the current bundle. Rerun them only after the corrected visual direction receives human approval.

## Browser interaction evidence

These checks used the production DOM with the explicit synthetic prototype adapter. They did not open an audio device or prove native window behavior.

- Primary window: 1120×720 and 720×560; no page-level horizontal overflow
- Appearance: light and dark, like-for-like at 1120×720
- Motion: reduced-motion media behavior active
- Keyboard: meeting tabs moved with End, Home, and Right; keyboard focus computed a 2px solid focus ring after the shared reset fix
- Settings: 720×560, seven stable tabs, Home/End/Right movement, no horizontal overflow
- Capture: consent remained blocked until all three attestations and retention were supplied
- Lifecycle: consent → arming → recording → degraded recording → processing → selected meeting
- Completion: the selected meeting opened with Transcript selected and its panel visible
- Product truth: the browser surface said it was a preview and opened no microphone or system-audio device

## Acceptance matrix

| Check | Result | Evidence | Still open |
|---|---|---|---|
| Installed Tauri app | Partial | The current bundle passed the main-window and Settings screenshot/interaction walk, including real retained data, Transcript selection, Command–Comma, keyboard focus, native close, and restoration | Recording, degraded recording, and processing were not driven with live audio in the installed app |
| Appearance | Partial after correction | The corrected integrated primary window was captured in installed Dark appearance; pre-correction Light/Dark captures remain as comparison evidence | Rerun current installed Light/Dark like-for-like after human approval |
| Geometry | Partial after correction | The corrected primary window filled its native panes at comfortable size without hiding critical actions; Settings remains fixed at 720×560 | Rerun the corrected primary window at exact 720×560 after human approval |
| Keyboard | Partial | Browser tab paths and installed Settings pane paths passed; Command–Comma passed | Space/Return and safe Escape need a current installed walk across all three migrated surfaces |
| Accessibility | Partial | AX labels were present; browser focus, reduced motion, contrast tokens, transparency tokens, and zoom modes are test-covered | Spoken VoiceOver, current installed increased contrast, reduced transparency, and 200% zoom are unproven |
| States | Partial | Automated and browser references cover loading, empty, ready, disabled, selected, error, degraded, stopping, failure, and recovered presentations | Real-device capture and interrupted recovery were not run in this package |
| Product truth | Pass | Tests, visible copy, and installed AX output keep Planned, synthetic, local-only, consent, and permission boundaries explicit | A cold operator has not reviewed the wording |
| Consistency | Pass for migrated surfaces | Production imports foundations → components → patterns; migrated jobs use `ys-*`; remaining local jobs are listed in the migration ledger | The ledger must reach zero before the interim handoff retires |
| Comparison | Open after correction | The operator explicitly rejected the pre-correction installed screen; the corrected bundle now matches the SwiftUI reference's density and full-window pane behavior more closely | Human approval of the corrected installed bundle remains required |

## Decisive automated checks

```text
npm run test:ui
95 passed; 0 failed

cargo test -p local-meeting-notes-desktop --test shell_contract
34 passed; 0 failed

cargo test -p local-meeting-notes-desktop
passed

node --check ui/main.js
passed

node --check ui/settings.js
passed

git diff --check
clean

npm run build
passed; Yawn.app produced

codesign --verify --deep --strict target/release/bundle/macos/Yawn.app
passed
```

## Claims this receipt does not make

- VoiceOver quality is not proven by an accessibility tree.
- Browser renders do not prove native quality.
- The synthetic lifecycle does not prove real microphone, system-audio, file-closure, or transcription behavior.
- Prior operator comparison does not equal approval of this final build.
- No cold-operator comprehension, release readiness, notarization, or distribution claim was tested.
