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
mode: dark

colors:
  primary: "#333841"
  secondary: "#7C828D"
  accent: "#FFB020"
  neutral-50: "#F5F6F7"
  neutral-100: "#E3E5E8"
  neutral-200: "#C7CAD0"
  neutral-300: "#A2A7B0"
  neutral-400: "#7C828D"
  neutral-500: "#5C626D"
  neutral-600: "#444A54"
  neutral-700: "#333841"
  neutral-800: "#24282F"
  neutral-900: "#191C21"
  neutral-950: "#0E1014"
  surface-base: "#0E1014"
  surface-raised: "#191C21"
  surface-overlay: "#24282F"
  semantic-success: "#4E9A6B"
  semantic-error: "#C4553D"
  semantic-info: "#5A7FA8"
  semantic-warning: "#A2A7B0"

typography:
  ui:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif"
  mono:
    fontFamily: "'JetBrains Mono', 'SF Mono', ui-monospace, Menlo, monospace"
  step-xs:
    fontSize: "11px"
  step-sm:
    fontSize: "12px"
  step-base:
    fontSize: "13px"
  step-lg:
    fontSize: "15px"
  step-xl:
    fontSize: "18px"
  step-2xl:
    fontSize: "24px"

rounded:
  none: "0px"
  sm: "2px"
  md: "4px"
  lg: "6px"
---

# DESIGN.md — local-meeting-notes

Visual rules and engineering rules together, so neither gets decided ad hoc
surface by surface. Answers to [`DIRECTION.md`](./DIRECTION.md); the L5
inventory it covers is [`docs/screens-and-states.md`](./docs/screens-and-states.md).

---

## Color

**The accent is reserved.** `#FFB020` means one thing: capture is running. It is
forbidden in navigation, selection, links, focus rings, hover states, charts,
and every empty state. This is the direction's central constraint expressed as a
token rule, and it is the one rule here that a device can never buy its way out
of.

**`semantic-warning` has no hue on purpose.** It resolves to `neutral-300`. An
amber warning would be indistinguishable from the live indicator at menubar
size, which would destroy the single reading this product exists to make
trustworthy. Warnings are carried by neutral foreground plus text. If a warning
genuinely needs color, it is an error and takes `semantic-error`.

**Dark-first, single mode.** No light theme. The ramp is graphite rather than
pure grey so the panel reads as an object rather than as unstyled chrome.

**Contrast floors**, checked against `surface-base` and `surface-raised`:
body text ≥ 4.5:1, large text and UI glyphs ≥ 3:1. `neutral-300` on
`surface-raised` is the darkest permitted body pairing.

## Type

Two families. `ui` for chrome, `mono` for transcript and any timestamp. A
transcript in a proportional face stops being scannable as a record, which is
the only reason to keep it on screen.

The scale is deliberately small and dense — `step-base` is 13px, matching macOS
body rather than web defaults. Anything above `step-2xl` does not exist. There
is no display scale, because there is no marketing surface inside this app.

## Form

- **No shadows.** They read as depth this interface does not have, and they cost
  render time on a window that stays open for an hour.
- **No radius above `lg` (6px).** Pills and heavily-rounded cards belong to the
  soft-SaaS world the direction explicitly rejects.
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
- Progressive disclosure. The note is the summary; the transcript is on demand.
- Empty states carry real content, never a title card. First run shows what a
  note will look like, not a welcome graphic.

---

## Shell decision — Tauri, not SwiftUI

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
three runtimes in the process tree (Swift tap, Python ASR daemon, Rust/TS
shell), and native menubar/notification behavior needs plugins rather than
coming free.

**Chosen: B.** The deciding factor is not aesthetics or binary size — it is that
every design artifact in this directory is inert under A. A design system nobody
can check is the failure mode the workspace already documented twice, in
`rally-hq` and `website-nc`, where narrative `DESIGN.md` files parse to zero and
a gate over them would report clean while verifying nothing. Choosing A means
choosing that outcome deliberately at the start.

The three-runtime cost is real and is the strongest argument for A. It is
accepted because two of the three already exist: the Python daemon is
`local-dictation`, and the Swift sidecar is required regardless.

### The menubar item has a reference implementation, and a defect to avoid

`~/Workspace/dev/tools/local-dictation/menubar.py` is 63 lines of `rumps` driving a
menubar item over the same launchd daemon pattern this app needs, with
`com.local-dictation.menubar.plist` beside it. Per the workspace's
canonical-pattern-first rule an internal working implementation ranks with vendor
documentation, so the daemon lifecycle and the launchctl integration are copied from
there rather than derived.

**What is not copied is how it learns the state.** It polls `launchctl` on a
three-second timer and renders two glyphs, `◉` and `○`. Two states is right for a
dictation toggle and wrong here — this app has seven — but the polling is the part
that would be a defect rather than a simplification. `DIRECTION.md`'s thesis is that
one bit of state must be readable at a glance and trustworthy, and
`docs/screens-and-states.md` requires `degraded` to be distinguishable from
`recording` without a click. A three-second poll means up to three seconds of a
capture displaying as healthy after a leg has died. The state has to be pushed from
the capture process, and the poll can only be a backstop for a daemon that died
without reporting.

**The menubar glyph sits outside the design-QA net either way, and that is not a
consequence of this decision.** The resolver and the impeccable detector read CSS
custom properties and rendered DOM; a status item is neither, under Tauri's tray API
or under `rumps`. `docs/screens-and-states.md` already says the menubar item is not a
template and is specified directly. So the Tauri choice above buys enforceability for
the windows, and the one surface most sessions never look past is held to this
document by review rather than by a scan — which is worth stating plainly rather than
discovering when the first scan reports clean.

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
