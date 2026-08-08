# UI/UX shell audit and autonomous run

**Status:** H1 adopted. Mac Split is the selected visual composition, the
installed Tauri baseline, and the default prototype shell. Paper Focus remains
the complete functional wireframe;
Document and Native Reference remain comparison evidence. Cold-operator,
native-window, and native accessibility review remain.

**Snapshot:** 2026-08-08, branch `main`. This run preserved the workspace's
existing uncommitted product-shell work and extended it.

## Recommendation

Promote Mac Split as the visual shell. Keep Paper Focus's routes, state model,
and complete journey coverage as the planning wireframe. Retain the other two
high-fidelity compositions as regression controls:

1. **Mac Split** — conventional sidebar, meeting list, and selected record.
2. **Document** — the selected meeting owns the window; the library is an
   explicit return.
3. **Native Reference** — system-default geometry and controls, used as the
   quality floor rather than the brand direction.

The operator selected Mac Split on 2026-08-08. Persistent meeting context and a
three-action route to exact source words won over Document's calmer surface and
extra library-return action. Native Reference remains the floor the implementation
must meet, not the selected product styling.

Record and Stop belong in the integrated toolbar and the menubar. A bottom bar
may hold a contextual query, but it cannot be the primary or only capture
control. The ordinary encounter also hides roadmap labels, disabled future
functions, and synthetic-review notices. Those remain available in the complete
wireframe for product planning.

The prior comparison had task evidence but the wrong decision boundary. Paper
Focus and Paper Instrument both needed three actions to reveal exact source
words. Focus showed seven fewer buttons and thirty fewer words. That proved it
was quieter inside the same design system. It did not prove that the system felt
native, elegant, or finished beside a modern Mac app.

The earlier approach was useful for feature mapping and journey completeness.
Its goal was incomplete: visual approval never required native window anatomy,
platform controls, comfortable type scale, or a side-by-side quality check. The
calibration reset added those requirements, and Mac Split cleared the operator
composition gate. Native implementation quality remains a separate gate.

The old all-dark treatment is no longer a candidate. It came from a mistaken
premise: `DIRECTION.md` said no app surface existed, even though the paper app
already did. The interaction insight survives — recording state must be exact —
but it now lives in capture controls rather than repainting every meeting record
as hardware.

The selected shell now owns the installed Tauri baseline. Its important browser
states clear the wide and minimum-window review, but that is not proof of the
real menubar or accessibility behavior. A cold operator
must also complete the Mom Test tasks before planned features are wired into the
shell.

The 2026-07-31 acceptance does not carry forward to this shell. That receipt is
bound to an earlier exact private render. `docs/encounter-acceptance.md` requires
a new render, digest, and cold review after any interface change.

## Reader contract

- **Reader:** one person using Yawn on their own Mac.
- **Job:** find a meeting, understand its note, check the source words, and know
  whether Yawn is recording.
- **Assumed knowledge:** ordinary macOS use. No knowledge of local workers,
  evidence schemas, model admission, or project phases.
- **Plainness:** lay language in the app; practitioner language in this audit.
- **Precision locks:** recording audio, Transcript, Evidence, On this Mac, and
  what leaves this Mac. Planned and Partial remain audit terms, not ordinary
  navigation or decorative badges.
- **Copy sources:** `apps/desktop/ui/index.html`, `apps/desktop/ui/main.js`,
  `apps/desktop/ui/navigation-state.mjs`, and the product documents that define
  feature status.

The interface must answer four questions without explanation from the builder:

1. Is Yawn listening now?
2. Which meeting am I looking at?
3. What can I do here now?
4. What stays on this Mac, and what would leave it?

## Status against planned features and functions

`Shipped` means there is real hardware or receipt evidence. `Registered` means
the command, capability, and UI exist with synthetic evidence. A placeholder
does not change either status.

