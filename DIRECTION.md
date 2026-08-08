# Direction — local-meeting-notes

Art direction for the Yawn desktop app. This record was rebaselined on
2026-08-08 from the implemented paper app, the delivery site's harvested brand,
and direct operator review. It supersedes the earlier graphite "field recorder"
direction, which incorrectly described the surface as unshipped and treated an
interaction metaphor as permission to replace the product's visual identity.

A finding with no ledger verdict is a defect. Absence of a record is not
permission. Direction constrains *how* a correctness failure is fixed — never
*whether*.

---

## The contract

The block below is the canonical direction text and stays under 150 words.

```html
<!--
THESIS: Yawn is a private meeting record whose capture state is unmistakable.
The record feels calm; the live control feels exact.

OWN-WORLD: A first-party Mac utility with a private meeting record at its
center. Native window anatomy, familiar controls, and flexible navigation own
the shell. Yawn's editorial voice belongs inside the record.

STORY: Browse, choose, focus, capture, verify. The note is the reading surface;
the transcript remains the evidence beneath it.

FIRST VIEWPORT: The library and a selected recent note. Real content, with the
operator still choosing which meeting to open. Never an empty dashboard.

FORM: System sans and familiar symbols own the chrome. A restrained serif may
mark the meeting title; mono marks transcript evidence. Terracotta carries
identity. Dedicated green plus a state word and mark carries live capture.
Critical capture control never depends on a bottom bar. No ambient motion.
-->
```

---

## Why this thesis and not another

The earlier direction correctly identified the hardest interaction problem:
Yawn can listen without a bot or browser tab, so the operator must always know
whether capture is running. It then made an unsupported leap from that behavior
to an all-dark hardware atmosphere.

That leap erased evidence already in the product. The implemented app used a
paper canvas, deep green, editorial serif headings, and restrained terracotta.
The Yawn delivery site later documented those same choices as harvested from
the app and explicitly described the app as a paper surface. The dark record
said no surface existed. Both claims could not be true, and the implemented
lineage wins.

The correction preserves the useful part of the instrument idea. Instrument
precision belongs where capture is controlled: the header state, quick control,
recording workflow, meters, elapsed time, and degraded-channel warning. It does
not require every retained note, library row, and settings page to look like a
mixing console.

The 2026-08-08 side-by-side review exposed a second unsupported leap. Restoring
the paper lineage did not make the shell feel native. The Paper Focus decision
measured task steps, visible controls, and words against Paper Instrument. It
proved only that Focus was less cluttered inside the same visual frame. It did
not test Mac window anatomy, perceived quality, platform familiarity, or
composition beside a finished desktop app.

The functional shell therefore remains useful as an interaction map, but it is
not the visual direction. Native calibration compared a conventional split
view, a document-first window, and a system-default reference. The operator
selected the conventional Mac split on 2026-08-08: persistent meeting context
won over the Document candidate's calmer but hidden library.

---

## Constraints this thesis generates

**Brand and live state are separate tokens.** Terracotta identifies Yawn and may
mark selected or emphasized product actions. It never claims that capture is
running. Dedicated green is reserved for healthy live capture. The word
"Recording" and a clear state mark accompany it, so color is never the only
signal. Degraded capture changes both wording and shape.

**Native chrome is the product shell; paper belongs to the record.** Window
frame, toolbar, sidebar, controls, symbols, active state, and resizing follow
Mac conventions before Yawn styling. Warm paper and editorial treatment may
appear inside the selected meeting. They do not repaint navigation, settings,
or system status as a document.

**Serif type marks the record, not the controls.** A retained meeting title may
use the editorial serif. Navigation, buttons, labels, status, settings, and
workflow instructions use the UI sans. Transcript turns and timestamps use the
mono face. Marketing-scale display type does not enter the desktop shell.

**Depth represents actual layering.** System materials, adjacency, tone, and
borders establish window hierarchy. Shadows are reserved for real overlays
such as a command launcher, popover, or modal. Cards do not float merely to
decorate empty space.

**Critical capture control stays in the window frame or menubar.** A record
button may live in the integrated toolbar and the current state remains in the
menubar. A bottom bar can display contextual information, but it cannot be the
only or primary home for Record or Stop.

