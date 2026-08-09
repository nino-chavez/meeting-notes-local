# DS-4 desktop design-system verification receipt

**Date:** 2026-08-09

**Scope:** production Library and selected meeting, native Settings → Capture, and consent through transcript handoff

**Outcome:** the integrated system is buildable, the automated contracts pass, and the current signed bundle was relaunched and exercised in its Tauri windows. Human and platform-assistive gates remain open below.

## What is in the current bundle

- App: `target/release/bundle/macos/Yawn.app`
- Bundle identifier: `com.ninochavez.local-meeting-notes`
- Version: `0.5.1`
- Executable SHA-256: `1607ad59c5dfe15482e413f6ca26a3011fd6ee474ced20d32d124ddb23526d49`
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

DS-2 separately proved the isolated native Settings reference in both appearances, at 720×560, including App-menu entry, Command–Comma, focus, close, reopen, and pane restoration. That accepted reference supports the appearance row. It does not prove the current integrated bundle in light appearance.

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
| Appearance | Partial | Integrated production passed light/dark browser comparison; isolated Settings passed both appearances in Tauri | Current integrated bundle needs like-for-like installed light/dark captures |
| Geometry | Partial | Post-fix browser passed 1120×720 and 720×560; current native Settings passed 720×560; the current primary window passed a resized installed inspection without hidden header action or horizontal scrollbar | The primary window was not measured at an exact installed 720×560 |
| Keyboard | Partial | Browser tab paths and installed Settings pane paths passed; Command–Comma passed | Space/Return and safe Escape need a current installed walk across all three migrated surfaces |
| Accessibility | Partial | AX labels were present; browser focus, reduced motion, contrast tokens, transparency tokens, and zoom modes are test-covered | Spoken VoiceOver, current installed increased contrast, reduced transparency, and 200% zoom are unproven |
| States | Partial | Automated and browser references cover loading, empty, ready, disabled, selected, error, degraded, stopping, failure, and recovered presentations | Real-device capture and interrupted recovery were not run in this package |
| Product truth | Pass | Tests, visible copy, and installed AX output keep Planned, synthetic, local-only, consent, and permission boundaries explicit | A cold operator has not reviewed the wording |
| Consistency | Pass for migrated surfaces | Production imports foundations → components → patterns; migrated jobs use `ys-*`; remaining local jobs are listed in the migration ledger | The ledger must reach zero before the interim handoff retires |
| Comparison | Partial | Primary structure follows the authorized Mac Split decision; Wispr and Granola roles and the SwiftUI reference were rechecked in the governing records | No new human side-by-side approval was performed on the final integrated bundle |

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
