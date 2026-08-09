# DS-3 reference surfaces

This isolated workbench proves two desktop patterns without changing a production
screen:

1. Library, meeting list, and selected meeting in the primary Mac window.
2. Consent, healthy recording, degraded recording, and local processing in a compact
   capture utility.

The workbench uses reference content. It does not read local meetings, open audio
devices, or call a Tauri command.

## Reader contract

| Surface | Reader and job | Assumed knowledge | Plainness | Precision locks |
|---|---|---|---|---|
| Product specimen | A Mac user must know whether Yawn is recording, what remains on this Mac, and what action is safe now | Ordinary macOS use | Lay | Recording, degraded capture, recording audio, Transcript, On this Mac, no participant notification |
| Migration map | DS-4 must replace duplicate production selectors without changing the Rust state authority | HTML, CSS, JavaScript, Tauri | Practitioner | Selector coverage, state exceptions, 1120×720, 720×560, 620×560, 520×520 |

Visible copy is owned by `index.html`. State changes and keyboard behavior are owned by
`reference-surfaces.mjs`. Foundations and component treatments are owned locally by
`reference-surfaces.css` until DS-4 binds the reviewed DS-1 assets.

## Open the workbench

From this directory:

```bash
python3 -m http.server 8000
```

Then open `http://127.0.0.1:8000/`. The controls change the surface, state,
appearance, and geometry. Add `presentation=true` to hide the workbench controls while
keeping the reference-evidence caption.

Supported query values:

| Parameter | Values |
|---|---|
| `surface` | `primary`, `capture` |
| `state` | Primary: `loading`, `empty`, `ready`, `error`; capture: `consent`, `recording`, `degraded`, `processing`, `error` |
| `appearance` | `light`, `dark` |
| `geometry` | `comfortable`, `minimum` |
| `presentation` | `true` to hide workbench controls |

## Keyboard paths

- Up and Down move through product navigation and meeting rows.
- Left, Right, Home, and End move and select meeting tabs.
- Space and Return use native button and form behavior.
- Escape cancels consent and hides non-recording capture states.
- Escape never stops or dismisses healthy or degraded recording. Use Stop.

## Evidence and limits

The `evidence/` folder holds like-for-like browser renders of both appearances, both
declared geometries, a visible focus state, healthy recording, degraded recording, and
processing. The focused test also sweeps every loading, empty, disabled, selected,
error, and degraded state.

These renders prove webview layout and interaction behavior. They do not prove native
titlebar placement, VoiceOver order, menubar state, real capture, real local data, or
installed-app quality. Those remain DS-4 gates.

Run the focused checks with:

```bash
node --test apps/desktop/ui/reference-surfaces/reference-surfaces.test.mjs
```

Use [`MIGRATION.md`](./MIGRATION.md) for selector ownership and the exact DS-4
integration sequence.
