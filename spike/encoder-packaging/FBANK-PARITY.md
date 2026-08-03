# Torch-free Fbank front end — parity measurement

Every number below was independently re-derived before commit: the full
prep → export → bench chain was re-run in a fresh work directory and
reproduced each reported value exactly, and the quoted configuration was
re-read from the pinned snapshot's `hyperparams.yaml`.

Run 2026-08-03 on the development Mac (Apple silicon, CPU), Python 3.13.14, numpy 2.4.6,
torch 2.13.0, speechbrain 1.1.0, onnxruntime 1.28.0, onnx 1.22.0. Encoder checkpoint
fingerprint `0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2`. Every input is
a deterministic synthetic clip from `fixtures.py` (seed 20260803); no private recording entered
this experiment.

## Question

`RESULTS.md` records that full-chain ONNX export fails on SpeechBrain's STFT ("STFT does not
currently support complex types"), so the shipped artifact is embedding-only and a native
deployment must carry its own feature front end. The operator's decision requires that front
end be torch-free. This measures one: does a numpy reimplementation of `compute_features`
(Fbank) plus `mean_var_norm` (InputNormalization) preserve the gate's cosine scores?

The answer here is a measurement on synthetic fixtures, not an admission. See *Gaps*.

## Configuration, as pinned

From `hyperparams.yaml` in the pinned `speechbrain/spkrec-ecapa-voxceleb` snapshot
(`~/.cache/speaker-gate/hyperparams.yaml`), the only lines that configure the front end:

```yaml
n_mels: 80

compute_features: !new:speechbrain.lobes.features.Fbank
    n_mels: !ref <n_mels>

mean_var_norm: !new:speechbrain.processing.features.InputNormalization
    norm_type: sentence
    std_norm: False
```

Everything else is a speechbrain 1.1.0 default. Rather than recall them, the values were read
off the constructed modules at runtime:

```
STFT: n_fft 400 win 400 hop 160 center True pad_mode constant normalized False onesided True
Filterbank: n_mels 80 log_mel True shape triangular f_min 0 f_max 8000 sr 16000
Filterbank: power_spectrogram 2 multiplier 10 amin 1e-10 ref 1.0 top_db 80.0 db_multiplier 0.0
Fbank: deltas False context False
Norm: type sentence std_norm False eps 1e-10
```

## Derived pipeline

Implemented in `native_fbank.py`; the docstring there maps each stage to its speechbrain
source lines.

1. **Frame.** Zero-pad the signal by `n_fft // 2 = 200` on both sides, then take 400-sample
   frames every 160 samples — `1 + (padded − 400) // 160` frames, which reduces to
   `1 + samples // 160`. A 3.0 s clip (48000 samples) gives 301 frames.
2. **Window.** Hamming, `0.54 − 0.46·cos(2πn/400)`.
3. **Spectrum.** `rfft` to 201 bins, then `re² + im²`.
4. **Mel filterbank.** 82 points linear in mel between `to_mel(0)` and `to_mel(8000)`, mapped
   back to Hz. Filter *i* is a triangle centered at `hz[i+1]` with half-width `hz[i+1] − hz[i]`
   on both sides, peak 1.0. Frequency axis `linspace(0, 8000, 201)`. Matrix-multiply the power
   spectrum by this (201, 80) matrix.
5. **Log.** `10·log10(max(x, 1e-10))`, then floor the whole utterance at
   `(max over time and mel) − 80`.
6. **Normalize.** Subtract the per-mel mean over time.

### Where SpeechBrain differs from the common conventions

Five details would each have been wrong if taken from librosa/torchaudio habit:

- **The window is periodic, not symmetric.** `torch.hamming_window(400)` divides by 400;
  `np.hamming(400)` divides by 399 and is wrong here by up to 5.5 × 10⁻³. The equivalent numpy
  expression is `np.hamming(401)[:400]` (agrees with the formula to 4.4 × 10⁻¹⁶).
- **Padding is zeros, not reflection.** `pad_mode="constant"`, where librosa defaults to
  `reflect`. This changes the first and last two frames materially.
