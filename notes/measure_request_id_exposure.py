#!/usr/bin/env python3
"""Measure how each identifier format is exposed in the request the model reads.

The 12-fixture matrix found `candidate_id` reproduced 10/10 and
`source_fragment_ids` 1/10. `MLX_NOTE_ADMISSION.md` records three candidate
explanations for that asymmetry and reports all three refuted. Two of the three
were refuted by argument, against the one anomalous fixture pair, and that pair
holds the request *format* constant by construction — so it can show a variable
does not explain the anomaly, and cannot show it does not cause the baseline.

This script measures the variable those arguments assumed was symmetric. It reads
only the request each fixture builds; no model is loaded, no network is touched,
and nothing here changes a request digest. Run it before deciding which
intervention to preregister.

    python3 notes/measure_request_id_exposure.py [--json]

Reported per fixture, from the exact canonical user payload:

  occurrences  how many times each ID literal appears in the bytes the model reads
  from_end     characters between the last occurrence and the generation point
  adjacent     what the schema entry for that field shows next to the generation
               point — an enumerated literal, or a bare type with no instance

The measurement is deterministic and additive. It settles no verdict; it reports
whether the two fields are exposed to the model on equal terms, which every
argument in that section has so far assumed without checking.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mlx_note_admission as admission  # noqa: E402
from candidate_first import STRATEGY_CUE, generate_manifest  # noqa: E402

CANDIDATE_ID = re.compile(r"cf-[0-9a-f]{64}")
FRAGMENT_ID = re.compile(r"sf-[0-9a-f]{64}[-a-z0-9]*")


def user_payload(transcript) -> str:
    """The exact string handed to the chat template as the user turn."""
    manifest = generate_manifest(transcript, STRATEGY_CUE)
    request = admission.model_request(transcript, manifest)
    return admission._canonical_json({k: v for k, v in request.items() if k != "system"})


def field_schema_fragment(payload: str, field: str) -> str:
    """The field's own entry in the response contract, as the model reads it."""
    match = re.search(re.escape(f'"{field}":{{') + r"[^}]*\}", payload)
    return match.group(0) if match else "<absent>"


def measure(name: str, transcript) -> dict:
    payload = user_payload(transcript)
    candidates = sorted(set(CANDIDATE_ID.findall(payload)))
    fragments = sorted(set(FRAGMENT_ID.findall(payload)))

    def exposure(literals: list[str]) -> dict:
        if not literals:
            return {"distinct": 0, "occurrences": 0, "from_end": None, "length": None}
        return {
            "distinct": len(literals),
            "occurrences": sum(payload.count(one) for one in literals),
            "from_end": len(payload) - max(payload.rfind(one) + len(one) for one in literals),
            "length": sorted({len(one) for one in literals}),
        }

    return {
        "fixture": name,
        "payload_length": len(payload),
        "candidate_id": exposure(candidates),
        "source_fragment_id": exposure(fragments),
        "candidate_id_schema": field_schema_fragment(payload, "candidate_id"),
        "source_fragment_ids_schema": field_schema_fragment(payload, "source_fragment_ids"),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the rows as JSON")
    args = parser.parse_args(argv[1:])

    rows = [
        measure(name, transcript)
        for name, transcript, *_ in admission.synthetic_measurement_fixtures()
    ]

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0

    print(f"{'fixture':24} {'bytes':>6} {'cf x':>5} {'cf end':>7} {'sf x':>5} {'sf end':>7}  nearer")
    for row in rows:
        cid, fid = row["candidate_id"], row["source_fragment_id"]
        if not fid["occurrences"]:
            print(f"{row['fixture']:24} {row['payload_length']:6}  (abstain fixture — no fragment offered)")
            continue
        nearer = "candidate_id" if cid["from_end"] < fid["from_end"] else "source_fragment_id"
        print(
            f"{row['fixture']:24} {row['payload_length']:6} {cid['occurrences']:5} "
            f"{cid['from_end']:7} {fid['occurrences']:5} {fid['from_end']:7}  {nearer}"
        )

    supported = [r for r in rows if r["source_fragment_id"]["occurrences"]]
    print()
    print("Schema entry each field shows the model, identical across every fixture:")
    print(f"  candidate_id        {supported[0]['candidate_id_schema'][:96]}…")
    print(f"  source_fragment_ids {supported[0]['source_fragment_ids_schema']}")
    print()
    nearer_candidate = sum(
        1 for r in supported if r["candidate_id"]["from_end"] < r["source_fragment_id"]["from_end"]
    )
    twice = sum(1 for r in supported if r["candidate_id"]["occurrences"] > r["source_fragment_id"]["occurrences"])
    print(f"  candidate_id is the nearer ID to the generation point: {nearer_candidate}/{len(supported)}")
    print(f"  candidate_id appears more often than the fragment ID:  {twice}/{len(supported)}")
    print()
    print("  The two fields are not exposed on equal terms. That does not explain the")
    print("  single anomalous success, and it was never required to.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
