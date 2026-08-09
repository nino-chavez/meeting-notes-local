# DS-3 migration map

This map covers the current CSS selectors that serve the Library, selected meeting,
consent, recording, degraded capture, processing, and transcript handoff. The focused
test extracts those selectors from `styles.css` and `native-calibration.css`. It fails
when a relevant selector matches no row in `migration-map.json`.

The map is intentionally by owned job rather than by stylesheet. A selector appearing
in both production stylesheets has one destination. DS-4 removes both local
implementations after the shared component owns production use.

| Current selector family | Destination | Classification | Migration rule |
|---|---|---|---|
| `.app-header`, header actions, global Record and Stop | `ds-window-toolbar` + `ds-button` | Shared component | Keep Record or Stop in the frame. Never move the critical action to a bottom dock. |
| Header state and `.quick-control*` | `ds-status-indicator` | Shared component | One reducer presentation supplies a word and a mark. Terracotta never means recording. |
| `.app-workspace` | `ds-primary-window-layout` | Shared component | Comfortable: sidebar + meeting list + record. Minimum: 96px product rail + meeting list + record. |
| `.app-sidebar`, `.product-nav*`, `.sidebar-*` | `ds-product-sidebar` + `ds-product-sidebar-row` | Shared component | Use roving vertical keyboard focus and `aria-current="page"`. |
| `.meeting-context*`, `.library-row`, `.library-list`, `.library-empty`, `.library-search*`, `.library-filter*` | `ds-meeting-list`, `ds-meeting-list-row`, `ds-empty-row` | Shared component | Loading, empty, selected, disabled, and error remain inside the list pane. |
| `.meeting-split-view`, `#meeting-detail-screen`, `.meeting-detail-content` | `ds-primary-window-layout` + `ds-meeting-record` | Shared component | Layout owns the split. The meeting record owns only its reading column. |
| `.meeting-workspace*`, `.meeting-heading*`, `.meeting-detail-state`, `.meeting-detail-back`, `.local-badge` | `ds-meeting-record-heading` + `ds-locality-badge` | Shared component | Heading contains meeting identity and time. Trust explanations stay beside the action they qualify. |
| `.meeting-tabs*`, `.retained-meeting-tabs`, `.meeting-tab-panel` | `ds-text-tabs` + `ds-meeting-tab-panel` | Shared component | Arrow, Home, and End move and select one tab. Tab shape is not reused as a filter. |
| `.meeting-claim*`, `.meeting-no-note`, `.meeting-retention`, `.note-generation*`, `.claim-*` | `ds-note-section`, `ds-source-link`, `ds-inline-notice` | Shared component | Preserve read order. Evidence remains one quiet action away. |
| `.workspace-empty*` | `ds-empty-row` | Shared component | Keep context and a truthful next action. Do not render a welcome or title card. |
| `.primary`, `.secondary`, `.text-button`, `.danger*`, `.screen-actions` | `ds-button` variants | Shared component | One height, radius, focus ring, and disabled treatment. Live green is reserved for live capture actions. |
| `.notice*`, `.form-error` | `ds-inline-notice` | Shared component | Information, warning, and error always include explicit text. |
| `#idle-screen`, `#start-form`, `.preflight-*`, `.check-row`, `.retention-field` | `ds-consent-pattern`, `ds-disclosure-row`, `ds-field-row` | State-specific exception | Attempt-scoped consent blocks Start. Yawn states that it did not notify anyone. |
| `#arming-screen`, `.capture-state*` | `ds-capture-arming-state` + `ds-status-indicator` | State-specific exception | Waiting for both channels must not look live. |
| `#recording-screen`, `.channel-grid`, `.channel-mark`, `.live-note*`, live kicker and health copy | `ds-capture-live-state`, `ds-capture-channel`, `ds-operator-note` | State-specific exception | Recording and degraded states keep a compact utility grammar and continue through recoverable loss. |
| `.capture-progress*`, `#processing-screen`, `.processing-card*`, `.processing-spinner` | `ds-progress-list` + `ds-progress-row` | Shared component | Use complete/current/pending rows. No ambient spinner or repeated four-step wizard. |
| `#transcript-screen`, transcript actions/turns, `.turn*`, `.result-handoff` | `ds-meeting-record`, `ds-transcript-turn`, `ds-button` | State-specific exception | Handoff exits capture into the retained meeting. The transcript remains the source of record. |

## DS-4 integration sequence

1. Cherry-pick the reviewed DS-1, DS-2, and DS-3 commits into the integration
   worktree. Resolve names against DS-1’s actual component API; keep the job mapping
   above even if DS-1 chose different class names.
2. Replace this specimen’s local foundation values with DS-1 foundation imports.
   Verify light, dark, reduced motion, increased contrast, and reduced transparency
   before moving markup.
3. Move the primary pattern into production first. Bind existing Library handles,
   selected meeting state, tabs, and transcript actions to shared components. Do not
   copy specimen data or the workbench controls.
4. Move consent, recording, degraded capture, and processing next. Keep the existing
   Rust reducer and command authority. The UI may present state; it must not create a
   second capture state machine.
5. For each migrated row, remove the matching rules from both `styles.css` and
   `native-calibration.css`. Run the migration coverage test after every family. A
   selector left behind needs a new documented state reason; visual similarity is not
   a reason.
6. Route finished capture into the selected retained meeting’s Transcript view. Keep
   the current copy and restoration truth until a separately admitted product change
   replaces it.
7. Integrate DS-2’s Settings window independently. Do not reuse either DS-3 window
   composition for Settings.
8. Run the handoff acceptance matrix in the installed Tauri app at 1120×720 and the
   720×560 primary minimum, plus the accepted capture-utility sizes. The browser
   screenshots in this package are comparison evidence only.
9. Delete the workbench and reference-only data only after the installed surfaces have
   matching reviewed evidence and `migration-map.json` reports no current selector in
   scope.

## Gates that remain outside DS-3

- Actual macOS titlebar, toolbar placement, window restoration, and menubar state.
- VoiceOver order and labels in the Tauri webview.
- Exact 200% zoom at the native minimum.
- Native increased-contrast and reduced-transparency behavior.
- Real capture, recovery, local data, and cold-operator acceptance.
- DS-1 component names and DS-2 Settings-window behavior until their reviewed commits
  are available to DS-4.
