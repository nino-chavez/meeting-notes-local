---
# Hand-authored to the google-labs/design.md shape so impeccable's reader parses
# it. A DESIGN.md that parses to zero is worse than none — it makes a project
# look like it has a design system while the gate checks nothing.
# Colors must be string values ONE LEVEL under `colors:` (flat aliases, not
# nested maps); typography roles are read at `typography.<role>.fontFamily` and
# type steps at `typography.step-<name>.fontSize`. The radius key is `rounded:`,
# NOT `radii:` — `addRoundedScale` reads `frontmatter.rounded` and a `radii:`
# block parses to zero silently. Verified against impeccable's own reader.
schemaVersion: 1
name: local-meeting-notes
tagline: Meeting notes that never leave the machine
mode: light

colors:
  primary: "#425049"
  secondary: "#66706A"
  accent: "#843B31"
  capture-live: "#146B4A"
  neutral-50: "#FFFAF5"
  neutral-100: "#F2F0E9"
  neutral-200: "#EAE7DD"
  neutral-300: "#D8D4CA"
  neutral-400: "#AEB6B0"
  neutral-500: "#7D8781"
  neutral-600: "#66706A"
  neutral-700: "#4F5B55"
  neutral-800: "#425049"
  neutral-900: "#29332E"
  neutral-950: "#17201D"
  surface-base: "#F2F0E9"
  surface-raised: "#FFFAF5"
  surface-muted: "#EAE7DD"
  surface-overlay: "#FFFAF5"
  semantic-success: "#146B4A"
  semantic-error: "#9E3028"
  semantic-info: "#486A73"
  semantic-warning: "#8B5A2B"

typography:
  ui:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif"
  record:
    fontFamily: "Iowan Old Style, Palatino Linotype, Book Antiqua, Palatino, Georgia, serif"
  mono:
    fontFamily: "'JetBrains Mono', 'SF Mono', ui-monospace, Menlo, monospace"
  step-xs:
    fontSize: "11px"
  step-sm:
    fontSize: "13px"
  step-base:
    fontSize: "15px"
  step-lg:
    fontSize: "16px"
  step-xl:
    fontSize: "20px"
  step-2xl:
    fontSize: "36px"

rounded:
  none: "0px"
  sm: "2px"
  md: "5px"
  lg: "8px"
---

# DESIGN.md — local-meeting-notes

Visual rules and engineering rules together, so neither gets decided ad hoc
surface by surface. Answers to [`DIRECTION.md`](./DIRECTION.md); the L5
inventory it covers is [`docs/screens-and-states.md`](./docs/screens-and-states.md).

**System status — rebaseline required 2026-08-09:** Mac Split remains the
selected primary-window composition and installed Tauri baseline. Its persistent
product sidebar, meeting list, and selected record remain authorized. The later
claim that one visual grammar should also own Ask, Actions, Settings, consent,
capture, processing, and transcript handoff is withdrawn. It turned operational
surfaces into document pages and let page-level refinements drift without a shared
pattern layer. The browser prototype remains useful interaction evidence, not
native-quality approval. Paper Focus stays available as the complete planning wireframe at
`?prototype=1&calibration=wireframe`, and Document and Native Reference remain
comparison evidence. Native-window, VoiceOver, increased-contrast, and exact
200% zoom checks remain release gates. The active execution plan is
[`docs/desktop-design-system-handoff.md`](./docs/desktop-design-system-handoff.md).

---

## Color

**System-first shell, paper record.** Native window chrome, toolbar, sidebar,
active state, and controls come first. `surface-base` and `surface-muted` may
separate structural panes. Warm `surface-raised` belongs to a selected meeting
record or bounded input; it is not the global window identity.

**Brand and capture use different colors.** `accent` is Yawn terracotta. It may
carry identity, selection, and deliberate product emphasis. `capture-live` is
the dedicated healthy-recording color. It appears only when capture is active
and is always paired with a state word and a mark. A terracotta button never
means the microphone is open.

**Status semantics do not borrow the brand.** Success may share the live green
only outside capture controls and only with explicit text. Error uses red;
warning uses umber; information uses blue-green. Degraded capture changes its
wording and icon shape, not merely its hue.

