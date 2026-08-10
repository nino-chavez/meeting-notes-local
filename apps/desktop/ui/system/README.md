# Desktop UI system specimen

This directory is DS-1's isolated executable contract. It does not affect the
production shell. Open `index.html` through a local static server or the Tauri
webview to review foundations, component states, window roles, and accessibility
preferences.

Run the deterministic checks from `apps/desktop/`:

```sh
node --check ui/system/specimen.js
node --test ui/system/system.test.mjs
```

## What this proves

- light and dark semantic tokens exist;
- increased contrast, reduced motion, reduced transparency, forced colors, and
  a deterministic 200% specimen scale have explicit behavior;
- the initial component set has reviewable interaction and status states;
- primary, record, Settings, capture, and transient roles use distinct patterns;
- capture and record fallbacks preserve current product truth.

It does not prove native toolbar or Settings-window behavior, system materials,
VoiceOver order, installed-app keyboard routing, exact native 200% zoom, real
menubar state, or recording behavior.

## DS-5 primary-window comparison

The specimen compares three structures derived from a blind review of product
tasks, production behavior, Mac guidance, and the 720 × 560 width constraint. It
does not treat the existing split or prior option labels as authority.

1. **Persistent three-pane.** Sources, meeting list, and selected record remain
   visible. It switches fastest at comfortable width and compresses the record at
   the minimum.
2. **Adaptive two-pane.** Meeting list and selected record remain adjacent while
   space supports them. At the minimum, the collection and full-width record
   become two restorable navigation states.
3. **Single-pane stack.** Meetings, Search, and a selected record replace one
   another at every width. It reads most calmly and makes repeated switching
   slower.

The comparison did not justify freezing one structure for every operator and
window. The production contract keeps one route, selection, and record model,
then lets pane visibility vary through one persisted preference:

- **Automatic** is the default: list plus record while the record stays useful,
  then one pane below 800px.
- **Focus** always uses one pane and preserves the Meetings return path.
- **Library** shows sources, list, and record above 900px, then yields sources
  before the record becomes cramped.

The earlier adaptive result still informs Automatic. It no longer excludes the
other two valid working styles. `View → Layout` and Settings → Desktop Behavior
must edit the same closed preference; the route and content model do not change.

Use the global appearance control for light and dark, and **Front-door geometry**
for the comfortable and 720 × 560 comparison. These are browser composition
proxies, not installed-window evidence. Installed evidence belongs in a
digest-bound run under `docs/desktop-installed-app-reviews/`.

## DS-4 integration contract

1. Import `foundations.css`, then `components.css`, then `patterns.css` from the
   production `apps/desktop/ui/index.html`. Keep that order. Do not import
   `specimen.css` or `specimen.js`.
2. Map existing production custom properties to the `--ys-*` semantic tokens.
   Remove a legacy declaration only after every production selector using it has
   moved. Keep `--ys-brand` separate from `--ys-live`.
3. Replace production controls one job at a time with the matching `ys-*` class.
   Preserve IDs, `data-*` hooks, Tauri command names, and accessibility attributes
   until the shell tests are updated in the same integration change.
4. Migrate the three accepted references in this order: primary Library plus
   selected meeting; Settings Capture pane in the DS-2 native auxiliary window;
   consent through transcript-ready capture using the DS-3 pattern.
5. Keep `apps/desktop/ui/system/index.html` as the regression specimen. Add
   `node --test ui/system/system.test.mjs` to `test:ui` only during integration,
   when `apps/desktop/package.json` is in DS-4's ownership.
6. Delete no screen-local rule until its job resolves to one shared component or
   a documented product state that the shared component cannot express.
7. Run the installed-app acceptance matrix. Browser results may support geometry
   and interaction review, but cannot close native, VoiceOver, menubar, material,
   or exact zoom gates.
