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

**No ambient motion anywhere.** A pulse, breath, shimmer, or looping gradient can
be misread as activity. The only moving element permitted is an audio level
meter, which is moving *because* audio is arriving — it is a reading, not
decoration. Reduced-motion still applies to it.

**Degraded is never silent.** Any state where capture is running with one leg
down must be visually distinct from healthy capture at menubar size, not only in
an opened window. This is what makes `degraded` a design constraint rather than
an error-handling detail.

**First viewport shows real content.** The window opens on the last meeting's
note. This inherits the workspace default — previews show real content, not a
title card — and it is the reason there is no dashboard surface in the L5
inventory.

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

**This record is not machine-checked yet, and whether it ever will be depends on
the shell decision in `DESIGN.md`.** The `tools/design-qa` resolver, the
impeccable detector, and the forge-brand token bridge are all web-surface tools:
they read CSS custom properties, rendered DOM, and linked stylesheets. A SwiftUI
shell orphans all of it and leaves this file as prose only. A web-based shell
(Tauri) makes it enforceable — `sites/local-meeting-notes/site.json` pointing at
this record, and suppressions required to cite an `authorized` row.

That is a real consequence of a stack choice, and it is stated here rather than
discovered later.