**Contrast floors**, checked against `surface-base`, `surface-raised`, and
`surface-muted`: body text ≥ 4.5:1; large text and UI glyphs ≥ 3:1. No essential
state is conveyed by color alone.

**Dark mode adapts the semantic tokens instead of reusing the light values.**
Yawn terracotta becomes `#D98F80`; healthy live capture becomes `#68C999`.
Dark filled controls use dark ink (`#1C1B19` for brand, `#17201D` for live)
rather than white text. The dark shell separates window `#1D1D1C`, sidebar
`#222221`, meeting list `#282826`, and record `#2D2C2A` with dividers rather
than shadows.

## Type

Three roles, with a hard boundary between them. `record` is only for the title
of a retained or synthetic meeting or transcript artifact. `ui` owns navigation,
buttons, labels, status, settings, instructions, transcript turns, and all
operational copy. `mono` owns locators and machine-readable evidence; timestamps
remain tabular UI text.

The functional wireframe used a 13px base, 11px labels, and 10px badges. The
side-by-side review found that hierarchy too small and status-heavy beside a
finished Mac app. Native calibration uses 15px for primary reading text and
14px for navigation and controls; smaller text is reserved for secondary
metadata, not product-state taxonomy. The meeting title may reach 34–36px. A
serif title can signal "you are reading the record"; serif workflow chrome
remains a contract violation.

## Form

- **Structural panes have no shadows.** Adjacency, tone, and one-pixel borders
  establish their hierarchy. Popovers, menus, and modals may use one restrained
  shadow because they are real layers above the window.
- **No radius above `lg` (8px)** on app surfaces. Full pills are reserved for
  compact status or segmented controls whose shape carries grouping.
- **Control shape names the job.** Underlined text tabs change views within one
  meeting. A compact segmented control filters one collection. Buttons perform
  actions. These roles do not borrow one another's selected state.
- **No ambient motion.** No pulse, breath, shimmer, or looping gradient. The
  audio level meter is the sole exception, and only because it moves as a
  reading of arriving audio rather than as decoration.
- **One gesture, one value.** Any transition that appears on more than one
  surface is defined once as a named token, not re-typed per component. The
  photography record documents what happens otherwise: four implementations of a
  single hover treatment across one codebase.
- **Never stack two transition properties on one element** — both emit
  `transition-property` and one silently wins. Name them together:
  `transition-[transform,border-color]`.
- **Reduced motion is global**, set once at the root, not per component.

## Composition

