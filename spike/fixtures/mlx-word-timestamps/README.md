# MLX word-timestamp fixtures

This directory intentionally contains no speech audio or transcript text.

`synthetic-silence-v1` is generated in memory by the benchmark and can exercise
the installed MLX runtime without network access or meeting data. It tests no
speech, silence hallucinations, timing shape, latency, memory, and repeatability.

To run a registered public fixture, copy this manifest and its 16 kHz mono
16-bit WAV to an external directory, replace the audio digest, and add only
content-free expectations:

- metric counts for fillers, false starts, repeated words, corrections, names,
  numbers, negation, looping, and early termination;
- SHA-256 hashes of normalized public reference tokens for seam/drop checks;
- seam timestamps and source/digest information.

The benchmark validates the audio digest, emits only aggregate counts and
digests, and never writes recognized words. Do not add private recordings,
transcript text, model output, or Preview/product data here.

The two arms compare the current `condition_on_previous_text=False` baseline to
an isolated continuation comparator. A result does not alter the shipped model,
runtime, transcription policy, transcript locator, or product schema.

For latency or peak-memory comparison, invoke each arm separately with
`--arm baseline_no_previous_text` and `--arm continuation_seam_comparator` so
each is the first model load in its process. `--arm both` is suitable only for a
quick output-quality comparison because the second arm inherits a warm process.
