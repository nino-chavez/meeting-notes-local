#!/usr/bin/env python3
"""Run a content-free synthetic MLX note-candidate probe.

The only persisted data is identifiers, hashes, sizes, timings, and refusal
classes. It never writes a note artifact or retains a transcript/model reply.
"""

from __future__ import annotations

import argparse
import resource
import time
from pathlib import Path

from mlx_note_admission import (
    MLX_RUNTIME,
    _canonical_json,
    _harness_identity,
    local_mlx_provider,
    run_control_arm,
    run_model_arm,
    synthetic_corrective_probe_fixtures,
    tree_sha256,
)
from summarize import structured_artifact_citations

ACCEPTED = "accepted-research-candidate"
TRANSCRIPT_ONLY = "transcript-only"

# A fixture whose expected outcome is this one is asking the two arms a question
# neither is authoritative about. Registered 2026-08-07 as intervention seven.
#
# Every other expected outcome grades the model against a fixed answer, and for
# `transcript-only` that answer is also what the deterministic arm produces — so
# a disagreement between the arms could only ever be scored as a model failure.
# That assumes the control is right. It is measurably not: it reads
# "If we decided to ship Tuesday, we would need Dana" as a decision, because it
# is word-presence, the same defect the polarity gate exists for on the other
# arm. A model that abstains there behaves better than its reference, and
# grading it would suppress the one result most worth finding.
#
# So the outcome is recorded rather than graded. Nothing new is written to do
# that: the fixture row's `outcomes` and `codes` already carry which way each
# arm went, per call.
ARMS_RECORDED = "arms-recorded"


def model_call_checks(result, transcript, expected_outcome: str, required_terms) -> dict:
    """The model-side gates for one call.

    Extracted so the fresh-process matrix orchestrator applies exactly these and
    not a second, drifting copy — a matrix that graded itself more leniently than
    the probe would look like progress.
    """
    citations = []
    if result.note is not None:
        # `items` is a count; the rows are under `cited`, and each carries the
        # verbatim transcript span as `quote`. This line had never executed: no
        # arm had produced an accepted note before the structure-constrained
        # run, so iterating an integer and reading a missing key both survived.
        citations = [row["quote"] for row in structured_artifact_citations(result.note, transcript)["cited"]]
    joined = "\n".join(citations).casefold()
    if expected_outcome == ARMS_RECORDED:
        # Not graded on which arm wins. Still graded on honesty: if the model
        # did produce a note, that note must cite what it claims. Abstaining is
        # vacuously fine, and is the interesting result rather than a failure.
        return {
            "expected_outcome": result.outcome in (ACCEPTED, TRANSCRIPT_ONLY),
            "required_citation_terms": (
                result.note is None
                or all(term.casefold() in joined for term in required_terms)
            ),
            "strict_empty_abstention": True,
        }
    return {
        "expected_outcome": result.outcome == expected_outcome,
        "required_citation_terms": all(term.casefold() in joined for term in required_terms),
        "strict_empty_abstention": expected_outcome != TRANSCRIPT_ONLY or result.code == "no-model-candidates",
    }


def control_expected(control, expected_outcome: str) -> bool:
    """What the deterministic arm must do for the fixture to be measuring anything.

    `ARMS_RECORDED` expects the control to ACCEPT. That is the whole point: the
    fixture only asks its question when the extractor has offered a candidate,
    so a control that abstained would mean the transcript was mis-written rather
    than that the model behaved well.
    """
    if expected_outcome == ARMS_RECORDED:
        return control.outcome == ACCEPTED
    return control.outcome == (
        ACCEPTED if expected_outcome == ACCEPTED else TRANSCRIPT_ONLY
    )


def fixture_receipt(phase: str, identifier: str, transcript, expected_outcome: str, required_terms, provider) -> dict:
    control = run_control_arm(transcript)
    result = run_model_arm(transcript, provider)
    checks = {
        "control_expected": control_expected(control, expected_outcome),
        **model_call_checks(result, transcript, expected_outcome, required_terms),
    }
    return {
        "phase": phase,
        "id": identifier,
        "control": {"outcome": control.outcome, "code": control.code},
        "outcome": result.outcome,
        "code": result.code,
        "refusal_category": result.receipt.get("refusal_category"),
        "error_type": result.receipt.get("error_type"),
        "elapsed_s": result.receipt.get("elapsed_s"),
        "response_sha256": result.receipt.get("response_sha256"),
        "response_bytes": result.receipt.get("response_bytes"),
        "generation": result.receipt.get("generation"),
        "identity": result.receipt.get("identity"),
        "checks": checks,
    }


def fixtures_for_scope(scope: str):
    if scope == "probe":
        return synthetic_corrective_probe_fixtures()
    raise ValueError(
        "full-scope-not-implemented: use a fresh-process orchestrator for the registered cold/warm repeat matrix"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--scope", required=True, choices=("probe", "full"))
    # Off by default: the unconstrained arm must stay exactly what the
    # 2026-08-02 corrective probe ran, and the receipt records which was used.
    parser.add_argument("--constrained", action="store_true")
    args = parser.parse_args()
    try:
        fixtures = fixtures_for_scope(args.scope)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    preflight_tree_sha256 = tree_sha256(args.model_directory)
    if preflight_tree_sha256 != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise SystemExit("model tree does not match registered identity")
    provider = local_mlx_provider(args.model_directory, constrained=args.constrained)
    load = getattr(provider, "load_receipt")

    cold = fixture_receipt("cold-call", *fixtures[0], provider)
    warm = fixture_receipt("warm-call", *fixtures[1], provider)
    postflight_tree_sha256 = tree_sha256(args.model_directory)
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    passed = all(all(row["checks"].values()) for row in (cold, warm)) and postflight_tree_sha256 == preflight_tree_sha256
    receipt = {
        "schema": "mlx-note-corrective-probe/1",
        "scope": args.scope,
        "decoding": "structure-constrained" if args.constrained else "unconstrained",
        "harness": _harness_identity(),
        "registered_model": {
            "repository": MLX_RUNTIME["model"]["repository"],
            "revision": MLX_RUNTIME["model"]["revision"],
            "tree_sha256": MLX_RUNTIME["model"]["expected_tree_sha256"],
        },
        "preflight_tree_sha256": preflight_tree_sha256,
        "postflight_tree_sha256": postflight_tree_sha256,
        "load": load,
        "peak_rss": peak_rss,
        "calls": [cold, warm],
        "passed": passed,
    }
    print(_canonical_json(receipt))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
