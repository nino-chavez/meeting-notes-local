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

## First measured run

Run date: 2026-08-02. Fixture: `synthetic-silence-v1`, 3.0 seconds at 16 kHz.
Runtime: pinned `mlx-whisper==0.4.3`, local large-v3-turbo weights digest
`951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6`.

| Invocation | Arm | Process state | First run | Repeat run | Aggregate repeatability | Result |
|---|---|---:|---:|---:|---:|---|
| A | No previous text | first model load, then warm | 3631.50 ms | 1007.26 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |
| A | Continuation comparator | warm after baseline | 1105.93 ms | 947.18 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |
| B | No previous text | first model load, then warm | 2055.91 ms | 645.91 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |
| B | Continuation comparator | warm after baseline | 681.00 ms | 657.09 ms | 1 distinct fingerprint | 2 timed words; silence hallucination |

Both arms produced the same aggregate outcome in all eight decodes. The two word
times were finite, monotonic, and inside the fixture duration. Peak resident
process memory was 1,313,980,416 bytes in invocation A and 1,819,197,440 bytes
in invocation B. Those are process high-water marks, not incremental model
memory; the variance is another reason not to treat either number as a model
footprint measurement. The weights digest was read before transcription and OS
file-cache state was uncontrolled, so "first model load" is not a cold-disk
claim. The continuation arm followed the baseline arm in these invocations, so
its latency is warm-biased and is not a fair performance comparison.

This run fails the silence-hallucination expectation. It establishes that the
sidecar executes the pinned runtime and captures decoded timing, cold/warm
latency, memory, and content-free repeatability. It does not evaluate fillers,
false starts, repetitions, corrections, names, numbers, negation fidelity,
long-form drops/duplication, or operator evidence-seek value because silence has
none of those cases and no seams. It provides no basis for changing
`condition_on_previous_text`, admitting word timing to the product, or claiming
product value.

## Run

Use the pinned runtime and local model directory. Keep output outside the
repository:

```sh
PINNED_PYTHON=/path/to/pinned/python-runtime/bin/python3
PINNED_MODEL=/path/to/pinned/models/whisper-large-v3-turbo
"$PINNED_PYTHON" spike/mlx_word_timestamp_benchmark.py \
  --fixture synthetic-silence-v1 \
  --model "$PINNED_MODEL" \
  --model-id mlx-community/whisper-large-v3-turbo \
  --repetitions 2 \
  --out /tmp/mlx-word-timestamp-silence.json
```

The next valid measurement needs a distributable public long-form fixture whose
reference metadata covers fillers, false starts, repetitions, corrections,
names, numbers, negation, and known seams. Add only verified digests and
content-free expectations to an external fixture manifest. Do not add speech or
transcript text to this repository.

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
