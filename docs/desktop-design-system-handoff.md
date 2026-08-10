# Desktop design-system rebaseline — execution handoff

**Status:** active interim plan
**Opened:** 2026-08-09
**Retire when:** the three installed reference surfaces pass the acceptance matrix,
the shared components own production use, and the migration ledger is empty.

## The next work is a system correction, not another styling pass

Keep one Meetings route and retained-record model. Automatic, Focus, and Library
may vary pane visibility, with Mac Split retained as the wide Library reference.
Stop applying the meeting-record grammar to every route. Build one desktop UI
system that distinguishes the main window, meeting record, Settings window,
capture utilities, and transient layers. Prove it in installed Tauri before
migrating the remaining screens.

The current browser prototype is useful for journeys and state coverage. It is not
evidence that Yawn feels native. The 2026-08-09 operator comparison found Settings
replacing the whole app, large unused canvases, report-like rows, and overlapping
screen-specific CSS. Those are system defects. More token tuning cannot close them.

## Reader contract

- **Reader:** a successor implementation session and the operator reviewing its work.
- **Job:** implement and judge one coherent Mac desktop system without reconstructing
  this conversation.
- **Assumed knowledge:** ordinary web, Tauri, CSS, JavaScript, Rust, and macOS app
  conventions; no knowledge of the prior session chronology.
- **Plainness:** practitioner.
- **Precision locks:** Tauri remains the implementation baseline; Meetings remains
  the root; layout preference changes pane visibility, not routes or content; no
  native-quality claim comes from Chrome; Planned,
  Partial, and synthetic evidence do not become shipped features; live capture green
  remains separate from brand terracotta.
- **Copy sources:** `DIRECTION.md`, `DESIGN.md`, `docs/screens-and-states.md`,
  `docs/journeys.md`, `docs/ui-ux-shell-audit.md`, and the product source under
  `apps/desktop/`.

## Authority and evidence

Use the sources in this order when they disagree:

1. Product scope and behavior: `product-definition.md`.
2. Admitted executable behavior: current state reducers and their tests.
3. Surface and journey detail: `docs/screens-and-states.md` and
   `docs/journeys.md`, subject to later product-definition amendments.
4. Art direction: `DIRECTION.md` and its ledger.
5. Design-system decisions: `DESIGN.md`.
6. This execution plan.
7. Prior screenshots, comparison notes, and prototype modes.

Apple's Human Interface Guidelines set the behavior floor:

- [Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/)
- [Windows](https://developer.apple.com/design/human-interface-guidelines/windows)
- [Settings](https://developer.apple.com/design/human-interface-guidelines/settings)
- [Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)

Comparator evidence supplies patterns, not authority. Use Wispr for containment,
control density, hierarchy, and transient layering. Use Granola for the meeting as
the organizing object, source inspection, and retrieval. Cloud, sharing, calendar,
generated-summary, and account capabilities must not appear current or authorized in
the DS-1 specimen. Some remain possible Phase 2 directions, but their visible,
refusable egress and product contracts are outside this package.

## The system to build

### 1. Window roles

| Role | Initial reference | Required behavior |
|---|---|---|
| Primary application window | Library plus selected meeting | Native frame and toolbar, resizable split view, persistent context, remembered size and selection |
| Meeting record | Selected meeting Note and Transcript | Reading measure, progressive disclosure, restrained record type, evidence one action away |
| Auxiliary settings window | Capture pane | App-menu entry, Command–Comma, stable noncustomizable pane toolbar, active-pane title, most recent pane restored, pane-specific size, dimmed minimize and maximize controls, native close behavior |
| Capture utility | Consent through active capture | Compact hierarchy, unmistakable state, continued operation through recoverable degradation, no unrelated navigation |
| Transient layer | Command menu and destructive confirmation | Temporary task, retained context, focus return, Escape dismissal where safe |

### 2. Foundations

Define once and exercise in light and dark mode:

- UI and record type roles, sizes, weights, line heights, and tabular numerals
- spacing and density scales
- window, navigation, content, selected, overlay, and control surface roles
- brand, live capture, success, warning, error, information, and locality semantics
- control heights, radii, borders, shadows, focus rings, and disabled states
- SF Symbols or one equivalent symbol vocabulary
- motion, reduced motion, increased contrast, and reduced transparency

Do not choose glass by appearance. Material is a functional navigation or control
layer. It is not the meeting content background and cannot replace hierarchy.
Desktop controls default to 28×28pt or larger; Apple's 20×20pt macOS minimum is
reserved for constrained, noncritical controls. A web specimen can represent these
contracts but cannot prove native material, window, toolbar, or accessibility behavior.

### 3. Shared components

The first implementation set is deliberately small:

- window toolbar, status item, toolbar button, and primary action
- product sidebar row, meeting-list row, disclosure row, and empty row
- text tab, segmented filter, ordinary button, icon button, and menu item
- grouped settings section, settings row, select, toggle, radio choice, and help text
- status indicator, inline notice, progress row, confirmation, popover, and dialog

Each component includes default, hover, active, focus-visible, disabled, selected,
error, and dark-mode behavior where applicable. A component is not complete while a
production screen still carries a competing local implementation of the same job.

### 4. Reference patterns

Build and approve these before broad migration:

1. **Library plus selected meeting** — proves primary chrome, split view, list,
   record, tabs, status, empty state, and resizing. The record exercises a
   populated operator note, transcript-only, metadata-only/no-transcript,
   summary-failed with a retained transcript, transcript-unavailable, and
   meeting-unavailable states. Automatic notes remain unavailable.
2. **Settings → Capture** — proves the auxiliary window, pane navigation, grouped
   controls, permission state, forms, and Command–Comma behavior.
3. **Consent → arming → recording → degraded recording → stopping → processing →
   transcript ready** — proves operational hierarchy, the non-recording countdown,
   live and degraded state, safe file closure, progress, and focus behavior. Failure
   and recovered interruption remain explicit and never read as complete.

Ask, Actions, retained Transcript, remaining Settings panes, and first run migrate
only after these references pass. Voice enrolment, Shortcuts, and About now have
source integration in native Settings, but each still needs the installed acceptance
matrix before it can count as an approved native migration.

## Work packages and ownership

The packages are designed for isolated worktrees. No producer edits another
producer's owned path. The integration package owns the final migration and may
change shared production files after reviewing producer commits.

### DS-1 — foundations and executable specimen

**Owns:** `DESIGN.md`, `DIRECTION.md`, this plan, and a new isolated design-system
specimen and shared foundation/component assets under `apps/desktop/ui/system/`.

**Deliver:** foundations, component states, window-role specimens, light/dark and
accessibility controls, honest capture and record fallbacks, and deterministic UI
tests. Do not restyle production screens in this package.

### DS-2 — native Settings-window proof

**Owns:** a bounded Settings reference implementation and the smallest Tauri/Rust
proof needed to open and restore an auxiliary Settings window. Keep experimental
markup and styles isolated from the production route until integration.

**Deliver:** App-menu and Command–Comma entry, one Capture pane, stable navigation,
focus and close behavior, remembered pane, light/dark rendering, and a written list
of platform behavior that the webview cannot supply by CSS.

### DS-3 — primary and capture reference patterns

**Owns:** isolated primary-window and capture specimens built from the shared
contract. Do not modify the Settings proof.

**Deliver:** Library plus selected meeting; consent, arming, recording, degraded,
stopping, processing, transcript-ready, failure, and recovered states; minimum and
comfortable geometry; keyboard paths; and a migration map from every current selector
to a shared component or documented exception.

### DS-4 — integration, migration, and verification

**Starts after:** DS-1, DS-2, and DS-3 each produce a reviewed commit and receipt.

**Owns:** production `apps/desktop/ui/index.html`, `main.js`, `styles.css`,
`native-calibration.css`, Tauri window wiring, and shell tests.

**Deliver:** merge the approved patterns, remove superseded local implementations,
migrate the three reference surfaces, run the acceptance matrix, and leave an
explicit ledger for remaining screen migrations. Do not widen feature scope or claim
that placeholder behavior shipped.

## Acceptance matrix

Every reference surface must pass all rows. A browser pass cannot substitute for an
installed-app row.

The durable execution and evidence contract is
[`desktop-installed-app-review.md`](desktop-installed-app-review.md). Retirement
requires a validated digest-bound run plus an explicit operator verdict. Historical
screenshots or receipts for another executable cannot close the current matrix.

| Check | Required evidence |
|---|---|
| Installed Tauri app | Screenshot and interaction walk in the actual window |
| Appearance | Light and dark, compared like-for-like |
| Geometry | Comfortable size and declared minimum size; no hidden critical action |
| Keyboard | Tab order, Space/Return activation, Escape where safe, Command–Comma for Settings, documented shortcuts |
| Accessibility | VoiceOver labels, focus visible, reduced motion, increased contrast, reduced transparency, 200% zoom |
| States | Loading, empty, ready, disabled, selected, error, and degraded where relevant |
| Product truth | No Planned or synthetic control appears live; no egress or recording claim exceeds evidence |
| Consistency | Shared jobs resolve to one component; local overrides have a documented state reason |
| Comparison | Primary window, Settings, and capture each reviewed beside the most relevant comparable app |

## Current repository state

The handoff was written over an uncommitted working tree on `main`. Preserve it.
At handoff time the modified paths were:

- `DESIGN.md`
- `DIRECTION.md`
- `docs/screens-and-states.md`
- `docs/ui-ux-shell-audit.md`
- `docs/desktop-design-system-handoff.md`
- `apps/desktop/src-tauri/tests/shell_contract.rs`
- `apps/desktop/ui/index.html`
- `apps/desktop/ui/main.js`
- `apps/desktop/ui/native-calibration.css`
- `apps/desktop/ui/shell-references.test.mjs`

The inherited app changes predate this plan and remain evidence, not an approved
design-system baseline. Do not discard, reset, or silently commit them. Each successor
must stage only its owned paths. The integration session decides which inherited UI
changes survive after comparing them with the accepted reference patterns.

## Verification baseline

Re-derived immediately before this handoff:

```text
q npm run test:ui
ok

q cargo test -p local-meeting-notes-desktop --test shell_contract
34 passed; 0 failed

git diff --check
clean
```

These checks prove the current contracts pass. They do not prove native visual
quality, accessibility, cold-operator comprehension, or release readiness.
