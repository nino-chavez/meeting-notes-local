# Desktop design-system migration ledger

**Updated:** 2026-08-10

**Owner:** the next production UI integration package

**Retire this ledger when:** every row is migrated, removed, or recorded as a deliberate exception with its own acceptance evidence.

**Review authority:** `docs/desktop-installed-app-review.md`. The stable
`surface_id` values in `apps/desktop/ui/review/review-plan.json` bind future run
receipts to these migration rows. The current review run is recorded below; a
`fail` or `unproven` verdict keeps the row open.

## Migrated in DS-4

| Surface | Shared production owner | What changed |
|---|---|---|
| Library and selected meeting | `ys-toolbar`, `ys-sidebar-row`, `ys-meeting-row`, `ys-primary-split`, `ys-primary-list`, `ys-meeting-list-pane`, `ys-record`, `ys-meeting-record`, `ys-tabs`, `ys-tab` | One route and record model now supports three visibility preferences. Automatic shows list plus record above 800px and one pane below it. Focus always uses one pane. Library shows sources, list, and record above 900px, then yields sources before the record becomes narrow. Meetings is the stable collection root. |
| Settings → Capture | `ys-window`, `ys-settings-toolbar`, `ys-settings-pane`, `ys-button`, `ys-select`, `ys-status`, with pane-local flat setting groups | Capture lives in a fixed 720×560 native Settings window. Flat divider rows replace the scrollable report-card composition. The pane reads permission status only. It does not request access or invent device choice. |
| Settings → Desktop Behavior | native View menu plus `ys-settings-pane` rows and layout radios | Automatic, Focus, and Library share one persisted closed vocabulary. `View → Layout` and Settings update the same durable preference immediately. The pane also states the runtime-verified window boundary: close hides, Quit exits, and no system-notification path is active. Pane collapse is a safety behavior, not a second preference. |
| Settings → Voice profile | `ys-settings-pane`, `ys-settings-section`, `ys-radio-choice`, `ys-inline-notice`, `ys-confirmation`, and the eight existing named profile commands | The native Voice pane now owns the existing enrollment, measured-option, preservation, and reset flow. The production first-run entry opens that pane. The browser `profile-screen` remains an evidence-only fallback. Source contracts cover the wiring; installed appearance, lifecycle behavior, keyboard order, VoiceOver, and human review remain open. |
| Settings → Shortcuts and About | `ys-settings-pane`, `ys-settings-section`, `ys-settings-row`, and `ys-inline-notice` | The native panes now list only installed routes and current product boundaries: Meetings, Search, Settings, native About, local-only data, no account, and unavailable automatic notes/actions. Source contracts cover the copy and shortcuts. Installed appearance, keyboard traversal, VoiceOver, and human review remain open. |
| Consent and arming | `ys-capture-utility`, `ys-disclosure-row`, `ys-select`, `ys-actions`, `ys-button`, `ys-inline-notice` | Existing consent, retention, and start behavior remains authoritative. Route visibility now uses semantic `hidden` state so returning from Consent restores the selected meeting to the installed accessibility tree. |
| Recording and degraded recording | `ys-capture-utility`, `ys-status`, `ys-button`, `ys-inline-notice` | Live green remains separate from the brand accent. Degraded capture keeps recording truth and the affected channel visible. |
| Stopping and processing | `ys-capture-utility`, `ys-status`, `ys-progress-row`, `ys-inline-notice` | Processing remains local and does not imply completion before the reducer reports it. |
| Transcript-ready handoff | selected-meeting record plus `ys-tabs` | Completion reopens the retained meeting by durable ID and selects Transcript directly. The temporary workflow transcript no longer flashes before the stable record route. After handoff, the global action becomes **Record another meeting**; the retained transcript remains reachable from Meetings and the transcript-ready status control. |
| Retained transcript reader | `ys-record`, `ys-transcript`, `ys-inline-notice`, `ys-actions`, and `ys-button` | The direct post-capture and retained-meeting readers now share one record heading, warning, copy, source-turn, match, and restoration grammar. The renderer still withholds text before it can reach the DOM, and restoration remains bound to the existing durable transcript identity. Source contracts cover that wiring; installed appearance, long-content behavior, keyboard order, VoiceOver, and human review remain open. |
| Meeting and recording deletion confirmations | `ys-confirmation`, `ys-inline-notice`, `ys-actions`, and `ys-button` | The existing reveal, cancel, focus, and confirmed-command flow now uses the shared destructive confirmation grammar. It still distinguishes recording-only deletion from whole-meeting deletion, keeps the consequence text visible, and never relies on a browser confirmation dialog. Source contracts cover that wiring; installed appearance, keyboard order, VoiceOver, and human review remain open. |
| Focus foundation | shared `:focus-visible` rule | The neutral control reset now uses `:where(...)`, so roving `tabindex` cannot suppress the focus ring. |

