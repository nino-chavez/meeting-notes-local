# MLX local-note admission harness

This is an isolated research harness. It takes only synthetic/public transcript
objects in memory. It does not write product records, use Preview data, add an
app command, or change the installed runtime.

The harness compares two arms:

- `control`: deterministic candidate-first cue extraction. It is a repeatable
  locator/recovery baseline, not an automatic-note product proposal.
- `mlx`: a caller-supplied, private MLX-LM process. Its response is untrusted.
  Local code validates candidate IDs, source-fragment IDs, exact citations,
  response shape, local model-tree digest, and then replays the existing
  `note/2` evidence validation in memory.

Every failure produces `transcript-only` and no note object. Content-free
receipts distinguish JSON syntax, root/schema/field-order/type,
citation/source/locator, and length/truncation failures, plus timeout and
runtime/model-identity refusal.

## Candidate pin

The first `SmolLM2-1.7B-Instruct` experiment remains **unadmitted**. Its
historical output was checked against a prompt contract that did not advertise
the parser's exact root/item shape, so it is an inconclusive protocol
measurement—not evidence that the model produced non-JSON. Do not use it to
generalize about MLX, PyTorch, or other models.

### Preregistration comparison — 2026-08-02

| Candidate | License / official source | MLX artifact and immutable revision | Context / template evidence | Download artifact | Decision |
| --- | --- | --- | --- | --- | --- |
| **Qwen2.5-1.5B-Instruct 4-bit** | Apache-2.0 on the [official Qwen card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | `mlx-community/Qwen2.5-1.5B-Instruct-4bit@8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | Official card: 32,768 tokens and `apply_chat_template`; it reports improved structured outputs, especially JSON. The MLX conversion documents `apply_chat_template`. | 880,172,064 bytes total metadata inventory; `model.safetensors` 868,628,559 bytes (about 869 MB decimal) | **Selected for the two-fixture corrective probe only.** The prior 12-fixture result is inconclusive because its advertised output contract was incomplete. |
| Phi-3.5-mini-instruct 4-bit | MIT on the [official Microsoft card](https://huggingface.co/microsoft/Phi-3.5-mini-instruct) | `mlx-community/Phi-3.5-mini-instruct-4bit@7b2052fd882fe017300d4d42a4eb06a27b816af4` | Official card: 128K context, chat format, and a claim of instruction adherence. | `model.safetensors` 2,149,696,133 bytes | Plausible fallback, but larger and its conversion inventory carries custom Python source; no remote code is permitted in this experiment. Evaluate only after a separate local MLX-only compatibility inspection. |
| Llama-3.2-3B-Instruct 4-bit | [Llama 3.2 Community License](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) permits commercial use subject to its attribution, distribution, acceptable-use, and scale terms. | `mlx-community/Llama-3.2-3B-Instruct-4bit@7f0dc925e0d0afb0322d96f9255cfddf2ba5636e` | Official card: instruction-tuned models for retrieval/summarization and 128K native context; conversion has an MLX chat template. | `model.safetensors` 1,807,496,278 bytes | Plausible but not selected: materially larger, source access is gated, and its custom license adds release obligations that Apache avoids. |

The conversion pins and byte counts above came from the Hugging Face model
metadata endpoints on 2026-08-02; no model data was downloaded. MLX-LM's
[official README](https://github.com/ml-explore/mlx-lm) documents Apple-silicon
generation, Hugging Face/MLX artifacts, `load`, `generate`, and
`apply_chat_template`. Its [long-prompt guidance](https://github.com/ml-explore/mlx-lm#long-prompts-and-generations)
documents the rotating `max_kv_size` trade-off. The selected conversion's
[model card](https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit)
documents its MLX conversion, MLX-LM loading, chat template, and 869 MB listed
artifact size. These are compatibility and author claims, not evidence of
schema adherence or note usefulness.

Exact research sources consulted:

- Qwen source card and license: <https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct>
- Selected conversion at the registered revision: <https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/tree/8b403126fc14f14cfc99bb4cfa72ecbc129ea677>
- Selected conversion metadata and LFS size/hash: <https://huggingface.co/api/models/mlx-community/Qwen2.5-1.5B-Instruct-4bit?blobs=true>
- MLX-LM official compatibility/API documentation: <https://github.com/ml-explore/mlx-lm>
- Phi source card and license: <https://huggingface.co/microsoft/Phi-3.5-mini-instruct>
- Phi MLX conversion at the compared revision: <https://huggingface.co/mlx-community/Phi-3.5-mini-instruct-4bit/tree/7b2052fd882fe017300d4d42a4eb06a27b816af4>
- Llama source card and commercial license: <https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct>
- Llama MLX conversion at the compared revision: <https://huggingface.co/mlx-community/Llama-3.2-3B-Instruct-4bit/tree/7f0dc925e0d0afb0322d96f9255cfddf2ba5636e>

The registered research pin is `mlx-lm==0.30.4` (MIT) and
`mlx-community/Qwen2.5-1.5B-Instruct-4bit` at immutable revision
`8b403126fc14f14cfc99bb4cfa72ecbc129ea677`. The selected base model is
Apache-2.0. The private experimental provider imports MLX/MLX-LM only; it
does not import PyTorch, use a server, or ship in the product path. Neither
license nor a preregistered pin admits a dependency: downloaded inventory,
tree digest, package wheel hash, transitive licenses, signing behavior, macOS
14.4 memory, latency, and semantic review remain admission gates.

The revision and its measured model tree digest are pinned now.
`tree_sha256` covers model files only and excludes Hugging Face's mutable local
`.cache` transfer metadata. Do not substitute a moving Hub tag.

## Run the protocol tests

```sh
python3 -m unittest discover -s notes -p 'test_mlx_note_admission.py' -v
python3 notes/mlx_note_admission.py --self-test
```

### Measurement protocol and pass gates

Fetch only the selected immutable revision into a disposable research
directory. Its expected full inventory is 880,172,064 bytes; the expected
`model.safetensors` SHA-256 is
`0979f33d1bc58afcf696d13f57977644e7b11a6f0eec3e631d8e9463d18c0717`.
Record the full non-cache `tree_sha256`, the package/wheel identity, and the
local macOS version before an inference call. A mismatch is transcript-only.

```sh
hf download mlx-community/Qwen2.5-1.5B-Instruct-4bit \
  --revision 8b403126fc14f14cfc99bb4cfa72ecbc129ea677 \
  --local-dir /private/tmp/lmn-mlx-note-admission-model
```

The request stays at the existing 4,096-token rotating KV budget and 512-token
output cap: native Qwen context (32,768) is larger than the registered prompt
budget. Use the model's documented chat template with exactly two messages:
the current `SYSTEM_PROMPT` as `system`, and canonical request JSON as `user`.
Use temperature `0.0`, seed `0`, one non-streaming completion, no retries, no
remote code, and no schema-constraining decoder. The response contract now
explicitly requires one root field, `items`, whose value is an array of objects
with exactly this order: `candidate_id`, `source_fragment_ids`, `citation`,
`label`, `claim`; an abstention is exactly `{"items":[]}`. The parser remains
the enforcement boundary; it does not unwrap fences or prose.

The first corrective run is deliberately smaller: one supported fixture and
one empty-candidate fixture. It hashes the model tree before load and after the
two calls, records load time separately from each call, and retains only
response hash/byte length, exact refusal category, prompt/template hashes, and
available MLX streaming metadata. Run the full fixture suite only if both
corrective calls cross strict parsing and all mechanical gates pass.

Run the deterministic control first, then 12 synthetic/public transcript
fixtures: four ordinary supported claims; two locator-order cases; two
name/number preservation cases; two explicit negation cases; and two
abstention/no-supported-candidate cases. Each is run three times from a fresh
process for cold timing and twice more in the same loaded process for warm
timing. Never use meeting recordings, Preview data, or product records.
The current measurement runner deliberately refuses `--scope full`; a future
fresh-process orchestrator must implement this exact repeat matrix before the
full suite can run or support an admission claim.

| Gate | Pass condition | Failure |
| --- | --- | --- |
| Syntax and schema | All 12 fixtures return one strict JSON object. All 10 supported fixtures pass local response plus `note/2` validation on all three repeats; both abstention fixtures return strict empty `items` and remain transcript-only. | Any malformed JSON, duplicate key, extra/missing field, unknown ID, timeout, non-empty abstention, or validation refusal rejects the candidate. |
| Locator / names / numbers / negation | 100% exact canonical citations; 100% of fixture assertions preserve every identifier, numeral/date, and asserted negation. | One wrong locator, invented/changed name or number, or lost/reversed negation rejects the candidate. |
| Repeatability | Raw response SHA-256 and accepted note/receipt are identical across the three cold runs. | Any variation rejects the candidate; do not average it away. |
| Latency | Cold median at most 30 s; warm median at most 15 s, measured and reported separately on the same macOS 14.4+ machine. | Exceeding either threshold rejects the candidate for the supported local envelope. |
| Memory | Peak process footprint at most 4,282,063,304 bytes and no memory-pressure/termination signal. This is the prior harness's measured envelope, not a hardware guarantee. | Exceeding it rejects the candidate for that envelope. |
| Human semantic/usefulness review | A human reviews every accepted fixture output for usefulness, support, and appropriate abstention. | No admission without a recorded human decision, even if every mechanical gate passes. |

The 869 MB artifact makes this candidate plausibly smaller than the previous
3.2 GiB SmolLM2 download and plausibly within the already measured 4.28 GB
research footprint, but peak memory has not been measured. That is an
inference from artifact size, not a supported-Mac claim.

**Selection is not admission.** This plan neither changes the product runtime
nor asserts that automatic notes are useful. It remains an isolated research
exercise until every mechanical gate and the human semantic/usefulness review
are complete.

### 2026-08-02 Qwen synthetic-only measurement — inconclusive

The prior Qwen run used synthetic data only, but the advertised contract did
not state the parser's required `{"items":[...]}` root, ordered item fields, or
the empty response. Its retained hashes and timings do not prove a non-JSON
model response or a warm-latency failure, because the timed suites also mixed
tree hashing and orchestration with generation. Qwen remains unadmitted. The
corrective probe below is the only measurement eligible to decide whether to
continue to the full fixture suite.

### 2026-08-02 Qwen corrective probe — rejected

The corrected harness advertised the exact strict root and ordered item shape,
bound the registered model tree and local runtime metadata, and ran the
deterministic control before each model call. It used only one supported and
one empty-candidate synthetic fixture. Model load was measured separately;
pre/post tree hashing happened outside each call's timing. No model reply or
fixture text was retained.

| Check | Supported fixture | Empty-candidate fixture |
| --- | --- | --- |
| Control | accepted | transcript-only, `no-deterministic-candidates` |
| Strict result | `response-json-syntax` | `response-contract` (wrong root/schema/field shape) |
| Response receipt | 345 bytes; SHA-256 `e244bd14ed15d32790e93ba6a3583382249cde427c7e3599408a3cab1c7f6338` | 2 bytes; SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| MLX streaming metadata | 496 prompt tokens; 181 generated tokens; finish `stop` | 267 prompt tokens; 2 generated tokens; finish `stop` |
| Call time | 2.870 s | 0.374 s |

The exact source tree SHA-256 was
`3aaeeac4e5bffd4308187dac1b34d5145bc697f589255ff57d04cc53381ddb95`
both before and after the probe. The pinned MLX runtime loaded in 1.072 s;
peak process RSS was 1,171,488,768 bytes. Per-call request/template hashes,
runtime package metadata hashes, and harness source hash are retained in the
content-free receipt. The result failed both mechanical parsing gates, so the
full suite did not run. Locator replay, names/numbers/negation, repeatability,
and human semantic/usefulness review remain unperformed.

Qwen is **not admitted**. This corrective result is limited to this pinned
model, exact template/contract, runtime, and two synthetic fixtures; it does
not make a product-readiness claim.

### Preregistered amendment — 2026-08-05 — structure-constrained decoding

**Registered before any install, download, or inference call.** Nothing in this
section reports a result. This is the single bounded decoding repair
`docs/vertical-slice.md` wave D requires before any new model search, and it is
registered rather than run first because the measurement protocol above states
"no schema-constraining decoder" in as many words. That sentence is what is
being amended, and amending it silently would make every later number
unfalsifiable.

#### What the amendment changes, and nothing else

**Change:** the model arm gains a logits processor that masks the sampling
distribution so the emitted token sequence can only be a prefix of a
contract-shaped response. `mlx_lm.stream_generate` documents the hook —
`logits_processors: Optional[List[Callable[[mx.array, mx.array], mx.array]]]` —
and MLX-LM's own `setup.py` carries no grammar, regex, or JSON-schema decoding
dependency, so the mask is written here rather than imported. A library would
drag transitive licences and wheel hashes into a probe whose whole purpose is
to be disposable.

**Everything else stays pinned exactly as registered:** the model
`mlx-community/Qwen2.5-1.5B-Instruct-4bit` at revision
`8b403126fc14f14cfc99bb4cfa72ecbc129ea677`, `mlx-lm==0.30.4`, temperature 0.0,
seed 0, one completion, no retries, no remote code, the 4,096-token rotating KV
budget, the 512-token output cap, the unchanged `SYSTEM_PROMPT`, the unchanged
parser, and the same two corrective-probe fixtures (one supported, one
empty-candidate). The parser remains the enforcement boundary and is not
relaxed; the mask must earn its result through the same `_decode_response`.

#### Structure only — what is constrained and what is deliberately left free

Constrained: JSON syntax, the single root field `items`, the five item field
names in the registered order `candidate_id`, `source_fragment_ids`,
`citation`, `label`, `claim`, and the exact abstention `{"items":[]}`.

**Left free: every value.** The candidate ID, the source-fragment IDs, the
citation text, the label, and the claim are all sampled without constraint,
even though the offered IDs are known to the harness and the citation must
equal a specific fragment.

That restraint is the whole design, and the alternative was considered and
rejected. Masking IDs to the offered set and forcing the citation to copy
verbatim from source would make the protocol's locator gate — "one wrong
locator, invented/changed name or number, or lost/reversed negation rejects the
candidate" — structurally impossible to fail. That does not pass the gate; it
deletes it. A verbatim-copy decoder is a legitimate design and belongs in its
own registered experiment with its own gate table, not folded into this one.

#### The question this answers, stated before the answer is known

Both prior failures were shape: `response-json-syntax` on the supported fixture
(181 generated tokens, finish `stop`) and `response-contract` on the
empty-candidate fixture (2 generated tokens — an abstention of the wrong
shape). Neither says whether the model understood the transcript. Removing
shape as a confound separates two outcomes that are currently indistinguishable:

- **Schema-valid and correct** — right candidate ID, right fragment IDs, exact
  citation, right label. The small-model path is alive and the full 12-fixture
  matrix becomes worth building.
- **Schema-valid and wrong** — well-formed items citing the wrong fragments or
  inventing claims. That is the finding that justifies closing the small-model
  path, and nothing measured so far can distinguish it from a JSON bug.

Either result is worth having. A third outcome — the mask itself is wrong —
is guarded against below.

#### Gates, and which one this change makes non-discriminating

| Gate | Status under this amendment |
| --- | --- |
| Syntax and schema | **No longer discriminating for the model.** The mask withholds every token that would leave the contract, so this gate now measures the mask, not the candidate, and must not be reported as a model result. Stated as written on 2026-08-05 — "unreachable by construction" — this was an overclaim: the mask as first committed also completed strings `json.loads` rejects. See the correction below. |
| Locator / names / numbers / negation | **Fully discriminating and now reachable for the first time.** Values are unconstrained. |
| Repeatability | Unchanged. Temperature 0.0 and seed 0; response SHA-256 must be identical across repeats. |
| Latency | Reported, and expected to worsen: the mask runs in Python on every step. A latency failure here is not a candidate rejection under this amendment. |
| Memory | Unchanged threshold, 4,282,063,304 bytes. |
| Human semantic/usefulness review | Unchanged and still required for any admission. |

#### The mask is tested before the model is downloaded

A masker that is subtly wrong produces a confident, meaningless run. So the
finite-state mask is exercised against a synthetic vocabulary first — asserting
which continuations survive at each position, and that both a populated
response and the exact abstention are reachable. Only then is the pinned
revision fetched, and its
`model.safetensors` SHA-256 must equal
`0979f33d1bc58afcf696d13f57977644e7b11a6f0eec3e631d8e9463d18c0717` against a
full inventory of 880,172,064 bytes. A mismatch is transcript-only and the run
stops.

#### Scope

Synthetic fixtures only. No meeting recording, Preview data, or product record.
A disposable environment under `/private/tmp`, as the SmolLM2 measurement used.
This changes no product runtime, adds no command, and admits nothing. Selection
is not admission, and a decoding repair is not a usefulness claim.

#### Protocol correction found while reproducing the pin — 2026-08-05

Rebuilding the registered runtime to run this amendment surfaced a defect in the
pin itself, and it is recorded here because it changes what earlier receipts
prove.

`runtime_identity` hashed each distribution's `RECORD` file whole. `RECORD`
lists the installed package files with their hashes **and** the generated
console scripts under `../../../bin/`, which embed the environment's absolute
interpreter path in their shebang. The digest therefore depends on the directory
the disposable environment happens to occupy — and no receipt records the
directory the 2026-08-02 probe used.

Measured: three environments built from identical wheels
(`mlx-lm==0.30.4`, `mlx==0.32.0`, `transformers==5.0.0rc1`, CPython 3.14.6) at
three paths produced three different `RECORD` digests, none equal to the pin,
while every `METADATA` digest matched. Diffing two console scripts shows a
one-line difference and that line is the shebang.

So the registered runtime identity was **unreproducible by anyone**, including a
later run on the same machine. A pin that cannot be re-derived does not verify a
runtime; it only records that one existed.

Corrected by excluding the `../`-relative rows before hashing. Every package
file's own hash stays covered — the integrity the pin was for — and the digest is
now identical across all three paths. The three `record` values in `MLX_RUNTIME`
are re-pinned to the path-independent digests; `METADATA` values are unchanged,
which is the evidence that the wheels themselves are the same ones.

What this does **not** invalidate: the model pins. `model.safetensors` SHA-256
`0979f33d…`, the 880,172,064-byte inventory, and `tree_sha256`
`3aaeeac4…` all reproduced exactly on a fresh download of the pinned revision,
so the corrective probe's model identity stands as recorded.

### 2026-08-05 Qwen structure-constrained probe — both fixtures passed

Run under the amendment registered above, against the same pinned model,
runtime, prompt, parser, and two synthetic fixtures. Receipt:
`notes/mlx_note_constrained_probe_receipt.json`.

| Check | Supported fixture | Empty-candidate fixture |
| --- | --- | --- |
| Control | accepted | transcript-only, `no-deterministic-candidates` |
| Strict result | **`accepted-research-candidate`** | **`transcript-only`, `no-model-candidates`** |
| Response receipt | 344 bytes; SHA-256 `8a55ccac35514dc691d1…` | 12 bytes; SHA-256 `eef46741adfc3a9f7629…` |
| MLX streaming metadata | 496 prompt tokens; 181 generated; finish `stop` | 267 prompt tokens; 6 generated; finish `stop` |
| Call time | 3.51–3.86 s | 0.40–0.46 s |

All four mechanical checks passed on both calls, including
`required_citation_terms` — the accepted item's citation resolved to the exact
canonical transcript span, and the locator gate stayed able to fail because no
value was constrained. The empty-candidate fixture returned exactly
`{"items":[]}` in six tokens. Model load 0.479–0.575 s, measured separately;
peak process RSS 1,171,210,240–1,174,487,040 bytes against the 4,282,063,304-byte
envelope; the model tree digest `3aaeeac4…` was identical before and after.

Call time is stated as the range across the three committed receipts rather than
a single figure, because it is the one number here that moves with machine load
and not with the candidate. An earlier set of three, taken while this machine was
busy, recorded 20.6–43.0 s cold for byte-identical responses — a 12× spread on
work that did not change. Under the amendment latency is reported and is not a
rejection criterion, which is what makes quoting one clean figure misleading
rather than merely imprecise.

**Repeatability held.** Three consecutive cold runs produced identical response
digests on both fixtures and identical receipts once timings are excluded. All
three are committed — `mlx_note_constrained_probe_receipt.json` and its
`_run2` / `_run3` siblings — and
`test_the_committed_constrained_receipts_evidence_the_repeatability_gate`
compares them against each other, so the gate rests on artifacts rather than on
this sentence. Four fields differ and all four are timings or process
footprint — `call_elapsed_s`, `elapsed_s`, `load.model_load_elapsed_s`, and
`peak_rss`. Everything else in the `load` block, including the tree the model
was loaded from and the runtime it was loaded into, is compared. The
receipts were regenerated after the trailing-comma correction below; the
response digests are unchanged by it, and the `decoder` digest they carry pins
the corrected mask.

#### What this answers

Both prior failures were shape. The supported fixture now generates **181
tokens** and finishes `stop` — the same token count the 2026-08-02 unconstrained
probe recorded, at 344 bytes against its 345. The model was producing
substantially this content all along, and one byte of it was invalid JSON. The
2026-08-02 rejection measured a serializer, not a reader.

So of the two outcomes registered in advance, this is the first:
**schema-valid and correct.** The small-model path is alive, and the full
12-fixture cold/warm matrix is now worth the fresh-process orchestrator it
requires.

#### What this does not answer

Nothing here is an admission, and four gates remain untouched.

- **Two fixtures is not twelve.** Names, numbers, negation, locator ordering,
  and the remaining abstention case are unmeasured. One correct citation is
  evidence that the path is worth continuing, not that it is reliable.
- **The syntax and schema gate no longer discriminates**, exactly as the
  amendment registered. It now measures the mask.
- **No human has read the output for usefulness.** That gate is unchanged and
  no mechanical result can stand in for it.
- **The mask is a research decoder, not a product one.** It scans the
  vocabulary per distinct machine state in Python. That is fine for two
  fixtures; a product path needs a compiled index, and admitting one is its own
  dependency decision.

#### Four defects found by running it

Recorded because each one had been silently true, and three of them would have
made any result meaningless:

1. **`runtime_identity` was unreproducible.** Described above — `RECORD` hashes
   embedded the environment's absolute path.
2. **`measure_mlx_note_candidate.py` had not run since 2026-08-02.** Commit
   `636d24c` inserted `fixtures_for_scope` into the middle of `fixture_receipt`,
   severing its `return`, so the runner returned `None` and crashed on every
   invocation. The receipt recorded that day was produced before that commit.
3. **The runner read `["items"]` for citation rows.**
   `structured_artifact_citations` returns `items` as a *count* and the rows as
   `cited`. That line had never executed, because no arm had ever produced an
   accepted note.
4. **The accepted path recorded no response digest.** Every refusal path spread
   the response receipt; acceptance did not. The registered repeatability gate
   is stated as "raw response SHA-256 … identical across the three cold runs",
   which an accepted run could not evidence at all.

Two mask defects were also found and fixed before the passing run, and both
would have produced a confident wrong answer rather than an error: the stop
token sat above `vocab_size` and so was never admitted, leaving a *correct*
response unable to terminate and padding whitespace to the 512-token cap; and
the decoder rendered that stop token into the text it walked, so a completed
response was rejected for leaving a contract it had just satisfied.

#### Correction — the mask admitted invalid JSON, and the guarantee was overstated

Found in review of `621e89c`, after the result above had already been reported.

`("item_end", n)` on a comma returned `("items", n)`, which accepted `]`
unconditionally, so `{"items":[{…},]}` walked to a complete response. The
fragment-ID list had the same shape, so `["f1",]` did too. Both are invalid
JSON. `_strict_json` calls `json.loads`, which rejects a trailing comma and
raises `response-json-syntax` — the exact refusal class the mask exists to
remove, and the class the 2026-08-02 probe attributed to the model.

The scale was larger than the two example strings suggest. Enumerating the whole
accepted language at a reduced ceiling (one item, two fragment IDs) gives **385
completed strings under the shipped mask, 288 of them invalid JSON.** Under the
corrected mask: 97 strings, none invalid.

**What survives.** The measured result. The response parsed, all four mechanical
checks passed, three cold runs agreed, and re-running against the corrected mask
reproduces both digests byte-for-byte — the hole was permissiveness the model
never exercised, and it could not have been, because no visited state's allowed
set changed.

**What does not.** The guarantee. The honest claim is *shape was not violated in
these runs, and after this correction cannot be* — not "unreachable by
construction", which is what was written while it was untrue.

**Why the existing tests missed it.** Every case in
`test_structured_decoding.py` passed against the broken mask. A case list tests
the strings someone thought of. Two properties are now walked instead:

- **Soundness** — enumerate every string the machine completes at a reduced
  ceiling and `json.loads` each one, asserting the root and the field order.
  This is the check that fails on the shipped mask.
- **Non-blocking** — every reachable state can still reach a complete response.
  This is *blind* to a trailing comma, because the offending state does reach
  the end; that is the bug. It catches the opposite failure, and it caught one
  introduced by the fix itself: removing `]` from `("ids", …)` stranded
  `("ids", n, MAX_FRAGMENT_IDS)`, where a model that had emitted the maximum
  number of IDs and then taken a comma could sample nothing at all. Both list
  ceilings now guard the comma.

A third defect in the same review: `_runtime_receipt` made `decoder` mandatory
and the receipt then dropped it, so no committed receipt named which sampler
produced it. For the masked arm that digest is the only pin on *which* mask ran,
and the mask has now been revised twice.

Carrying it through the accepted and refused paths still missed the one that
matters most. `MaskRefused` is raised inside the logits processor, inside
`stream_generate`, inside the provider closure — so the provider *throws* and
there is no observed dict to read an identity from. A mask refusal is by
construction the mask's failure and not the model's, which made it the one
receipt with no way to name the mask. The digest is known when the provider is
built, so it is now attached to the provider itself and survives the throw.

Two further gaps closed at the same time. `ITEM_FIELDS` and both ceilings were
declared in `structured_decoding.py` and checked against nothing; if the
contract's `ordered_fields` or its `max_items` moved, the mask would silently
block valid responses or admit ones `_decode_response` rejects, and the receipt
would still read `passed`. They are cross-pinned to `response_contract` now, the
same way `ALPHA_OPERATIONS` is pinned to `internal_alpha_operations`. And the
mask's own `MAX_ITEMS = 8` is an extra restriction the contract does not state,
so a test holds it above the most items any fixture could legitimately produce —
currently two.

### 2026-08-05 registered 12-fixture matrix — failed, and the cause is the harness

Run by `notes/orchestrate_mlx_note_matrix.py`, which implements the registered
repeat matrix the single-process runner refuses: 12 fixtures, 3 cold calls each
from a fresh process, 2 warm in the first worker's loaded process. 36 processes,
60 calls. Receipt: `notes/mlx_note_matrix_receipt.json`.

**Three fixtures of twelve pass.** Two are the corrective probe's own —
`ordinary-decision` and `abstain-chitchat`. The third, `abstain-plain`, had never
been run and passed: a previously unseen fixture generalized correctly, and it is
the only supported evidence on this path that anything generalizes at all. Every
*supported* fixture first exercised here failed.

| Gate | Result |
| --- | --- |
| Every fixture ran, tree unchanged | Pass |
| Repeatability | Pass on all 12 — response, note, and receipt digests identical across the three cold runs |
| Latency | Pass — 5.79 s cold median against a 30 s ceiling, 4.39 s warm against 15 s |
| Memory | Pass — 1,183,694,848 bytes peak against 4,282,063,304 |
| Per-fixture checks | **Fail on 9 of 10 supported fixtures** |

#### Eight of the nine failures are one mechanism, and it is not comprehension

Reported refusal classes look like three separate problems — six
`response-contract`, two `citation-locator`, one
`response-length-truncation`. Capturing the replies in-process shows the first
eight are one cause:

**The model ends every 90-character `source_fragment_id` after 67 characters.**
It emits `sf-` plus the fragment's own correct 64-hex digest and stops, dropping
the `-t000000-c000000-000040` positional tail, deterministically. A short ID is
not an offered ID, so the locator check refuses it; when the model then pads the
list to three copies of the same string, the uniqueness check refuses first and
reports `response-contract` instead. One behaviour, two refusal classes,
depending on how many IDs were emitted.

Calling this truncation, or a copy-fidelity failure, is wrong. **The model
reproduces 64 opaque hex characters perfectly** — the fragment's own digest, not
the candidate's — and stops at a length that is not arbitrary. `candidate_id`
is `cf-` plus 64 hex, exactly 67 characters, and the string the model emits is
`sf-` plus 64 hex, exactly 67 characters. It is producing a well-formed ID with
the shape of the other format the request carries. Why it does so on nine
fixtures and not the tenth is unexplained; see below.

What the same responses got right, on all ten supported fixtures:

| Field | Correct | Advertised to the model as |
| --- | --- | --- |
| `candidate_id` | 10 / 10 | an `enum` of the offered candidate IDs |
| `label` | 10 / 10 | an `enum` of the four labels |
| `source_fragment_ids` | 1 / 10 | `{"type": "array", "min_items": 1, "max_items": 3}` |

**The mechanism is not established, and the one success is why.**

`ordinary-decision` produced the full 90-character ID on all five of its calls.
`ordinary-action` shortened it on all of its. The two requests are structurally
identical: one candidate, one visible fragment, the same two identifier formats,
the same 90-character target. Three candidate explanations were checked against
that pair and all three fail on it:

| Hypothesis | Refuted by |
| --- | --- |
| **Enum absence** — the model copies exactly only what the contract enumerates | a property of the request *format*, which is identical in both |
| **Shape priming** — the model normalizes the long format to the short one also present | same: identical format, opposite outcomes |
| **Token boundary** — the 67-character point falls mid-token for some digests | measured: token-aligned for all 11 offered anchors, the success included |

The first two are refuted by argument, which is self-contained. The third is an
empirical claim and therefore has a probe and a receipt rather than a sentence:
`notes/measure_id_token_alignment.py` and
`notes/mlx_note_id_alignment_receipt.json` report every fragment ID a request
actually offers — the anchor, one per candidate, 11 across the 12 fixtures —
all 90 characters, with the 67-character point a clean token edge on every one. It was first written here from
a terminal measurement that was never landed, which is precisely the defect the
rest of this section exists to record.

So: 9 of 10 supported fixtures end the identifier at exactly the length and
shape of the other format in the request, 1 of 10 does not, and nothing measured
here distinguishes them. **We cannot account for the one success.** This section
has now asserted two different mechanisms as established and retracted both; it
is not going to assert a third.

What survives is narrower and still decisive for the next step: the field the
contract enumerates is reproduced exactly 10 times out of 10, the field it does
not is reproduced exactly 1 time out of 10, and that asymmetry is a property of
the instrument rather than a measurement of the candidate. Enumerating the
offered fragment IDs would remove the variable rather than explain it. The
falsifier to carry into any such amendment: **if the model also shortens
90-character entries that appear in an enum, enum-presence was never the
mechanism** — and on this evidence that outcome is live, not remote.

#### Correction — two of the three hypotheses were not refuted, and the variable they assumed symmetric is not

*Added 2026-08-06. Receipt: `notes/measure_request_id_exposure.py`, which reads
only the built requests — no model, no network, and no request digest changes.*

The table above refutes **enum absence** and **shape priming** with the same
sentence: the request *format* is identical in `ordinary-decision` and
`ordinary-action`, so neither can explain why one succeeds. That is true, and it
is not a refutation. Both hypotheses were offered as explanations of the
**aggregate** — why 9 of 10 shorten the identifier at all. Testing them against
the anomaly pair, which holds format constant by construction, can show a
variable does not explain the *difference* between two cases. It cannot show the
variable is not a cause of what they *share*. A constant explains no variance and
is not thereby falsified.

So the section retracted the right conclusion about the anomaly and the wrong one
about the baseline. Enum-presence has been carried since as a variable to be
removed rather than a mechanism to be tested, and that framing is what makes
"enumerate the fragment IDs" read as evasion.

**Measured, because both hypotheses rest on a symmetry nobody checked.** The two
fields are not exposed to the model on equal terms:

| | `candidate_id` | `source_fragment_ids` |
|---|---|---|
| Literal occurrences in the payload | **2** on all 10 supported fixtures | **1** |
| Characters from last occurrence to the generation point | **365**, on every fixture | 726–794 |
| The field's own schema entry, which sits nearest the generation point | `{"enum":["cf-<64 hex>"],"type":"string"}` | `{"max_items":3,"min_items":1,"type":"array"}` |
| Reproduced exactly | 10 / 10 | 1 / 10 |

`_canonical_json` sorts keys, so `candidates` precedes `response_contract` and the
ordering is fixed for every request. The consequence is structural rather than
incidental: the enumerated ID is written twice, and its second occurrence is the
**last complete identifier the model sees before it generates** — 67 characters
ending in a quote. The fragment ID is written once, roughly twice as far back, and
the schema entry the model reads immediately before generating shows *no instance
of it at all*, only a bare array type.

That is not proof of causation, and this section is not going to assert a third
mechanism. It is the removal of an assumption: the claim "the format is identical
in both" is true of the format and false of the exposure, and every argument in
the table above depends on the second reading.

**What it changes about the two interventions.** They are not interchangeable and
only one of them is a defect fix:

- **Stating the three unstated parser rules is required regardless of what it
  does to the verdict.** A candidate refused for breaking rules it was never given
  is not measured, whatever the outcome. It is also the smaller claim, and it has
  a live chance of moving the result on its own — rule 2, "each must be one of that
  candidate's offered fragments," is precisely the instruction the model is
  failing, and it has never been told it.
- **Enumerating the fragment IDs removes the transcription task.** On the measurement
  above it is also the intervention that equalizes exposure, so it is a mechanism
  test rather than an evasion — but it can no longer be read as measuring whether
  the model can copy a long identifier, because it will not have to.

**Run them separately, in that order.** Bundled, a pass is uninterpretable: the
defect fix and the exposure change would land in the same digest and neither could
be credited. The doc's existing falsifier still applies to the second and is
unchanged.

**What remains unexplained, and the cheapest thing that would explain it.** The one
success. Nothing above touches it, and the structural asymmetry is constant across
all ten, so it cannot. The measurement that would settle whether there is anything
to explain is the **logit margin at the decision point** — the token where the model
has emitted `sf-` plus 64 hex and chooses between `-` and `"`. If that margin is
near zero across all ten, there is no mechanism behind the one success, only an
unstable argmax, and the honest statement becomes *the model copies a
non-enumerated 90-character identifier unreliably*. If the margin is decisive and
inverts on the success, the trace names the cause.

