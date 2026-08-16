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

**Resolved, 2026-08-15 — enforcement is now real.** The launcher's `pre_exec`
calls `sandbox_init` with the named `no-network` Seatbelt profile between fork
and exec, so the kernel denies the interpreter child every socket. The sandbox
survives exec and wraps no binary, so the pinned interpreter path and the
code-signing admission chain are unchanged; application is fail-closed (a
child the profile cannot be applied to does not launch). Verified before
landing: the profile denies a local TCP connect (EPERM) and leaves mlx GPU
compute working, both probed empirically; a characterization test in
`note_projector_process.rs` pins the behavior (the connect an unsandboxed
control child completes is denied in the sandboxed child). `sandbox_init` is
deprecated in the headers with no replacement for this shape — sandboxing a
child the parent is about to exec — which is the "why not canonical"
sentence: the supported alternatives (App Sandbox entitlements, a
NetworkExtension content filter) either sandbox the wrong process or are
system-wide machinery for a per-child guarantee.

## Merge checklist (recorded 2026-08-14, owner: the session that merges)

Four finished branches wait on the measurement gate, all runtime-agnostic:
bridge admission (`worktree-agent-a331fcc4b9544b303`, 15 commits), projector
(`worktree-agent-a4d535796e42db89a`, 10 commits), command/protocol
(`worktree-agent-a3028d9a18ca4af29`), catalog (`worktree-agent-a7cd23fd64579a7c6`).
Items no branch owns, which must not evaporate at merge:

1. **Shared cross-language fixture pass** (after all branches land): one
   non-ASCII result frame; `invalid_result_frames` rows for
   `strictly_sorted`, digest length, locator cap, empty claim text
   (genuine Rust-side gaps); control-character and surrogate rows as
   parity locks. Both closing agent reports state it identically.
   **Done, 2026-08-15**: `note-projection-v1.fixture` gained
   `valid_results[2]` (the fixture's one non-ASCII claim text, parsed on
   both sides) and six `invalid_result_frames` rows — unsorted locators,
   truncated claim digest, four locators, empty claim text,
   control-character claim text, lone-surrogate escape — each generated
   from the same template as the parsing valid row and mutated in exactly
   one field, so the rejection is attributable. Both consumers exercise
   them: the Rust generic loop plus a `results[2]` assertion, the Python
   structural loop.
2. **Network enforcement before ship** (see Correction above): sandbox
   profile or equivalent on the generator child, or weaken this doc's
   posture language.
3. **Seam-6 alignment**: the projector's one-id-per-role model mapping is
   pinned by a characterization test and must widen when the catalog's
   sharded-weights role merges; `worker/build_manifest.py` needs the
   `note-runtime-generate.json` sibling constant.
   **Done, 2026-08-15**: `note_runtime_models` now derives one identifier
   per file from `catalog.note_models` (shards carry their designator:
   `note-generator-weights-00001-of-00002`; duplicate identifiers collapse
   the derivation to empty — honest refusal, never an ambiguous match), and
   `build_manifest.py::note_runtime_model_id` mirrors it, each side pinned
   to the same expected list by its own test. The catalog carries the
   registration-pinned gemma-3-12b-it-qat-4bit entry (snapshot 66fc51ef…,
   six files), hosted on the same R2 bucket as the whisper weights. A
   six-file tree was measured to load and tokenize byte-identically to the
   full snapshot on the product rendering path before the entry landed —
   the fixed two-turn rendering never calls the tokenizer's chat template,
   so the files the catalog cannot express are behaviorally inert.
4. **Registration adoption**: the official gated run adopts the ±2 view,
   the ollama two-turn rendering, the MLX runtime identity, and — if the
   pruning arm passes its second-capture validation — the pruning stage,
   as one preregistered registration change with a fresh operator lock.
   **Satisfied, 2026-08-15**: the candidate-first program's registration
   (digest 98dcbbd9…, `notes/EVAL.md`) carries the ±2 view, the two-turn
   rendering, the MLX runtime identity, and the budget-fitted pruner;
   four corpora hold official passes under it, each with a recorded lock
   (operator-delegated, supersession chains in the packets).
5. **Wiring recipe** for `admit_note_projector` at `library_reader.rs:338`
   is in the projector agent's report (catalog from
   `verified_model_catalog`, resource root from `StorageContext`, cache
   the admission decision off the hot rebuild path).
   **Done, 2026-08-15**: `library_snapshot_with` (the one production
   rebuild site) now injects `admitted_note_projector(state)` — catalog
   from `verified_model_catalog`, manifest paths from the resource root
   via constants owned by `note_projector_process.rs`, successful
   admission cached for the process lifetime, refusal re-derived per
   rebuild so a model installed mid-session admits without a restart
   (`admit_note_projector` now returns `Option` to make that split
   possible). Today it resolves to `UnavailableProjector` — no generate
   manifest is bundled and the catalog carries no note-model role — and
   activates mechanically once the catalog entry ships.