The accepted surfaces resolve shared jobs through `ys-*` components. Legacy selectors remain only where an unmigrated screen or an explicit comparison mode still consumes them. They were not bulk-deleted because that would change inherited behavior outside DS-4.

## Retired from production

| Surface | What changed |
|---|---|
| Legacy Home review markup | Removed the hidden `home-screen`, its local journey/card styles, and every Home return path. Meetings is now the product root in both installed and synthetic routes; the review plan names the explicit `prototype-meeting-screen` fixture instead. |
| Superseded desktop-behavior dialog | Removed the synthetic hide-to-menubar dialog, its focus trap, and its local styles. Native Settings now presents the source-verified window boundary beside the persisted layout control; this still needs installed review. |

## Remaining production migrations and installed evidence

| Priority | Surface or state | Current owner | Required next evidence |
|---|---|---|---|
| 1 | Startup, installation check, first run, permission denied/unavailable, repair, fatal error | `ys-capture-utility`, `ys-status`, `ys-inline-notice`, `ys-actions`, and the existing state reducers | The shared operational utility now owns the bounded panel and its state/status/action grammar. Installed cold launch, each permission branch, keyboard order, VoiceOver, recovery wording, and minimum geometry remain open. |
| 2 | Ask/Search and search results | `ys-search`, `ys-inline-notice`, `ys-button`, and existing retrieval commands | The shared source-first pattern now owns empty, query, results, notices, passage quotes, preparation, and result controls. Exact-result return revalidates the current local query; meaning-result return focuses the original wording without rerunning the model. Installed light/dark and minimum geometry, pointer activation, keyboard order/return, VoiceOver, live retained-source truth, and human review remain open. |
| 3 | Planned Actions prototype | hidden `promises-screen` and local action-table styles | Keep out of production navigation until product authority exists; then admit and migrate it or remove it. |
| 4 | Settings → Privacy | native placeholder plus legacy `settings-panel-privacy` | Real controls and authority boundary, native appearance/geometry, keyboard and VoiceOver |
| 5 | Settings → Connections | native placeholder plus legacy `settings-panel-connections` | Keep all account, sync, sharing, and calendar paths unavailable until product authority exists |
| 6 | Retained transcript reader installed review | `ys-record`, `ys-transcript`, and existing transcript/restore commands | Durable-ID reopen, withheld restoration, copied text, exact-search return, keyboard return, long content, minimum geometry, Light/Dark, VoiceOver, and human review |
| 7 | Start-transition and interrupted recovery | `start-meeting-error-screen` plus local error styles | Installed command failure, retry, dismissal, focus return, no false completion |
| 8 | Help and system-state review | `help-screen`, `state-review-screen` and local reference styles | Decide whether each remains an operator-only surface; migrate or remove before release |
| 9 | Quick control and command menu | prototype-only popover/backdrop and local overlay styles | Admit product behavior first; then verify focus trap/return, Escape, status truth, and native layering |
| 10 | Destructive-confirmation installed review | `ys-confirmation`, existing delete/reset commands, and the browser-only profile fallback | Separate confirmation, destructive wording, keyboard order, focus return, VoiceOver, and human review |
| 11 | Prototype meeting and retained comparison modes | `prototype-meeting-screen`, wireframe/document/reference calibrations | Keep as evidence-only until the production replacement has an equal or better deterministic harness; never expose them as shipped features |

