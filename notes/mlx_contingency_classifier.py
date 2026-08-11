#!/usr/bin/env python3
"""Measure a separate, research-only note-modality classifier.

This probe does not build, suppress, relabel, render, or persist a note. It asks
the pinned local MLX model to classify synthetic candidate text on one axis:
DIRECT, CONDITIONAL, or HYPOTHETICAL. Expected labels stay outside the request.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Callable

from mlx_note_admission import (
    AdmissionRefused,
    MLX_RUNTIME,
    _canonical_json,
    _provider_user_request,
    _runtime_receipt,
    _sha256,
    local_mlx_provider,
)

SCHEMA = "mlx-note-modality-probe/1"
REQUEST_SCHEMA = "mlx-note-modality-request/1"
RESPONSE_SCHEMA = "mlx-note-modality-response/1"
REPEATS = 3
MODALITIES = ("DIRECT", "CONDITIONAL", "HYPOTHETICAL")

SYSTEM_PROMPT = """\
Classify the modality of every offered meeting-note candidate.

DIRECT means the record itself is stated without depending on a condition.
CONDITIONAL means a real decision, action, proposal, or question is stated, but
its outcome depends on an explicit condition or precondition. HYPOTHETICAL means
the would-be record is only imagined or counterfactual rather than made.

Classify modality only, not whether the record is a decision, action, proposal,
or question. A decision made subject to a precondition is CONDITIONAL, not
HYPOTHETICAL. Read the meaning rather than matching marker words.