| ID | Planned feature | Current truth | Owner in the complete planning wireframe |
|---|---|---|---|
| A1 | Consent-first two-leg capture and recovery | Shipped | Record flow, quick control, recovery states |
| A2 | Operator voice isolation | Shipped in 0.4.0; live meeting audio remains unmeasured | Settings → Voice profile |
| A3 | Named speakers | Unbuilt | Transcript controls and Connections, labelled Planned |
| A4 | Meeting-length transcription | Partial | Capture status and Transcript, labelled Partial |
| A5 | Two-channel timing correction | Detection shipped; correction unbuilt | Transcript status, labelled Partial |
| B1 | Operator-authored live note | Shipped | Recording and retained Note |
| B2 | AI-enhanced note | Prototyped; no generator admitted | Note, labelled Planned |
| B3 | Meeting templates | Unbuilt | Note toolbar, labelled Planned |
| B4 | Automatic title | Partial; deterministic title works | Library and meeting title |
| B5 | Evidence-linked claims | Prototyped | Evidence and claim rows, labelled Partial |
| B6 | Honest incompleteness | Prototyped | Transcript and evidence states |
| B7 | Restore and regenerate after correction | Restore registered; regeneration unbuilt | Transcript recovery and Note toolbar |
| C1 | Actions with owner and status | Unbuilt | Meeting Actions, labelled Partial; cross-meeting Actions, labelled Planned |
| C2 | Actions across meetings | Unbuilt | Actions root, labelled Planned |
| C3 | Export or share as a document | Unbuilt | Meeting title, Details, and Connections, labelled Planned |
| D1 | Ask across meetings with citations | Unbuilt | Ask answer room and meeting dock, labelled Planned |
| D2 | Exact and meaning search | Registered; usefulness remains unadjudicated | Ask, with two visible modes |
| D3 | Folder, date, title, and people filters | Three of four registered; people waits on A3 | Browse-all Meetings |
| D4 | Saved searches and future streams | Unbuilt | Ask and Saved views, labelled Planned |
| D5 | Open a result on its exact claim | Unbuilt | Ask example and Evidence, labelled Planned |
| E1 | Folders and workspaces | Partial; create, move, unfile, and filter have synthetic evidence | Navigation, Meetings, Details |
| E2 | One meeting with sibling views | Partial | Note, Transcript, Actions, Evidence, Details |
| E3 | Preparation brief | Unbuilt | Library context, labelled Planned |
| E4 | Honest menubar-size state | Shipped | Header and quick control |
| E5 | Retention with named periods | Automatic deletion shipped; reusable choices unbuilt | Privacy and Details |
| E6 | Local corpus and retrieval | Partial; SQLite is written and meaning search reads it | Meetings and Ask |
| P1–P3 | Calendar, directory, and meeting-window context | Phase 2 | Connections and preparation brief |
| P4 | Cloud sync and multiple devices | Phase 2 | Connections |
| P5 | Slack, Notion, and CRM destinations | Phase 2 | Connections |
| P6 | Shared workspaces and team retrieval | Phase 2 | Connections |

The complete wireframe makes the intended product legible without pretending the
empty rooms are implemented. Native-calibration mode removes those future rooms
from ordinary use so the product encounter is not a roadmap rendered as UI.

## Intended information architecture

The primary navigation stays small:

1. **Meetings** — default. Library and selected note share the first view.
2. **Ask** — exact and meaning search now; cited answers and saved views later.
3. **Actions** — the future cross-meeting follow-through view.
4. **Settings** — Capture, Privacy, Connections, Voice profile, Desktop
   behavior, Shortcuts, and About.

Recording is global. It can begin while the operator is reading any meeting,
so it does not become another sidebar destination.

The prototype hides Home. Its dashboard cards repeated the navigation and
grouped product capabilities instead of the meeting the operator came to use.
Home remains only in the shared installed-app markup. The prototype hides it so
it cannot create a second, dashboard-shaped route to the same destinations.

## User journey coverage

