# Yawn Settings window reference

This isolated Tauri build proves the window contract for DS-2. It does not replace
the production Settings route. It cannot read Yawn data, request capture permissions,
or call a product command.

## The reference proves one narrow Settings shape

The host window stands in for Yawn's primary window. Choose **Yawn Settings
Reference → Settings…** or press **Command–Comma**. A separate 720×560 Settings
window opens with Capture selected.

The reference includes seven stable pane destinations. Capture is the only complete
pane. Its device, permission, and recording-behavior groups are interactive reference
controls. The other panes prove navigation, focus, titles, and restoration without
presenting unbuilt product settings as live.

Apple's current guidance is the behavior floor:

- [Settings](https://developer.apple.com/design/human-interface-guidelines/settings)
  calls for an App-menu Settings item, Command–Comma, stable panes, a current-pane
  title, disabled minimize and zoom controls, and restoration of the latest pane.
- [Windows](https://developer.apple.com/design/human-interface-guidelines/windows)
  defines the native frame, key-window focus, system appearance, and ordinary window
  movement and closing behavior.

Tauri supplies the native menu and window plumbing through its
[window-menu](https://v2.tauri.app/learn/window-menu/) and webview-window APIs.

## Platform plumbing and webview content have separate jobs

| Behavior | Owner in this proof |
|---|---|
| App-menu Settings command and Command–Comma | Tauri native menu, rendered and dispatched by macOS |
| One Settings window at a time | Rust looks up the `settings-reference` window before creating one |
| Bounded 720×560 geometry | Tauri `inner_size`, matching minimum and maximum size, and `resizable(false)` |
| Disabled minimize and zoom | Tauri window builder |
| Native close | Tauri/macOS; DS-2 installs no `CloseRequested` interception for the Settings window |
| Reopen and focus an existing Settings window | Tauri `show`, `unminimize`, and `set_focus` |
| System light or dark appearance signal | macOS/WKWebView |
| Pane order, labels, selected state, and arrow/Home/End navigation | Webview HTML and JavaScript |
| Most-recent-pane restoration | Webview `localStorage`, validated before use |
| Current-pane window title | Webview chooses the title; the one allowed Tauri window capability applies it to the native window |
| Grouped controls, help text, focus rings, and light/dark tokens | Webview HTML and CSS |
| Capture-control values in this reference | Webview `localStorage`; they never reach Yawn product state |

CSS cannot create an App-menu command, a key window, native traffic-light behavior,
or native close and focus semantics. Tauri cannot make webview controls form a clear
group, expose a useful tab order, or explain an unmeasured permission state. DS-4 has
to preserve that boundary.

## Run and build the isolated app

From `apps/desktop/`:

```sh
npm run settings-reference
npm run settings-reference-build
```

The build uses its own product name, bundle identifier, frontend, feature, capability,
and ad-hoc signature. Its capability contains only `core:window:allow-set-title` for
the host and Settings windows. It has no product runtime resources.

## DS-4 integration instructions

1. Keep the production primary window and current Settings route unchanged until the
   installed reference is reviewed. Do not treat this producer commit as migration
   approval.
2. Port the menu item and `open_settings_window` behavior from
   `src-tauri/src/settings_reference.rs` into the production Tauri builder. Keep one
   Settings window label. On repeated App-menu or Command–Comma activation, show,
   unminimize, and focus the existing window.
3. Narrow the production global close handler. It currently hides every window to keep
   the tray alive. Apply that interception only to the primary window label. Let the
   Settings label close normally so the red traffic-light button performs a native
   close.
4. Add a dedicated production Settings-window capability. Grant only the commands the
   integrated Capture pane actually reads or changes. Do not copy the main window's
   capture, deletion, storage, or enrolment authority onto the auxiliary window.
5. Move the approved pane navigation and grouped-control jobs into the shared assets
   produced by DS-1. Do not paste this reference CSS into production
   `native-calibration.css`, and do not keep a second local implementation after the
   shared component owns the job.
6. Replace the reference-only Capture values with measured product state. Preserve
   `permissions-partial`; keep an unmeasured permission explicit; never request access
   merely to render Settings.
7. Keep pane restoration independent from control persistence. Validate the stored
   pane against the owned pane list, update the native title to the active pane, and
   keep arrow, Home, and End navigation in the stable tab sequence.
8. Remove the production route replacement and page-bottom Back behavior only after
   the auxiliary window passes installed-app review. A secondary discoverability link
   may open the same native window; it must not navigate the primary window.
9. Re-run the handoff acceptance matrix in the installed app: light and dark, declared
   geometry, Command–Comma, keyboard-only traversal, native close/reopen/focus,
   VoiceOver labels and order, reduced motion, increased contrast, reduced
   transparency, and 200% zoom.
10. Delete this isolated build lane only after the production Settings window passes
    the same checks and the migration ledger names no remaining Settings override.

## Evidence boundary

The source and deterministic tests prove configuration isolation, menu and window
intent, stable pane logic, system-derived appearance CSS, and the absence of product
permissions. A successful `.app` build and code-signature check prove an installable
native bundle was produced. They do not prove what the window looked like or how it
behaved on screen.

The 2026-08-09 native inspection attempt was blocked before the accessibility tree or
a screenshot was available: **“The Mac is locked and automatic unlock could not
unlock it.”** Do not replace that missing installed-window evidence with a browser
render or source inspection.
