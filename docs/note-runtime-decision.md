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

**Operational close-out (2026-08-16) — three defects found running the
chain for real, one still blocking.** The note model was hand-installed
against the sealed catalog digests (`gemma-3-12b-it-qat-4bit`, six
files under `models/note.d/<id>/<revision>/`) and the packaged app was
driven end-to-end for the first time on this machine.

*Release-blocking catalog bug, fixed (commit 98102da).* The packaged
worker's exact-shape check on the runtime catalog predated `note_models`
joining that schema, so the shipped 0.5.7 worker refused the whole
catalog and exited silently at startup once a note model was present.
Widened the check plus a regression fixture; full worker suite green.

*Running a local build requires the release lane's signing stage, not
just `npm run build`.* The preview-signed dev bundle has an
ad-hoc/linker-signed Python and an outer app with no hardened-runtime
flag, so `SecurityCodeVerifier` correctly refuses child admission
before any model runs. A runnable local build needs the same signing
`scripts/sign-notarize.sh` performs minus the Apple submission: sign
every nested Mach-O (`--options runtime --timestamp`, Python gets
`--identifier com.ninochavez.local-meeting-notes.python-runtime` and
the Python entitlements), refresh `app-runtime.json` and the
`note-runtime-*.json` manifests from the signed bytes
(`worker/build_manifest.py`, which must run *before* the outer sign —
running it after breaks the outer seal), then sign and verify the
outer bundle. Never replace the binary on disk under a running
process — the kernel SIGKILLs it on the next `CODESIGNING`/"Invalid
Page" fault; always stop the app first.

*Admission defect, fixed (commit 13d1aff).* With a properly signed
bundle, admission reached child spawn and then failed at the dynamic
bind: `SecCodeCheckValidity` with `kSecCSMatchGuestRequirementInKernel`
returned `errSecCSReqInvalid` for the live child. Reproduced standalone
outside the app — same result against a fresh admission child,
`/bin/sleep`, and the process's own self-code, on macOS 26.5.2,
independent of which requirement was passed (a bare cdhash requirement
failed identically to the full designated requirement). The flag has
never worked in this app; the affected path (`drive_bridge_child` →
`bind_live_code`) is shared by both the `project` and `generate` roles,
so 46a3eef's admitted note projector never actually admitted a live
child on this OS either — the library-rebuild path degrades to no
projection, not a crash, so this was silent. Fix: dropped the flag,
keeping the plain designated-requirement match. The residual guarantee
against a between-checks path swap is unchanged — `bind_live` already
re-verifies the live executable's pinned fd identity and digest
(`verify_live_executable_file`) after the dynamic check returns.

*Packaging gap, unresolved — this is what blocks the run.* With
admission fixed, generation itself now runs the full sandboxed child
protocol (spawn, ready, result) cleanly, but the child immediately
refuses with `response-contract`. Traced to source: `worker/note_generator_mlx.py`
imports `mlx_lm` to load and decode against the model, but `mlx_lm` is
not installed anywhere in the bundled Python runtime
(`apps/desktop/vendor/python-runtime` and the staged
`apps/desktop/runtime/python-runtime` both carry `mlx` and
`mlx_whisper` for transcription only). `_Session.resolve()` raises
`ModuleNotFoundError` → the child writes `{"error": "model could not be
loaded"}` and exits → the bridge reads a well-formed JSON line whose
shape isn't the classifier contract → `response-contract`,
non-recoverable. This is a first-run discovery, not a regression: no
build has ever run this path to completion, so the dependency gap was
never exercised. `mlx-lm==0.31.3` is what the research venv used for
model selection (`notes/EVAL.md`), but naively `pip install`-ing it
into the product runtime pulls a newer `mlx`/`mlx-metal` (0.29.3 →
0.32.0) as a transitive dependency, upgrading the same package
`mlx_whisper`'s already-shipped transcription path depends on — an
untested, unrequested change to a working feature. There is no
lockfile for either vendored Python runtime tree (both are
git-ignored, machine-local); `spike/requirements.txt` pins
`mlx-whisper`, `numpy`, `speechbrain`, `torch` and has never named
`mlx-lm`. This is a packaging decision, not a one-line fix — see the
options below. The end-to-end run and the operator's read of a
generated note stay blocked until it lands.