| Moment | Entry | Main action | Exit or recovery |
|---|---|---|---|
| Open Yawn | Meetings list and selected note | Choose a recent meeting | Record, Ask, or Settings |
| Choose a meeting | Library row | Open the selected record | Keep the list visible or use Show library, depending on the candidate |
| Before a call | Planned preparation strip | Review recent context | Start consent review |
| Start capture | Global Record control | Confirm consent and retention | Cancel before audio opens |
| During capture | Header, quick control, recording view | Check both channels; write your note | Stop; degraded state stays explicit |
| Process locally | Progress view | Wait for transcription | Return to progress from another room |
| Review | Selected meeting | Read Note; inspect sibling views | Open exact transcript words or library |
| Recall | Ask | Search exact words or describe a passage | Open the retained meeting |
| Follow through | Actions | Review future owner, status, and evidence | Export later |
| Correct or recover | Transcript or Details | Restore, correct, or delete with consequence copy | Return to the same meeting |
| Configure boundaries | Settings | Choose local behavior and inspect planned connections | Return to the previous room |

## What the comparators teach us

### Wispr Flow Notetaker — direct screenshot review

The supplied screenshots show a document-first system:

- one serif meeting title;
- three plain sibling tabs: **My thoughts**, **Transcript**, and **Summary**;
- a sparse reading canvas with few permanent borders;
- context actions at the top right;
- a capture and query bar pinned to the bottom during the meeting;
- temporary popovers for sharing and overflow actions;
- coaching through one dimmed screen and one highlighted control.

The strongest lesson is not “use more white.” It is that one meeting owns the
screen. Navigation, capture, source review, generated output, and sharing are
attached to that object. Its larger type, native window frame, restrained control
count, and generous reading measure make the hierarchy legible before decoration.

Borrow:

- the document title versus UI-control type hierarchy;
- sibling views instead of separate destinations for thoughts, transcript, and
  generated output;
- a persistent contextual-query boundary that does not replace the window-level
  Record and Stop controls;
- overlays only for temporary actions;
- short labels that name the user's object, not the mechanism.

Do not borrow:

- the cloud and sharing assumption;
- the amount of unused space on short or empty notes;
- a bottom action that is visually remote from its recording state;
- a generated summary that can appear equal to the transcript without Yawn's
  evidence boundary;
- mint as a general decorative accent. In Yawn, green has a state job.

### Granola — prior primary-source review

Granola's documented model combines meetings, folders, notes, enhanced notes,
source inspection, and questions scoped to one or more meetings. The useful
pattern is one meeting object with several ways to work with it.

Borrow the clear meeting object, scoped questions, source inspection, and
familiar folders. Do not borrow ambient sharing, cloud workspace assumptions,
or generated answers without quoted evidence.

Primary references retained from the prior audit:

- <https://docs.granola.ai/help-center/getting-started/granola-101>
- <https://docs.granola.ai/help-center/taking-notes/ai-enhanced-notes>
- <https://docs.granola.ai/help-center/getting-more-from-your-notes/chatting-with-your-meetings>

## Gestalt audit

| Principle | Finding | Correction | Remaining risk |
|---|---|---|---|
| Figure and ground | The paper color covered chrome, navigation, and record, so the entire window read as one low-contrast sheet | System chrome and structural panes own the shell; warm paper may appear inside the selected record | Real Tauri materials and titlebar behavior remain unverified |
| Proximity | Planning labels and disabled controls crowded the meeting's actual work | Native-calibration mode keeps Note, Transcript, Evidence, and Details together and hides roadmap scaffolding | The complete wireframe must stay clearly marked as review-only |
| Similarity | Tiny status chips made product state look like decoration | Ordinary use removes project-state taxonomy; recording and destructive states retain words plus distinct color and shape | Native states need VoiceOver and increased-contrast review |
| Common region | Nested rounded cards created more regions than concepts | Sidebars, lists, and records use adjacency and one-pixel dividers; overlays alone float | The candidate chosen at wide size must still hold at the minimum window |
| Continuity | Home → Meetings → Detail broke the main scan path | Meetings opens with a selected record; Split keeps the list, Document provides Show library | Document adds one return action and needs cold-user testing |
| Prägnanz | Capture, future functions, preview status, and record content competed | A compact toolbar owns global state; one meeting owns the content area | The browser traffic lights are only a stand-in, not native proof |
| Focal point | Small type and uniform beige reduced the difference between shell and content | A 27–31px meeting title and 14px base establish a readable hierarchy | Long titles and localization still need stress tests |