- **`spectral_magnitude` returns the power spectrum despite its name.** Its default
  `power=1` yields `re² + im²`. The `eps` term in that function is never added here, because
  it applies only when `power < 1`.
- **The mel triangles are symmetric and unnormalized.** Filter *i* uses half-width
  `hz[i+1] − hz[i]` on *both* sides, not the standard asymmetric `hz[i] … hz[i+2]` span, and
  there is no Slaney area normalization — the analytic triangles all peak at 1.0. Sampled on
  the 40 Hz FFT grid they do not: 20 of the 80 filters have a band narrower than one bin (the
  narrowest is 22.1 Hz), so realized column maxima run from 0.19 to 0.9986 and only 4 filters
  reach 0.99. The low-frequency filters are badly undersampled by construction. A native port
  must reproduce that, not fix it — normalizing filter area or widening the low bands would
  change the distribution the encoder was trained on.
- **The dB floor is per utterance, over time and mel jointly.** `top_db` clips against the
  single maximum of the whole (frames, mels) array, not a per-frame maximum. The
  `db_multiplier` subtraction that follows the log is exactly zero here, because
  `log10(max(amin, ref_value)) = log10(1.0) = 0`.

Two smaller ones: `mean_var_norm` with `std_norm: False` collapses to plain mean subtraction
(the std branch returns ones, and the `epsilon` clamp never binds), and window/hop are derived
as `round(sample_rate / 1000 · milliseconds)`, so they are sample-rate dependent by
construction.

## Parity

`bench_fbank_parity.py`, torch-free (it asserts `"torch" not in sys.modules`), over all 12
fixture clips. Three embedding sets are compared, because a single "parity" number would hide
two different errors:

- **native** — native features → ONNX. The deployable path.
- **bridged** — torch features → ONNX. Conversion only; the existing `bench_onnx.py` arm.
- **torch** — torch features → torch `embedding_model` output, pre-embedding-norm. Reference.

| Measure | Value |
|---|---|
| Feature shape, every clip | (301, 80) float32 — identical to torch |
| Feature max abs diff | 7.19 × 10⁻⁴ dB |
| …as a fraction of the 93.5 dB feature span | 7.7 × 10⁻⁶ |
| Worst per-clip cosine, native vs torch | 1 − 3.41 × 10⁻¹² |
| Worst per-clip cosine, native vs bridged | 1 − 2.08 × 10⁻¹² |
| **Score matrix max abs Δ, native vs torch** | **9.68 × 10⁻⁷** |
| Score matrix max abs Δ, native vs bridged (front end alone) | 5.90 × 10⁻⁷ |
| Score matrix max abs Δ, bridged vs torch (conversion alone, control) | 4.24 × 10⁻⁷ |

The score-matrix figure is the deciding one: the gate thresholds a quantile over cosine
scores. **9.68 × 10⁻⁷ is about 3,100× smaller than the 0.003 margin the README already treats
as too thin to ship on.** Swapping the torch front end for this one moves the pairwise scores
by roughly what the ONNX conversion alone already moves them (5.9 × 10⁻⁷ against a 4.2 × 10⁻⁷
control) — the front end roughly doubles an already negligible perturbation rather than adding
a new error class.

Identical output across three consecutive runs; nothing here is run-to-run noise.

### Residual, and which stage owns it

There is no structural mismatch. Comparing torch and numpy stage by stage on clip 0:

| Stage | max abs diff | relative |
|---|---|---|
| Hamming window | 2.25 × 10⁻⁷ | 2.3 × 10⁻⁷ |
| Frequency axis | 0 | 0 |
| Filterbank matrix | 1.01 × 10⁻⁵ | 1.0 × 10⁻⁵ |
| Power spectrum | 3.86 × 10⁻⁴ | 1.5 × 10⁻⁷ |
| Linear fbank | 4.70 × 10⁻³ | 2.3 × 10⁻⁶ |
| Log-mel | 2.37 × 10⁻⁴ | 5.0 × 10⁻⁶ |
| After mean subtraction | 2.37 × 10⁻⁴ | 5.4 × 10⁻⁶ |