That probe loads the pinned model and reads the same requests, so it changes no
digest and burns nothing. It is preregistration-free for the same reason
`measure_id_token_alignment.py` was, and it should run before either intervention
is spent.

#### Result — it ran, and there is nothing to explain about the one success

*2026-08-06. `notes/measure_id_decision_margin.py`, receipt
`notes/mlx_note_id_decision_margin_receipt.json`. Runtime identity verified equal
to `MLX_RUNTIME` on all four pinned fields — Python 3.14.6, CPython, mlx 0.32.0,
transformers 5.0.0rc1, `mlx-lm==0.30.4`. The probe wraps the harness's own
`make_contract_logits_processor`, so it observes the real decoding path. No mask
edit, no contract change, no request digest changed.*

At the step where the model has emitted `sf-` plus the fragment's 64 hex
characters, the margin between continuing the identifier and closing the string:

| fixture | margin (continue − close) | produced |
|---|---|---|
| `ordinary-decision` | **+0.1562** | **90 chars** |
| `negation-decision` | −0.3125 | 67 |
| `name-number-decision` | −0.4844 | 67 |
| `negation-proposal` | −0.6719 | 67 |
| `locator-second-turn` | −0.8750 | 67 |
| `name-number-action` | −1.0156 | 67 |
| `ordinary-action` | −1.1562 | 67 |
| `ordinary-proposal` | −1.7188 | 67 |
| `ordinary-question` | −1.7812 | 67 |
| `locator-canonical-order` | −2.4062 | 67 |