The meeting record remains the organizing object. Paper is now one material
inside that object, not the identity of every pane in the window.

## Copy audit

The best copy names state or consequence:

- **Nothing is recording**
- **On this Mac**
- **Focus meeting / Show library**
- **Delete recording** versus **Delete meeting**

Keep these exact distinctions:

| Term | Classification | Reader rule |
|---|---|---|
| Recording audio | Load-bearing object | Never shorten it where deletion is discussed |
| Transcript | Load-bearing object | It is the retained words, not the note |
| Automatic note | Necessary category | Call it a reading aid until a person verifies it |
| Evidence | Load-bearing concept | Define it as the exact retained words behind a claim |
| Retained | Necessary but unfamiliar | Pair first use with “kept on this Mac” |
| Withheld speech | Necessary state | Explain that Yawn set it aside rather than pretending to know the words |
| Planned | Product truth | Keep next to every inactive future function |
| Partial | Product truth | Use only when a real part works |
| Fixture, renderer, admitted generator | Engineering vocabulary | Keep out of the product encounter |

Deterministic copy defects corrected before cold review:

- meeting-context actions now say **Open**, not the vague **View**;
- the prototype no longer exposes duplicate **Home** or **Back to Meetings**
  controls;
- both deletion reviews name what goes and what stays;
- the synthetic shell says deletion is unavailable instead of leaving an
  apparently live irreversible button.

Copy still needing encounter evidence:

- whether **Ask** is understood as both current search and future answers;
- whether **Evidence** is clear before its tab opens;
- whether **retained** is worth its precision in visible copy;
- whether the dedicated planning wireframe makes **Partial** and **Planned**
  understandable without teaching those terms through the ordinary product;
- whether removing disabled future controls makes the current product feel
  simpler without concealing important limits.

## Mom Test audit

Do not ask whether someone likes the palette, would use Actions, or thinks a
preparation brief sounds helpful. Those questions reward politeness.

Use behavior and concrete tasks:

1. Without clicking, tell me whether Yawn is listening.
2. Find the decision from last week's pilot meeting. Narrate where you look.
3. Show the exact words behind one automatic claim.
4. Tell me about the last meeting action you lost. Where did you put it?
5. Find recording audio due for deletion. Explain what remains afterward.
6. Start a meeting, then back out before audio opens.
7. One audio channel fails. Show how you know and what you do.
8. Try to share a note to Notion. Show where you expect that action and what you
   expect to review before anything leaves the Mac.
9. In each candidate, choose another meeting, inspect its source words, then
   return to the meeting list. Record the path, wrong turns, time, and anything
   missed.

A preference is useful only after the task evidence. A future-tense compliment
is not evidence.

## Typography

Use system typography for the shell. Keep editorial type as a bounded option
inside the record, not as the product's default voice:

| Role | Face | Size | Use |
|---|---|---:|---|
| UI | macOS system sans, then system-ui | 13–17px; 14px base | window title, navigation, buttons, labels, status, instructions |
| Record title | Iowan Old Style, then Palatino or Georgia in Mac Split and Document | 27–31px | the selected meeting title only |
| Evidence | SF Mono, then Menlo or ui-monospace | 12–13px | transcript turns, timestamps, locators, meters |

This keeps what worked in the old Yawn identity without asking the whole app to
perform it. System sans says “this belongs on this Mac.” A restrained serif may
say “this is the record.” Mono says “this is exact source material.” The old
13/11/10px hierarchy was mechanically compact but looked undersized beside a
finished desktop app.

## Look and feel

Yawn should feel like a first-party Mac utility with a private editorial record
and an exact capture control:

- native and quiet at rest;
- comfortably dense rather than miniature;
- editorial only where the meeting becomes a document;
- system materials, borders, and adjacent tones for structure;
- one restrained shadow on real overlays;
- no ambient motion;
- a dedicated live state that cannot be mistaken for brand decoration;
- clear enough that the transcript still outranks generated prose as evidence.

It should not feel like a generic beige AI notepad, a card dashboard, a full
audio workstation, or an all-black “pro” skin.

## Color palette

| Role | Value | Use |
|---|---|---|
| Window proxy | `#F4F4F2` | browser-only stand-in for native window material |
| Structural pane proxy | `#EBEBE8` | browser-only sidebar and list separation |
| Record | `#FFFFFF`; Document may use `#FDFCF9` | selected meeting reading surface |
| Ink | `#242724` | body copy and primary UI |
| Strong ink | `#161816` | headings and focus outline |
| Muted ink | `#6F736F` | metadata and secondary copy |
| Yawn terracotta | `#843B31` | identity, selection, deliberate primary actions |
| Live capture | `#146B4A` | healthy recording mark, channel state, and Stop while live |
| Warning | `#8B5A2B` | degraded state with changed word and shape |
| Error | `#9E3028` | destructive or failed state with explicit copy |
| Information | `#486A73` | rare informational state with explicit copy |

Measured WCAG contrast:

- ink on white: 15.10:1;
- muted ink on white: 4.82:1;
- terracotta on white: 7.92:1;
- live green on white: 6.50:1;
- ink on Document paper: 14.72:1;
- muted ink on Document paper: 4.70:1.

Color never carries a state alone. **Recording**, **Degraded**, and the relevant
mark remain visible even when hue is unavailable.

## Previous H1 decision — reopened

| | Paper Instrument | Paper Focus |
|---|---|---|
| Identity | Paper record with deep-green control rail | The same paper record with quiet top navigation |
| Structure | Product rail + meeting list + record always visible | Library + record, then explicit document focus |
| Capture control | Header and quick control | Header, quick control, and bottom meeting dock |
| Best for | Switching, monitoring, seeing the whole product map | Reading, writing, and one-meeting work |
| Main risk | Density at small window sizes | Hidden context and an over-prominent dock |
| Relative result | Rejected: same task path, with 7 more visible buttons and 30 more words | Quieter: removes context without adding work |

The operator approved Paper Focus on 2026-08-08 based on this comparison. The
selector, Instrument rules, legacy comparison CSS, and treatment-routing
JavaScript were then removed. The later side-by-side review with Wispr Flow
showed that both Yawn candidates shared the same non-native frame, small type,
bottom-dock dependence, and low perceived finish. The approval is therefore
rescinded as a visual decision. Paper Focus remains interaction evidence.

## Native calibration decision

All three candidates use the same content and core task: open **Weekly product
check-in**, open **Evidence**, and show the exact words behind the decision.
Only the window composition and visual system change.

| | Mac Split | Document | Native Reference |
|---|---|---|---|
| Window model | Integrated top frame, product sidebar, meeting list, record | Integrated top frame; selected meeting owns the window; explicit Show library return | System-default split geometry, sidebar selection, and segmented sibling views |
| Core task | 3 actions | 4 actions because the library must first be shown | 3 actions |
| Current narrow behavior | Product sidebar yields; meeting list and record remain | Record remains primary; library opens on request and closes after selection | Product sidebar yields; meeting list and record remain |
| Type | 14px system base; 27px restrained serif title | 14px system base; 31px restrained serif title | 14px system base; 27px system title |
| Strongest quality | Fast switching with visible context | Calm reading and strongest distinction between shell and record | Clearest platform baseline and least custom invention |
| Main risk | Three columns can become dense at a small window | Hidden context and one extra retrieval action | Can feel generic and is not yet a rendered native build |
| Evidence authority | Browser-rendered Tauri candidate | Browser-rendered Tauri candidate | Browser geometry proxy plus syntax-parsed SwiftUI source; no native render yet |
| H1 result | **Selected** | Not selected | Retained as the quality floor |