## Merge record (2026-08-14, late night)

All four branches merged to local main under the operator's standing
delegation, after the measurement gate cleared via the batch-size-1
adoption (notes/EVAL.md). One cross-branch fix at merge: the projector's
test catalogs gained the catalog branch's `note_models` field. Full lanes
green post-merge: session-core, desktop, UI, worker, root. Worktrees
removed. Remaining from the checklist: the shared cross-language fixture
pass (open, owner still unassigned), network enforcement (pre-ship),
seam-6 widening for sharded weights (pinned by characterization test),
catalog entry + model hosting (needs the external-publish step the
delegation excludes), and app-side admission wiring (in progress:
bridge product alignment + real MLX generator child).

## Merge record addendum (2026-08-14, later)

The bridge product-alignment branch merged to local main under the same
delegation: the generate lane now runs the product registration (±2
window, batch size 1, prune-then-budget on the pruned set, 3600 s
deadline bound to the registration at startup), and the real
`worker/note_generator_mlx.py` child exists with its sync obligation
enforced as a byte-identity test against `notes/product_run.py`. The
generate manifest builder lands unwired by decision: Rust refuses an
empty-models manifest and the signed catalog carries no note-model role
yet, so wiring waits on the catalog entry. All lanes green post-merge.
(The id constraint this paragraph originally stated — exactly
`note-generator-config` and `note-generator-weights`, sorted — described
the pre-widening derivation; seam 3's 2026-08-15 closure in the checklist
above owns the current per-file scheme.)

Caveat carried from notes/EVAL.md: the product registration this lane
aligns to is under an open refusal — official run 1 missed the recall
gate at the registered ±2 window. The lane binds to the registration
mechanism, not the numbers; an amendment moves the digest and the
startup binding check refuses any half-updated bundle loudly.
(Superseded 2026-08-14/15: the amended registration 98dcbbd9… holds
official passes on four corpora; see EVAL.md.)

## Merge record addendum (2026-08-15) — the catalog entry shipped

The operator pointed out the hosting question answered itself: the whisper
weights already serve from the `yawn-releases` R2 bucket, so the note model
ships the same way. Landed as one thread: the six-file catalog entry
(checklist item 3 above), `main()` writing the generate manifest, and the
packaging flip —
the five note runtime resources moved from a forbidden list to a required
one in both Tauri configs, `prepare-preview-bundle.sh`,
`sign-notarize.sh`, and `verify-release-bundle.py`, each flip pinned by its
updated test. The Settings window gained a "Note model" section backed by
three new commands (`note_model_settings`, `install_note_model`,
`remove_note_model`); `model_download::install` was generified over
`DownloadableModel` exactly as its trait comment documented. Unlike a
speech model, the note model may be removed while active — "no note model"
is an ordinary state the library renders honestly — so removal deactivates
first (`deactivate_note_model`) and drops the cached projector admission.

Hosting status at the time of this addendum: four of the six objects
(config, weights index, tokenizer, tokenizer config) are uploaded and live
on R2. The two weight shards (~8 GB) are **not uploaded** — the transfer was
stopped mid-flight when the operator moved to a metered connection — and no
public byte-count or downloaded-hash verification has run for any object.
Until the shards land and all six objects verify against the catalog pins,
an `install_note_model` against the published catalog fails at download or
at digest verification; the catalog entry is code-complete but not yet
servable. Upload and verification resume on operator clearance.

**Resolved, 2026-08-15 evening**: on operator clearance the aborted
multipart was cleaned, both shards uploaded, and all six objects were
downloaded end-to-end from the public URLs — byte counts and sha256
digests match the catalog pins exactly. The catalog entry is servable;
the hosting requirement of the distribution runbook is met.

## Design — the generation invocation chain (2026-08-15)

The last unbuilt stretch: nothing invokes generation. `regenerate_note`
is registered but `accept_regeneration` refuses by design; the worker
refuses `note.create` (no admitted generator); the Rust child launcher
only speaks the `project` role. Three candidate structures were
developed and compared before committing to one.