Mean −1.03, median −0.95, full range 2.56 logits. **All ten lean the same way, and
the one success is the least-negative case rather than a different one.** It clears
zero by 0.16 logits — on a 4-bit quantised 1.5 B model that is indistinguishable
from a tie.

**So the question "why does one fixture escape" was ill-posed, and this section can
stop asking it.** There is no second mechanism. There is one preference, present on
every fixture, and one fixture sits 0.16 logits on the other side of the threshold.
Nothing distinguishes `ordinary-decision` because nothing needs to.

Two consequences worth stating plainly:

1. **`ordinary-decision`'s full-length identifier is not evidence that the model can
   copy a 90-character non-enumerated ID.** It is a coin flip that landed. Any
   perturbation — a different quantisation, a one-token change upstream — is larger
   than 0.16 logits. The matrix's 1-of-10 should be read as *zero demonstrated
   capability with one near-miss*, not as one success.
2. **The bias is systematic, which is what the exposure measurement predicted.** Ten
   of ten lean toward closing at exactly the length of the enumerated format. That
   is consistent with the asymmetry recorded above and remains short of proving it
   causal — the probe measures the preference, not its origin.

**A preregisterable prediction, which is what this buys.** Both registered
interventions are now falsifiable in logits rather than in vibes. Any intervention
claiming to fix identifier transcription must move this margin, and the table says
exactly how far:

| Claim | Required average shift |
|---|---|
| Flips five of the ten | **+1.02** |
| Flips every supported fixture | **+2.41** |
| Flips the easiest one only | +0.31 |

*(Each figure is the shift that clears that fixture's own margin, read off the
table above — not a statistic. An earlier draft of this row called +1.02 "the
median"; the median is −0.95 and the +1.02 threshold belongs to
`name-number-action`, the fifth-hardest.)*

Register the predicted shift before running either intervention, then read this same
probe after. An intervention that fixes the outcome without moving the margin by at
least +1.02 changed something other than what it claimed to.

**Python was the one pin that did not match at first,** and re-running under 3.13
against 3.14.6 produced byte-identical margins. Recorded because it is a robustness
result rather than a formality: these numbers do not depend on the interpreter.

Citations, labels, and the negation cases were substantively right in the
replies inspected — `"We decided not to cancel Project Atlas."` preserved its
negation, `"Case 481"` its number.

#### The ninth failure is unrelated, and it is the model alone

`locator-second-turn` is a different event: 512 generated tokens, finish
`length`, an unterminated string, and a tail of `…123456789abcde123456789abc`
repeating to the cap. The model degenerated into a repetition loop inside a
free-text hole.

The obvious suspicion is the mask. It forbids a raw quote, backslash, or control
character inside a string value, so the only exit from a free-text hole is the
closing quote — a model that has begun repeating cannot leave the string any
other way. That reasoning is wrong, and running the same fixture through both
decoders settles it: **the unconstrained arm produces byte-identical output** —
512 tokens, 684 bytes, the same tail, also unparseable. The mask changes nothing
here. This one is the model, and it is the only failure on this path that the
harness cannot be blamed for.

Recorded because the counterfactual was drafted as fact before it was run, and
it was the opposite of true.

#### A second harness defect, independent of the above

`_decode_response` enforces three rules on `source_fragment_ids` that
`response_contract` never states:

1. the IDs must be unique,
2. each must be one of that candidate's offered fragments,
3. they must appear in canonical order.

The contract handed to the model advertises only `min_items` and `max_items`. A
candidate is being rejected for breaking rules it was never given, which is not
a measurement of the candidate. This is a defect whether or not it changes any
verdict, and it is the same shape as everything else found on this path: the
harness graded something it never asked for.