At the current 624×351 in-app viewport, Mac Split and Native Reference each show
14 visible buttons and 145 visible words. Document shows 11 buttons and 113
words. These counts are operating diagnostics, not the result. The operator
selected Mac Split based on the completed task, visible context, reading quality,
and perceived fit at the same review size.

Mac Split is now the default for `?prototype=1`. The complete Paper Focus
wireframe remains at `?prototype=1&calibration=wireframe`; Document and Native
Reference remain at their explicit calibration URLs.

The ordinary selected encounter hides synthetic-preview notices, project-state
badges, planned controls, generation toolbars, and the bottom meeting dock. The
complete Paper Focus wireframe retains them so future product coverage can still
be reviewed without presenting the roadmap as the current app.

## Accessibility and desktop behavior

Implemented in the prototype shell:

- two-pixel high-contrast focus outline with offset;
- state words alongside colored marks;
- no ambient animation or transition dependency;
- Meetings `⌘1`, Ask `⌘2`, Actions `⌘3`, Settings `⌘,`, Commands `⌘K`;
- arrow keys, Home, and End across tab lists;
- explicit **Show library** return from meeting focus;
- route changes and meeting selection move focus to the opened heading;
- modal focus containment through inert background regions and focus return;
- no duplicate IDs, broken ARIA references, or unnamed enabled fields in the
  rendered meeting-details encounter;
- exactly one selected and one keyboard-focusable tab in each visible tab list;
- destructive copy that names what is removed and what remains;
- deletion consequence reviews that focus **Cancel** and keep the final action
  disabled in the synthetic shell;
- a 14px system reading base in native-calibration mode;
- Record and Stop in the integrated top frame rather than a vulnerable bottom
  dock;
- no horizontal overflow in the current 624×351 zoomed in-app viewport.

Still requires native verification:

- VoiceOver order in the Tauri webview;
- focus after asynchronous native responses;
- exact 200% zoom at the native minimum window;
- the real meter with reduced motion;
- healthy versus degraded recognition in the menubar;
- macOS increased-contrast behavior.

## Autonomous run and gates

Completed in this run:

1. Corrected the design authority to acknowledge the implemented paper app.
2. Separated terracotta brand emphasis from green live capture.
3. Restored the serif meeting title while keeping controls sans and transcript
   evidence mono.
4. Rebuilt Paper Instrument with a persistent green rail and three work zones.
5. Rebuilt Paper Focus with an explicit focus transition, return path, and
   bottom meeting-control dock.
6. Kept planned functions disabled and labelled at their intended destination.
7. Added contract tests for the palette, type roles, focus state, and dock.
8. Ran the same retrieval, source-inspection, capture, degradation, stop,
   processing, and result tasks in both candidates.
9. Kept source inspection inside the selected meeting instead of navigating to
   an unrelated transcript fixture.
10. Reset meeting focus before consent and capture so hidden navigation does not
    leak into another workflow.
11. Measured Paper Focus against Paper Instrument on the same task before making
    the direction decision.
12. Corrected the Shortcuts panel to match the routes the app actually handles.
13. Recorded operator approval and removed Instrument, the treatment selector,
    treatment-routing JavaScript, and the superseded comparison CSS.
14. Removed duplicate legacy navigation from the prototype encounter and moved
    focus to the newly opened meeting title.
15. Named the live-note field and verified the rendered ARIA reference graph,
    enabled form labels, and visible tab-list state.
16. Exposed both deletion consequence reviews with synthetic-only references,
    disabled final actions, explicit shell-boundary copy, and focus return.
17. Checked Settings, consent, and meeting details in the current zoomed in-app
    viewport with no horizontal overflow.
18. Reopened H1 after the finished-app comparison exposed the missing native
    quality gate.
19. Preserved Paper Focus as the full functional wireframe instead of deleting
    its journey and feature coverage.
20. Added isolated Mac Split, Document, and Native Reference modes over the same
    markup and state model.
