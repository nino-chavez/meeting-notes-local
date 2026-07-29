# Direction — local-meeting-notes

Art direction for this surface. Unlike the records that quote an existing
`DESIGN.md`, this one is **authored, not derived**: there is no shipped
`DESIGN.md` stating a direction to quote, because there is no shipped surface.
The thesis below is written first and `DESIGN.md`'s tokens answer to it, rather
than the reverse.

A finding with no `authorized` row here is a defect. Absence of a record is not
permission. Direction constrains *how* a correctness failure is fixed — never
*whether*.

**The ledger is empty on purpose.** Every device row in the six existing records
adjudicates shipped code and cites a file and line. A ledger of hypothetical
devices would be exactly the "reads like a mood" failure the direction contract
rejects. Rows are added as devices land, not before. An empty ledger is a valid
state: it means the defect gate wins by default, which is the correct posture
for a surface that does not exist yet.

---

## The contract

The ≤150-word block below is the canonical direction text. It ships as an HTML
comment in the emitted markup so it survives the production build, per
impeccable's direction contract (`skill/reference/new-work.md:71`).

```html
<!--
THESIS: One bit of state — is it listening — must be readable at a glance;
everything else recedes.

OWN-WORLD: An instrument, not a productivity app. A field recorder's panel:
dark, dense, metered. Not the soft pastel SaaS notetaker.

STORY: Dormant, alert, armed, running, settled. One indicator carries the whole
arc; the window is only where it lands.

FIRST VIEWPORT: The last meeting's note, already written. Never an empty
dashboard, never a welcome card.

FORM: Dark neutral ramp, monospace transcript, no shadows, no ambient motion.
The single accent is reserved for live capture and appears nowhere else.
-->
```

---

## Why this thesis and not another

The product's defining fact is that it listens to a room and you never watch it
work. Every competing product resolves that by putting recording chrome in front
of you — a bot tile in the participant grid, a browser tab, a floating window.
This one has no such affordance by construction, which makes ambiguity about its
state the central design risk rather than a detail.

So the thesis is not a mood ("calm", "focused", "minimal"). It is a ranking: the
listening indicator outranks every other element on every surface, and anything
that competes with it loses. That ranking is falsifiable, which is the test the
direction contract applies.

**The instrument framing is a rejection, not a reference.** Naming Linear,
Stripe and Vercel as references asks the surface to look like the category —
that is genre assignment, not art direction. The reference here is a class of
object: metered hardware whose job is to show you one reading you can trust. It
generates constraints the genre label cannot, most obviously the accent rule
below.

---

## Constraints this thesis generates

These bind `DESIGN.md` and pre-commit any device that would violate them.

**The accent means live and nothing else.** One color, used for exactly one
meaning: capture is running. It appears nowhere in navigation, selection,
links, focus rings, or charts. The immediate consequence — the palette carries
**no amber warning color**, because a warning that resembles the live indicator
destroys the one reading the product exists to make trustworthy. Warnings are
neutral foreground plus text.

*This collides with a real accessibility requirement, and the collision is resolved
here rather than at the first focus ring.* film-room's interaction contract states
"every keyboard-reachable control has a visible accent focus ring"
(`~/Workspace/dev/wip/film-room/docs/design-system/interaction-contract.md`), and
that project is further along than this one, so the instinct is to copy it. It
cannot be copied: an accent focus ring would put the live-capture color under the
cursor on every tab press. **Focus rings here are a high-contrast neutral outline
plus an offset**, which is visible against both the dark ramp and any raised
surface, and carries no state meaning at all. Contrast, not hue, is what makes a
focus ring findable — the accent was never doing that job, only marking it.

*And no state may be carried by color alone.* film-room's component catalog requires
every health and progress stage to "pair state word/icon with color". Here that is
not merely accessibility hygiene: `recording` and `degraded` must be distinguishable
at menubar size, and one accent used for both with only a tint between them fails
the product's central reading. Shape and a mark carry the difference; the accent
says only that something is live.

**No ambient motion anywhere.** A pulse, breath, shimmer, or looping gradient can
be misread as activity. The only moving element permitted is an audio level
meter, which is moving *because* audio is arriving — it is a reading, not
decoration. Reduced-motion still applies to it.

**Degraded is never silent.** Any state where capture is running with one leg
down must be visually distinct from healthy capture at menubar size, not only in
an opened window. This is what makes `degraded` a design constraint rather than
an error-handling detail.

**First viewport shows real content — but does not resume a session.** The window
opens on the notes library with the most recent note already rendered beside it,
not on a bare list and not on a single note filling the frame.

The second half of that is a correction, and it comes from the operator rejecting
exactly this pattern in a sibling project. Reviewing film-room
(`~/Workspace/dev/wip/film-room`), he wrote:

> "that intent feels incorrect. it's not how i would start lightroom or capcut. i
> would expect to open to a starting page then select what 'job' or 'library' or
> 'project' i wanted to work on, rather than assuming i want to go straight back to
> the last job/library/project."

An earlier version of this rule said the window opens *on* the last meeting's note,
which is the pattern he rejected. It is not fully transferable — film-room switches
between projects where "the last one" is genuinely ambiguous, while this tool holds
one chronological stream where the newest note usually is the answer — but the
underlying objection survives the difference: **do not decide for him which note he
came for.** Choosing is his; having something real to look at while he chooses is
ours.

List–detail with the newest note pre-rendered satisfies both, and it is why the
inventory has a library surface and no dashboard. The failure this avoids is also
recorded in that project — "so where is the content I use for reviewing with 630?"
— an app that could not show the operator his own material.

---

## Ledger

Verdicts: `authorized` / `condemned` / `undecided` / `removed`. Parsed only under
this heading, rows shaped `| \`device-id\` | verdict | … |`. Populated as devices
ship.

| id | verdict | device | cites the thesis by | rules |
|---|---|---|---|---|
| — | — | *No devices shipped yet.* | — | — |

---

## Notes

**This record is not machine-checked yet, but it will be, and the stack choice
that decides it is already made.** `DESIGN.md § Shell decision` chose Tauri over
SwiftUI, and enforceability of this file was the deciding factor rather than a
side effect: the `tools/design-qa` resolver, the impeccable detector, and the
forge-brand token bridge are all web-surface tools reading CSS custom properties,
rendered DOM and linked stylesheets, so a SwiftUI shell would have left this file
as prose nobody checks.

What remains is wiring, not deciding: `sites/local-meeting-notes/site.json`
pointing at this record, and suppressions required to cite an `authorized` row.
Neither can be built before a surface exists, which is why the ledger below is
still empty.

An earlier version of this note described the shell as an open question. It was
not — `DESIGN.md` had already decided it with both candidates developed — and
leaving that phrasing in place had a reader treat a settled call as a live fork.