**Candidate A — generation inside the worker.** Admit `note.create` into
the worker's operation set and have the worker itself run the model
(spawn `note-generator-mlx.py` or load MLX in-process). One transport
(the existing supervised worker), and the `note.create` heartbeat and
Rust progress plumbing already exist. Rejected on one decisive fact: the
kernel no-network sandbox and the code-signing admission chain are
applied by the Rust one-shot launcher's `pre_exec`; the standing worker
is not launched that way, so the model child would run without the
guarantee the bridge architecture was built to provide. Sandboxing the
long-lived worker instead is a far larger change with its own risks.

**Candidate C — the bridge generate lane publishes end-to-end.** Extend
`validator.generate` to assemble the note/2 pair and write it. One
launch, sandbox intact. Rejected because it breaks two deliberate
boundaries the code states in its own comments: the validator "writes no
note" by design, and durable publication (immutable pair, meeting
record, lifecycle) is the worker's storage discipline — duplicating it
into the one-shot bridge is drift in the most hardened component.

**Candidate B — split at the points boundary (chosen).** Two steps, each
component doing exactly what it was built for:

1. A generate-role launch of the hardened one-shot child
   (`note_projector_process.rs` grows a generate lane): same
   interpreter admission, same `pre_exec` seatbelt, generate manifest
   (`note-runtime-generate.json`), registered 3600 s deadline. The
   bridge runs the model child and returns
   `note-generation-result/1` — KEEP verdict points, locators only,
   bounded by the existing 64 KiB frame cap.