*Known gap, not addressed here.* `recover_incomplete` exists in
session-core but the desktop never calls it, so a failed or
interrupted generation leaves a nonterminal operation record that
permanently refuses every later `regenerate_note` attempt for that
meeting (`Ambiguous("another nonterminal operation already exists")`).
Manual workaround used during this session: delete the stale directory
under `.../operations/<uuid>/` (safe when it holds only
`request.json`). Wiring the recovery call into the desktop coordinator
is its own slice.

**mlx-lm packaging options, priced.** Whichever is chosen, land it as
its own slice with the arm harness re-run to confirm `mlx_whisper`
still passes.

1. *Add `mlx-lm` + transitive deps to the shared product runtime,
   upgrading `mlx`/`mlx-metal` in the process.* Cheapest to implement —
   one `pip install --target`, one re-sign. Cost: ~15 new packages
   (`transformers`, `safetensors`, `sentencepiece`, `protobuf`, `typer`,
   `rich`, …) with new compiled `.so` files into a bundle whose
   admission model rests on signed, digest-pinned bytes — bundle-size
   and notarization-surface growth — and an unverified `mlx_whisper`
   run against a newer `mlx` than it shipped on.
2. *Pin an older `mlx-lm` release compatible with the already-installed
   `mlx==0.29.3`,* if one exists, avoiding the shared-dependency bump
   entirely. Needs a compatibility check against the release history
   before committing; not yet done.