- The window opens on the notes library with the most recent note already rendered
  beside it — real content in the first viewport, and still the operator's choice
  which note they came for. There is no dashboard. `DIRECTION.md § Constraints`
  carries the reason and the evidence: an earlier version of this line said the
  window opens *on* the last note, which is the pattern the operator rejected in a
  sibling project ("rather than assuming i want to go straight back to the last
  job/library/project").
- One action per surface. The consent notification is the strict case: record,
  decline, never-for-this-app — and nothing else competes with them.
- Progressive disclosure. The note is the reading surface; transcript, actions,
  evidence, and details stay available without competing in the first scan.
- The retained-meeting heading contains identity and time, not an explanation of
  the note model. Trust explanations belong beside the action or evidence they
  qualify. Repeated source actions render as quiet links rather than a stack of
  boxed buttons.
- Mac Split keeps product navigation, meeting context, and the selected record
  available at wide sizes. At the minimum desktop window, product navigation
  becomes a 96px rail and the meeting list remains visible. The list yields only
  below the desktop minimum.
- Consent, arming, recording, degradation, processing, and transcript handoff
  hide unrelated navigation. Capture truth remains in the integrated toolbar,
  so focus does not make listening state ambiguous.
- Capture screens name the current state in the heading and show progress in
  place. They do not repeat a four-step wizard above every operational state.
- Settings is an auxiliary Mac settings window, opened from the App menu and
  Command–Comma. It keeps stable pane navigation and sizes to its current pane;
  it is not a primary-window route with a page-bottom Back button.
- Paper Focus's transition remains interaction evidence, not the approved
  production composition. Document and Native Reference remain controls for
  future regression review.
- Record and Stop live in the integrated toolbar and the menubar state. A bottom
  bar cannot be their primary or only home.
- Empty states carry real content, never a title card. First run shows what a
  note will look like, not a welcome graphic.

## Surface roles and pattern ownership

Window role is decided before page composition, typography, or material. Related
surfaces share foundations and components; they do not share a universal layout.

| Role | Owns | Required grammar | Must not become |
|---|---|---|---|
| Primary application window | Meetings, Ask, Actions | Native frame and toolbar; sidebar or split view where hierarchy requires it; flexible resizing | A centered responsive webpage inside a large canvas |
| Meeting record | Note, Transcript, Actions, Evidence, Details | Calm reading measure, progressive disclosure, restrained record typography | The visual model for Settings or capture |
| Auxiliary settings window | Capture, Privacy, Connections, Voice profile, Desktop behavior, Shortcuts, About | Bounded settings window, stable pane navigation, grouped controls, native close and keyboard behavior | A primary destination, modal web page, or long report |
| Capture utility | Consent, arming, recording, degradation, processing handoff | Compact operational hierarchy, unmistakable state, no unrelated navigation | A document, dashboard, or blocking modal for recoverable degradation |
| Transient layer | Menus, popovers, destructive confirmation, command launcher | One temporary task above retained context | Permanent navigation or decorative elevation |

The design system has four owned layers:

1. **Foundations:** typography, color and materials, spacing, density, iconography,
   focus, motion, appearance, and accessibility.
2. **Components:** toolbar actions, sidebar and list rows, tabs, segmented filters,
   buttons, grouped settings rows, status indicators, menus, and progress.
3. **Patterns:** the five roles above, including their window behavior and state
   transitions.
4. **Verification:** a rendered specimen plus the installed Tauri reference
   surfaces in light and dark mode, minimum and comfortable sizes, keyboard-only,
   reduced-motion, increased-contrast, and 200% zoom checks.

`DESIGN.md` owns the decisions. Shared CSS and JavaScript own their implementation.
A screen-specific override is permitted only when the screen has a documented
state the shared pattern cannot express. The override must not silently redefine a
shared control.

---

## Shell decision — Tauri baseline, Mac Split selected

**Current status:** Tauri remains the working implementation so the existing
runtime and state contracts stay intact. Mac Split is the approved primary-window
composition, not blanket approval of its current styling or of every secondary
surface. The SwiftUI reference and Apple Human Interface Guidelines remain
native-quality checks; switching stacks is not authorized merely because a CSS
detail misses the bar.

Decided rather than defaulted, because it determines whether every artifact in
this directory is enforceable or merely advisory.

**Candidate A — SwiftUI.** Swift is already in the build for the Core Audio tap,
so this adds no new language. Native window behavior, menubar item, and
notifications come free and correct. Smallest binary, lowest memory, best fit
for a background app that stays resident. Cost: it orphans the entire design-QA
toolchain — the `tools/design-qa` pointer resolver, the impeccable detector, and
the forge-brand token bridge all operate on CSS custom properties, rendered DOM,
and linked stylesheets. `DIRECTION.md` degrades to prose nobody checks, and the
tokens above become a document rather than a gate. It is also the only stack in
this workspace with no other consumer, so every pattern is first-principles.

**Candidate B — Tauri.** The Swift tap ships as a sidecar binary either way, so
"one less language" is weaker than it looks — Swift is in the build under both
candidates. A web shell makes `DESIGN.md` machine-checkable (`kit-from-css.mjs`
harvests the custom properties, impeccable checks the render against them) and
makes `DIRECTION.md` enforceable through the resolver. `anarlog` is MIT-licensed,
actively maintained, and Tauri — a reference implementation for the exact
product, which the canonical-pattern-first rule says to treat as a primary
source. The UI stack is the one maintained daily here. Cost: heavier than native,
three runtimes in the process tree (Swift tap, local Python worker, Rust/TS
shell), and native menubar/notification behavior needs plugins rather than
coming free.

**Implementation choice: B remains.** The original deciding factor was not aesthetics or binary size — it was that
every design artifact in this directory is inert under A. A design system nobody
can check is the failure mode the workspace already documented twice, in
`rally-hq` and `website-nc`, where narrative `DESIGN.md` files parse to zero and
a gate over them would report clean while verifying nothing. Choosing A means
choosing that outcome deliberately at the start.

That rationale remains evidence for maintainability. The native-calibration run
then supplied the missing product decision: Mac Split won the operator review.
`apps/desktop/native-reference/` carries a thin SwiftUI comparison source. On
this machine its syntax parses, but the active Command Line Tools compiler and
SDK versions do not match and full Xcode is not installed, so it has not built
or rendered. The browser system-reference mode remains geometry evidence only.

The three-runtime cost is real and is the strongest argument for A. It is
accepted because the Python capture and note logic already exists, and the
Swift sidecar is required regardless. Their packaged application boundary is
new work; a working CLI is not a bundled worker.

### The menubar item has references, not a daemon to copy

`~/Workspace/dev/tools/local-dictation/menubar.py` is 63 lines of `rumps` driving a
menubar item over a `launchd` daemon, with
`com.local-dictation.menubar.plist` beside it. It confirms the useful lifecycle
principles: one process owns state, crash exit is observable, and the menubar is
not a second application authority. Its daemon lifetime and `launchctl`
integration are not copied.

This product's consent is scoped to one capture attempt. A job that can restart
or outlive the Tauri application would make it ambiguous whether an interrupted
attempt is still recording. The Rust shell therefore owns one local worker
process group, and the Swift tap exists only inside an approved capture. App
exit, timeout, or recovery stops and waits for that whole group. The packaged
Tauri shell in `~/Workspace/dev/wip/film-room/apps/shell` is the closer internal
reference for bundled-resource checks, startup deadlines, child cleanup,
private diagnostics, and a window that can render without its worker. Its
loopback HTTP transport is not required here.

An ordinary process group does not cover a Rust crash. The shell keeps the only
write end of a parent-liveness pipe; the worker and tap stop on EOF. A
fresh-process recovery verifies the recorded process identity before signalling
anything that survived. `docs/vertical-slice.md` carries the exact contract and
the parent-`SIGKILL` test.

The `local-dictation` timer also confirms a defect to avoid. It polls every
three seconds and renders two glyphs, `◉` and `○`. Two states is right for a
dictation toggle and wrong here — this app has seven — and a three-second poll
could show a healthy capture after an audio leg has died. The tray reads the
same Rust reducer as the window. Capture and worker events push transitions;
child-exit observation is the failure backstop.

The exact process, protocol, persistence, recovery, and fault contracts are in
[`docs/vertical-slice.md`](./docs/vertical-slice.md). That document prepares the
post-approval implementation; it does not override the encounter gate.

**The menubar glyph sits outside the design-QA net either way, and that is not a
consequence of this decision.** The resolver and the impeccable detector read CSS
custom properties and rendered DOM; a status item is neither, under Tauri's tray API
or under `rumps`. `docs/screens-and-states.md` already says the menubar item is not a
template and is specified directly. So the Tauri choice above buys enforceability for
the windows, and the one surface most sessions never look past is held to this
document by review rather than by a scan — which is worth stating plainly rather than
discovering when the first scan reports clean.

---

## Context inputs — one read-only provider, not a connector framework

`journeys.md` J0 needs to know a meeting is coming and who is on it, and the audio
supplies neither. So the product needs an inbound context source. Two things were
checked before designing anything, and both changed the answer.

**The smallest shape that serves the case is one provider with a read interface, and
no registry.** A calendar is the only input any journey here needs; a plugin system for
inputs nobody has asked for would be scaffolding around a single call. The contract is
therefore narrow on purpose: given a time window, return the meeting's title and its
invitees. Nothing more, and no write path anywhere in the module — the guarantee is that
the code has no function that could write, not that it chooses not to.

### macOS will not grant read-only calendar access, and that has to be said out loud

Apple's own documentation is explicit: *"Your app can't request read-only access to
either events or reminders. To read events or reminders from the event store, your app
needs full access."* Write-only exists; read-only does not.

So "nothing writes back" is enforceable in this code and **not** at the permission
layer. Reading the operator's calendar means holding a grant that also permits editing
and deleting it. Three ways to sit with that, and none is free:

| | Current data | Network | Permission held |
|---|---|---|---|
| **EventKit** | Yes | None | Full access — over-privileged |
| An `.ics` file the operator points at | Stale from the moment it is exported | None | None |
| Cloud API with a read-only scope | Yes | Required, plus a stored token | Least privilege |

**Chosen: EventKit.** J0 is "the call starting in two minutes", which an exported file
cannot answer, and a cloud scope buys least privilege by adding a network dependency and
a long-lived token to a product whose entire claim is that the machine is enough. The
over-privilege is real and is handled by being stated at the grant moment — the operator
is told macOS offers no narrower grant and that this app contains no code that writes —
rather than by pretending TCC is doing work it cannot do.

### Context is metadata for filing and preparation, never input to the summarizer

This is the constraint that would have been missed, and it is a measured regression
rather than a precaution.

`notes/summarize.py: check_attribution` is the strongest fabrication check in the
project, and at `channel` — which is what the *recommended* headphones capture produces
— its forbidden set is exactly `["Them"]`. It holds no real names, because the audio
never supplies one. Put calendar invitees into the summarization prompt and the model
can write "Brian agreed to send the draft" over audio that identified nobody, the check
passes because it is not watching that name, and the result is **more** dangerous than
an ordinary hallucination because it is plausible: Brian really was invited.

So invitee names reach filing, titling, and the J0 brief, and **do not reach the
prompt**. Adding them to the prompt and then to the forbidden list is the obvious repair
and it is incoherent — injecting a name in order to forbid its use leaves the name doing
no work. The attribution contract stays derived from the audio alone, which is the one
property that makes it checkable.

`docs/teardown.md` establishes that speaker names come from the meeting UI rather than
the sound. A calendar is that UI by another route, and it identifies who was *invited* —
not who spoke, not who attended, and not who said any particular sentence.

---

## Engineering baseline

Sized for a native-shelled desktop app, not a web prototype. The Blueprint Stage
2 baseline is adopted where it applies and dropped where it does not.

| Category | Setup | Note |
|---|---|---|
| Lint / types | eslint + `tsc --noEmit` on the shell, `swift-format` on the sidecar | CI gate |
| Unit | Vitest for the transcript-assembly and drift-correction logic only | This is where the real bugs are; do not unit-test panels |
| Integration | A fixture pair of pre-recorded mic + system WAVs with known drift, asserted end to end | The one test that would have caught the resampling class before shipping |
| E2E | Playwright over the Tauri webview, happy path per surface, `@smoke` | |
| Design conformance | `impeccable detect` against a built artifact, plus `resolve-pointers.mjs` once a `sites/` entry exists | Two scans — source for the type ramp, rendered for slop |
| Security | Gitleaks + Dependabot | Non-negotiable |

**Dropped deliberately:** Lighthouse-CI (no page load, no Vercel preview),
coverage gates, and portal conformance reviewers. None have a target here.

**Conformance needs two scans, not one.** `design-system-font-size` never fires
in browser mode — it is a registry entry with no implementation there, and the
real check runs only in the source pass. Color, font and radius do work in
browser mode through a linked stylesheet. A single scan silently skips the whole
type ramp.

---

## Verify before trusting this file

Two checks, both cheap, both required before this document is treated as an
authority:

1. Load the frontmatter through impeccable's own reader
   (`loadDesignSystemForTarget`, the same one
   `tools/design-qa/bin/consumer-contract.mjs` uses) and confirm every axis
   parses non-zero. A file that parses to zero is worse than no file at all.

   **Verified 2026-07-28** — `colors: 15, fonts: 5, sizes: 6, radii: 4`. The
   first run returned `radii: 0` because the key was written `radii:`; the
   reader takes `rounded:`. The colour count is 15 against 21 declared entries
   because six are deliberate aliases of the same value — `primary`/`neutral-700`,
   `secondary`/`neutral-400`, the three `surface-*` tokens, and
   `semantic-warning`/`neutral-300` — and the reader stores a set. Six tokens
   did not go missing; six names point at six values that already exist.
2. Confirm findings are located before acting on them. impeccable reports some
   rules with `file` set to the page URL and `line` set to `0`. A rule that says
   *what* without *where* can be adjudicated but not audited, and the element
   must be found by reading source.

Split every finding list by `severity` before sizing work. Advisory findings are
reported and never counted toward the exit code.