21. Removed roadmap scaffolding and the bottom meeting dock from each ordinary
    calibration encounter.
22. Moved Record and Stop into an integrated top frame and restored a 14px
    reading base.
23. Added a thin SwiftUI NavigationSplitView reference without connecting it to
    capture or local data.
24. Ran the same meeting-to-evidence task in all three candidates and recorded
    the extra library-return action in Document.
25. Recorded the operator's Mac Split selection, made it the default prototype
    shell, and preserved the wireframe and comparison modes behind explicit URLs.
26. Applied Mac Split to first run, consent, arming, healthy and degraded
    recording, processing, transcript handoff, Settings, Ask, and Actions.
27. Kept the integrated capture state visible while removing unrelated product
    navigation from consent and active-capture workflows.
28. Added a 96px product rail at the minimum window, retained the meeting list
    in the reading flow, and replaced clipped Settings cards with a compact
    seven-section map.
29. Re-ran the rendered shell at 1000×680 and 720×560 with no page-level
    horizontal overflow, unnamed enabled controls, duplicate IDs, or broken
    ARIA references.

H1 used the same anchors in every candidate:

1. library and selected note;
2. healthy and degraded recording;
3. Transcript and Evidence;
4. Privacy, Connections, and recovery.

Next gates:

1. Verify the real Tauri titlebar, toolbar, resizing, sidebar behavior, and
   menubar state; use the SwiftUI reference as the quality floor when a matching
   Xcode toolchain is available.
2. Run the Mom Test tasks with a cold operator and fix navigation and copy.
3. Verify VoiceOver, increased contrast, and exact 200% zoom at
   the native minimum window.
4. Only then resume automatic note and templates; actions and export; speaker
   naming and correction; meeting-length transcription; calendar; and Phase 2.

## Verification and limits

Current mechanical and live-browser evidence:

- `node --check` passes for `main.js`;
- the UI contract suite passes and keeps Mac Split as the prototype default while
  preserving the complete functional wireframe explicitly;
- the Rust shell contract still passes;
- Mac Split, Document, and Native Reference render from explicit prototype query
  parameters over the same HTML and application state;
- Mac Split and Native Reference keep the meeting list visible after selection;
- Document opens in focus, **Show library** restores the list, and selecting a
  meeting returns to the record;
- the core meeting-to-exact-words task takes 3, 4, and 3 actions respectively;
- all three use a 14px base, keep Record visible in the top frame, and remove the
  bottom meeting dock;
- all three fit the current 624×351 in-app viewport without horizontal overflow;
- the selected Mac Split shell was visually exercised at 1000×680 and 720×560
  across the retained record, first run, consent, arming, healthy and degraded
  recording, processing, transcript handoff, Settings, Ask, and Actions;
- the minimum-window shell keeps a compact product rail and meeting context for
  browsing, while consent and capture workflows use the full content width;
- all seven Settings sections remain visible at the minimum width instead of
  disappearing into an unmarked horizontal strip;
- each visible tab list has one selected tab and one tab in the keyboard sequence;
- arrow-key Settings tab movement and `Command-1`, `Command-2`, and `Command-3`
  route navigation work in the rendered prototype;
- the rendered semantic sweep found no duplicate IDs, broken ARIA references,
  or unnamed enabled controls in the selected record, Settings, or consent;
- the direct candidate pages report no browser runtime errors;
- `YawnNativeReference.swift` passes Swift syntax parsing.

The SwiftUI reference has not built or rendered. The active Command Line Tools
compiler is Swift 6.3.3 while the installed SDK was built for Swift 6.3.2, and
full Xcode is not installed. The browser traffic lights and system-reference
mode are geometry proxies only. They do not prove native materials, resizing,
toolbar behavior, VoiceOver order, or platform fit.

These checks also do not prove real recording, local data migration, semantic
usefulness, release readiness, or cold-operator acceptance. The screenshots are
comparator evidence, not permission to copy Wispr's cloud model or visual system
wholesale.