Return only one JSON object matching the supplied response contract."""

FIXTURES = (
    ("direct-decision", "Dana decided that Battery 7 ships Tuesday.", "DIRECT"),
    ("direct-action", "Marco will send invoice 2048 by June 14.", "DIRECT"),
    ("direct-proposal", "Priya proposed moving the renewal to Q4.", "DIRECT"),
    ("direct-question", "Could Aisha confirm whether the North room is available?", "DIRECT"),
    ("conditional-decision", "We decided to ship Tuesday if QA approves the release.", "CONDITIONAL"),
    ("conditional-barring", "Barring Dana's return, the team could ship Tuesday.", "CONDITIONAL"),
    ("conditional-pending", "The decision is to ship Tuesday, pending QA approval.", "CONDITIONAL"),
    ("hypothetical-if", "If we decided to ship Tuesday, we would need Dana.", "HYPOTHETICAL"),
    ("hypothetical-past", "Had we shipped Tuesday, Dana would have been needed.", "HYPOTHETICAL"),
    ("hypothetical-scenario", "Imagine the team ships Tuesday; Dana handles rollout in that scenario.", "HYPOTHETICAL"),
)


class _Pairs:
    def __init__(self, pairs: list[tuple[str, object]]):
        self.pairs = pairs


def fixture_sha256() -> str:
    return _sha256(_canonical_json(FIXTURES))


def response_contract(candidate_ids: list[str]) -> dict:
    return {
        "schema": RESPONSE_SCHEMA,
        "root": {
            "type": "object",
            "ordered_fields": ["items"],
            "items": {
                "type": "array",
                "length": len(candidate_ids),
                "candidate_order": candidate_ids,
                "item_ordered_fields": ["candidate_id", "modality"],
                "modality_enum": list(MODALITIES),
            },
        },
    }


def model_request() -> dict:
    candidate_ids = [f"m{index + 1:04d}" for index in range(len(FIXTURES))]
    return {
        "schema": REQUEST_SCHEMA,
        "system": SYSTEM_PROMPT,
        "response_contract": response_contract(candidate_ids),
        "candidates": [
            {"candidate_id": candidate_id, "text": text}
            for candidate_id, (_name, text, _expected) in zip(
                candidate_ids, FIXTURES, strict=True
            )
        ],
    }


def expected_modalities() -> list[str]:
    return [expected for _name, _text, expected in FIXTURES]


def _strict_json(raw: str) -> _Pairs:
    if not isinstance(raw, str) or not raw.strip():
        raise AdmissionRefused("response-contract")

    def pairs(values: list[tuple[str, object]]) -> _Pairs:
        keys = [key for key, _value in values]
        if len(keys) != len(set(keys)):
            raise AdmissionRefused("response-contract")
        return _Pairs(values)

    try:
        decoded = json.loads(raw, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise AdmissionRefused("response-json-syntax") from exc
    if not isinstance(decoded, _Pairs):
        raise AdmissionRefused("response-contract")
    return decoded


def decode_response(raw: str, request: dict) -> list[dict]:
    decoded = _strict_json(raw)
    if tuple(key for key, _value in decoded.pairs) != ("items",):
        raise AdmissionRefused("response-contract")
    rows = decoded.pairs[0][1]
    expected_ids = [row["candidate_id"] for row in request["candidates"]]
    if not isinstance(rows, list) or len(rows) != len(expected_ids):
        raise AdmissionRefused("response-contract")

    safe = []
    for row, expected_id in zip(rows, expected_ids, strict=True):
        if not isinstance(row, _Pairs):
            raise AdmissionRefused("response-contract")
        if tuple(key for key, _value in row.pairs) != ("candidate_id", "modality"):
            raise AdmissionRefused("response-contract")
        values = dict(row.pairs)
        if values["candidate_id"] != expected_id:
            raise AdmissionRefused("response-contract")
        if values["modality"] not in MODALITIES:
            raise AdmissionRefused("response-contract")
        safe.append({"candidate_id": expected_id, "modality": values["modality"]})
    return safe


def response_shape(raw: str) -> dict:
    """Content-free diagnostic for a response strict decoding refused."""
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"root_type": "invalid-json"}
    if isinstance(decoded, list):
        return {
            "root_type": "array",
            "items": len(decoded),
            "item_keys": sorted({
                tuple(row.keys())
                for row in decoded
                if isinstance(row, dict)
            }),
        }
    if isinstance(decoded, dict):
        rows = decoded.get("items")
        return {
            "root_type": "object",
            "root_keys": list(decoded),
            "items": len(rows) if isinstance(rows, list) else None,
            "item_keys": sorted({
                tuple(row.keys())
                for row in rows or []
                if isinstance(row, dict)
            }) if isinstance(rows, list) else [],
        }
    return {"root_type": type(decoded).__name__}


def untrusted_modalities(raw: str, expected_count: int) -> list[str]:
    """Read categorical diagnostics from the one known invalid array shape.

    These values never satisfy decoding. They only show whether repairing the
    envelope would expose a semantic miss behind the structural refusal.
    """
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if (
        not isinstance(decoded, list)
        or len(decoded) != expected_count
        or any(
            not isinstance(row, dict)
            or set(row) != {"modality"}
            or row["modality"] not in MODALITIES
            for row in decoded
        )
    ):
        return []
    return [row["modality"] for row in decoded]


def run_probe(provider: Callable[[dict], tuple[str, dict]]) -> dict:
    request = model_request()
    expected = expected_modalities()
    expected_request_sha256 = _sha256(_canonical_json({
        "system": request["system"],
        "user": _provider_user_request(request),
    }))
    calls = []
    for index in range(REPEATS):
        raw = ""
        runtime = None
        try:
            raw, observed = provider(deepcopy(request))
            runtime = _runtime_receipt(observed, expected_request_sha256)
            rows = decode_response(raw, request)
            actual = [row["modality"] for row in rows]
            code = None
        except AdmissionRefused as exc:
            actual = []
            code = exc.code
        diagnostic = untrusted_modalities(raw, len(expected))
        calls.append({
            "index": index,
            "phase": "cold" if index == 0 else "warm",
            "code": code,
            "response_sha256": _sha256(raw),
            "response_shape": response_shape(raw),
            "actual": actual,
            "untrusted_actual": diagnostic,
            "untrusted_agreement": sum(
                left == right
                for left, right in zip(diagnostic, expected, strict=False)
            ),
            "agreement": sum(
                left == right for left, right in zip(actual, expected, strict=False)
            ),
            "passed": code is None and actual == expected,
            "runtime": runtime,
        })

    response_digests = {row["response_sha256"] for row in calls}
    actual_sequences = {tuple(row["actual"]) for row in calls}
    repeatable = len(response_digests) == 1 and len(actual_sequences) == 1
    labels_hidden = all(
        expected not in _canonical_json(request["candidates"])
        for expected in MODALITIES
    )
    passed = all(row["passed"] for row in calls) and repeatable and labels_hidden
    return {
        "schema": SCHEMA,
        "harness_sha256": _sha256(Path(__file__).read_bytes()),
        "fixture_sha256": fixture_sha256(),
        "model": {
            "repository": MLX_RUNTIME["model"]["repository"],
            "revision": MLX_RUNTIME["model"]["revision"],
            "tree_sha256": MLX_RUNTIME["model"]["expected_tree_sha256"],
        },
        "request_sha256": expected_request_sha256,
        "fixtures": [
            {"fixture": name, "expected": expected}
            for name, _text, expected in FIXTURES
        ],
        "calls": calls,
        "gates": {
            "all_fixtures_match": all(row["passed"] for row in calls),
            "repeatable": repeatable,
            "expected_labels_hidden": labels_hidden,
        },
        "passed": passed,
        "admits": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", required=True, type=Path)
    args = parser.parse_args()
    provider = local_mlx_provider(args.model_directory, constrained=False)
    receipt = run_probe(provider)
    print(_canonical_json(receipt))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
