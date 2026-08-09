# Desktop design-system migration ledger

**Updated:** 2026-08-09

**Owner:** the next production UI integration package

**Retire this ledger when:** every row is migrated, removed, or recorded as a deliberate exception with its own acceptance evidence.

## Migrated in DS-4

| Surface | Shared production owner | What changed |
|---|---|---|
| Library and selected meeting | `ys-toolbar`, `ys-sidebar-row`, `ys-meeting-row`, `ys-primary-split`, `ys-primary-list`, `ys-record`, `ys-tabs`, `ys-tab` | Mac Split remains the primary composition. Meeting rows are vertical at production breakpoints. Long titles keep the locality label below the heading. |
| Settings → Capture | `ys-window`, `ys-settings-toolbar`, `ys-settings-pane`, `ys-settings-section`, `ys-settings-row`, `ys-select`, `ys-toggle`, `ys-status` | Capture moved to a separate native Settings window. The pane reads permission status only. It does not request access or invent device choice. |
| Consent and arming | `ys-capture-utility`, `ys-disclosure-row`, `ys-select`, `ys-actions`, `ys-button`, `ys-inline-notice` | Existing consent, retention, and start behavior remains authoritative. |
| Recording and degraded recording | `ys-capture-utility`, `ys-status`, `ys-button`, `ys-inline-notice` | Live green remains separate from the brand accent. Degraded capture keeps recording truth and the affected channel visible. |
| Stopping and processing | `ys-capture-utility`, `ys-status`, `ys-progress-row`, `ys-inline-notice` | Processing remains local and does not imply completion before the reducer reports it. |
| Transcript-ready handoff | selected-meeting record plus `ys-tabs` | Completion reopens the retained meeting by durable ID and selects Transcript. |
| Focus foundation | shared `:focus-visible` rule | The neutral control reset now uses `:where(...)`, so roving `tabindex` cannot suppress the focus ring. |

The accepted surfaces resolve shared jobs through `ys-*` components. Legacy selectors remain only where an unmigrated screen or an explicit comparison mode still consumes them. They were not bulk-deleted because that would change inherited behavior outside DS-4.

## Remaining production migrations

| Priority | Surface or state | Current owner | Required next evidence |
|---|---|---|---|
| 1 | Startup, installation check, first run, permission denied/unavailable, repair, fatal error | `startup-screen`, `first-run-screen`, `error-screen` and local startup styles | Installed cold launch, each permission branch, keyboard order, VoiceOver, recovery wording, minimum geometry |
| 2 | Home | `home-screen` and local journey/card styles | Loading/empty/ready/error, primary-window geometry, keyboard and focus, product-truth review |
| 3 | Ask and search results | `find-screen` and local search/result styles | Empty/query/results/error, result activation, return focus, retained-source truth |
| 4 | Actions | `promises-screen` and local action-table styles | Empty/partial states, Planned labeling, keyboard table/list behavior, minimum geometry |
| 5 | Settings → Privacy | native placeholder plus legacy `settings-panel-privacy` | Real controls and authority boundary, native appearance/geometry, keyboard and VoiceOver |
| 6 | Settings → Connections | native placeholder plus legacy `settings-panel-connections` | Keep all account, sync, sharing, and calendar paths unavailable until product authority exists |
| 7 | Settings → Voice | native placeholder; measured workflow remains in `profile-screen` | Move enrollment, operating points, legacy preservation, and reset without changing reducer or confirmation behavior |
| 8 | Settings → Desktop, Shortcuts, About | native placeholders plus legacy settings/prototype styles | Admit only implemented window behavior; verify shortcuts and version/data truth in Tauri |
| 9 | Full retained transcript and source inspection | `library-transcript-screen` and local transcript styles | Durable-ID reopen, withheld speech, copied text, keyboard return, minimum geometry |
| 10 | Start-transition and interrupted recovery | `start-meeting-error-screen` plus local error styles | Installed command failure, retry, dismissal, focus return, no false completion |
| 11 | Help and system-state review | `help-screen`, `state-review-screen` and local reference styles | Decide whether each remains an operator-only surface; migrate or remove before release |
| 12 | Quick control and command menu | prototype-only popover/backdrop and local overlay styles | Admit product behavior first; then verify focus trap/return, Escape, status truth, and native layering |
| 13 | Desktop-behavior dialog | prototype-only dialog and local styles | Remove if the native Settings Desktop pane replaces it; otherwise document the distinct transient job |
| 14 | Voice-profile reset, recording deletion, meeting deletion | local confirmation blocks | Shared confirmation/dialog pattern, destructive wording, separate confirmation, keyboard and VoiceOver |
| 15 | Prototype meeting and retained comparison modes | `prototype-meeting-screen`, wireframe/document/reference calibrations | Keep as evidence-only until the production replacement has an equal or better deterministic harness; never expose them as shipped features |

## Legacy CSS removal ledger

These local groups remain because the rows above still use them:

- startup, first-run, help, state-review, and error layouts
- Home, Ask, Actions, and full-transcript layouts
- voice-profile enrollment, operating-point, preservation, and reset layouts
- command menu, quick control, desktop preview, and destructive confirmations
- wireframe, document, native-reference, and synthetic prototype comparison rules

For each future row, migrate behavior first, add installed evidence, then delete the now-unreferenced selector group. Do not replace the remaining stylesheet in one pass. The reducers, command allowlists, durable IDs, and retained-content truth stay authoritative throughout the migration.