##### Correction 2026-08-06 — the count is wrong in both directions

Two of the three are stated, and four more are not. `SYSTEM_PROMPT` reads: *"Every
item must name the offered candidate_id and one to three offered source fragment
IDs in canonical order."* That is rule 2 and rule 3, in prose, in the message the
model receives. The sentence above is precisely true — `response_contract` does not
state them — and misleading as used, because "rules it was never given" is false for
two of the three. **Only uniqueness is genuinely unstated anywhere.**

Reading `_decode_response` against `SYSTEM_PROMPT` line by line also finds four
enforced rules this section never counted, none of them stated in either place:

| Rule `_decode_response` enforces | Stated in the system prompt? | Stated in the contract? |
|---|---|---|
| `source_fragment_ids` must be offered | **yes** | no |
| `source_fragment_ids` in canonical order | **yes** | no |
| `source_fragment_ids` must be unique | no | no |
| a `candidate_id` may appear in only one item | no | no |
| items must appear in increasing candidate order | no | no |
| a fragment may be the primary citation for only one item | no | no |
| `claim` may contain no control characters | no | no |

So the defect is real and larger than recorded — seven enforced rules, five of them
unstated anywhere — while the specific argument built on it is weaker than recorded.
Four of the five bite only on multi-item or multi-fragment responses, which most
fixtures cannot produce; `locator-canonical-order` is the one that can.

**This matters for the intervention, not just the bookkeeping.** The reason to expect
"state the rules" to fix the truncation was that the model had never been told to use
the offered IDs. It has been told, in prose, on every call, and it truncates anyway.
The preregistration below is written against that corrected premise.

#### What this does and does not establish

It does **not** establish that the small-model path is closed. The registered
second outcome is "schema-valid and wrong — well-formed items citing the wrong
fragments or inventing claims", and that is not what happened: the model cited
the right fragment and mis-transcribed its name.

It does **not** establish the path is good either. Ten fixtures ran once each
under a measurement now known to be unfair on its decisive field, and no human
has read any output for usefulness.

What it does establish is that the orchestrator works, that the mechanical
envelope is comfortable — latency at a sixth of its ceiling, memory at a
quarter — and that every result on all 12 fixtures is bit-for-bit repeatable
across three cold processes. The matrix is a working instrument that has now
found a defect in itself.

**No admission. No amendment made here.** Two distinct interventions are
available and they should not ride in together:

- **(a) State the three rules the parser already enforces.** Grading a candidate
  against unstated rules is invalid measurement regardless of any experiment
  budget. This is a defect fix.
- **(b) Enumerate the offered fragment IDs**, symmetric with `candidate_id`.
  This removes identifier transcription from the test entirely, which is a
  larger claim and needs its own justification — it must not arrive as a
  side effect of (a).

Either changes the request the model sees and therefore every request digest on
this path, so both are preregistration decisions and not fixes to apply quietly
mid-run. Whichever is registered carries the falsifier stated above.

## 2026-08-02 SmolLM2 measurement — inconclusive

This measurement used no meeting recording, Preview data, or product record.
It used the `synthetic_transcript()` fixture in this module and a disposable
Python 3.12 environment under `/private/tmp`.

| Item | Measured value |
| --- | --- |
| Downloaded model tree | `4cadbd458f4790d1958e4acfecccfb9d41cde8458748ab3d1fcc41092d5f621f` |
| Downloaded size | 3.2 GiB on disk; model page's advertised size is about 3.42 GB |
| `model.safetensors` | `821ae8a85a20a81957b36a03d93b1313b54e7ac6946907331442156282879499` |
| Runtime resolved in disposable environment | `mlx-lm==0.30.4`, `mlx==0.32.0`, `transformers==5.0.0rc1` |
| First cold run | 13.90 s; 2,573,516,800-byte maximum resident set; 4,282,063,304-byte peak footprint |
| Repeated run timing | cold 11.407 s; warm 9.132 s; warm 9.121 s |
| Repeated response digest | `07c0d7c13ea81d0a74fba3c9d7540404eba7786ac2a5d708e2d7e64e011d8e08` on all three runs |
| Output outcome | malformed response → transcript-only; zero claims on all runs |

The exact non-cache inventory was:

| File | SHA-256 |
| --- | --- |
| `.gitattributes` | `11ad7efa24975ee4b0c3c3a38ed18737f0658a5f75a0a96787b576a78a023361` |
| `README.md` | `903f9541fc69014bee74af0a390544a8282cef948b0b451a7d539e04a1d4ecd2` |
| `config.json` | `faafbb054b2be93596a3ea0452a5f88b8c8558447c3d158a802f79e841398a9c` |
| `merges.txt` | `0b54e8aa4e53d5383e2e4bc635a56b43f9647f7b13832d5d9ecd8f82dac4f510` |
| `model.safetensors` | `821ae8a85a20a81957b36a03d93b1313b54e7ac6946907331442156282879499` |
| `model.safetensors.index.json` | `e8ed9c7489be6ffb201325977b92561fb0379d603ced6f32308674e5a3a082d7` |
| `special_tokens_map.json` | `2b7379f3ae813529281a5c602bc5a11c1d4e0a99107aaa597fe936c1e813ca52` |
| `tokenizer.json` | `7d27c493c729a66ecefc837280b05d948b1ed50d130eebdbf911b1b36cf38ed7` |
| `tokenizer_config.json` | `a27f638bd2831f5c3dea654a75838930f2b11fbe550c4d4e1d5d7bd07157b2ee` |
| `vocab.json` | `82b84012e3add4d01d12ba14442026e49b8cbbaead1f79ecf3d919784f82dc79` |

The first prompt form exceeded the candidate tokenizer's declared 2,048-token
limit (2,541 tokens). The harness then reduced the context. Because neither
historical prompt advertised the strict parser shape, the recorded output
digest is not valid syntax-gate evidence. SmolLM2 remains **unadmitted**;
locator, semantic usefulness, human review, and fair latency classification
remain unmeasured. No runtime replacement is justified by this result.

---

## Preregistered amendment — 2026-08-06 — state every enforced rule in the contract

**Registered before the run. The prediction below is the point of the exercise; a
result recorded after the fact is not evidence about what was expected.**

### What this changes, and nothing else

`response_contract` gains a machine-readable statement of every rule
`_decode_response` enforces, so the harness stops grading behaviour it never asked
for. Seven rules, five of which appear nowhere today and two of which appear only
in `SYSTEM_PROMPT` prose — the corrected table under "A second harness defect"
is the authority on which is which.

Nothing else moves. Same pinned model and revision, same mask, same decoding
parameters, same fixtures, same gates, same `_decode_response` behaviour. This
amendment adds no rule and relaxes none; it writes down the rules already enforced.

**It does change every request digest on this path.** The committed 12-fixture
matrix receipt describes the old contract and is not comparable call-for-call after
this lands. That cost is the reason the amendment is registered rather than
attempted.

### Why this one first, and why alone

It is the smaller of the two registered interventions and the only one that is a
defect fix regardless of outcome. A candidate refused for breaking rules it was
never given is not measured, whatever the verdict — so this has to happen before
any admission decision, independently of whether it improves anything.

It runs alone because the second intervention — enumerating the offered fragment
IDs — lands in the same digest. Bundled, a pass could not be attributed.

### The prediction, stated before the answer is known

The decision-margin probe gives this a numeric form rather than a hope.
`notes/mlx_note_id_decision_margin_receipt.json` records the margin between
continuing and closing the identifier on all ten supported fixtures: mean −1.03,
range −2.41 to +0.16. A shift of **+1.02** flips five of ten; **+2.41** flips all
ten.

**Registered prediction: this amendment moves the mean margin by less than +0.50,
and flips at most two of the ten fixtures.**

The reasoning, so the prediction is falsifiable rather than hedged. The model is
already told in prose, on every call, to use "one to three *offered* source fragment
IDs in canonical order," and it truncates anyway on 9 of 10. The exposure
measurement says what actually correlates with the truncation point: the nearest
complete identifier *instance* in the context ends at 67 characters. A rule is not
an instance. Restating a rule the model already receives, in a different part of the
same message, should not move a token-level copy preference much.

**Two controls, registered with it:**

1. `candidate_id` is already reproduced 10/10. If this amendment degrades that, the
   change did something other than what it claims.
2. `abstain-chitchat` and `abstain-plain` already pass. They must still pass; an
   amendment that buys supported fixtures by breaking abstention is a regression.

### Falsifiers

- **If the mean margin moves +1.02 or more**, the prediction is wrong and the
  finding is large: where a rule is stated — prose versus machine-readable schema —
  changes token-level copying in this model. That would deserve its own follow-up
  and would change how every contract on this path is written.
- **If per-fixture outcomes improve while the margin does not move by at least
  +1.02**, the improvement came from somewhere other than the identifier decision,
  and the causal story in this section is wrong. Find it before claiming the fix.
- **If nothing changes at all**, the defect is closed and the measurement is
  unchanged, which is the expected and still-worthwhile outcome. It does not admit
  the candidate, and it makes the next intervention interpretable.

### What a pass would and would not authorize

It would authorize running the second intervention against a harness that no longer
grades unstated rules. It would **not** admit a note generator, wire anything into
Preview, or satisfy the human semantic gate in `vertical-slice.md` wave D. Those are
unchanged and unaffected by anything in this amendment.

### Result — 2026-08-06 — the defect is closed and the measurement got worse

Ran against the amended contract, same pinned runtime, same probe.

| | before | after | delta |
|---|---|---|---|
| Mean decision margin | −1.03 | **−1.79** | **−0.76** |
| Fixtures reproducing the full 90-character ID | 1 of 10 | **0 of 10** | −1 |
| `candidate_id` correct | yes | yes | unchanged |
| Abstain fixtures emit exactly `{"items":[]}` | yes | yes | unchanged |

Per fixture, every one moved the same way:

| fixture | before | after | delta |
|---|---|---|---|
| `ordinary-decision` | +0.1562 | −0.2812 | −0.44 |
| `negation-decision` | −0.3125 | −0.7656 | −0.45 |
| `name-number-decision` | −0.4844 | −1.9219 | −1.44 |
| `negation-proposal` | −0.6719 | −2.2656 | −1.59 |
| `locator-second-turn` | −0.8750 | −1.2500 | −0.38 |
| `name-number-action` | −1.0156 | −1.8281 | −0.81 |
| `ordinary-action` | −1.1562 | −1.7188 | −0.56 |
| `ordinary-proposal` | −1.7188 | −2.6250 | −0.91 |
| `ordinary-question` | −1.7812 | −2.7656 | −0.98 |
| `locator-canonical-order` | −2.4062 | −2.4844 | −0.08 |

**The registered prediction was satisfied and it was badly framed.** It said the
mean would move "less than +0.50" and at most two fixtures would flip. The mean
moved −0.76 and none flipped, so both clauses hold — but a one-sided bound is
satisfied by any harmful result, which is not a test. The prediction should have
been two-sided: a magnitude and a direction. Recorded as a defect in the
preregistration rather than as a hit, because scoring this as a successful
prediction is exactly the charitable reading this file exists to refuse.

**The substantive result is that stating the rules made the thing it was supposed
to help measurably worse**, and cost the only full-length reproduction on the path.

**The direction was predicted by the exposure model, and this is the first
manipulation on this path that behaves like a mechanism.** Writing seven rules into
the contract added roughly 400 characters between the fragment identifier and the
generation point:

| | before | after |
|---|---|---|
| `candidate_id` distance from generation | 365 | **771** |
| `source_fragment_id` distance | 726–794 | **1132–1200** |
| Request size | 981–1353 bytes | 1387–1759 |

The earlier section argued that what correlates with the truncation point is the
nearest complete identifier *instance*, not the rule. Pushing every instance ~406
characters further away moved the margin against continuation on **10 of 10**
fixtures. That is a manipulation with a predicted direction and a measured effect
matching it everywhere, which is stronger than the correlation it came from — and
still not proof, because distance and added token count moved together.

**The amendment stays.** Closing the defect is a validity requirement, not an
optimisation: a candidate refused for a rule it was never given is unmeasured
whatever the margin does. What this result changes is that the fix has a known
cost, and the cost is in the implementation rather than the idea. A compact
statement of the same seven rules, or one placed before the candidates instead of
after them, would test that directly and is the obvious follow-up.

### What this predicts for the second intervention, registered now

If instance proximity is the mechanism, enumerating the offered fragment IDs is not
a small change — it places a complete 90-character `sf-` instance inside the
contract, adjacent to the generation point, in the same position the `cf-` enum
occupies today.

**Registered prediction, two-sided this time: enumerating the fragment IDs moves the
mean margin by at least +2.41 and flips all ten fixtures.** If it moves less than
+1.02, instance proximity is not sufficient and the exposure model is wrong or
incomplete. If it flips all ten while the margin moves less than +1.02, something
other than this decision is carrying the result and it must be found before the
fix is claimed.

### Result — 2026-08-06 — intervention two: magnitude predicted correctly, count predicted wrongly

Ran against the enumerated contract, same pinned runtime, same probe. Receipt:
`notes/mlx_note_id_decision_margin_receipt_enumerated.json`.

