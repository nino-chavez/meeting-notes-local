# Speaker-encoder packaging spike — results

Run 2026-08-03 on the development Mac (Apple silicon, CPU execution in both
arms), Python 3.13.14, torch 2.13.0, speechbrain 1.1.0, onnxruntime 1.28.0,
onnx 1.22.0. Encoder checkpoint fingerprint
`0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2` (the pinned
`speechbrain/spkrec-ecapa-voxceleb` snapshot `speaker_gate.encoder_fingerprint`
computes). Every input is a deterministic synthetic clip from `fixtures.py`
(seed 20260803); no private recording entered this experiment.

## Question

The packaged runtime records a placeholder as its encoder, which blocks both
profile admission and meeting-time gating. If the product ships voice
isolation, the encoder must be packaged. Two candidate shapes were measured:

- **Arm A — packaged PyTorch/SpeechBrain**: the implementation every number in
  `spike/RESULTS.md` was measured on.
- **Arm B — ONNX export under onnxruntime**: one realistic native-runtime
  conversion. ONNX was chosen over Core ML for the first arm because
  onnxruntime ships a small, self-contained dylib set; Core ML remains
  unmeasured.

## Measurements

| | Arm A: torch + SpeechBrain | Arm B: onnxruntime |
|---|---|---|
| Installed runtime size | 504 MB (torch 494 + speechbrain 6 + torchaudio 4) | 70 MB |
| Model artifact | 85 MB HF checkpoint | 83.4 MB `.onnx` |
| Native libraries | 8 dylibs, largest `libtorch_cpu.dylib` 326 MB | 2, largest 37 MB |
| Import + load (cold) | 0.618 s + 0.865 s = **1.48 s** | 0.038 s + 0.068 s = **0.11 s** |
| First inference | 0.047 s | 0.031 s |
| Warm inference, 3 s clip | 20.8 ms mean / 23.2 ms max (audio → embedding) | 29.5 ms mean / 31.5 ms max (features → embedding only) |
| Peak RSS (process) | 472 MB | 251 MB |

Process RSS baseline (venv python + numpy alone): 26 MB. Both arms' RSS
include the 12-clip fixture set; Arm B's also includes the features array.

The size rows compare runtime libraries alone. The complete speaker stack —
runtime plus the model artifact both arms must carry — is 504 + 85 = **589 MB**
for Arm A and 70 + 83.4 = **153 MB** for Arm B, about **3.8× smaller** overall.
The ~7× figure in the Reading below is the runtime-only ratio.

## Parity

Measured at the exact boundary the ONNX artifact reproduces
(`embedding_model` output), on identical inputs:

- **Per-clip cosine between arms: ≥ 0.99999988** (worst of 12).
- **Pairwise cosine-score matrix, max |Δ| between arms: 5.4 × 10⁻⁷.** The
  gate's threshold is a quantile over cosine scores, so score stability is
  the number that decides whether a conversion preserves gate behavior. A
  score perturbation of 5 × 10⁻⁷ is four orders of magnitude below the
  0.003 margin the README already treats as too thin to ship on.
- The embedding-space normalizer `encode_batch` applies after this boundary
  changed direction by < 1.2 × 10⁻⁷ cosine on these fixtures (it is close to
  a no-op here, but it is part of the chain and a native deployment must
  apply it).

## What the export could not do

Full-chain (audio → embedding) export **failed**: the torchscript ONNX
exporter rejects SpeechBrain's STFT with "STFT does not currently support
complex types". The shipped artifact is **embedding-only**: it takes 80-dim
Fbank features, so a native deployment must carry its own feature front end
(STFT + mel filterbank + per-utterance mean-var norm). In this spike that
front end ran in torch; its output shape is (frames, 80) at 10 ms hop. This
is ordinary DSP with no learned weights, but it is a second parity surface
that would need its own registered equivalence check against the SpeechBrain
implementation before any product claim.

## Boundaries on these claims

- Synthetic fixtures bound **conversion error**, not speech behavior. The
  clips are speech-shaped harmonic stacks, not speech; no operating-point or
  household-separation number from `spike/RESULTS.md` is re-validated here.
  Given score parity at 10⁻⁷, re-measuring those on real material under ONNX
  is expected to reproduce, but that is an expectation, not a result.
