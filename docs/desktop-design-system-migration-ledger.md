# Desktop design-system migration ledger

**Updated:** 2026-08-09

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
| Settings → Desktop Behavior | native View menu plus `ys-settings-pane` radio rows | Automatic, Focus, and Library share one persisted closed vocabulary. `View → Layout` and Settings update the same durable preference immediately. Pane collapse is a safety behavior, not a second preference. |
| Settings → Voice profile | `ys-settings-pane`, `ys-settings-section`, `ys-radio-choice`, `ys-inline-notice`, `ys-confirmation`, and the eight existing named profile commands | The native Voice pane now owns the existing enrollment, measured-option, preservation, and reset flow. The production first-run entry opens that pane. The browser `profile-screen` remains an evidence-only fallback. Source contracts cover the wiring; installed appearance, lifecycle behavior, keyboard order, VoiceOver, and human review remain open. |
| Consent and arming | `ys-capture-utility`, `ys-disclosure-row`, `ys-select`, `ys-actions`, `ys-button`, `ys-inline-notice` | Existing consent, retention, and start behavior remains authoritative. Route visibility now uses semantic `hidden` state so returning from Consent restores the selected meeting to the installed accessibility tree. |
| Recording and degraded recording | `ys-capture-utility`, `ys-status`, `ys-button`, `ys-inline-notice` | Live green remains separate from the brand accent. Degraded capture keeps recording truth and the affected channel visible. |
| Stopping and processing | `ys-capture-utility`, `ys-status`, `ys-progress-row`, `ys-inline-notice` | Processing remains local and does not imply completion before the reducer reports it. |
| Transcript-ready handoff | selected-meeting record plus `ys-tabs` | Completion reopens the retained meeting by durable ID and selects Transcript directly. The temporary workflow transcript no longer flashes before the stable record route. After handoff, the global action becomes **Record another meeting**; the retained transcript remains reachable from Meetings and the transcript-ready status control. |
| Focus foundation | shared `:focus-visible` rule | The neutral control reset now uses `:where(...)`, so roving `tabindex` cannot suppress the focus ring. |

The accepted surfaces resolve shared jobs through `ys-*` components. Legacy selectors remain only where an unmigrated screen or an explicit comparison mode still consumes them. They were not bulk-deleted because that would change inherited behavior outside DS-4.

## Retired from production

| Surface | What changed |
|---|---|
| Legacy Home review markup | Removed the hidden `home-screen`, its local journey/card styles, and every Home return path. Meetings is now the product root in both installed and synthetic routes; the review plan names the explicit `prototype-meeting-screen` fixture instead. |

## Remaining production migrations and installed evidence

| Priority | Surface or state | Current owner | Required next evidence |
|---|---|---|---|
| 1 | Startup, installation check, first run, permission denied/unavailable, repair, fatal error | `ys-capture-utility`, `ys-status`, `ys-inline-notice`, `ys-actions`, and the existing state reducers | The shared operational utility now owns the bounded panel and its state/status/action grammar. Installed cold launch, each permission branch, keyboard order, VoiceOver, recovery wording, and minimum geometry remain open. |
| 2 | Ask/Search and search results | `ys-search`, `ys-inline-notice`, `ys-button`, and existing retrieval commands | The shared source-first pattern now owns empty, query, results, notices, passage quotes, preparation, and result controls. Exact-result return revalidates the current local query; meaning-result return focuses the original wording without rerunning the model. Installed light/dark and minimum geometry, pointer activation, keyboard order/return, VoiceOver, live retained-source truth, and human review remain open. |
| 3 | Planned Actions prototype | hidden `promises-screen` and local action-table styles | Keep out of production navigation until product authority exists; then admit and migrate it or remove it. |
| 4 | Settings → Privacy | native placeholder plus legacy `settings-panel-privacy` | Real controls and authority boundary, native appearance/geometry, keyboard and VoiceOver |
| 5 | Settings → Connections | native placeholder plus legacy `settings-panel-connections` | Keep all account, sync, sharing, and calendar paths unavailable until product authority exists |
| 6 | Settings → Shortcuts and About | native placeholders plus legacy settings/prototype styles | Admit only implemented shortcuts and version/data truth; verify both in Tauri |
| 7 | Full retained transcript and source inspection | `library-transcript-screen` and local transcript styles | Durable-ID reopen, withheld speech, copied text, keyboard return, minimum geometry |
| 8 | Start-transition and interrupted recovery | `start-meeting-error-screen` plus local error styles | Installed command failure, retry, dismissal, focus return, no false completion |
| 9 | Help and system-state review | `help-screen`, `state-review-screen` and local reference styles | Decide whether each remains an operator-only surface; migrate or remove before release |
| 10 | Quick control and command menu | prototype-only popover/backdrop and local overlay styles | Admit product behavior first; then verify focus trap/return, Escape, status truth, and native layering |
| 11 | Superseded desktop-behavior dialog | prototype-only dialog and local styles | Remove after the comparison harness points to the native Desktop Behavior pane. It no longer owns product behavior. |
| 12 | Voice-profile reset, recording deletion, meeting deletion | local confirmation blocks | Shared confirmation/dialog pattern, destructive wording, separate confirmation, keyboard and VoiceOver |
| 13 | Prototype meeting and retained comparison modes | `prototype-meeting-screen`, wireframe/document/reference calibrations | Keep as evidence-only until the production replacement has an equal or better deterministic harness; never expose them as shipped features |

