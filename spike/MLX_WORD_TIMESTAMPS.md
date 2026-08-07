# MLX word-timestamp sidecar benchmark

## Scope

This is an isolated research sidecar for the already-pinned Apple-silicon MLX
Whisper runtime. It does not alter worker defaults, product records, Preview
data, transcript schemas, evidence locators, model admission, or packaging.

The benchmark requests decoded word timestamps and compares:

- the shipped anti-poisoning baseline, `condition_on_previous_text=False`;
- a research-only continuation/seam comparator,
  `condition_on_previous_text=True`.

Recognized text is never written. Public speech fixtures must be explicitly
registered with a verified audio digest. The repository includes only a
deterministic, in-memory silence fixture.

## Historical v1 observation — not current evidence

Run date: 2026-08-02. Fixture: `synthetic-silence-v1`, 3.0 seconds at 16 kHz.
Runtime: pinned `mlx-whisper==0.4.3`, local large-v3-turbo weights digest
`951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6`.

| Invocation | Arm | Process state | First run | Repeat run | Aggregate repeatability | Result |
|---|---|---:|---:|---:|---:|---|
| A | No previous text | first model load, then warm | 3631.50 ms | 1007.26 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |
| A | Continuation comparator | warm after baseline | 1105.93 ms | 947.18 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |
| B | No previous text | first model load, then warm | 2055.91 ms | 645.91 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |
| B | Continuation comparator | warm after baseline | 681.00 ms | 657.09 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |

These numbers came from the older receipt schema. That schema did not bind the
Python executable, MLX version, model revision, or config digest. Its timing
check also failed to reject `NaN` and infinity. The table remains a historical
observation, but none of its timing rows qualifies as a current pass.

Peak resident process memory was 1,313,980,416 bytes in invocation A and
1,819,197,440 bytes in invocation B. Those are process high-water marks, not
incremental model memory. The continuation arm followed the baseline arm, so
its latency was warm-biased. Neither value supports a model-footprint or
arm-performance claim.

The historical output reported a silence hallucination. It did not evaluate
fillers, false starts, repetitions, corrections, names, numbers, negation,
long-form drops or duplication, or operator evidence-seek value. It provides no
basis for changing `condition_on_previous_text`, admitting word timing to the
product, or claiming product value.

## Evaluation rules

The runner records observations. Only a metric named in the fixture's
`coverage` list is eligible for adjudication. Expected values without matching
coverage are refused, as are unknown expected keys.

| Metric | Eligible pass condition | Synthetic silence coverage |
|---|---|---|
| Timing | Every decoded word has numeric, finite start/end values; `timed_words == words`; missing, non-finite, non-monotonic, and out-of-bounds counts are all zero | registered |
| Repeatability | At least two runs produce one content-free fingerprint | registered |
| Silence | `silence_hallucination == 0` and registered expected word count is zero | registered |
| Fillers, false starts, repetitions, corrections, names, numbers, negation | Category is registered; its exact aggregate expectation matches; every registered token digest is found | ineligible |
| Early EOT / truncation | Truncation is registered with `minimum_words`; `early_eot == 0` and `truncation == 0` | ineligible |
| Long-form seams | No pass condition exists in fixture schema v2 | mechanically unsupported |
| Latency / memory | Values are observations only; no quality threshold is registered | registered, not pass/fail |

Fixture schema v2 has no time-bound token-window contract for seam drops or
duplicates. Global token counts cannot substitute for one. Seam evaluation is
therefore ineligible, and a disposable audio-seek viewer is not justified by
this benchmark. A future research schema would need declared seam windows and a
registered public long-form fixture first.

## Run

Use the pinned runtime and its local model directory. The runner accepts only
the Python, `mlx-whisper`, MLX, model revision, config digest, and weights digest
declared by the canonical runtime pins. Model identity is derived from those
pins; there is no operator-supplied model label.

The output must be a new file outside this repository. Receipt creation uses an
exclusive create and never replaces a prior file:

```sh
PINNED_PYTHON=/path/to/pinned/python-runtime/bin/python3
PINNED_MODEL=/path/to/pinned/models/whisper-large-v3-turbo
"$PINNED_PYTHON" spike/mlx_word_timestamp_benchmark.py \
  --fixture synthetic-silence-v1 \
  --model "$PINNED_MODEL" \
  --repetitions 2 \
  --out /tmp/mlx-word-timestamp-silence.json
```

Use repeatable `--protected-root /absolute/path` arguments when Preview,
product, or private roots exist outside this repository. Those roots are then
refused for both fixtures and receipts. An unrelated Git checkout is not
rejected merely because it contains `.git`; public license, provenance, and
audio digest remain the fixture authority.

The next valid measurement needs a distributable public long-form fixture whose
reference metadata covers fillers, false starts, repetitions, corrections,
names, numbers, and negation. Add only verified digests and content-free
expectations to an external fixture manifest. Long-form seam evaluation remains
unsupported in schema v2. Do not add speech or transcript text to this
repository.

Run each arm in a separate process for comparable first-load and warmed timing:

```sh
"$PINNED_PYTHON" spike/mlx_word_timestamp_benchmark.py \
  --fixture public-longform-v1 --fixture-root /path/to/public-fixtures \
  --model "$PINNED_MODEL" --arm baseline_no_previous_text \
  --out /tmp/mlx-baseline.json
"$PINNED_PYTHON" spike/mlx_word_timestamp_benchmark.py \
  --fixture public-longform-v1 --fixture-root /path/to/public-fixtures \
  --model "$PINNED_MODEL" --arm continuation_seam_comparator \
  --out /tmp/mlx-continuation.json
```