Every stage sits at or near float32 resolution. This module computes in float64 and casts to
float32 on return; SpeechBrain computes the same chain in float32
(`fwd_default_precision` on `Fbank.forward`), so the residual is torch's single-precision
rounding, not a different pipeline.

The table above is clip 0, whose worst cell is 2.37 × 10⁻⁴; the headline 7.19 × 10⁻⁴ is clip
6, so the attribution was re-checked across all 12. That worst cell (clip 6, frame 72, mel 1)
is **not** at the `top_db` floor — its log-mel value is −37.4 against a floor of −46.8 — and
within that clip the clamped cells differ by at most 4.39 × 10⁻⁵ against 7.19 × 10⁻⁴ for the
unclamped ones. The nonlinearity suppresses disagreement rather than amplifying it, because
both paths pin clamped cells to the same floor. Per-clip worst cells cluster on the narrow
low-frequency filters (10 of 12 fall at mel index ≤ 6), where few FFT bins contribute, the
linear fbank value is small, and `10·log10` amplifies relative rounding. Mean error is not
higher in that band group (7.2 × 10⁻⁶ for mel 0–19 against 8.8 × 10⁻⁶ for mel 20–79) — the
narrow filters own the extremes, not the average.

The filterbank matrix looks like the outlier at 10⁻⁵, and it has a specific cause: SpeechBrain
builds its mel grid with a float32 `linspace` and a float32 `10**x`, and the exponential
amplifies that rounding to ~10⁻³ Hz on the upper center frequencies. It is *not* the driver of
the feature residual — substituting torch's own filterbank matrix into the numpy pipeline
leaves the feature diff unchanged at 2.365 × 10⁻⁴, which attributes the residual to float32
accumulation in the STFT and the matmul instead. The float64 grid here is the more accurate of
the two.

One reporting note: the raw pointwise relative feature diff peaks at 0.28, which is an
artifact, not a finding. These features are mean-subtracted, so a cell whose reference value is
1.9 × 10⁻⁵ turns a 10⁻⁴-scale absolute difference into a large ratio. The bench prints that
reference value alongside the ratio so the number cannot be read as a 28% error. Read the
span-relative figure.

## Registered public-audio fixtures — the real-speech half

Added 2026-08-03 after the operator approved LibriSpeech as the public corpus. Twelve flac
clips, twelve distinct speakers (six recorded F, six recorded M), copied **byte-unmodified**
from LibriSpeech `dev-clean` (openslr.org/12, **CC BY 4.0**; Panayotov, Chen, Povey and
Khudanpur, "LibriSpeech: an ASR corpus based on public domain audio books", ICASSP 2015).
Provenance chain, verified in-session rather than recalled: archive
`dev-clean.tar.gz` sha256 `76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3`,
md5 `42e2234ba48799c1f50f24a7926300a1` — byte-equal to the line openslr publishes in its
`md5sum.txt`. Selection is a deterministic rule, not hand-picking, and the rule is executable:
`select_librispeech_fixtures.py` (6 lowest-ID speakers per recorded sex; per speaker the
lexicographically first clip ≥ 3.0 s). Per-file digests live in
`fixtures-librispeech/manifest.json`; `public_fixtures.py` refuses any fixture whose bytes
disagree with its registered digest before a measurement can run.

Results over the twelve real-speech clips (4.0 s to 20.2 s — 400 to 2023 frames, so
variable length is now exercised on real material with shape asserted per clip):