## Latest installed review

The current prepared product run is `2026-08-10-8c341b16-signing`. It binds the
clean source commit and strictly verified local bundle. It records one
agent-assisted Desktop Settings observation; all 127 checks remain `unproven`
because the full state, appearance, geometry, interaction, and human requirements
are still open. The table keeps the latest evidence-bearing run for each surface,
which remains historical until that surface is rerun for the current executable.

| Surface ID | Current atomic standing | Latest run |
|---|---|---|
| `main.shell` | `unproven` — the final executable cold-launched through installation checking to the retained Meetings root in Dark at comfortable geometry. Light, minimum, confirmed drag coordinates, minimize, other lifecycle states, and human review remain open. The broader `74160b48` run is historical evidence only | `2026-08-09-531ec638-layout` |
| `main.library` | `unproven` — the final executable showed retained meeting context beside the selected record. Automatic/Focus/Library switching and pane thresholds passed on `74160b48` but must be rerun for the final digest | `2026-08-09-531ec638-layout` |
| `meeting.record` | `unproven` — the final executable rendered one retained record and its Transcript tab in Dark. Light, minimum, remaining tabs, fallbacks, and human review stay open | `2026-08-09-531ec638-layout` |
| `meeting.transcript` | `unproven` — source migration now gives both transcript routes one retained-record reader while preserving the existing withheld-text and restoration contract. No installed run has checked this source revision for appearance, long content, restoration, search return, keyboard order, VoiceOver, or human review | not yet run after source migration |
| `settings.capture` | `unproven` — fixed geometry, native open/close/reopen, pane restoration, and keyboard tabs/focus pass in Light and Dark. The first installed pass found clipped Consent Review; the corrected 720×560 bundle keeps it visible. Remaining permission states, Check Again, VoiceOver, and human review stay open | `2026-08-09-972ef3c9` |
| `settings.remaining` | `unproven` — Desktop Behavior rendered without clipping, saved all three layout choices, and stayed synchronized with View → Layout on `74160b48`. macOS locked before the final-digest rerun; Light appearance, keyboard traversal, other panes, VoiceOver, and human review remain open | `2026-08-09-74160b48-layout` |
| `settings.voice` | `unproven` — source wiring moves the existing lifecycle into native Settings and routes first-run there. No installed run has checked the pane’s appearance, state transitions, storage-event pane handoff, destructive confirmation, keyboard order, VoiceOver, or human comprehension | not yet run after source migration |
| `settings.shortcuts-about` | `unproven` — source wiring replaces the placeholders with the current installed routes and product boundary. No installed run has checked pane restoration, shortcut labels, keyboard traversal, VoiceOver, or human comprehension | not yet run after source migration |
| `prototype.references` | `pass` — the separately identified installed synthetic bundle preserves its watermark and Consent Back restores the selected meeting, tab group, and note subtree | `2026-08-09-ui-review-cf5f303c` |
| all other plan surfaces | `unproven` | latest applicable historical run; not rerun for `74160b48` |

## Legacy CSS removal ledger

These local groups remain because the rows above still use them:

- startup, first-run, help, state-review, and error layouts
- hidden Home and planned Actions reference layouts, plus browser comparison transcript rows
- browser-only voice-profile enrollment, operating-point, preservation, and reset layouts for the evidence-only `profile-screen` fallback
- browser-only Settings shortcut and About reference styles for the evidence-only `profile-screen` fallback
- command menu, quick control, and the browser-only profile-reset fallback
- wireframe, document, native-reference, and synthetic prototype comparison rules

For each future row, migrate behavior first, add installed evidence, then delete the now-unreferenced selector group. Do not replace the remaining stylesheet in one pass. The reducers, command allowlists, durable IDs, and retained-content truth stay authoritative throughout the migration.
