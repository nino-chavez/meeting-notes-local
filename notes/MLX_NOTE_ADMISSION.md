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