**No ambient motion anywhere.** A pulse, breath, shimmer, or looping gradient can
be misread as activity. The audio level meter is the only permitted repeating
motion, because it is a reading of arriving audio. Reduced-motion still applies.

**First viewport shows real content without choosing the operator's intent.**
The window opens on the notes library with a recent note already rendered beside
it. The operator can choose another meeting. Focus mode is entered by selecting
a meeting or using the explicit Focus control; it is never an invisible default.

**Planned work stays out of ordinary use.** A dedicated review mode may expose
placeholder rooms to make the complete journey inspectable. The normal product
encounter presents what works now and does not turn roadmap classifications into
navigation, badges, or disabled controls.

---

## Ledger

Verdicts: `authorized` / `condemned` / `undecided` / `removed`. Parsed only under
this heading, rows shaped `| \`device-id\` | verdict | … |`.

| id | verdict | device | cites the thesis by | rules |
|---|---|---|---|---|
| `paper-canvas` | authorized | Warm treatment inside the selected meeting record | Gives the private record an editorial identity without repainting Mac chrome | native calibration boundary |
| `record-title-serif` | authorized | Serif only on retained meeting titles | Marks the document without turning workflow chrome into editorial display | `apps/desktop/ui/styles.css:1514` |
| `capture-live-green` | authorized | Dedicated live green plus word and mark | Separates capture truth from terracotta brand emphasis | `apps/desktop/ui/styles.css:1586` |
| `overlay-elevation-only` | authorized | Shadows only on popovers, dialogs, and menus | Makes depth correspond to an actual layer | `apps/desktop/ui/styles.css:1644` |
| `graphite-everywhere` | removed | All-dark shell for every state and record | Confused an interaction metaphor with the product's visual identity | superseded 2026-08-08 |
| `display-serif-in-chrome` | condemned | Serif buttons, navigation, labels, or workflow copy | Breaks the record-versus-control type hierarchy | this record |
| `instrument-shell` | removed | Paper Instrument control rail + library + record | Added seven visible controls and thirty words without shortening the equal task | removed 2026-08-08 after operator approval |
| `focus-shell` | removed | Library shell with explicit document focus | Calmer record, but hides meeting context and adds a return action | not selected 2026-08-08 |
| `bottom-capture-dock` | condemned | Critical Record and query controls fixed to the lower window edge | Detaches the primary action from Mac window anatomy and can disappear at the vulnerable edge | 2026-08-08 side-by-side review |
| `native-shell` | authorized | Integrated toolbar plus flexible sidebar, list, and record | Uses familiar Mac anatomy while keeping the selected meeting central | `apps/desktop/ui/native-calibration.css` |
| `mac-split-shell` | authorized | Product sidebar, meeting list, and selected record at wide sizes; compact product rail at the desktop minimum; focused capture states hide unrelated navigation | Keeps switching context visible in the reading flow without weakening capture truth | operator selection and full-state pass 2026-08-08 |
| `native-reference` | authorized | System-default comparison geometry, not a product treatment | Keeps platform familiarity as the quality floor for implementation review | `apps/desktop/native-reference/YawnNativeReference.swift` |

---

## Notes

The product surface now exists, and this record is no longer hypothetical.
The complete Paper Focus shell is retained as a functional wireframe at
`?prototype=1&calibration=wireframe`. Mac Split is the default prototype shell;
Document and Native Reference remain comparison evidence. The installed Tauri
window now adopts Mac Split by default; browser-only traffic-light geometry is
suppressed there in favor of the native overlay titlebar.

The ledger authorizes the record identity and rejects both the superseded dark
atmosphere and the bottom critical-action dock. Paper Focus completed the same
retrieval and source-check path with fewer visible controls and words, but the
side-by-side review rescinded its visual approval. Mac Split then won the native
calibration comparison. H1 is closed.

Tauri remains the implementation baseline. Mac Split earned the composition
decision through operator comparison, not because its CSS is testable. A thin
SwiftUI reference source records the native comparison ceiling; it remains a
platform check, not a requirement to reopen the selected composition. No stack
migration is authorized without rendered evidence from both implementations.