| fixture | baseline | + rules | + enum | shift | full 90 |
|---|---|---|---|---|---|
| `ordinary-decision` | +0.16 | −0.28 | **+2.47** | +2.75 | yes |
| `ordinary-action` | −1.16 | −1.72 | **+0.92** | +2.64 | yes |
| `ordinary-proposal` | −1.72 | −2.62 | **+0.73** | +3.36 | yes |
| `ordinary-question` | −1.78 | −2.77 | −1.16 | +1.61 | no |
| `locator-canonical-order` | −2.41 | −2.48 | **+2.16** | +4.64 | yes |
| `locator-second-turn` | −0.88 | −1.25 | **+2.12** | +3.38 | yes |
| `name-number-decision` | −0.48 | −1.92 | **+0.56** | +2.48 | yes |
| `name-number-action` | −1.02 | −1.83 | −0.69 | +1.14 | no |
| `negation-decision` | −0.31 | −0.77 | **+2.72** | +3.48 | yes |
| `negation-proposal` | −0.67 | −2.27 | −0.36 | +1.91 | no |

Mean margin −1.79 → **+0.95**, a shift of **+2.74**. Full-length reproductions
**0 → 7 of 10**. Controls hold: `candidate_id` still correct, both abstain fixtures
still emit exactly `{"items":[]}`, all 12 protocol tests pass.

**Scoring the registered prediction honestly: one clause right, one wrong.**

- *"moves the mean margin by at least +2.41"* — **correct.** +2.74.
- *"flips all ten fixtures"* — **wrong.** Seven.

**The failed clause failed for a nameable reason, and it is my error rather than
the model's.** The "+2.41 flips every supported fixture" threshold was read off the
table computed against the *original* contract, whose deepest margin was −2.41.
Intervention one then moved the floor to −2.77, and I registered the second
prediction without recomputing the threshold against the state it would actually
be applied to. The three that did not flip are exactly the three whose required
shift exceeded what they got: they needed +2.77, +1.83 and +2.27 and received
+1.61, +1.14 and +1.91. Predicting from a stale table is the same defect this file
records elsewhere as quoting a status instead of re-deriving it.

**The mechanism is now supported about as well as this path can support anything.**
A manipulation that inverts instance proximity — the fragment ID goes from one
occurrence 1,132–1,200 characters away to two occurrences with the nearest at 478,
overtaking `candidate_id` at 898 — moved **all ten fixtures in the predicted
direction**, by +1.14 to +4.64. Two manipulations now, in opposite directions, both
matching prediction on every fixture: adding distance moved 10/10 negative, and
restoring proximity moved 10/10 positive. That is no longer a correlation.

**What it does not establish, and the distinction matters for admission.** Seven of
ten reproducing the identifier is not evidence the model can transcribe a
90-character string, because it no longer has to — the string is in the enum, and
the mask can copy it. What the enumeration buys is that the harness now measures
what it was built to measure. Identifier transcription was consuming the result and
hiding whatever the candidate does or does not understand about citation and
comprehension. Those gates are still unmeasured.

**The next run is the registered 12-fixture matrix**, which is what actually
produces per-fixture verdicts; the probe measures one token. Three fixtures are
expected to fail on the identifier still, and `locator-second-turn`'s repetition
loop is unrelated to any of this and expected to persist — it reproduced
byte-identically with the mask off.

### Registered 12-fixture matrix on the enumerated contract — 2026-08-06 — 8 of 12

Receipt: `notes/mlx_note_matrix_receipt_enumerated.json`. Run on the registered
runtime; the harness's own guard admitted the environment rather than my say-so.

| Gate | Before (2026-08-05) | After |
|---|---|---|
| Fixtures passing every gate | **3 of 12** | **8 of 12** |
| Cold median latency | 5.79 s | **2.50 s** (ceiling 30 s) |
| Peak RSS | 1.184 GB | 1.190 GB (ceiling 4.28 GB) |
| Tree unchanged, every fixture ran | pass | pass |
| `admits` | false | **false** |

Every remaining failure is the same code — `citation-locator` on `ordinary-action`,
`ordinary-question`, `name-number-action` and `negation-proposal`. The six refusal
classes that used to be spread across `response-contract`,
`response-length-truncation` and `citation-locator` have collapsed to one.

**`locator-second-turn` now passes, and that falsifies a claim this file made.**
It was recorded as "the ninth failure is unrelated, and it is the model alone" — a
512-token repetition loop inside a free-text hole, reproduced byte-identically with
the mask off, and therefore "the only failure on this path that the harness cannot
be blamed for." A harness change fixed it. The mask-off counterfactual was sound and
its conclusion did not follow: showing the *mask* was not responsible is not showing
the *harness* was not responsible, and enumeration — a different harness change —
removed the loop. The margin probe shows the same thing from the other side: this
fixture produced a 494-character string before and a clean 90 after.

**Three of the four remaining failures are the three fixtures whose decision margin
stayed negative**, which is the predicted result and not new information.

**The fourth is the interesting one.** `ordinary-action` reproduces the full
90-character identifier — margin +0.92, full length confirmed — and still refuses on
`citation-locator`. That is the first failure on this path that is about citation
rather than about transcribing an identifier, which is what the harness was built to
measure and what identifier truncation has been hiding since 2026-08-02. It is
unexplained and is the next thing to look at.

**This does not admit the candidate.** `admits` is false, the semantic and usefulness
gates are untouched, and no generator is wired into Preview. What changed is that
the instrument now measures what it was built for.

#### Provenance note — the registered runtime is installer-sensitive

The first matrix attempt refused all 36 workers with `runtime-package-mismatch`, on
an environment whose Python, CPython, mlx, mlx-lm and transformers versions were all
identical to the pin. The cause is `package_metadata_sha256`: an environment built
with `uv` produces different `RECORD` digests from one built with `pip`, even at
identical versions, and only the `pip`-built one satisfies the guard.

The pin's docstring records that it was already narrowed once, to stop `RECORD`
depending on the directory the environment lives in. This is the same class of
problem one level up: it now depends on the installer. Worth recording rather than
fixing here — the guard is doing its job, and a pin that is too strict fails closed.

**The margins are unaffected.** Every fixture's decision margin is byte-identical
between the `uv` and `pip` environments, so the wheel-identity difference does not
reach the computation. The numbers in the two sections above stand; they were
produced on an environment the guard would have refused, and re-running them on the
environment it admits changed nothing.

### Which `citation-locator` branch — 2026-08-06

Receipt: `notes/mlx_note_citation_branch_receipt.json`. Probe:
`notes/measure_citation_refusal_branch.py`. Registered runtime, constrained arm, the
same provider the matrix worker builds. Reproduced identically on three runs.

`_decode_response` raises `AdmissionRefused("citation-locator")` from five distinct
places and the receipt records only the string, so "every remaining failure is the
same code" above is a statement about the label that I let read as a statement about
the cause. The probe catches the refusal and walks the traceback to the raising line.
That localizes the branch without editing the harness, which matters because
`_harness_identity()` hashes the harness source and an edit would invalidate
comparison against the receipts committed at `c07e1a6`.

| Fixture | Identifier | Citation | Branch |
|---|---|---|---|
| `ordinary-action` | 90 chars, correct | **wrong** | citation is not the canonical slice |
| `ordinary-question` | **67 chars** | wrong | source id was not offered |
| `name-number-action` | **67 chars** | wrong | source id was not offered |
| `negation-proposal` | **67 chars** | correct | source id was not offered |

Two branches. Two mechanisms.

**Correction: identifier truncation did not go away, and it has never had a code of
its own.** Three of the four failures emit `sf-` followed by 64 hex and stop — 67
characters, the exact truncation point the decision-margin probe measures, on exactly
the three fixtures whose margin stayed negative (−1.16, −0.69, −0.36). The section
above attributes those three correctly and then says the refusal classes "collapsed
to one", which conflates two different things called truncation.
`response-length-truncation` means the generator hit its token ceiling;
`finish_reason` is `stop` on all ten fixtures here, so nothing hit a ceiling. A
truncated identifier fails the membership check and reports `citation-locator`, which
is what it has always done. Fewer codes is not fewer causes.

**The fourth is explained, and the explanation is a defect I introduced.**
`ordinary-action` puts the canonical text in `claim` and puts this in `citation`:

```
the exact text of the fragment named first in source_fragment_ids
```

That is `response_contract`'s own rule text, copied verbatim out of the value of the
`citation.equals` key. `git log -S` puts that string in `e773809` — intervention one,
the amendment that wrote the unstated rules down. Before it the key did not exist and
the model could not have copied it.

The model's reading is consistent, not careless. Every other value-shaped key in that
contract carries a literal it is meant to emit: `candidate_id.enum`, `label.enum`,
and since intervention two `source_fragment_ids.item.enum`. Only `citation.equals`
carries an English sentence in the position where its neighbours carry values. A
model that treats `equals` the way JSON Schema's `const` behaves produces exactly
this response.

Three of ten fixtures do it — `ordinary-action`, `ordinary-question`,
`name-number-action`. Two of those refuse on the truncated identifier first, so the
substitution never reaches their verdict. `negation-proposal` cites correctly and
fails on the identifier alone. That fixture is what keeps the two mechanisms
separable instead of confounded.

**What this costs the earlier claim.** Intervention one was recorded as closing a
documented defect and making the measurement worse, with the harm attributed to
distance — 406 added characters pushing the identifier away from the generation
point. That attribution stands; the margins moved as predicted and moved back under
the opposite manipulation. What was missed is that the same amendment introduced a
second failure in a different field, and the identifier failure then hid it. Writing
a rule down in a slot that reads like a value is not a neutral act of documentation.

### Preregistration — intervention three, 2026-08-06

Registered before the change is written and before it is run.

**Hypothesis.** The substitution is caused by the *key name*, not by the presence of
prose. `equals` asserts equality, so the value beside it reads as the thing to equal.
A key that describes rather than asserts should not attract the copy.

**The change is one variable.** Rename `citation.equals` to `citation.rule`. The
prose is unchanged, character for character. Nothing else in the contract, the
system prompt, the mask, or `_decode_response` moves. No rule is added or relaxed.

**Prediction.** The three fixtures that currently emit the rule text —
`ordinary-action`, `ordinary-question`, `name-number-action` — stop emitting it, and
none of the seven that currently cite correctly starts.

**Not predicted.** Whether `ordinary-action` then passes. It would still have to
transcribe a 40-character slice exactly, which is a separate question this
intervention does not address, and predicting a pass would let a lucky
transcription score a hit the mechanism did not earn.

**Falsifier.** If the fixtures still emit the rule text under the new key, the key
name is not doing the work — the model is copying the nearest available literal
regardless of what the key asserts — and the two remaining candidates are the ones
below, neither of which is a test.

**Two alternatives considered and deliberately not run first.** Both would make the
failure disappear without establishing what caused it.

- *Enumerate the citation*, as intervention two did for the identifier. Consistent
  with the contract's own idiom and near-certain to work. It converts transcription
  into selection, and with one candidate per fixture there is exactly one option, so
  citation would stop being measured at all.
- *Delete `citation` from the response.* `_decode_response` already computes the
  canonical value at line 342 and requires exact equality, so the field carries no
  information the harness lacks; provenance comes from `source_fragment_ids[0]`,
  which is validated separately. This is defensible as a contract correction and it
  relaxes a rule, which the amendment discipline above forbids doing silently. It
  belongs in its own registered change, after the mechanism is known.

### Result — intervention three, 2026-08-06 — the prediction holds, 9 of 12

Receipts: `notes/mlx_note_citation_branch_receipt_rule_key.json`,
`notes/mlx_note_matrix_receipt_rule_key.json`,
`notes/mlx_note_id_decision_margin_receipt_rule_key.json`. Registered runtime,
admitted by the harness's own guard. 12 protocol tests and 25 mask tests pass.

**The registered prediction was that three fixtures stop emitting the rule text and
none of the seven correct citers starts. That is what happened.**

| | `equals` | `rule` |
|---|---|---|
| Fixtures emitting the rule text as the citation | 3 of 10 | **0 of 10** |
| Fixtures citing the exact canonical slice | 7 of 10 | **10 of 10** |
| Fixtures passing every registered gate | 8 of 12 | **9 of 12** |
| `admits` | false | **false** |

Renaming one key removed the failure. The prose beside it is unchanged, character for
character, so the model was not confused by the sentence — it was reading the key.
`equals` names a relation between the slot and its value, and the model resolved that
relation the way JSON Schema's `const` does.

**The citation gate is now clean on every fixture.** That was not predicted and is the
part worth keeping. The three fixtures that still refuse cite the exact canonical text
and fail only on a 67-character identifier — `sf-` plus 64 hex, the same truncation
the decision-margin probe measures, on the same three fixtures whose margin is still
negative. One mechanism now, on three fixtures, and it is the one this file has been
measuring since 2026-08-02.

Three fixtures sharing a truncation point would be consistent with three independent
coincidences landing on the same tokenizer boundary, so the claim rests on the margin
receipt rather than on the shared length: all three refuse at the same decision step
with the same runner-up token, `-t`, at −1.11, −0.52 and −0.31. That is one decision
losing three times, not three decisions.

**Nothing else moved, which the registration required checking.** Identifier decision
margins under the renamed key differ from the enumerated run by at most 0.17 logits,
no fixture changes sign, and full-length reproduction stays at 7 of 10. Cold median
latency 2.54 s against a 30 s ceiling; peak RSS 1.190 GB against 4.28 GB.

