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

Every failure produces `transcript-only` and no note object: malformed output,
unknown candidate/source IDs, citation mismatch, timeout, package mismatch, and
model-digest mismatch are explicitly covered.

## Candidate pin

The first `SmolLM2-1.7B-Instruct` experiment remains rejected: it returned
malformed non-JSON on every repeat. That is a result about that exact pin and
prompt, not a claim about MLX, PyTorch, or other models. Do not retry it as the
next candidate.

### Preregistration comparison — 2026-08-02

| Candidate | License / official source | MLX artifact and immutable revision | Context / template evidence | Download artifact | Decision |
| --- | --- | --- | --- | --- | --- |
| **Qwen2.5-1.5B-Instruct 4-bit** | Apache-2.0 on the [official Qwen card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | `mlx-community/Qwen2.5-1.5B-Instruct-4bit@8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | Official card: 32,768 tokens and `apply_chat_template`; it reports improved structured outputs, especially JSON. The MLX conversion documents `apply_chat_template`. | 880,172,064 bytes total metadata inventory; `model.safetensors` 868,628,559 bytes (about 869 MB decimal) | **Selected for measurement only.** Smallest candidate with an Apache pin, documented MLX conversion, 4,096-token registered request budget below native context, and model-card JSON relevance. |
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
remote code, and no schema-constraining decoder. The parser is the enforcement
boundary; this measures whether the model follows the prompt unaided.

Run the deterministic control first, then 12 synthetic/public transcript
fixtures: four ordinary supported claims; two locator-order cases; two
name/number preservation cases; two explicit negation cases; and two
abstention/no-supported-candidate cases. Each is run three times from a fresh
process for cold timing and twice more in the same loaded process for warm
timing. Never use meeting recordings, Preview data, or product records.

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

### 2026-08-02 Qwen synthetic-only measurement — rejected

This measurement used only the 12 registered synthetic fixtures in
`synthetic_measurement_fixtures()` and the private, disposable MLX process. It
did not open Preview, product records, meeting transcripts, or audio. Its
receipt code emits fixture IDs, hashes, outcomes, timings, and boolean checks;
it does not retain fixture text or model replies.

| Pre-run check | Observed value | Gate |
| --- | --- | --- |
| Source revision | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | Exact registered revision |
| Non-cache inventory | 11 files; 880,172,064 bytes | Exact registered byte budget |
| `model.safetensors` SHA-256 | `0979f33d1bc58afcf696d13f57977644e7b11a6f0eec3e631d8e9463d18c0717` | Exact registered file digest |
| Full non-cache tree SHA-256 | `3aaeeac4e5bffd4308187dac1b34d5145bc697f589255ff57d04cc53381ddb95` | Recorded before and after all runs |
| Disposable runtime | Python 3.14; `mlx-lm==0.30.4`; `mlx==0.32.0`; `transformers==5.0.0rc1` | MLX/MLX-LM only in the experiment; no PyTorch import or shipped-path change |
| Host | arm64, macOS 26.5.2 | One machine, not a general hardware claim |

One initial execution was deliberately discarded: its receipt was accidentally
opened inside the model tree, so the harness returned `model-digest-mismatch`
for every fixture. The receipt was moved outside the tree; the exact pre-run
tree digest and byte budget were then re-established before the valid runs
below. That is a harness recovery, not model evidence.

The valid protocol was three fresh-process cold suites and two suites in one
loaded warm process, with the registered system/user chat-template messages,
temperature `0.0`, seed `0`, 512 output tokens, 4,096 KV tokens, no retry, no
remote code, and no constrained decoder. It made 60 total fixture calls.

| Gate | Observed result | Verdict |
| --- | --- | --- |
| Strict JSON / response schema | All 60 calls were `malformed-response`: 0/50 supported-fixture calls reached `note/2`; 0/10 abstention calls produced valid empty `items`. | **Fail** |
| Exact citation / locator replay | Unmeasured: no response crossed strict JSON validation. | Not reached |
| Names, numbers, negation | Unmeasured: no response crossed strict JSON validation. | Not reached |
| Repeatability | For each of the 12 fixture IDs, all five raw response SHA-256 values and all outcome codes matched. The repeatable result was malformed output, not a repeatable valid note. | Syntax gate still fails |
| Cold latency | 20.33 s, 19.25 s, 18.98 s whole-suite wall time; median 19.25 s (30 s ceiling). | Pass on this machine |
| Warm latency | 23.931 s and 23.353 s per suite in one loaded process (15 s ceiling). | **Fail** |
| Peak memory | Largest `time -l` peak footprint: 2,024,900,336 bytes; largest maximum resident set: 1,176,272,896 bytes (4,282,063,304-byte ceiling). | Pass on this machine |
| Human semantic/usefulness review | No candidate output passed the mechanical boundary. | Not reached; required for any future admission |

`mlx-community/Qwen2.5-1.5B-Instruct-4bit` is therefore **rejected for this
automatic-note admission protocol**. It is not admitted, no product runtime
or schema has changed, and the selected model's advertised JSON capability did
not survive this exact constrained extraction test. This finding applies only
to the pinned model, registered prompt/template/decoding settings, and
synthetic fixture suite; it is not a claim about MLX, PyTorch, Qwen generally,
or automatic-note product readiness.

## 2026-08-02 rejected SmolLM2 measurement

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
limit (2,541 tokens). The harness now limits this first experiment to one
canonical anchor per candidate and one source reference per output, then reran
the same fixture. That reduces context and is not a semantic-quality result.

This candidate is **not admitted**. It failed the structured-output syntax gate
on every measured run, so exact locator, semantic usefulness, and human-review
gates were not reached. The disposable dependency set also differs from the
shipped MLX runtime; no runtime replacement is justified by this result.