2. The worker's `note.create`, admitted at last, with its generator
   argument satisfied by a *deterministic assembler* built from those
   points: kept locators → `render_structured_note` → citation checks →
   `note_artifact` (all already shipped in the runtime's `summarize`)
   → the validated immutable pair. No model in the worker — the
   adapter's "no model default" stance is preserved literally; the
   model never runs outside the sandboxed one-shot child.

Consequences accepted with B: the `note.create` argument contract widens
to carry the generation points; the coordinator sequences two child
launches per regeneration; failure surfaces stay honest and distinct
(model-side failures arrive as the bridge's `transcript-only` outcome,
assembler failures are deterministic artifact bugs that must be loud).

Sub-decision within B, recorded here: the generate-role child launches
through an **extended descriptor bootstrap** (a fourth descriptor for
the generator bytes), not through the path-based `main()` entry. The
descriptor protocol exists so the child executes pinned bytes, never
pathnames; a path-based generate launch would quietly weaken that for
the one role that runs the model. Both structural refusals — the Rust
`BOOTSTRAP` role check and `verify_descriptor_runtime`'s
project-only gate — widen together, with the generator descriptor
required exactly when the role is `generate` (the same biconditional
the manifest already enforces).

Build order: (1) Rust generate transport + descriptor widening, (2)
worker `note.create` admission + assembler (operation sets move in
lockstep with `supervision::internal_alpha_operations()`), (3)
coordinator sequencing behind `accept_regeneration`, (4) the UI
regenerate control.

**Slice 1 landed 2026-08-15 (commit `ad2eeec`).** The descriptor set and
the role are one decision on both sides: three descriptors speak
`project` exactly as before, a fourth — the manifest-pinned generator
bytes — speaks `generate`. Rust's hardened child-drive is one
role-parameterized sequence shared by `ProcessNoteProjector` and the new
`ProcessNoteGenerator`; `admit_note_generator` applies the projector's
admission rules and binds the verified installed model directory.

**Slice 2 spec (recorded before building, 2026-08-15).** The generate
lane returns `note-generation/1` points: located anchor excerpts with no
claim type and no prose — deliberately, because the candidate-first
program classifies KEEP/ABSTAIN over transcript-anchored candidates and
writes no claims. The note/2 claim vocabulary today is four types
(decision, action, proposal, question) inherited from the cue-era
extraction pipeline. Assigning any of those four to a typeless kept
point would be mis-attestation by construction. The product brief
resolves the shape: generated content is "points — a draft from the
transcript", each with a clear path back to the source text. So slice 2
adds one honest vocabulary entry — a `point` claim type rendering under
a single "Points" section — rather than faking types or widening the
note into a summary. Claim text is the anchor excerpt verbatim (claim
and quote coincide; the pipeline writes no prose by design). The entry
widens together everywhere the vocabulary is pinned: `summarize`'s label
set, render titles and claim parser; `note_projection.rs::ClaimType`;
the shared cross-language fixture (one additive valid row); and the UI
claim presentation. `note.create`'s argument contract gains the
generation result (points), and the injected generator becomes a
deterministic assembler: points → excerpt items → the existing
memory-only note/2 build chain (`attach_evidence_items` →
`normalize_extraction_items` → `render_structured_note` →
`structured_citations` → `structured_artifact_citations` replay), the
same chain `mlx_note_admission.py` already drives for research
candidates. The worker's operation sets and
`supervision::internal_alpha_operations()` move in lockstep, exactly as
the `corpus.embed` drift note in `supervision.rs` warns.

**Slice 2a landed 2026-08-15: the vocabulary, with one compatibility
finding.** The `point` type is admitted end-to-end (summarize's label
set, `_TYPES` section mapping, render titles; the validator's claim-row
gate; `ClaimType::Point`; the library reader's serialization — the UI
humanizes types generically). The finding: the model-extraction request
schema embeds the label enum, and every retained note/2 replays that
schema digest-for-digest through `structured_citations` — widening the
enum in place refused eight fixture notes, which is exactly what it
would do to a shipped user's existing notes after an update. So the
extraction contract is now its own frozen four-label constant
(`_EXTRACTION_LABEL_VALUES`); POINT lives only in the validation
vocabulary and rendering, and a points-note must carry candidate-first
provenance rather than a synthesized extraction stage. That constrains
the slice-2 assembler design: it cannot reuse the extraction stage
receipts; the `checks` a product note stores come from `report()`,
whose gates assume a model-written note (`calls`, prompt-echo,
context), so the assembler needs either a candidate-first-native checks
path or a deliberate satisfaction of those gates — the next design
question, not yet decided.

**Slice 2b design (decided 2026-08-16): a second evidence contract,
not a synthesized model run.** `structured_artifact_citations`
hard-replays extraction stage receipts — per-slice prompts, request
schemas, model identity — none of which a deterministic points assembly
possesses, and synthesizing them would be the same mis-attestation the
fake claim types were rejected for. The note/2 artifact already carries
a discriminator (`claim_evidence_contract`, single-valued until now),
so points-notes declare `candidate-evidence/1` and the citation entry
point dispatches on it. Its replay is stronger than storage: the
candidate manifest is a pure function of the transcript and the
registered product contract, so the validator regenerates it
(`generate_manifest`, broad strategy, ±2 window), requires the stored
`manifest_sha256` to match, resolves each point's `candidate_id` back
to its anchor fragment, and re-derives every locator span and digest
from the transcript itself. Claim text must equal the anchor excerpt
verbatim. The stored `checks` object keeps the one shared verdict
formula (`verdict()` stays the only owner): `citations` is computed for
real by the candidate replay; gates that measure model pathologies
record their own truthful state — `context.ok: null` (not scored — the
established meaning for a stage that does not exist), `attribution`
and `extraction` `applies: false`, `numbers` computed genuinely against
the transcript text, `prompt_echo` vacuously true with its reason
recorded. The assembler and the candidate replay both live in
`summarize` — one owner, shipped to the worker and the validator bundle
alike. Memory contention is already handled: whisper's
runtime is released inside the worker before the `transcript.create`
terminal frame, so any regeneration accepted at `TranscriptReady` or
later starts past the release.

**Slice 2 landed (2026-08-16, commit 4a3404a).** The worker now admits
`note.create` with an optional exact-shape `generation` payload
(`note-generation/1`: transcript pin, `manifest_sha256`, candidate
count, points, run receipt) and assembles a published note/2 through
the deterministic candidate-point assembler in `summarize`
(`candidate_note_document`). Points-notes declare
`claim_evidence_contract: candidate-evidence/1` and their citations
replay by regenerating the manifest from the transcript, exactly as
designed in 2b — the end-to-end dispatch test drives manifest points
through the worker to a published note whose artifact replays
digest-for-digest. Bare `note.create` (no payload) still refuses, and
`ALPHA_OPERATIONS`/`internal_alpha_operations` moved in lockstep. All
four lanes green (session-core 412, worker 192+40, desktop 130, UI 10).
Remaining: slice 3 (coordinator sequencing behind `accept_regeneration`
— the desktop `NoteGenerationWorker` impl that runs the generate child,
parses `note-generation-result/1`, and issues this `note.create`), then
slice 4 (UI regenerate control).

**Model-size research (2026-08-16, operator question: newer open-weight
models with better compression).** Web research plus direct HF API
verification. The current note model (gemma-3-12b-it-qat-4bit, 8.06 GB)
now has credible smaller challengers; the two worth evaluating, both
license-verified Apache-2.0 via the HF API (redistribution on our R2
mirror is clean, no Gemma-terms passthrough):

- **Qwen3.5-4B** (mlx-community/Qwen3.5-4B-MLX-4bit): 3,061,132,920
  bytes (verified). Vendor benchmarks place it above the Gemma-3-12B
  class; hybrid linear-attention architecture should also cut per-call
  latency. Risk: newer architecture — confirm the pinned mlx-lm
  supports it before committing. Conservative fallback:
  Qwen3-4B-Instruct-2507-4bit (2.28 GB, standard transformer).
- **Granite-4.0-h-micro** (3B, 1.81 GB): best verified
  instruction-following for its size (IFEval 82.3 from IBM's card);
  hybrid Mamba2 built for exactly our latency profile. Knowledge below
  12B class — but the product task is constrained KEEP/ABSTAIN plus
  extractive points, where instruction adherence dominates.

Also noted: Gemma 4 reportedly moved to Apache-2.0 (single-source,
re-verify before mirroring), but its E4B is 5.25 GB at MLX 4-bit —
over target; LFM2.5-2.6B (1.54 GB) is capped by its license at <$10M
commercial revenue — rejected for a shipped product; MLX now supports
MXFP4/NVFP4 and DWQ conversions, a second compression lever beyond
uniform 4-bit.

Any adoption runs the full preregistered eval (11/13 recall bar on all
four corpora) as a new arm — sequenced after the offer-stride arm
lands, which halves the cost of exactly that evaluation.

**Family follow-up (operator question: GLM, Grok, DeepSeek).** All
three ruled out, verified against the HF API through Aug 2026. GLM:
licensing is fine (MIT across the family) but size is not — the
smallest MLX conversions are GLM-4-9B-0414 at 5.31 GB and
GLM-4.6V-Flash at 7.09 GB, the 2026 releases are all flagship-scale
MoE, and GLM-Edge (1.5B/4B, 2024) has no MLX conversion at all. Grok:
xAI has only ever open-weighted 100B+ models (Grok-1, Grok-2.5, the
latter under a restrictive community license); nothing small exists.
DeepSeek: every 2026 release is giant MoE (V4-Flash is 304B —
"Flash" is not small); the R1-Distill small models are reasoning-tuned
and emit long chain-of-thought before answering — the wrong shape for
a single-token constrained verdict, and slower, not faster, per call.
Shortlist unchanged: Qwen3.5-4B, then Granite-4.0-h-micro.

**Model-selection closure (2026-08-16).** All three shortlist
candidates were evaluated against the four locked corpora under the
preregistered gates (notes/EVAL.md): Qwen3-4B-2507 passed 1 of 4,
Granite-4.0-h-micro 0 of 4, Qwen3.5-4B 0 of 4 (run under a separate
research venv with mlx-lm 0.31.3; the product runtime pin is
untouched). Small models under-keep real meeting speech by 5–25x and
miss most locked events; a probe confirmed the abstention is model
judgment, not the harness. **The 12B stays; the question is closed**
until a materially new small-model release, and the arm harness in the
packet makes a future re-test a one-command affair per candidate.

**Slice 3 landed (2026-08-16, commit a5462e4).** `accept_regeneration`
now runs the real chain: the desktop admits the generate child per
call from live storage (verified catalog, generate manifest), runs it
sandboxed, parses the `note-generation-result/1` frame under a strict
envelope (session-core `parse_note_generation_result` — request-id and
transcript pins bound, outcome/payload coherence enforced), and hands
the generation object verbatim to the worker's `note.create`, whose
frozen contract and deterministic assembler own every deeper judgment.
A `transcript-only` child outcome becomes a durable Rejected receipt
carrying only recoverability; the published pair is re-inspected
through the worker's `note.inspect` before the meeting record
advances. Without an installed note model, admission refuses before
any process is launched. Remaining: slice 4 — the UI regenerate
control and the facade command registration, where the long-running
generate call moves off the command thread.

**Slice 4 landed (2026-08-16, commit 2d2db87) — the chain is complete.**
The meeting view renders a Generate-note control whenever the backend's
note response carries `regeneration_source_sha256` — the eligibility
signal and the source pin in one field, present exactly when the
facade would admit the operation. The button goes busy per meeting
while the minutes-long command runs (Tauri executes it off the main
thread; snapshot polling and the rest of the app stay live), and
completion re-opens the meeting to show either the published note or
the summary-failed answer. The command now finishes the facade's
single-operation slot at the terminal receipt and carries the same
setup-recording guard as restoration; `regenerate_note` joined the
shell contract's pinned product-command set. With slices 1–4 landed,
the full path exists: button → facade → coordinator → sandboxed
generate child (admitted model, strided offer, constrained verdicts,
pruner) → worker `note.create` (deterministic assembler,
candidate-evidence/1 replay) → fresh `note.inspect` → published
meeting note. What remains is operational, not structural: a real
end-to-end run on this machine against an installed model, and the
operator's read of a generated note.