**What this does not establish.** `ordinary-action` passing is not evidence the model
transcribes a 40-character slice reliably; it is one fixture, and the intervention was
registered as not predicting it. And nothing here touches the semantic or usefulness
gates, which remain unmeasured. `admits` is false.

**The remaining work is the one thing left.** Three fixtures truncate the identifier
at 67 characters. The two alternatives registered above — enumerating the citation,
deleting the citation field — are no longer needed for this failure and should not be
run to chase it; they addressed a mechanism that no longer fires.

#### Amendment — two things the first pass of this section did not check

**The citation count was read off the first row of each fixture, and the receipt
could not score it where it mattered.** `citation_matches` was computed by resolving
the canonical slice through the identifier the row emits, so on the three fixtures
that truncate the identifier it resolved to nothing and recorded `false` — reporting
the citation wrong on exactly the rows whose citation is right. The probe now falls
back to the candidate the row names, which keeps identifier transcription and
citation fidelity independently measurable. Regenerated receipt: 10 rows across 10
fixtures, **10 citing the exact canonical slice**, and the three that resolve via
`candidate_id` are the three that truncate. The table above is unchanged; it is now
derivable from the receipt instead of from the printed strings.

**`locator-canonical-order` is offered two candidates and returns one, and passes
every registered gate.** Nothing in `_decode_response` requires a row per candidate —
it refuses only on an empty list. So the fixture whose name says it tests canonical
ordering has never had two items to order, and the contract's `order` and
`unique_by_first_source_fragment_id` rules are not exercised anywhere in the matrix.
This predates all three interventions; the `equals`-era receipt shows the same one
row against two offered candidates. Recorded, not fixed: a completeness rule is a
rule added, which the amendment discipline says must be registered on its own rather
than folded into a change measuring something else.

## 2026-08-06 — the first look at what the model actually wrote

Every measurement above scores the shape of a response. None of them reads one. This
file has said since 2026-08-02 that no human has read any output for usefulness, and
that was partly a packaging problem: the outputs existed only as digests and booleans
inside receipts, so there was nothing to hand a reader. `notes/read_semantic_support.py`
lays each claim beside the evidence it cites. It loads no model, touches no network,
builds no request, and changes no digest — it presents results already recorded.

**This is not the semantic gate.** That adjudication is the operator's and it has not
been run. What follows is what a mechanical pass over the same rows shows, with the
evidence printed next to it so any of it can be overruled.

**One claim contradicts the evidence it correctly cites.** On `negation-proposal` the
cited slice is `I propose that we do not merge the red branch.` — exact, `citation_matches`
true — and the claim is `merge the red branch`. A reader shown that claim in a decision
log reads the opposite of what was said. This is the registered second outcome,
"schema-valid and wrong", which every prior section of this file has correctly reported
had not yet occurred. It has now.

**The gate that refused it did not refuse it for that.** `negation-proposal` is one of
the three fixtures failing on the 67-character identifier. Had the identifier been
transcribed correctly, nothing in `_decode_response` would have caught the inversion:
the parser checks the citation against the canonical slice and never checks the claim
against either. So the count of refusals on this path has been reading as a floor on
correctness, and on this row it was an accident.

**The label is type-checked and never truth-checked.** `_decode_response` validates that
`label` is one of `DECISION | ACTION | PROPOSAL | QUESTION` and stops. The harness holds
a `cue_type` for every candidate — it is carried in the candidate rows and used to build
the control arm's label — and never compares the two. They disagree on 4 of 10 rows, 2 of
those on fixtures that pass every registered gate. On `ordinary-decision` the disagreement
is not arguable: the cited evidence is `Dana decided that Battery 7 ships on Tuesday.` and
the emitted label is `ACTION`. On `ordinary-question` the cue strategy's own `PROPOSAL` for
a sentence beginning "Could" is at least as questionable as the model's `ACTION`, which is
why this is reported as disagreement and not as error.

**Recorded, not fixed — for the third time on this path.** Comparing `label` to `cue_type`
is a rule added, and the amendment discipline above requires it be registered on its own
rather than folded into a change measuring something else. The same applies to any claim
check. The standing list of unexercised rules is now three: the `order` and
`unique_by_first_source_fragment_id` rules that `locator-canonical-order` never exercises,
and the label. All three are cases of the harness holding the data and not looking at it.

**What this does and does not establish.** It does not establish that the small-model path
is closed — ten synthetic fixtures, one row each, one run. It does not establish the path
is good. It removes an assumption that has been load-bearing since the matrix first ran:
that a fixture passing every registered gate has produced a usable note. Nine fixtures
pass; two of them are abstentions and emit no row, so seven passing rows exist. Of those
seven, 2 carry a label that disagrees with the harness's own cue_type and 4 emit a claim
shorter than the evidence it cites — the second number is a pointer, not a defect, since
a shorter claim may be a fair summary and on this fixture set several are. The registered
gates rate all seven identically. `admits` is false, and the reason it is false is no
longer only mechanical.

Reproduce:

    python3 notes/read_semantic_support.py          # the reading sheet
    python3 notes/read_semantic_support.py --json   # the same rows, machine-readable

---

## 2026-08-07 — the first reading of the sheet, and what it found

`read_semantic_support.py` was written on 2026-08-06 and then stranded on an
unmerged branch until it was rescued on 2026-08-07. This is the first time
anyone has read its output. It changes what the next intervention should be.

### The finding

Fixture `negation-proposal`. The cited evidence is:

> I propose that we do **not** merge the red branch.

The model's claim is:

> merge the red branch

That is not a shortening or a paraphrase. It asserts the opposite of the
sentence it cites as its evidence, which is the precise failure this product
exists to not ship.

**No registered gate caught it.** The fixture failed, and it failed on
`citation-locator` — the 67-character identifier truncation that also fails
`ordinary-question` and `name-number-action`. All three failures across the
whole matrix carry that one code and no other. Nothing in `_decode_response`
compares a claim's polarity to its evidence's.

**So the identifier fix must not ship alone.** The next intervention registered
in this file is the fourth attempt at the identifier truncation, and
`vertical-slice.md`'s build queue lists it as buildable-now. Landing it by
itself would remove the only thing currently refusing this claim, and a
semantically inverted claim would become an accepted research candidate. The
mechanical picture would improve — 9 of 12 to 12 of 12 — while the product got
worse. That is the exact shape of a metric moving in the wrong direction for a
real reason.

### Two smaller observations from the same sheet

**The label vocabulary has collapsed to two values.** Across ten rows the model
emits only `ACTION` (6) and `DECISION` (4). It never emits `PROPOSAL`, including
on the two fixtures whose deterministic cue is `PROPOSAL`. Label-against-cue
disagreement is 4 of 10.

**Type disagreement fails nothing.** `ordinary-decision` and `ordinary-proposal`
both pass every registered gate while labelling the claim `ACTION` against a
`DECISION` and a `PROPOSAL` cue. A note whose every claim carried the wrong type
would be mechanically green.

Neither is scored here. The cue is a heuristic from the deterministic cue
strategy, not ground truth, and `read_semantic_support.py` is right to report
rather than judge it.

### Preregistration — intervention four, polarity

**Registered before implementation, and honest about what is already known.**
The effect on the ten recorded rows is *not* a prediction: those responses exist
and were read to produce this section. Exactly one row (`negation-proposal`)
drops a polarity term. What is unknown, and what this preregisters, is the
gate's behaviour on any future response.

**The rule.** A claim is refused when a term from `POLARITY_TERMS` appears in the
cited canonical slice and in no form in the claim. The list is the one already in
`read_semantic_support.py`: `not, no, never, cannot, can't, don't, doesn't,
without`. New refusal code: `claim-polarity`.

**The prediction.** On a re-run of the registered 12-fixture matrix with this
gate active and no other change:

1. `negation-proposal` carries **two** codes, `citation-locator` and
   `claim-polarity`, rather than one.
2. `negation-decision` continues to pass every gate. It is the control: its
   evidence and its claim both contain "not", so a gate that fails it is
   over-broad and must be withdrawn.
3. No other fixture changes outcome. Nine of twelve remains nine of twelve,
   because the gate refuses nothing that was passing.

**What would falsify the rule rather than the prediction.** A claim that carries
the evidence's polarity through a paraphrase containing none of the listed terms
— "we are keeping the red branch" for "do not merge" — would be refused wrongly.
The gate is a word-presence test and cannot see that. If a future fixture shows
it, the gate is too crude and the finding still stands: the harness needs *some*
polarity check, not this one.

**This changes no request.** The gate reads a response, so no request digest on
this path moves and the pinned model, prompt, and mask are untouched.

> **Wrong, corrected 2026-08-07.** The gate does read a response, but the same
> change advertises it in `response_contract` under `must_not_drop_polarity_terms`,
> and `response_contract` is a request key. The request moved. Four of twelve
> fixtures returned a different `response_sha256` on the next run, and
> `negation-proposal` — the fixture this gate was built for — now passes instead of
> carrying the predicted second code, because the model read the advertised rule.
> See "Run — 2026-08-07, fresh environment" at the end of this document.

**This admits nothing.** `admits` stays false. A gate that refuses an inverted
claim removes a false positive; it does not demonstrate comprehension, and the
human semantic and usefulness adjudication remains unrun.

Reproduce the finding:

    python3 notes/read_semantic_support.py | grep -A3 negation-proposal

### Implemented 2026-08-07 — and what is still unmeasured

The gate is in `_decode_response` raising `claim-polarity`, advertised in
`response_contract` under the claim's `must_not_drop_polarity_terms`, and
categorised as `claim-contradicts-cited-evidence`. Six unit tests cover the
inversion, the control, evidence without polarity, that the rule is advertised
as well as enforced, that the term list has exactly one owner, and the category.

`read_semantic_support.py` now imports the term list rather than keeping a second
copy, and both its docstring and its printed summary were corrected: polarity was
described there as an unscored pointer a reader may overrule, and that stopped
being true the moment it became a gate.

**The prediction is not yet tested.** Re-running the registered 12-fixture matrix
needs `mlx_lm`, which is not installed in this repository's `.venv`. Installing it
would change the environment the committed receipts were produced in, so it was
not done casually as part of this change. Until that run happens:

- The gate's *logic* is verified against the recorded rows and by unit test.
- The gate's *effect on the matrix* — prediction items 1 through 3 — is unverified.
  Nobody may report 9 of 12, 12 of 12, or any other count from this change without
  running it.

That is the honest state, and it is why `admits` stays false for a reason that has
nothing to do with this gate.

---

## 2026-08-07 — the registered runtime cannot be rebuilt, so the matrix cannot be re-run

Attempting to verify the polarity gate's prediction found a larger problem. It is
recorded here rather than in a commit message because it blocks every future
intervention on this path, not just that one.

### What happened

`MLX_RUNTIME["runtime_identity"]` pins Python 3.14.6, mlx 0.32.0, mlx-lm 0.30.4,
transformers 5.0.0rc1, and a `package_metadata_sha256` of each package's
`METADATA` and `RECORD`. `local_mlx_provider` compares the running environment
against it and raises `runtime-package-mismatch` on any difference, which is
correct and is what happened: all 36 workers exited 1 and the matrix returned
`every_fixture_ran: false`.

Three environments were built on this machine to try to satisfy it. Python
version, implementation, and all three package versions matched exactly in every
one.

| environment | `METADATA` (3 packages) | `RECORD` (3 packages) |
|---|---|---|
| uv 0.8.17 | 3 of 3 match | **0 of 3** |
| pip, byte-compiled (default) | 3 of 3 match | **1 of 3** — `mlx-lm` only |
| pip `--no-compile` | 3 of 3 match | **0 of 3** |

**Every `METADATA` digest matched in every environment — 9 of 9.** The wheels are
byte-identical and the pin's package identity is sound. **`RECORD` matched once in
nine.**

### Why `RECORD` is the wrong thing to pin

`RECORD` is written by the installer, not shipped by the wheel. It lists installed
files, and its contents vary with things that have nothing to do with package
identity:

- **The installer.** uv reproduced none of the three; pip reproduced one.
- **Byte-compilation.** `mlx`'s `RECORD` carries 31 `.pyc` rows with empty hash
  fields, generated at install time. `mlx-lm` matched *with* compilation and
  stopped matching *without* it, so the pin was captured from a byte-compiled
  install — a fact recorded nowhere.
- **Something further**, still unidentified, that leaves `mlx` and `transformers`
  differing even under pip with compilation. Not chased further, because the
  conclusion does not depend on naming it: one more unknown source of variance in
  a value that already has two is enough to stop pinning it.

### This is the second time, and the first fix was believed to be complete

`package_sha256`'s docstring records the same class of defect being found on
2026-08-05 — the digest was reproducible only inside the exact disposable
directory the 2026-08-02 probe used — and fixed by excluding `../`-relative
script rows, "verified across those same three paths". That verification varied
the path and held the installer and install method fixed, so it could not have
caught this. A check that varies one dimension does not establish independence
from the others.

### What this blocks

The 12-fixture matrix cannot be run by anyone who does not still hold the exact
environment that produced the 2026-08-06 receipts. Concretely:

- **The polarity gate's predicted effect is unverified and stays that way.** No
  count from it may be reported. That is a defect in the pin, not in the gate.
- **Intervention five and every one after it is blocked**, because each is defined
  as a matrix run.
- The committed receipts remain valid evidence of what happened on 2026-08-06.
  They are not reproducible, which is a different and weaker claim than being
  wrong.

