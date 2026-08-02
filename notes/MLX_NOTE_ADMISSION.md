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

The research pin is `mlx-lm==0.30.4` and
`mlx-community/SmolLM2-1.7B-Instruct` at revision
`1c18454eb88e660ee6f0a201e310fa3602fad3e0`. The model source advertises
Apache-2.0; MLX-LM advertises MIT. Neither fact admits a shipped dependency:
the downloaded file inventory, tree digest, package wheel hash, transitive
licenses, signing behavior, macOS 14.4 memory use, latency, and semantic review
remain admission gates.

The revision is pinned now; the model tree digest is deliberately absent until
the exact download is inspected. `tree_sha256` covers model files only and
excludes Hugging Face's mutable local `.cache` transfer metadata. Do not
substitute a moving Hub tag.

## Run the protocol tests

```sh
python3 -m unittest discover -s notes -p 'test_mlx_note_admission.py' -v
python3 notes/mlx_note_admission.py --self-test
```

## Next measurement step — not run by this harness

The weights are not cached in this worktree. Fetch exactly this approximately
3.42 GB MLX candidate into a disposable research directory, then record its
tree digest before any run:

```sh
hf download mlx-community/SmolLM2-1.7B-Instruct --revision 1c18454eb88e660ee6f0a201e310fa3602fad3e0 --local-dir /private/tmp/lmn-mlx-note-admission-model
```

Only after the file inventory, `tree_sha256`, and license review are recorded
may a public/synthetic fixture call `local_mlx_provider`. That still does not
authorize Preview/product wiring, private recordings, or model admission.

## 2026-08-02 synthetic measurement

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
