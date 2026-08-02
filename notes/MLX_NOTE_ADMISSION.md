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
the exact download is inspected. Do not substitute a moving Hub tag.

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
