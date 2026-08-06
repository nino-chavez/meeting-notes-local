#!/usr/bin/env python3
"""Lay the generated claims beside the evidence they cite, for the human read.

Wave D's gate is semantic support and usefulness adjudication. `MLX_NOTE_ADMISSION.md`
has said since 2026-08-02 that no human has read any output for usefulness, and until
2026-08-06 that was partly a packaging problem: the outputs existed only as digests and
booleans inside receipts, so there was nothing to hand a reader.

This script produces that material. It reads only the committed citation receipt and the
local fixture definitions. No model is loaded, no network is touched, no request is built,
and no digest anywhere changes. It is a presentation of results already recorded, not a
new measurement of the model.

    python3 notes/read_semantic_support.py [--json] [--receipt PATH]

Per row it reports, side by side:

  cited        the canonical transcript slice the row cites, verbatim
  claim        the claim the model generated from it
  cue          the cue_type the harness's own deterministic strategy assigned the
               candidate, beside the label the model emitted
  gate         whether that fixture passed every registered gate in the matrix

Two things this deliberately does not do.

It renders no verdict. Whether a claim is semantically supported by its evidence, and
whether it is useful, is the operator's adjudication and this script has no opinion slot
for it. What it mechanically flags — polarity terms present in the evidence and absent
from the claim, and label-against-cue disagreement — are pointers for a reader, not
findings, and both are printed as observations with the evidence next to them so the
reader can overrule either.

And it adds no rule. `_decode_response` does not compare `label` to `cue_type`, and this
script does not make it. Adding a check is a rule added, which the amendment discipline
in MLX_NOTE_ADMISSION.md requires be registered on its own rather than folded into a
change that is measuring something else. The disagreement is reported and left in place.

The cue_type is itself a heuristic from the deterministic cue strategy, not ground truth.
A disagreement between it and the model's label is a prompt to look, not a defect.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mlx_note_admission as admission
from candidate_first import STRATEGY_CUE, generate_manifest

DEFAULT_RECEIPT = Path(__file__).resolve().parent / "mlx_note_citation_branch_receipt_rule_key.json"
DEFAULT_MATRIX = Path(__file__).resolve().parent / "mlx_note_matrix_receipt_rule_key.json"

# Terms whose disappearance between evidence and claim reverses the meaning rather
# than shortening it. Presence in the cited slice and absence from the claim is
# reported; it is not scored, and a reader may find a paraphrase that carries the
# polarity some other way.
POLARITY_TERMS = ("not", "no", "never", "cannot", "can't", "don't", "doesn't", "without")


def _words(text: str) -> set[str]:
    return {
        "".join(character for character in token if character.isalnum() or character == "'")
        .lower()
        for token in text.split()
    }


def _dropped_polarity(cited: str, claim: str) -> list[str]:
    in_evidence = _words(cited)
    in_claim = _words(claim)
    return [term for term in POLARITY_TERMS if term in in_evidence and term not in in_claim]


def read_rows(receipt_path: Path, matrix_path: Path) -> list[dict]:
    receipt = {entry["fixture"]: entry for entry in json.loads(receipt_path.read_text())}
    matrix = {
        entry["fixture"]: entry for entry in json.loads(matrix_path.read_text())["fixtures"]
    }
    out: list[dict] = []
    for name, transcript, expected, _terms in admission.synthetic_measurement_fixtures():
        entry = receipt.get(name)
        if entry is None:
            continue
        cues = [
            candidate["cue_type"].upper()
            for candidate in generate_manifest(transcript, STRATEGY_CUE)["candidates"]
        ]
        gates = matrix[name]["gates"]
        passed = all(value is True for value in gates.values())
        for index, row in enumerate(entry["rows"]):
            cited = row["canonical_repr"].strip("'")
            claim = row["claim"]
            out.append(
                {
                    "fixture": name,
                    "expected_outcome": expected,
                    "passed_every_registered_gate": passed,
                    "cited_evidence": cited,
                    "claim": claim,
                    "citation_matches_canonical": row["citation_matches"],
                    "harness_cue_type": cues[index] if index < len(cues) else None,
                    "model_label": row["label"],
                    "label_agrees_with_cue": (
                        cues[index] == row["label"] if index < len(cues) else None
                    ),
                    "polarity_terms_dropped": _dropped_polarity(cited, claim),
                    "claim_is_shorter_than_evidence": len(claim) < len(cited),
                }
            )
    return out


def _render(rows: list[dict]) -> str:
    lines: list[str] = []
    for row in rows:
        flag = "PASS" if row["passed_every_registered_gate"] else "FAIL"
        lines.append(f"--- {row['fixture']}  [{flag} every registered gate]")
        lines.append(f"    cited  {row['cited_evidence']}")
        lines.append(f"    claim  {row['claim']}")
        detail = f"    label  {row['model_label']}   harness cue {row['harness_cue_type']}"
        if row["label_agrees_with_cue"] is False:
            detail += "   <- disagree"
        lines.append(detail)
        if row["polarity_terms_dropped"]:
            terms = ", ".join(repr(term) for term in row["polarity_terms_dropped"])
            lines.append(
                f"    NOTE   polarity term(s) {terms} in the evidence, absent from the claim"
            )
        lines.append("")

    disagree = [row for row in rows if row["label_agrees_with_cue"] is False]
    polarity = [row for row in rows if row["polarity_terms_dropped"]]
    passing_disagree = [row for row in disagree if row["passed_every_registered_gate"]]
    lines.append(f"rows: {len(rows)}")
    lines.append(
        f"label disagrees with the harness's own cue_type: {len(disagree)}"
        f" ({len(passing_disagree)} of them on fixtures that pass every registered gate)"
    )
    lines.append(f"claims dropping a polarity term present in their evidence: {len(polarity)}")
    lines.append("")
    lines.append("Neither number is a gate and neither is a verdict. The semantic and")
    lines.append("usefulness adjudication is the operator's, and it has not been run.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the rows as JSON")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    args = parser.parse_args()

    rows = read_rows(args.receipt, args.matrix)
    if not rows:
        raise SystemExit("no rows found; check the receipt paths")
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        print(_render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