### The direction, grounded in the measurement above

Pin the wheel, not the installation. `METADATA` matched 9 of 9 across three
installers and two install methods; `RECORD` matched 1 of 9. The artifact identity
this experiment actually needs is the wheel's own digest — the value a lockfile or
PyPI's own hash records — and `RECORD` should be dropped from
`runtime_identity` rather than repaired.

That is a change to the registered runtime contract, so it is named here and
preregistered separately, not folded into this note.

Reproduce the failure:

    python3.14 -m venv env && env/bin/pip install --pre mlx-lm==0.30.4 \
      mlx==0.32.0 transformers==5.0.0rc1
    env/bin/python notes/orchestrate_mlx_note_matrix.py --model-directory <snapshot>
    # every worker exits 1 with runtime-package-mismatch

**Correction, 2026-08-07.** The paragraph above read "the registered runtime
contract and every request digest downstream of it" until this line was written.
The second half was wrong, and it made the change look more expensive than it is.
`request_sha256` is the digest of the system prompt and the remaining request keys
only (`mlx_note_admission.py:696` and `:907`); `runtime_identity` is not an input
to it and does not appear anywhere in a request. Dropping `RECORD` therefore moves
no request digest, and the committed receipts' request and response digests stay
comparable with any future run. What moves is the receipt's `runtime_identity`
block, which is the entire point. A test now pins that separation
(`test_dropping_record_moves_no_request_digest`) so the claim cannot drift back.

### Preregistration — intervention five, wheel-shipped runtime identity

**The rule.** `runtime_identity.package_metadata_sha256` pins `METADATA` only.
`RECORD` is removed, not narrowed a third time. `METADATA` travels inside the
wheel, so every installer writes the same bytes; `RECORD` is written by the
installer at install time.

**Why removal and not a third narrowing.** Both earlier attempts narrowed it and
both were believed complete. The 2026-08-02 pin hashed `RECORD` whole and was
reproducible only inside one disposable directory. The 2026-08-05 fix excluded the
`../`-relative console-script rows and was "verified across those same three
paths" — a check that varied the directory while holding the installer and the
install method fixed, so it could not have caught either remaining cause. **A
check that varies one dimension does not establish independence from the others.**
A third narrowing would inherit that structure.

**The mechanism, confirmed independently 2026-08-07.** The 9-of-9 versus 1-of-9
table above was measured on the three pinned packages. To check the mechanism
rather than re-read the finding, two environments were built on a package the
original measurement never touched (`idna==3.10`), same interpreter, same
installer, differing only in byte-compilation:

| | `METADATA` | `RECORD` | `.pyc` rows in `RECORD` |
|---|---|---|---|
| pip, byte-compiled | `5114796720df4353` | `d4a11041e100510a` | 8 |
| pip `--no-compile` | `5114796720df4353` | `288cff77be506542` | 0 |

Same wheel, same installer, one flag. `METADATA` identical, `RECORD` not. The
divergence is entirely install-time artifacts. Reproduce it with:

    python3 -m venv a && a/bin/pip install idna==3.10
    python3 -m venv b && b/bin/pip install --no-compile idna==3.10
    # compare */lib/python*/site-packages/idna-3.10.dist-info/{METADATA,RECORD}

**The prediction.** On a re-run of the registered 12-fixture matrix in a fresh
environment with matching Python and matching package versions, and no other
change:

1. No worker exits with `runtime-package-mismatch`. That refusal is what returned
   `every_fixture_ran: false` and is the only thing this change targets.
2. The matrix runs to completion, and the intervention-four polarity prediction —
   `negation-proposal` carrying both `citation-locator` and `claim-polarity`,
   `negation-decision` still passing, nothing else moving — becomes testable for
   the first time.
3. Every fixture's `request_sha256` equals the value in the committed 2026-08-06
   receipts, because no request input changed. **If any request digest moves, this
   change did something it was not supposed to do and must be withdrawn.**

Item 3 is the falsifier that matters. Items 1 and 2 are what the change is for;
item 3 is what proves it stayed inside its own boundary.

**What would falsify the rule rather than the prediction.** A `METADATA` digest
that diverges across installers for the pinned packages — meaning wheel-shipped
metadata is not installer-independent after all — would leave nothing derivable
from an installed environment worth pinning. The pin would then have to move to
the wheel's own distribution hash from a lockfile, which is a different mechanism,
not a repair to this one. `package_sha256` keeps its `filename` parameter so that
addition does not need a signature change.

**This admits nothing.** `admits` stays false. Making an experiment re-runnable is
not evidence about the thing being experimented on.

**The committed receipts are not rewritten.** They carry the two-key
`package_metadata_sha256` shape in their `registered_runtime` block, which is the
correct record of what was registered on 2026-08-06. `test_probe_receipts_repeat`
compares those three receipts against each other rather than against the current
pin, so it is unaffected.

### Implemented 2026-08-07

`RECORD` is gone from `MLX_RUNTIME["runtime_identity"]` and from the observed
identity `local_mlx_provider` builds. `package_sha256` lost its `RECORD` row-
filtering branch, and its docstring now records why the file is not pinned at all
rather than how it was filtered.

Three tests: that only wheel-shipped files are pinned (asserted on shape, so
re-adding any installer-written file under a new key still fails), that no request
digest depends on the runtime identity, and that an environment still reporting a
`record` digest is refused as `runtime-package-mismatch`.

### Run — 2026-08-07, fresh environment

Receipt: `notes/mlx_note_matrix_receipt_wheel_pin.json`. Environment built the same
day from the corrected specification: `python3 -m venv` on 3.14.6, pip, default
byte-compilation, into a scratch directory unrelated to any prior probe. Model tree
read from the HuggingFace cache; `preflight_tree_sha256` equals the pin and equals
the 2026-08-06 receipt's. `orchestrator_sha256` unchanged.

Before the run, the fresh environment's identity was compared to the pin directly:
`METADATA` matched 3 of 3. **All three `RECORD` digests differed from the values the
old pin carried** — `db09769b…`, `691ea958…`, `7be5a01f…` against `11151543…`,
`75a95fb4…`, `2fbbba0c…`. Under the old pin this environment would have been
refused 3 of 3, which is the defect reproduced one more time on the way out.

**Prediction item 1 — passed.** `every_fixture_ran: true`. It was `false` on every
attempt since 2026-08-06, and no worker exited `runtime-package-mismatch`. **The
registered matrix is re-runnable by anyone who can build the specification.** That
was the entire point of this intervention and it is the only claim here that rests
on it.

**Prediction item 2 — the matrix ran, and intervention four's prediction was
falsified.** Ten of twelve fixtures now pass every registered gate, against nine on
2026-08-06. `ordinary-question` and `name-number-action` still fail
`checks_pass_on_every_call` with `citation-locator`, exactly as before.

`negation-proposal` was predicted to carry **two** codes, `citation-locator` and
`claim-polarity`. It carries **none** — it passes every gate. `negation-decision`,
the registered control, also passes, so the gate is not over-broad. But the gate
did not fire at all, on the one fixture built to trigger it.

**Why, and it is the same mechanism intervention three found.** The polarity rule is
not only enforced in `_decode_response`; it is *advertised* in `response_contract`
under `must_not_drop_polarity_terms`. `response_contract` is a request key. The
model reads the rule, and produced a claim that keeps the evidence's polarity and
fixed its own locator — so there was nothing left to refuse. Intervention three
recorded this once already: renaming one request key moved the citation gate from 7
of 10 to 10 of 10, and the finding was "the model had been reading the key, not the
sentence." Advertising a rule changes behaviour upstream of enforcing it. That is
now observed twice and should stop being a surprise.

**Correction — intervention four's "This changes no request" is wrong.** Its
preregistration reads: "The gate reads a response, so no request digest on this path
moves and the pinned model, prompt, and mask are untouched." The gate does read a
response. But the same change added `must_not_drop_polarity_terms` to
`response_contract`, and that is inside the request. Verified mechanically:
`'must_not_drop_polarity_terms' in json.dumps(model_request(...))` is `True`. Four
of twelve fixtures returned a different `response_sha256` from the 2026-08-06 run —
`ordinary-decision`, `locator-second-turn`, `negation-decision`,
`negation-proposal` — which is the request having moved, not non-determinism: every
fixture's `response_sha256` is a single-element list, so all three cold processes in
this run agreed byte-for-byte, and `repeatable` is true on all twelve.

**Prediction item 3 — my own falsifier was unusable as written, and that is the
finding about this preregistration.** It said: "Every fixture's `request_sha256`
equals the value in the committed 2026-08-06 receipts... If any request digest
moves, this change did something it was not supposed to do and must be withdrawn."
The matrix receipt does not record `request_sha256`. I wrote a falsifier against a
value the instrument does not capture, so it could neither fire nor clear.

The change is not withdrawn, and here is the argument rather than an assertion. What
the falsifier was *for* is the claim that `runtime_identity` is not an input to any
request. That is pinned directly by `test_dropping_record_moves_no_request_digest`,
which asserts the runtime identity and its digests appear nowhere in a built
request. The request did move between 2026-08-06 and this run — by intervention
four, merged earlier the same day, whose own preregistration wrongly said it moved
nothing. Attributing that to this change would be wrong, and attributing it to
nothing would be worse.

**The lesson generalises past both.** Two consecutive preregistrations claimed "this
changes no request" and both were wrong, in opposite ways: intervention four moved
the request while saying it did not, and this one guarded against moving the request
using a value nothing records. A preregistration that names a digest must name where
that digest is written down, or it is prose. The matrix receipt should carry
`request_sha256` per fixture; it does not, and until it does this class of claim
cannot be checked from a receipt at all.

**Latency was not a confound.** Cold median 2.53 s against a 30 s ceiling, warm
1.76 s against 15 s; the 2026-08-06 run recorded 2.53 s and 1.74 s. Load average
2.25–2.56 during, against 3.6–4.18 for the baseline.

**This admits nothing.** `admits` stays false and `per_fixture_gates` stays false.
Two fixtures still refuse on the identifier-truncation mechanism, no generator is
wired into Preview, and the human semantic and usefulness adjudication remains
unrun. Making an experiment re-runnable is not evidence about the thing being
experimented on.

### Intervention six — the receipt records what the model was asked

**Registered and run 2026-08-07.** Receipt:
`notes/mlx_note_matrix_receipt_request_digest.json`, schema `mlx-note-matrix/3`.

**The defect this closes.** Two consecutive preregistrations made claims about the
request digest that no committed receipt could settle. Intervention four said "this
changes no request" while moving it. Intervention five guarded against moving it
with a falsifier written against a value nothing recorded. Neither was checkable
from an artifact, so both were prose.

Neither existing digest can stand in, and this was measured rather than assumed:

| digest | isolates a changed request? |
|---|---|
| `response_sha256` | No. Conflates a changed request with changed model behaviour. |
| `receipt_sha256` | No. Covers `runtime_identity` too, so it moved on **all twelve** fixtures when `RECORD` left the pin — a change that provably touches no request. |

`request_sha256` was already computed per call and carried inside each call's
`identity` block. The fixture aggregation dropped it. It is now promoted the same
way the other digests are: a sorted set over the cold calls, so a request that
moved mid-run reads as a multi-element list rather than silently taking one call's
value.

**Schema bumped to `/3`.** The `/1`-to-`/2` comment in the orchestrator records that
the shape once moved under an unchanged version string and says it must not happen
twice. Four `/2` receipts are in git and remain valid as `/2`; the frozen
2026-08-05 baseline is deliberately not back-filled, because inventing a digest for
a run nobody can re-do is the exact failure this line of work exists to stop.

**The instrument-identity check moved, and the move is a strengthening.** It
previously asserted that `mlx_note_matrix_receipt.json` — the *oldest* receipt —
named the current orchestrator, and did not look at the three later receipts at
all. The property now asserted is that the current orchestrator has produced *some*
committed receipt. A historical receipt naming a superseded instrument is not a
defect; it is what makes it history. An orchestrator that has produced no committed
receipt is the defect, because then every artifact in the tree describes a program
that no longer exists. The cost is unchanged: editing the orchestrator still
requires a matrix re-run, and that ratchet fired on this very change.

**Control.** The run is byte-identical to `_wheel_pin.json` on all twelve
`response_sha256` values — same environment, same day, orchestrator changed only in
what it records. Recording a field perturbed nothing.

**First use, first finding: the matrix has twelve fixtures and eleven distinct
requests.** `abstain-chitchat` and `abstain-plain` produce the byte-identical
request `fec1e608…`. Both transcripts yield zero deterministic candidates, and only
candidates reach the model — the transcript text does not — so at the model layer
they are one experiment run twice, not two.

This is not a code defect; a no-candidate transcript *should* produce a
no-candidate request. It is a coverage fact that was invisible until the digest was
recorded, and it qualifies a claim already in the test suite:
`test_nine_supported_fixtures_failed_and_one_unseen_abstention_passed` notes that
`abstain-plain` had never been run before and passed. It passed the same request
`abstain-chitchat` passed. The empty-abstention path is therefore pinned once, not
twice, and a second *distinct* abstention fixture — one that offers candidates and
should still abstain — is the gap.

**This admits nothing.** `admits` false, `per_fixture_gates` false, ten of twelve
fixtures passing every registered gate, the same two still refusing on the
identifier-truncation mechanism.

