# Proposal — wire the speaker gate into transcription

**Status: proposal. Nothing here is built.** Two questions in it are the
operator's to answer, and the second one the code has already answered.

Written 2026-08-05, against the tree at commit `9f0246e`.

---

## The recommendation, first

Build the gate, but only on the encoder-carrying lane, and make a profile that
cannot be applied **refuse the transcript** rather than quietly produce an
ungated one. That is one new filter in an existing seam plus one refusal path.
Everything else in this document is why.

---

## What is actually true today

The app promises operator voice isolation. It does not perform any.

`worker/transcription.py` builds a transcript by running two filters over each
leg — `drop_unvoiced` for voicing, `drop_bled` for bleed — and then merging the
surviving segments. **No profile is loaded and no gate is applied.** The merge
reads `segment.get("gated")`, `segment.get("gate_score")` and
`segment.get("gate_reason")` off every segment, and nothing anywhere sets them,
so those three reads are vestigial: they carry a contract nobody fulfils.

So the state of feature 2 is not "enrollment done, adoption pending." It is
**enrollment done, isolation absent.** An operator can record sittings, review
measured operating points, and build and publish a real voice profile, and every
transcript afterwards will contain exactly the same words it would have
contained with no profile at all.

That matters beyond feature 2. `transcript.restore` — the whole of J4, and a
registered command since 0.2.2 — exists to overrule a gate decision on a
withheld turn. Nothing withholds turns, so restoration is currently a correct
implementation of an operation that can never have an input.

---

## The two forks

### Fork 1 — a profile is installed and the runtime cannot apply it. What then?

This is the operator's decision and it is the reason this document exists.

The default build's runtime manifest records a **placeholder** encoder; only the
`build-alpha-encoder` lane packages the admitted ONNX encoder and onnxruntime.
Gating needs embeddings, so on a placeholder runtime the gate cannot run. The
adapter helper `_onnx_sitting_embedder` already refuses on exactly that lane,
with the comment that nothing there admits an encoder.

**Option A — refuse the transcript.** If a profile is installed and the encoder
is a placeholder, `transcript.create` fails closed. The operator gets an honest
error instead of an artifact whose isolation silently did not happen.
*Cost:* on a placeholder build, installing a profile disables transcription
entirely. *Requires:* no schema change.

**Option B — produce an explicitly ungated transcript carrying a health signal.**
The transcript is written, and something in it records that a profile was
installed and not applied.
*Cost:* **it does not fit the existing plumbing.** `_transcript_health` builds
its dict through `spike/capture_health.build`, whose signature is keyword-only
and closed — `mic_samples`, `system_samples`, `capture_elapsed_samples`,
`dropouts`, `tap_errors`, `transcription_requested`, `transcript_written` — with
no field for gate application. Its own docstring says these are "integrity
floors, not product-quality thresholds," and whether a gate ran is not a
capture-integrity fact, so widening that function fights its stated purpose.
Option B therefore needs a **new transcript-level field**, which is a storage
contract change, which is a human gate in `vertical-slice.md`.

**Recommended: A.** It is the smaller change, it fails closed, and it matches
the product's own non-negotiable — a surface must never imply an isolation that
did not happen. Option B is defensible only if the answer to "should a
placeholder build be able to transcribe at all while a profile exists" is yes,
and that is a product call, not an implementation detail.

### Fork 2 — withheld from the transcript, or marked in place?

**The code already answers this: marked in place.** Not a preference.

`_base_gated_turn_indices` walks `document["turns"]` **by list index**, requires
`turn["gated"]` to be a boolean when present, and collects the indices where it
is `True`. `transcript.restore` then refuses any source turn index that is not
in that set. So a withheld turn must remain a turn in the base document at a
stable index, carrying `gated: true` — removing it would destroy both the index
restore addresses and the record that anything was withheld at all.

This is also the honest shape. `journeys.md` J1 beat 4 says "not captured" and
"never said" must never look identical; a turn deleted from the transcript is
indistinguishable from a turn that never existed.

---

## What the slice would be, if approved

One filter, in the seam the module already has.

`create_transcript_revision` takes `voicing_filter` and `bleed_filter` as
injectable callables precisely so filters can be tested without audio. A
`gate_filter` joins them on the **mic leg only** — the operator's leg is the one
a voiceprint can speak to; the system leg is by definition not the operator.
Unlike the other two, it **marks rather than drops**: it sets `gated`,
`gate_score` and `gate_reason` on non-matching segments and returns every
segment it was given.

The math stays where it already lives. `spike/speaker_gate.py` is the canonical
implementation and `adapters.py` already imports `load_profile` from it; the new
code maps segments to its inputs and must not restate a threshold or a scoring
rule.

`transcript_create` loads the installed profile, and:

- no profile installed → no gate filter, unchanged behaviour, which is honest
  because the operator has not asked for isolation;
- profile installed and encoder admitted → gate runs;
- profile installed and encoder is a placeholder → refuse (Fork 1, option A).

---

## What would change this

- **If a placeholder build must keep transcribing with a profile present**,
  Fork 1 flips to B and the slice grows a storage-contract change and a human
  gate with it.
- **If gating should apply to the system leg too** — for instance to mark a
  second person on the operator's own microphone — the "mic leg only" rule is
  wrong and the design needs a second look. Nothing in the current inventory
  asks for that.
- **If the measured operating points turn out not to transfer** from
  leave-one-sitting-out evidence to live meeting audio, the threshold that
  enrollment produced is not the threshold that should gate a meeting, and the
  slice needs a calibration step before it is worth building.

---

## Provenance

Checked in the tree for this document, 2026-08-05: `worker/transcription.py`
`create_transcript_revision` (no gate; the three vestigial `segment.get` reads),
`worker/adapters.py` `transcript_create`, `_base_gated_turn_indices`,
`transcript_restore`, `_onnx_sitting_embedder` and `profile_adopt`,
`spike/capture_health.py` `build`, and `worker/main.py` `ALPHA_OPERATIONS`.
No claim here rests on another document's summary. The 30.7%-recall and
market-gap findings referenced by the honesty argument live in `journeys.md` and
`teardown.md` with their own dated provenance and were not re-derived here.
