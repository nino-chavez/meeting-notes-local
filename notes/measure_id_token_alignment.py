#!/usr/bin/env python3
"""Does the 67-character boundary fall on a token edge? Per fixture.

`MLX_NOTE_ADMISSION.md` refutes three explanations for why nine of ten supported
fixtures end `source_fragment_ids` after 67 characters and one does not. Two are
refuted by argument — they are properties of the request format, and the format
is identical across a success and a failure. The third is empirical: if 67
characters fell mid-token for some digests and on a clean edge for others, that
would explain the split.

That claim was written into the file from a measurement taken in a terminal and
never landed, which is the same defect the surrounding section exists to record.
This is the probe. Its output belongs beside the claim.

Content-free: identifiers, lengths, token counts, and booleans. No transcript
text and no model reply — this loads the tokenizer only, never the weights.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from candidate_first import STRATEGY_CUE
from mlx_note_admission import (
    MLX_RUNTIME,
    _admission_candidates,
    _canonical_json,
    _harness_identity,
    _sha256,
    generate_manifest,
    synthetic_measurement_fixtures,
    tree_sha256,
)

# Where the model stops: `sf-` or `cf-` plus a 64-character hex digest.
SHORT_FORM_LENGTH = 67


def alignment_rows(tokenizer) -> list[dict]:
    rows = []
    for identifier, transcript, _expected, _terms in synthetic_measurement_fixtures():
        manifest = generate_manifest(transcript, STRATEGY_CUE)
        for candidate in _admission_candidates(manifest):
            # The anchor, and only the anchor. `visible_fragment_ids` is a ±1
            # window around it, and `model_request` builds `source_fragments`
            # from `anchor_fragment_id` alone — so the window's neighbours were
            # never shown to the model. Measuring them inflated the count and
            # made the claim describe IDs no request ever carried.
            for fragment_id in [candidate["anchor_fragment_id"]]:
                pieces = [tokenizer.decode([token]) for token in tokenizer.encode(fragment_id)]
                # Walk the pieces and find where the short form would end.
                emitted, index, aligned = "", None, None
                for position, piece in enumerate(pieces):
                    emitted += piece
                    if len(emitted) >= SHORT_FORM_LENGTH:
                        index = position
                        aligned = len(emitted) == SHORT_FORM_LENGTH
                        break
                rows.append({
                    "fixture": identifier,
                    "fragment_id_length": len(fragment_id),
                    "candidate_id_length": len(candidate["candidate_id"]),
                    "tokens": len(pieces),
                    "short_form_token_index": index,
                    "boundary_is_token_aligned": aligned,
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", required=True, type=Path)
    args = parser.parse_args()
    # Token alignment is a property of one specific tokenizer, so the same
    # preflight the sibling entry points run applies here: a receipt measured
    # with some other model cannot refute anything about the pinned one.
    preflight = tree_sha256(args.model_directory)
    if preflight != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise SystemExit("model tree does not match registered identity")
    from mlx_lm import load

    _model, tokenizer = load(str(args.model_directory))
    rows = alignment_rows(tokenizer)
    if not rows:
        # `all of zero` is true, and a receipt asserting alignment from nothing
        # would re-affirm the doc's claim on an empty measurement.
        raise SystemExit("no offered fragment ids were measured")
    aligned = [row for row in rows if row["boundary_is_token_aligned"]]
    print(_canonical_json({
        "schema": "mlx-note-id-alignment/2",
        "short_form_length": SHORT_FORM_LENGTH,
        "scope": "anchor fragment ids as offered by model_request, one per candidate",
        "model": {
            "repository": MLX_RUNTIME["model"]["repository"],
            "revision": MLX_RUNTIME["model"]["revision"],
            "tree_sha256": preflight,
        },
        "harness": _harness_identity(),
        "probe_sha256": _sha256(Path(__file__).resolve().read_bytes()),
        "rows": rows,
        # The finding, stated so a reader does not have to re-derive it: if this
        # is true of every fixture, token alignment cannot be what separates the
        # one success from the nine failures.
        "every_boundary_is_token_aligned": len(aligned) == len(rows),
        "counts": {"fragments": len(rows), "aligned": len(aligned)},
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