## Latest installed review

| Surface ID | Current atomic standing | Latest run |
|---|---|---|
| `main.shell` | `unproven` — the final executable cold-launched through installation checking to the retained Meetings root in Dark at comfortable geometry. Light, minimum, confirmed drag coordinates, minimize, other lifecycle states, and human review remain open. The broader `74160b48` run is historical evidence only | `2026-08-09-531ec638-layout` |
| `main.library` | `unproven` — the final executable showed retained meeting context beside the selected record. Automatic/Focus/Library switching and pane thresholds passed on `74160b48` but must be rerun for the final digest | `2026-08-09-531ec638-layout` |
| `meeting.record` | `unproven` — the final executable rendered one retained record and its Transcript tab in Dark. Light, minimum, remaining tabs, fallbacks, and human review stay open | `2026-08-09-531ec638-layout` |
| `meeting.transcript` | `unproven` — the final View transcript action landed directly on the retained meeting Transcript tab and stayed there. The full reader, withheld restoration, search return, long content, and human review remain open | `2026-08-09-531ec638-layout` |
| `settings.capture` | `unproven` — fixed geometry, native open/close/reopen, pane restoration, and keyboard tabs/focus pass in Light and Dark. The first installed pass found clipped Consent Review; the corrected 720×560 bundle keeps it visible. Remaining permission states, Check Again, VoiceOver, and human review stay open | `2026-08-09-972ef3c9` |
| `settings.remaining` | `unproven` — Desktop Behavior rendered without clipping, saved all three layout choices, and stayed synchronized with View → Layout on `74160b48`. macOS locked before the final-digest rerun; Light appearance, keyboard traversal, other panes, VoiceOver, and human review remain open | `2026-08-09-74160b48-layout` |
| `settings.voice` | `unproven` — source wiring moves the existing lifecycle into native Settings and routes first-run there. No installed run has checked the pane’s appearance, state transitions, storage-event pane handoff, destructive confirmation, keyboard order, VoiceOver, or human comprehension | not yet run after source migration |
| `prototype.references` | `pass` — the separately identified installed synthetic bundle preserves its watermark and Consent Back restores the selected meeting, tab group, and note subtree | `2026-08-09-ui-review-cf5f303c` |
| all other plan surfaces | `unproven` | latest applicable historical run; not rerun for `74160b48` |

## Legacy CSS removal ledger

These local groups remain because the rows above still use them:

- startup, first-run, help, state-review, and error layouts
- hidden Home and planned Actions reference layouts, Ask/Search, and full-transcript layouts
- browser-only voice-profile enrollment, operating-point, preservation, and reset layouts for the evidence-only `profile-screen` fallback
- command menu, quick control, desktop preview, and destructive confirmations
- wireframe, document, native-reference, and synthetic prototype comparison rules

For each future row, migrate behavior first, add installed evidence, then delete the now-unreferenced selector group. Do not replace the remaining stylesheet in one pass. The reducers, command allowlists, durable IDs, and retained-content truth stay authoritative throughout the migration.