3. *Isolate the generate child's site-packages* from the transcription
   runtime's, so `mlx-lm`'s newer `mlx` only ever loads inside the
   sandboxed generate role and `mlx_whisper` keeps running against its
   already-verified `mlx==0.29.3`. Avoids the cross-feature risk
   entirely; costs a second vendored Python tree (or a second
   site-packages root the generate child's `sys.path` is pointed at)
   and a corresponding change to the admission/signing recipe, which
   currently assumes one Python runtime per bundle.

**Operational close-out, continued (2026-08-16) — the chain ran end to
end.** Option 3 above was chosen: `worker/note_bridge.py`'s generator
bootstrap now inserts a private `generate-site-packages/` ahead of the
shared one on `sys.path`, derived from `sys.executable`, before the
child imports anything. `mlx_whisper` keeps resolving the shared,
already-verified `mlx==0.29.3`; only the generate role's own bootstrap
sees the isolated tree carrying `mlx-lm` and its newer `mlx` pin. With
that in place, the app was driven through capture → transcript →
candidate generation → note publication → re-inspection on this
machine, against a real meeting, for the first time. Four more defects
surfaced running it, three fixed here and the fourth already fixed
above; the fifth (below) is why the run didn't complete on the first
try even with all four landed.

*Unbounded memory growth, fixed.* The registered classifier batch size
is 1, so `decide()` runs once per offered candidate — up to a few
hundred per real meeting — and mlx's Metal allocator caches freed
scratch buffers for reuse rather than returning them to the OS.
Nothing in the loop reused a cache across calls, so it grew unbounded
across the run instead of staying near one batch's peak: measured at
27GB on this machine, which forced a hard restart mid-session (Force
Quit reported the app at 27.39GB, non-responding). `mx.clear_cache()`
after each candidate's `decide()`, mirrored identically between
`worker/note_generator_mlx.py` and `notes/product_run.py`'s
`MLXVerdictTransport` per that file's own sync obligation, brought RSS
back to ~1GB between batches — verified by live memory monitoring
during a real run.

*Staged bundle missing a dependency, fixed.* Generation failed with
`ModuleNotFoundError: No module named 'candidate_first'` inside the
injected note generator, even though `notes/candidate_first.py`
already existed in the repo. `apps/desktop/runtime/notes/` — the
staging directory `tauri.conf.json` bundles into the app — was a stale
subset (3 of 82 files) that predated `note.create`'s dependency on it.
This directory is gitignored and rebuilt at package time, so the fix
is staging discipline, not a source change: copy `notes/candidate_first.py`
into the staging tree (and the currently-built app's `Resources/`
copy) alongside the other `notes/` modules it already carried.

*Admission gap, fixed (commit 9baa602).* `note.inspect` stayed
boundary-lane-only under the belief that it ran through the sandboxed
bridge's own `inspect` role rather than the standing worker port — but
`WorkerProcessNoteInspectBridge` always calls the standing worker
regardless of admission level, so under `internal-alpha` the worker
refused the operation outright. A published note could reach
`note.create` and then get stuck one step short of the meeting record:
`apply_result` never ran, `meeting.json`'s `lifecycle` never advanced
past its pre-note state. Promoted `note.inspect` into
`ALPHA_OPERATIONS`, the same move made for `corpus.embed` once its
model was packaged — see `crates/session-core/src/supervision.rs`'s
`the_alpha_operation_set_is_read_from_the_worker_itself`, which parses
`worker/main.py`'s literal set from source so the two sides cannot
silently disagree (a mismatch here is what caused the 2026-08-08
`OperationMismatch` incident referenced in that test).

*Read-time claim-length cap, fixed (commit 6d1c84d).* With generation,
creation, and inspection all landing, the library rebuild's
`note.project` step then refused the very first real note with
`artifact-invalid`, non-recoverable — on a retry, not a fluke.
Root-caused with a standalone script replaying `note_validator.py`'s
`project()` re-derivation against the actual published note file:
`validate_claim_rows` was rejecting a 165-character claim over its
160-character cap. That cap traces to the older LLM-extraction
contract's `MAX_STRUCTURED_CLAIM_CHARS`, enforced at write time only
for that contract — candidate-first claims are verbatim transcript
excerpts (`summarize.py`'s `validate_candidate_evidence`), never capped
at write time, and `candidate_first.py`'s fragment/anchor spans carry
no length bound either. Not a rare edge case: any note whose kept
candidates include one longer spoken sentence would write successfully
and then permanently fail projection, every time. Operator decision
(asked, since this was a real contract question, not a mechanical
bug): remove the cap entirely rather than special-case it to
`"point"`-type claims or push it upstream into candidate generation.
Removed from both `note_validator.py` and `note_projection.rs`'s
`parse_claim` — the Rust side independently re-enforced the same 160
characters and would not have followed a Python-only fix. Consequence
worth flagging: the projection frame no longer has a knowable
worst-case size, since claim length is now unbounded on both sides. A
meeting whose kept candidates run long enough could in principle
overflow `MAX_PROJECTION_FRAME_BYTES` (64KB) through ordinary claim
length rather than corruption; it fails closed as `Unavailable`, the
same fallback already documented for that case, so the failure mode is
unchanged even though it is now reachable by a different, more
ordinary path.

*Outcome.* With all five defects fixed, the packaged app ran the full
chain against a real meeting on this machine: `note.generate` (165
candidates) → `note.create` (published) → `note.inspect` (re-verified)
→ `meeting.json` committed (`lifecycle: "ready"`, `current_note` set)
→ library rebuild's `note.project` step succeeded. Confirmed three
ways: the standalone re-derivation script passing against the real
published note and transcript files under the fixed validator; the
full Rust (`cargo test --workspace`, 439 tests) and Python
(`pytest worker/tests/test_note_bridge.py`, 102 tests) suites green;
and the running app's own UI showing no `Generate note` prompt and no
refusal toast for that meeting after a clean relaunch. The operator's
own read of the generated note is the next step, and stays the
operator's alone — no note or transcript content appears in this repo
or in any tooling output from this close-out.