| Measure | Synthetic (above) | LibriSpeech |
|---|---|---|
| Feature max abs diff | 7.19 × 10⁻⁴ dB | 1.53 × 10⁻³ dB |
| …as a fraction of the feature span | 7.7 × 10⁻⁶ | 1.5 × 10⁻⁵ |
| Worst per-clip cosine, native vs torch | 1 − 3.41 × 10⁻¹² | 1 − 4.12 × 10⁻¹² |
| **Score matrix max abs Δ, native vs torch** | **9.68 × 10⁻⁷** | **7.38 × 10⁻⁷** |
| Score matrix max abs Δ, native vs bridged | 5.90 × 10⁻⁷ | 7.27 × 10⁻⁷ |
| Score matrix max abs Δ, bridged vs torch (control) | 4.24 × 10⁻⁷ | 3.74 × 10⁻⁷ |

The twelve distinct speakers give the score matrix genuine structure — cross-speaker cosines
span **−0.065 to 0.473** — so the ~7 × 10⁻⁷ delta is measured across realistic score
diversity, not a degenerate cluster. Real speech lands in the same float32-rounding class as
the synthetic clips; no new error mode appears, and the deciding score figure stays roughly
4,000× below the 0.003 margin.

## What these fixtures bound, and what they do not

The 12 synthetic clips are speech-*shaped* harmonic stacks with formant-like filtering, not
speech; the 12 LibriSpeech clips are real read speech from twelve speakers. Together they
bound **conversion and reimplementation error on real single-speaker speech**. No
operating-point, threshold, or household-separation number is re-validated here.

## Gaps

These are open, and each is a reason this measurement is not admission check 1:

- ~~No registered public-audio fixtures.~~ **Closed 2026-08-03**: the LibriSpeech half above,
  operator-approved corpus, digest-registered, deterministic selection rule.
- **No gate-classification comparison.** The check also requires comparing resulting gate
  classifications around registered margins. This measures features, embeddings, and scores —
  it stops short of classifications, because registered operating points do not exist until
  real calibration material does.
- **Padded batching is untested.** Variable length is now exercised on real speech (400 to
  2023 frames, shape asserted per clip) and was separately checked by truncation down to 25 ms
  (frame counts 301, 171, 101, 78, 51, 26, 3; residual ≤ 2.37 × 10⁻⁴). What remains untested
  is the padded-batch path: `fbank_features` takes one unpadded utterance and never exercises
  the relative-`lengths` masking in `InputNormalization`. A caller that batches utterances of
  unequal length is on untested ground.
- **The `top_db` floor is barely exercised.** It fires on 54 cells out of 288,960 across the
  12 clips (0.019%), so the one genuine nonlinearity in the chain is thinly covered. It is
  reached, so it is not dead code, but a fixture set with more dynamic range would test it
  properly.
- **Only 16 kHz.** The `round(sample_rate / 1000 · ms)` window/hop derivation is exercised at
  one sample rate.
- **numpy is not the deployment target.** This depends on `numpy.fft`. A Rust or C++ port
  would bring its own FFT and its own float32 choices, and would have to re-run this harness
  rather than inherit its numbers. In particular, a native f32 implementation would sit on the
  other side of the same precision gap measured above and needs its own measurement.
- **The `.onnx` digest still is not bound in a runtime manifest** — carried over from
  `RESULTS.md`, unchanged by this work.

## Reproduce

```sh
WORK=/tmp/fbank-work && mkdir -p $WORK
FIX=spike/encoder-packaging/fixtures-librispeech
.venv/bin/python spike/encoder-packaging/prep_features.py ~/.cache/speaker-gate $WORK $FIX
.venv/bin/python spike/encoder-packaging/export_onnx.py ~/.cache/speaker-gate $WORK/ecapa.onnx
.venv/bin/python spike/encoder-packaging/bench_fbank_parity.py $WORK/ecapa.onnx $WORK $FIX
```

The first two commands import torch; the third asserts it has not been imported. Omit the
`$FIX` argument to run the synthetic half alone. Regenerating the fixtures themselves needs
the public archive: download `dev-clean.tar.gz` and run
`select_librispeech_fixtures.py <dev-clean.tar.gz> <fixtures-dir>` — the script computes the
archive digests itself and reads every fixture byte out of that same archive, so the manifest
records only what the run derived, never a caller-asserted digest. A re-registration from the
digested archive reproduced every committed flac and per-file digest byte-identically.