- Latency is CPU execution on the development Mac in both arms, and the two
  rows measure unequal work: Arm A's number includes the Fbank front end,
  Arm B's starts from precomputed features — so on CPU, 29.5 ms is a *lower*
  bound on Arm B's true per-clip cost, which must add its native feature
  stage. Separately, no Core ML / ANE execution provider was tried.
- **Signing and notarization consequences are analyzed, not exercised.** Arm
  B adds 2 Mach-Os totalling ~67 MB; Arm A adds 8 totalling ~360 MB plus
  Python-level packages. Whether either triggers an executable-memory
  entitlement under the hardened runtime can only be settled by the
  release-lane control that caught llvmlite — the empty-entitlement import
  test against the signed bundle. Nothing here claims that test's outcome.
- The `.onnx` artifact derives deterministically from the pinned checkpoint
  bytes, but a product runtime identity contract must bind the `.onnx`
  digest itself in the manifest; the checkpoint fingerprint alone does not
  identify the converted artifact.

## Reading

If voice isolation ships, the measured evidence favors the ONNX shape:
~7× smaller runtime, ~13× faster cold load, no torch in the signed bundle,
and conversion error four orders of magnitude below the thinnest margin in
the project. Its cost is real but bounded: a native Fbank front end with its
own equivalence check, and an execution-provider decision. Packaged PyTorch
remains the fallback that requires no new parity work. Neither this spike nor
any test in it admits an encoder into the product runtime; that admission,
and whether voice isolation stays in the beta envelope at all, are operator
decisions.

## Decision (2026-08-03)

The operator reviewed this record and selected **ONNX Runtime CPU execution as
the preferred beta candidate**, keeping voice isolation in the first beta.
Terms of the decision:

- The converted ECAPA model is pinned by its own `.onnx` digest in the runtime
  manifest; the checkpoint fingerprint alone does not identify it.
- The feature front end is torch-free, built on already-packaged numerical
  dependencies where practical.
- PyTorch/SpeechBrain is retained only as the reference implementation and
  packaging fallback, not a shipping path.
- No Core ML or ANE work until CPU ONNX fails latency/memory admission or a
  later optimization is separately justified. Voice scoring is post-meeting,
  so CPU headroom over the missing Fbank stage is real.

**Preferred is not admitted.** Two checks stand between them, both mandatory:

1. **Fbank parity.** Identical deterministic and registered public-audio
   fixtures through SpeechBrain and the torch-free front end, comparing
   feature shapes, feature values, final embeddings, pairwise cosine scores,
   and resulting gate classifications around registered margins. The
   score/classification comparison decides, not raw feature equality.
   *Status: the deterministic half is measured — `FBANK-PARITY.md` records a
   numpy front end (`native_fbank.py`) whose score-matrix delta against the
   torch reference is 9.68 × 10⁻⁷ on the seeded fixtures, with a
   conversion-only control at 4.24 × 10⁻⁷. Registered public-audio fixtures
   and the gate-classification comparison remain open, so the check is not
   passed.*
2. **Release-lane packaging.** The actual signed app built with ONNX Runtime
   and the model must prove: every Mach-O signed, the bundle passes its closed
   verifier, hardened-runtime launch without unnecessary entitlements,
   Gatekeeper acceptance of the transferred build, offline cold load,
   runtime/model digests matching the manifest, and peak memory acceptable
   beside MLX transcription.

Until both pass, every product surface says **preferred ONNX candidate**,
never admitted encoder.

## Reproduce

```sh
.venv/bin/python spike/encoder-packaging/bench_torch.py \
  ~/.cache/speaker-gate /tmp/spike-work/torch_embeddings.npy
.venv/bin/python spike/encoder-packaging/export_onnx.py \
  ~/.cache/speaker-gate /tmp/spike-work/ecapa.onnx
.venv/bin/python spike/encoder-packaging/prep_features.py \
  ~/.cache/speaker-gate /tmp/spike-work
.venv/bin/python spike/encoder-packaging/bench_onnx.py \
  /tmp/spike-work/ecapa.onnx /tmp/spike-work
```

Requires the research venv plus `onnxruntime` and `onnx` (installed for this
spike; not added to `spike/requirements.txt`, which remains the capture
path's cost ledger).
