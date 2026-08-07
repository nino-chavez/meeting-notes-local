# MLX word-timestamp fixtures

This directory intentionally contains no speech audio or transcript text.

`synthetic-silence-v1` is generated in memory by the benchmark and can exercise
the installed MLX runtime without network access or meeting data. It tests no
speech, silence hallucinations, timing shape, latency, memory, and repeatability.

To run a registered public fixture, place its manifest and 16 kHz mono 16-bit
WAV outside this repository. Register the fixture's license, stable provenance
reference, audio digest, and exact metric coverage.

Fixture schema v2 accepts these coverage names:

- `silence`, `timing`, `repeatability`, `latency`, `memory`
- `fillers`, `false_starts`, `repeated_words`, `corrections`
- `names`, `numbers`, `negation`, `looping`, `truncation`

Coverage is not decorative. A fidelity category requires its exact aggregate
count and registered token digests. `names` requires token digests. `silence`
requires an expected word count of zero. `truncation` requires
`minimum_words`. Unknown expectations and expectations without matching
coverage are refused.

A minimal public silence fixture has this shape:

```json
{
  "schema": "mlx-word-timestamp-fixture/2",
  "fixtures": [{
    "id": "public-silence-v1",
    "source": "public",
    "license": "CC0-1.0",
    "source_ref": "https://publisher.example/stable-source",
    "audio": "public-silence-v1.wav",
    "audio_sha256": "<sha256>",
    "expect_speech": false,
    "coverage": ["silence", "timing"],
    "expected": {"metric_counts": {"words": 0}}
  }]
}
```

Transcript text does not belong in the manifest. Fidelity references use
SHA-256 hashes of normalized public reference tokens under
`expected.token_hash_counts`.

The benchmark validates the audio digest, emits only aggregate counts and
digests, and never writes recognized words. Do not add private recordings,
transcript text, model output, or Preview/product data here.

Fixtures and receipts are refused inside this repository. Pass each additional
known Preview, product, or private root with `--protected-root`. Other Git
checkouts are allowed; the registered public source, license, provenance, and
audio digest decide whether a fixture is eligible.

Receipts are created exclusively with owner-only permissions. An existing file
is never overwritten.

Schema v2 cannot evaluate long-form seams. It has no declared time/token-window
contract, so global token counts cannot prove a seam did not drop or duplicate
speech. Seam fields are refused and seam results remain ineligible.

The two arms compare the current `condition_on_previous_text=False` baseline to
an isolated continuation comparator. A result does not alter the shipped model,
runtime, transcription policy, transcript locator, or product schema.

For latency or peak-memory comparison, invoke each arm separately with
`--arm baseline_no_previous_text` and `--arm continuation_seam_comparator` so
each is the first model load in its process. `--arm both` is suitable only for a
quick output-quality comparison because the second arm inherits a warm process.
