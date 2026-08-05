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
| Syntax and schema | **No longer discriminating for the model.** The mask makes malformed JSON and wrong field order unreachable by construction. It now measures the mask, not the candidate, and must not be reported as a model result. |
| Locator / names / numbers / negation | **Fully discriminating and now reachable for the first time.** Values are unconstrained. |
| Repeatability | Unchanged. Temperature 0.0 and seed 0; response SHA-256 must be identical across repeats. |
| Latency | Reported, and expected to worsen: the mask runs in Python on every step. A latency failure here is not a candidate rejection under this amendment. |
| Memory | Unchanged threshold, 4,282,063,304 bytes. |
| Human semantic/usefulness review | Unchanged and still required for any admission. |

#### The mask is tested before the model is downloaded

A masker that is subtly wrong produces a confident, meaningless run. So the
finite-state mask is exercised against a synthetic vocabulary first — asserting
which continuations survive at each position, that the only reachable strings
are contract-shaped, and that both a populated response and the exact
abstention are reachable. Only then is the pinned revision fetched, and its
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
