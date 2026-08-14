# Decision — what runtime executes the note-generation model

Date: 2026-08-14. Status: decided. Owner: operator (posture admitted in
`notes/EVAL.md`, "Product decision, 2026-08-14").

## Decision

Note generation runs on **MLX-LM inside the existing supervised Python
worker child** — the same bundled CPython 3.12 runtime, process supervision,
and network-denied posture that already executes mlx-whisper. Model weights
are **not bundled**; they ship through the existing model-catalog path:
sha256-pinned, revision-locked download into the private `models/` directory
with an install receipt and re-verification on every use, exactly as the
1.61 GB whisper-large-v3-turbo does today.

No new runtime class enters the product. Rust keeps owning safety, storage,
digests, and the process boundary; Python keeps owning model execution.

## Why not the alternatives

- **Ollama (the research runtime).** The measured 11/13 recall ran on
  ollama + gemma3:12b, but ollama is an external daemon reached over
  localhost HTTP. The shipped note path enforces
  `SECURITY_NO_NETWORK_ACCESS` on the child and a `connect-src ipc:`-only
  CSP, and the product promises no external dependency the operator must
  install. The research pin cannot ship as-is; ollama remains the
  research-harness transport only.
- **Apple Foundation Models.** A 4,096-token window against a measured
  ~14–19k-token prompt need, and a macOS 26 floor against the shipped
  minimum of 14.4. Revisit if either constraint moves; not a candidate now.
- **A Rust inference crate (candle, mistral.rs, llama.cpp binding).** Would
  introduce a new dependency class the codebase deliberately avoids — no
  Rust crate executes any model today — for no measured benefit over MLX-LM
  on the same Metal hardware.

## Consequence: re-measurement is the first build step

Ship-gate condition 1 (`notes/EVAL.md`) requires recall ≥ 11/13 re-measured
after **any** change to model, prompt, view, or decoding. Moving from
ollama/gemma3:12b to an MLX-LM quantization is such a change. Therefore no
app code lands until a preregistered MLX-LM arm of the capture classifier
(`notes/capture_classifier.py`) clears the gate on the operator-locked
ledger. If the MLX arm cannot clear 11/13, this decision reopens.

## Integration seams, in dependency order (mapped 2026-08-14)

1. MLX-LM arm of the research harness clears the ship gate (above).
2. `worker/note_bridge.py` — lift the validator-only refusals; the manifest
   already carries `generator` and `models` fields.
3. Implement `NoteProjector` (`crates/session-core/src/note_projection.rs`)
   backed by the hardened one-shot child in `note_projector_process.rs`,
   replacing `UnavailableProjector`.
4. Register `regenerate_note` (`apps/desktop/src-tauri/src/product_facade.rs`)
   in `generate_handler!` with its permission TOML and capability entry,
   mirroring the transcript-model-settings commit shape.
5. Add the `Operation` variant, progress state, and worker heartbeat in
   `crates/session-core/src/protocol.rs` + `worker/main.py`.
6. Extend `model-catalog.json` and `model_store.rs` with a note-model role;
   reuse `model_download.rs::install` unchanged.

Known risk to manage at step 5: a ~7–8 GB 4-bit model and whisper weights
contend for unified memory in one MLX process; note generation must run
after transcription completes and release the whisper runtime first (the
release hook already exists in `worker/transcription.py`).

## Correction, 2026-08-14 — network denial is structural, not enforced

Two independent implementation sessions verified the same fact: the
`SECURITY_NO_NETWORK_ACCESS` flag in `note_projector_process.rs` is
`kSecCSNoNetworkAccess`, a code-signature *validation* option (it stops the
signature assessment from fetching revocation data over the network). It does
not deny the child process a socket, and the bundled Python's entitlements
carry no sandbox. Today the no-network promise for the generator child is
structural — its bytes are digest-pinned, so what runs is known — but nothing
enforces it at runtime. Before the note generator ships, the launcher must add
real enforcement (a sandbox profile or equivalent) or this document's
"network-denied posture" language must be weakened to match reality. Tracked
as a pre-ship requirement, not folded silently into any slice.