**A known gap, named rather than fixed here.** `mlx_note_admission.py` is hashed
into every receipt's `harness` block but is not ratcheted the way the orchestrator
is. It changed on 2026-08-07 when `RECORD` left the pin, and no test failed, so
every receipt committed before that names a hash of a file that has since moved.
Same stale-evidence class, unguarded. Fixing it means deciding whether the harness
digest should ratchet at all, which is a separate decision from this one.

### 2026-08-07 — the abstention path has a coverage ceiling, and the next fixture is not buildable

The build queue said the next build was "a second, distinct abstention fixture —
one that offers candidates and should still abstain." **That is not buildable
under the registered checks, and the reason is worth more than the fixture would
have been.** Recorded here rather than quietly dropped from the queue.

**First, the earlier finding generalises.** `abstain-chitchat` and
`abstain-plain` do not share a request by coincidence. Only candidates reach the
model — the transcript text does not — so *every* zero-candidate transcript builds
the byte-identical request. Measured on four transcripts including two the matrix
has never run:

| transcript | candidates | request digest |
|---|---|---|
| "The weather was pleasant and the coffee was warm." | 0 | `b74a34c8…` |
| "The window is open." | 0 | `b74a34c8…` |
| "Nothing of consequence occurred during the interval." | 0 | `b74a34c8…` |
| "Bananas." | 0 | `b74a34c8…` |

So `strict_empty_abstention` is pinned by exactly one request and cannot be pinned
by more. A third chitchat fixture costs three worker processes and buys nothing.
This is a coverage ceiling, not a defect — a no-candidate transcript *should*
produce a no-candidate request.

**Second, the fixture that would break the ceiling is blocked by the check
structure.** `strict_empty_abstention` is only reachable when the expected outcome
is `transcript-only`, and `control_expected` additionally requires the
deterministic arm to abstain on that same fixture. The control abstains only when
there are no candidates. "Offers candidates, should still abstain" therefore fails
on the control before the model is consulted, and would measure nothing.

**Third, and this is the part worth keeping.** The obvious candidate-bearing
abstention case is a hypothetical — a sentence containing a decision cue that
states no decision. Measured:

    "If we decided to ship Tuesday, we would need Dana."
    → 1 candidate, control outcome accepted-research-candidate

The deterministic control reads a hypothetical as a decision. That is the same
class of defect as the inverted claim intervention four was built for, on the
*other* arm — and unlike the model arm, nothing gates it. Both are word-presence
failures; the polarity gate exists precisely because word-presence is not
comprehension.

### Preregistration — intervention seven, and the decision it needs

**The rule to change.** `control_expected` currently makes "deterministic accepts,
model abstains" an automatic fixture failure. That treats the deterministic arm as
ground truth.

**The decision, and it is made rather than deferred: a disagreement between the
arms should be recorded, not graded.** The experiment exists to compare the two
arms. Grading the model against the control assumes the control is right, and this
document already contains the measurement showing it is not — it accepts a
hypothetical as a decision. A model that abstains there is behaving *better* than
its reference, and a check that scores that as a failure would suppress the one
result most worth finding.

**What that implies, concretely.** A fixture gains a third expected outcome
alongside `accepted-research-candidate` and `transcript-only`: one meaning *the
arms are expected to disagree, and the receipt must say which way*. The per-call
checks gain a recorded field rather than a stricter gate. `admits` is untouched by
any of it.

**Why it is not implemented in this change.** It moves `EXPECTED_FIXTURES`, the
registered fixture set, and the per-call check shape — three registered surfaces —
and every one of them requires a matrix re-run to re-establish evidence. That is
affordable now (the run is roughly four minutes and the environment is
reproducible, which was not true yesterday), but bundling a protocol change with
the finding that motivated it would make the pass unattributable. This document
has recorded that failure once already, on the identifier bug.

**The prediction, for when it is run.** The hypothetical fixture will be *accepted*
by the model arm, not abstained on — the model has no more notion of a
counterfactual than the extractor does, and nothing in the request marks one. If it
abstains, that is the first evidence in this document of the model arm exceeding
its reference, and it should be reported as such rather than folded into a count.

**What is pinned now, without the protocol change.** Two tests:
`test_every_abstaining_transcript_produces_one_identical_request`, so a future
change that lets transcript text into the request fails loudly rather than quietly
widening what a receipt means; and
`test_the_deterministic_control_accepts_a_hypothetical_as_a_decision`, so the
control's false positive cannot disappear unnoticed and take this argument with it.

**This admits nothing** and changes no request. No matrix re-run was needed: only
the test file moved, and it is hashed into no receipt.

### Intervention seven — run 2026-08-07. The prediction held, and both arms fail the same way

Receipt: `notes/mlx_note_matrix_receipt_arms_recorded.json`, schema
`mlx-note-matrix/3`, thirteen fixtures, `every_fixture_ran: true`.

**The prediction was that the model would accept the hypothetical rather than
abstain. It accepted.**

    fixture:  hypothetical-decision
    input:    "If we decided to ship Tuesday, we would need Dana."
    control:  accepted-research-candidate
    model:    accepted-research-candidate     codes: none

**So the arms agree, and agreeing is the bad outcome here.** The fixture was built
to find a disagreement worth recording. What it found is that neither arm can see a
counterfactual. The deterministic extractor is word-presence and was already known
not to. The model, given the same sentence, produced a note the citation gate
accepted.

**The citation gate passing is the part to read carefully.**
`required_citation_terms` held: the model cited the real sentence, containing both
"Dana" and "Tuesday". This is not a citation failure and no locator gate could have
caught it. It is correct citation with wrong inference — the same shape as the
inverted claim intervention four addressed, and nothing gates this one on either
arm.

**What that means for the product, stated plainly.** A meeting in which someone
says "if we decided to ship Tuesday, we would need Dana" would currently produce a
note recording a decision to ship Tuesday, correctly cited to a sentence that
decides nothing. Evidence-linked is not the same as true, and this is the cleanest
demonstration of that gap in this document.

**Do not read the pass count as progress.** Eleven of thirteen fixtures pass every
registered gate, against ten of twelve before. **The graded count is unchanged at
ten of twelve.** The entire increase is `hypothetical-decision`, which is ungraded
on outcome by design and therefore cannot fail. A suite that accumulated ungraded
fixtures would report a rising number while measuring less;
`test_synthetic_measurement_plan_has_registered_coverage` holds the count of them
at exactly one until another is argued for.

**Nothing else moved, and this is the first time that could be checked.** No
pre-existing fixture's `request_sha256` or `response_sha256` changed. Intervention
six added that field precisely because the two preregistrations before it made
claims of this kind that no receipt could settle; one run later it settles one.

**This admits nothing.** `admits` false, `per_fixture_gates` false, the same two
fixtures still refusing on the identifier truncation.

### Preregistration — intervention eight, and an argument against the obvious version

The obvious next move is a counterfactual gate shaped like the polarity gate:
refuse a claim whose cited slice opens with "if", "were", "would", "suppose".
**Registered here as the candidate, with the reason it may be wrong.**

The polarity gate taught two things. The first is that word-presence catches the
registered fixture and generalises badly — it cannot see "we are keeping the red
branch" as an inversion of "do not merge". A conditional gate inherits exactly that
limit: "had we shipped Tuesday, Dana would have been needed" carries no listed
term, and "if" appears in plenty of real decisions ("we decided to ship if QA
signs off") where refusing would be wrong.

The second is subtler and was measured: advertising the rule in
`response_contract` changed the model's output before the gate ever ran. A
conditional rule may therefore fix this fixture by teaching the model the word
rather than the concept, and the receipt could not tell those apart.

**The prediction, so it can be wrong.** With a conditional gate advertised and
enforced, `hypothetical-decision` stops being accepted. **The falsifier that
matters is a second, unadvertised conditional fixture using none of the listed
terms** — if that one is still accepted, the gate taught a vocabulary and not a
distinction, and should be withdrawn rather than kept for the fixture it passes.
That control fixture has to be written and run in the same change, or the result
means nothing.

**Not started.** Recorded so the next session does not reach for the word list
without the control.

### Intervention eight — run and withdrawn the same day, 2026-08-07

Receipt: `notes/mlx_note_matrix_receipt_conditional_withdrawn.json`, fourteen
fixtures, `every_fixture_ran: true`. **The gate is not in the harness. This
section is why, and the receipt is the evidence.**

**The falsifier fired.**

| fixture | evidence | model |
|---|---|---|
| `hypothetical-decision` | "**If** we decided to ship Tuesday, we **would** need Dana." | refused `claim-conditional` |
| `conditional-unmarked` | "Barring Dana's return, the team could ship Tuesday." | **accepted** |

The gate caught the fixture carrying its words and missed the one that did not.
Both sentences settle nothing. The preregistration named this outcome in advance
and said what it means: the gate taught a vocabulary rather than a distinction, and
must be withdrawn rather than kept for the fixture it happens to pass. It was
withdrawn.

Keeping it would have been indefensible in a specific way. `hypothetical-decision`
is registered, so a gate tuned to it is tuned to the test. The falsifier existed to
make that visible, shipped in the same change for exactly that reason, and it
worked.

**The cost was not zero, which is the more important half.** Two fixtures that had
been clean started failing:

| fixture | before | with the gate |
|---|---|---|
| `ordinary-proposal` | clean | `citation-locator` |
| `negation-proposal` | clean | `citation-locator` |

Graded fixtures passing every gate went from ten of twelve to **eight of twelve**.
Neither regression is about conditionals. Neither fixture contains one.

**Why an unrelated fixture regressed, and this generalises past this
intervention.** Advertising the rule put `must_not_drop_conditional_terms` into
`response_contract`, and `response_contract` is part of the request. **All thirteen
pre-existing fixtures' `request_sha256` values moved.** Every fixture on this path
therefore asked the model a different question than it had before, and four
responses changed — two of them for the worse.

**There is no such thing as a targeted contract change on this path.** A gain on
one fixture and a regression on two arrive as one indivisible edit. That is now
measured rather than suspected, and it is the third recorded instance of
advertising a rule moving behaviour upstream of enforcing it — the first two were
gains (intervention three's key rename, intervention four's polarity rule), and
this is the first showing the mechanism can cost more elsewhere than it buys.

**None of this was attributable before intervention six.** `request_sha256` was
added two changes ago because two preregistrations in a row made request claims no
receipt could settle. Without it, this would have read as "the gate works and two
fixtures got flaky."

**What is kept.** Both fixtures, both ungraded. What they record now is that
nothing gates a conditional on either arm: the deterministic extractor cannot see
one, and neither can the model. That is a worse state to be in than having a gate,
and a more honest one to publish.

**What is pinned.** `test_the_conditional_gate_was_withdrawn_and_nothing_replaced_it`
asserts the withdrawal by behaviour — no `CONDITIONAL_TERMS` attribute, no
`dropped_conditional_terms`, `claim-conditional` falling through to
`other-refusal`, the contract not advertising the rule, and the polarity rule still
advertised. Deliberately not a source grep: this document and the fixture comments
still discuss the withdrawn gate on purpose, and a text check would force deleting
the record to keep the suite green.

**This admits nothing**, and it removes nothing that was admitted.

### What the next attempt has to beat

Do not reach for a longer word list. The failure was not that the list was too
short; `conditional-unmarked` was built to be outside any list, and a longer list
just moves where the falsifier has to stand.

Two directions remain, and both are more expensive than a word list, which is why
the word list was tried first and is recorded here as spent rather than promising:

1. **Ask the model to classify rather than to comply.** A separate call whose only
   job is "is this fragment settled or contingent", scored against fixtures, with
   the note generation downstream of the answer. Costs a second call per candidate
   and needs its own admission.
2. **Accept that this class is not gateable here and surface it.** The product
   already has a vocabulary for a claim it cannot stand behind. A note that marks
   contingent items as contingent, rather than refusing them, may be the honest
   shape — and it is a product decision, not a harness one.

Either way the falsifier discipline holds: any candidate ships with an
unadvertised control fixture in the same change, or its pass means nothing.

### The withdrawal is verified, not asserted

Receipt: `notes/mlx_note_matrix_receipt_no_conditional_gate.json`, the fourteen-fixture
matrix re-run with the gate removed.

**Every pre-existing fixture returned to its exact pre-intervention values: 13 of 13
`request_sha256` restored, and 13 of 13 `response_sha256` restored.** Graded fixtures
passing every gate is back to ten of twelve, and the two regressions — `ordinary-proposal`
and `negation-proposal` — are gone. The only fixtures still refusing are the two that
were refusing before intervention eight, on the identifier truncation.

Both conditional fixtures are accepted again, which is the true state and the reason
the withdrawal is worth publishing rather than quietly reverting:

    hypothetical-decision   with gate: refused claim-conditional   now: accepted
    conditional-unmarked    with gate: accepted                    now: accepted

**Why this check is worth a four-minute run.** A revert that leaves a stray field in
the contract would still pass every unit test, still look clean in a diff review, and
would silently mean every future receipt on this path is incomparable with every
receipt before it. Byte-identical restoration is the only evidence that distinguishes
"the code was removed" from "the experiment was undone". This document has already
recorded two cases of a claim that could not be checked from an artifact; this is the
first time a revert could be.

It is also the strongest available confirmation of the finding above. The gate's cost
was not a coincidence of a noisy run: removing it removed exactly the two regressions
and nothing else, in the same environment, byte for byte.
