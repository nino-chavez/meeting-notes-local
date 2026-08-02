#!/usr/bin/env python3
"""Run only the registered synthetic MLX note-candidate measurement.

The emitted receipt is content-free: fixture identifiers, outcomes, digests,
timings, and boolean checks only.  It never opens a product store or writes a
note artifact.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from mlx_note_admission import (
    _canonical_json,
    local_mlx_provider,
    run_model_arm,
    synthetic_measurement_fixtures,
)
from summarize import structured_artifact_citations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--tree-sha256", required=True)
    parser.add_argument("--phase", required=True, choices=("cold-1", "cold-2", "cold-3", "warm"))
    args = parser.parse_args()

    provider = local_mlx_provider(args.model_directory)
    started = time.monotonic()
    runs = []
    passed = True
    for run_index in range(2 if args.phase == "warm" else 1):
        run_started = time.monotonic()
        fixtures = []
        run_passed = True
        for identifier, transcript, expected_outcome, required_terms in synthetic_measurement_fixtures():
            result = run_model_arm(
                transcript,
                provider,
                expected_model_tree_sha256=args.tree_sha256,
            )
            citations: list[str] = []
            if result.note is not None:
                citations = [
                    row["citation"]
                    for row in structured_artifact_citations(result.note, transcript)["items"]
                ]
            joined_citations = "\n".join(citations).casefold()
            checks = {
                "expected_outcome": result.outcome == expected_outcome,
                "required_citation_terms": all(term.casefold() in joined_citations for term in required_terms),
                "strict_abstention": (
                    expected_outcome != "transcript-only"
                    or (result.outcome == "transcript-only" and result.code == "no-model-candidates")
                ),
            }
            run_passed = run_passed and all(checks.values())
            fixtures.append({
                "id": identifier,
                "outcome": result.outcome,
                "code": result.code,
                "response_sha256": result.receipt.get("response_sha256"),
                "checks": checks,
            })
        passed = passed and run_passed
        runs.append({
            "index": run_index + 1,
            "elapsed_s": round(time.monotonic() - run_started, 6),
            "passed": run_passed,
            "fixtures": fixtures,
        })
    receipt = {
        "schema": "mlx-note-measurement/1",
        "phase": args.phase,
        "fixture_count": len(runs[0]["fixtures"]),
        "run_count": len(runs),
        "elapsed_s": round(time.monotonic() - started, 6),
        "passed": passed,
        "runs": runs,
    }
    print(_canonical_json(receipt))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
