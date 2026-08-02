#!/usr/bin/env python3
"""Isolated MLX-LM admission harness for evidence-linked local notes.

This is research code.  It accepts only a caller-provided ``Transcript`` and
returns in-memory results; it never opens a meeting store, writes an artifact,
or reaches Preview.  The real model is deliberately optional so the protocol
and its refusal paths can be tested before the multi-gigabyte candidate model
is fetched.

The model is not trusted with evidence locations.  It may select candidate and
source-fragment IDs, but local code re-resolves every selected fragment against
the canonical transcript and validates an exact returned citation before a
``note/2``-shaped candidate can be reported as accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from candidate_first import STRATEGY_CUE, generate_manifest, validate_manifest
import summarize as summary
from summarize import (
    SOURCE_EVIDENCE_CONTRACT,
    STRUCTURED_NOTE_SCHEMA,
    STRUCTURED_RUN_CONTRACT,
    _durable_consolidation_rows,
    _durable_extraction_rows,
    _json_sha256,
    _normalization_receipt,
    _response_provenance,
    attach_evidence_items,
    build_fragment_map,
    normalize_extraction_items,
    render_structured_note,
    structured_artifact_citations,
    structured_citations,
)
from transcript import NONE, Transcript, Turn


ADMISSION_SCHEMA = "mlx-note-admission/1"
MODEL_RESPONSE_SCHEMA = "mlx-note-response/1"

# This is a research pin, not a release manifest.  The revision pins the model
# source before download; the local model-tree digest is intentionally unknown
# until the explicit fetch/measurement step creates a reviewable inventory.
MLX_RUNTIME = {
    "schema": "mlx-note-runtime/1",
    "role": "research-only",
    "python": "3.12",
    "package": "mlx-lm==0.30.4",
    "package_license": "MIT",
    "model": {
        "repository": "mlx-community/SmolLM2-1.7B-Instruct",
        "revision": "1c18454eb88e660ee6f0a201e310fa3602fad3e0",
        "license": "Apache-2.0",
        "expected_tree_sha256": None,
        "status": "unfetched-not-admitted",
    },
    "decoding": {
        "temperature": 0.0,
        "max_tokens": 512,
        "max_kv_size": 4096,
        "seed": 0,
    },
    "network": "forbidden-after-local-model-verification",
    "product_records": "forbidden",
}

SYSTEM_PROMPT = """\
Return only one JSON object matching the supplied response contract.

Select only records directly supported by the supplied candidate context. Every
item must name the offered candidate_id and one to three offered source fragment
IDs in canonical order. citation must exactly equal the first selected source
fragment. label must be DECISION, ACTION, PROPOSAL, or QUESTION. claim may be a
concise interpretation, but do not invent names, numbers, dates, negation, or
commitments not present in the selected fragments. Omit unsupported items.
"""


class AdmissionRefused(ValueError):
    """The model arm must fall back to canonical transcript-only."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AdmissionResult:
    arm: str
    outcome: str
    code: str | None
    note: dict | None
    receipt: dict


ModelProvider = Callable[[dict], tuple[str, dict]]


def _sha256(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strict_json(raw: str) -> object:
    def pairs(items: list[tuple[str, object]]) -> tuple[tuple[str, object], ...]:
        names = [name for name, _ in items]
        if len(names) != len(set(names)):
            raise AdmissionRefused("malformed-response")
        return tuple(items)

    if not isinstance(raw, str) or not raw.strip():
        raise AdmissionRefused("malformed-response")
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise AdmissionRefused("malformed-response") from exc


def _object(value: object, names: tuple[str, ...]) -> dict:
    if not isinstance(value, tuple) or tuple(name for name, _ in value) != names:
        raise AdmissionRefused("malformed-response")
    return dict(value)


def response_contract(manifest: dict) -> dict:
    """The prompt contract; the parser below remains the actual boundary."""
    candidate_ids = [row["candidate_id"] for row in manifest["candidates"]]
    fragment_ids = sorted({
        fragment_id
        for row in manifest["candidates"]
        for fragment_id in row["visible_fragment_ids"]
    })
    return {
        "schema": MODEL_RESPONSE_SCHEMA,
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "maxItems": len(candidate_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "candidate_id", "source_fragment_ids", "citation", "label", "claim",
                    ],
                    "properties": {
                        "candidate_id": {"type": "string", "enum": candidate_ids},
                        "source_fragment_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": fragment_ids},
                            "minItems": 1,
                            "maxItems": 3,
                            "uniqueItems": True,
                        },
                        "citation": {"type": "string", "minLength": 1},
                        "label": {
                            "type": "string",
                            "enum": ["DECISION", "ACTION", "PROPOSAL", "QUESTION"],
                        },
                        "claim": {"type": "string", "minLength": 1, "maxLength": 160},
                    },
                },
            },
        },
    }


def model_request(transcript: Transcript, manifest: dict) -> dict:
    """Build a source-ID-only request; no product artifact leaves this function."""
    validate_manifest(manifest, transcript)
    fragments = {
        row["source_fragment_id"]: row
        for row in build_fragment_map(transcript)["fragments"]
    }
    candidates = []
    for row in manifest["candidates"]:
        visible = []
        for fragment_id in row["visible_fragment_ids"]:
            fragment = fragments[fragment_id]
            visible.append({
                "source_fragment_id": fragment_id,
                "text": transcript.turns[fragment["turn"]].text[
                    fragment["char_start"]:fragment["char_end"]
                ],
            })
        candidates.append({
            "candidate_id": row["candidate_id"],
            "cue_type": row["cue_type"],
            "source_fragments": visible,
        })
    return {
        "schema": "mlx-note-request/1",
        "system": SYSTEM_PROMPT,
        "response_contract": response_contract(manifest),
        "candidates": candidates,
    }


def _decode_response(raw: str, manifest: dict, transcript: Transcript) -> list[dict]:
    root = _object(_strict_json(raw), ("items",))
    rows = root["items"]
    if not isinstance(rows, list):
        raise AdmissionRefused("malformed-response")
    candidates = {row["candidate_id"]: row for row in manifest["candidates"]}
    fragment_map = build_fragment_map(transcript)
    fragments = {
        row["source_fragment_id"]: row for row in fragment_map["fragments"]
    }
    selected: list[dict] = []
    seen: set[str] = set()
    last_candidate_position = -1
    used_primary_fragments: set[str] = set()
    for raw_row in rows:
        row = _object(
            raw_row,
            ("candidate_id", "source_fragment_ids", "citation", "label", "claim"),
        )
        candidate_id = row["candidate_id"]
        if not isinstance(candidate_id, str) or candidate_id not in candidates:
            raise AdmissionRefused("unknown-candidate")
        if candidate_id in seen:
            raise AdmissionRefused("duplicate-candidate")
        seen.add(candidate_id)
        candidate_position = manifest["candidates"].index(candidates[candidate_id])
        if candidate_position <= last_candidate_position:
            raise AdmissionRefused("candidates-out-of-order")
        last_candidate_position = candidate_position
        source_ids = row["source_fragment_ids"]
        if (
            not isinstance(source_ids, list)
            or not 1 <= len(source_ids) <= 3
            or any(not isinstance(value, str) for value in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            raise AdmissionRefused("malformed-response")
        allowed = candidates[candidate_id]["visible_fragment_ids"]
        if any(value not in allowed or value not in fragments for value in source_ids):
            raise AdmissionRefused("unknown-source-fragment")
        positions = [allowed.index(value) for value in source_ids]
        if positions != sorted(positions):
            raise AdmissionRefused("source-fragments-out-of-order")
        citation = row["citation"]
        if not isinstance(citation, str):
            raise AdmissionRefused("malformed-response")
        primary = fragments[source_ids[0]]
        if source_ids[0] in used_primary_fragments:
            raise AdmissionRefused("duplicate-primary-source")
        used_primary_fragments.add(source_ids[0])
        canonical_citation = transcript.turns[primary["turn"]].text[
            primary["char_start"]:primary["char_end"]
        ]
        if citation != canonical_citation:
            raise AdmissionRefused("citation-mismatch")
        label = row["label"]
        claim = row["claim"]
        if (
            not isinstance(label, str)
            or label not in {"DECISION", "ACTION", "PROPOSAL", "QUESTION"}
            or not isinstance(claim, str)
            or not claim.strip()
            or len(claim) > 160
            or any(ord(character) < 32 for character in claim)
        ):
            raise AdmissionRefused("malformed-response")
        selected.append({
            "source_fragment_ids": source_ids,
            "label": label,
            "claim": claim.strip(),
        })
    return selected


def _runtime_receipt(observed: dict, expected_tree_sha256: str) -> dict:
    required = {"package", "model_tree_sha256"}
    if not isinstance(observed, dict) or set(observed) != required:
        raise AdmissionRefused("model-digest-mismatch")
    if observed["package"] != MLX_RUNTIME["package"]:
        raise AdmissionRefused("runtime-package-mismatch")
    if observed["model_tree_sha256"] != expected_tree_sha256:
        raise AdmissionRefused("model-digest-mismatch")
    return {
        "runtime": deepcopy(MLX_RUNTIME),
        "observed": dict(observed),
        "expected_model_tree_sha256": expected_tree_sha256,
    }


def _note2_candidate(
    transcript: Transcript,
    items: list[dict],
    *,
    model_identity: dict,
    arm: str,
) -> dict:
    """Build and replay a memory-only note/2 candidate through existing checks."""
    fragment_map = build_fragment_map(transcript)
    lookup = {row["source_fragment_id"]: row for row in fragment_map["fragments"]}
    attached = attach_evidence_items(
        items, 1, lookup, transcript, fragment_map["transcript_view_sha256"]
    )
    consolidated = normalize_extraction_items(attached)
    # Existing note/2 validation also fixes generated field order: evidence IDs
    # precede the label and claim. Do not canonical-sort this response.
    safe_response = json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":"))
    turn_windows = summary._chunk_turn_windows(transcript, 32, 8)
    if len(turn_windows) != 1:
        raise AdmissionRefused("research-fixture-exceeds-single-slice")
    _visible, visible_ids, schema, user = summary._extraction_request(
        transcript, fragment_map, turn_windows[0]
    )
    source_ids = [fragment_id for item in items for fragment_id in item["source_fragment_ids"]]
    stage = _response_provenance(
        f"{transcript.source} [slice 1/1]",
        1,
        {"message": {"content": safe_response}},
        schema,
        model_identity,
        MLX_RUNTIME["decoding"]["max_kv_size"],
        summary.extraction_num_predict(len(visible_ids)),
        {"done": True, "done_reason": "stop"},
        summary._structured_system(transcript),
        user,
        {
            "transcript_view_sha256": fragment_map["transcript_view_sha256"],
            "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
            "fragment_map_sha256": fragment_map["fragment_map_sha256"],
            "visible_fragment_ids_sha256": _json_sha256(visible_ids),
            "visible_fragments": len(visible_ids),
            "selected_fragment_references": len(source_ids),
        },
        {
            "items": len(attached),
            "selected_fragment_references": len(source_ids),
        },
    )
    evidence = {
        "schema": SOURCE_EVIDENCE_CONTRACT,
        "transcript_view_sha256": fragment_map["transcript_view_sha256"],
        "fragment_contract": fragment_map["fragment_contract"],
        "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
        "fragment_map_sha256": fragment_map["fragment_map_sha256"],
        "extraction_items": _durable_extraction_rows(attached),
        "consolidated_items": _durable_consolidation_rows(consolidated["items"]),
    }
    structured_contract = {
        "schema": STRUCTURED_RUN_CONTRACT,
        "evidence_contract": SOURCE_EVIDENCE_CONTRACT,
        "extraction_receipt_contract": "structured-stage-receipt/5",
        "normalization_receipt_contract": "local-normalization-receipt/1",
        "normalization_contract": deepcopy(summary.LOCAL_NORMALIZATION_CONTRACT),
        "normalization_contract_sha256": _json_sha256(
            summary.LOCAL_NORMALIZATION_CONTRACT
        ),
        "extraction_output_contract": deepcopy(summary.EXTRACTION_OUTPUT_CONTRACT),
        "extraction_output_contract_sha256": _json_sha256(
            summary.EXTRACTION_OUTPUT_CONTRACT
        ),
        "target_words": 32,
        "overlap_words": 8,
        "num_ctx": MLX_RUNTIME["decoding"]["max_kv_size"],
        "temperature": MLX_RUNTIME["decoding"]["temperature"],
        # Existing note/2 replay owns this field. The stricter local-tree check is
        # retained separately in the admission receipt, not misrepresented here.
        "model_identity_validation": "cross-checked receipt; historical tags response is not retained",
        "input_sources": len(attached),
        "covered_sources": sum(len(item["source_item_ids"]) for item in consolidated["items"]),
        "output_records": len(consolidated["items"]),
        "rendered_claims": len(consolidated["items"]),
        "max_normalization_group": 3,
        "merged_groups": sum(len(item["source_item_ids"]) > 1 for item in consolidated["items"]),
        "max_observed_group": max((len(item["source_item_ids"]) for item in consolidated["items"]), default=0),
        "normalization_semantics": (
            "local only: merge up to three items iff label, canonical decoded "
            "claim UTF-8, and ordered source fragment IDs are identical"
        ),
        "render_contract": deepcopy(summary.STRUCTURED_NOTE_CONTRACT),
        "render_contract_sha256": _sha256(_canonical_json(summary.STRUCTURED_NOTE_CONTRACT)),
    }
    result = {
        "claim_evidence_contract": SOURCE_EVIDENCE_CONTRACT,
        "note": render_structured_note(consolidated["items"]),
        "model": model_identity["requested"],
        "model_identity": model_identity,
        "consolidated_records": consolidated,
        "evidence_contract": evidence,
        "structured_provenance": [stage, _normalization_receipt(attached, consolidated["items"], 2)],
        "structured_contract": structured_contract,
    }
    citations = structured_citations(result, transcript)
    note = {
        "schema": STRUCTURED_NOTE_SCHEMA,
        "claim_evidence_contract": SOURCE_EVIDENCE_CONTRACT,
        "note": result["note"],
        "claims": [{"status": "located", **row} for row in citations["cited"]],
        "evidence": evidence,
        "provenance": {
            "model": result["model"],
            "model_identity": model_identity,
            "structured_stages": result["structured_provenance"],
            "structured_contract": structured_contract,
            "source_evidence": {
                key: evidence[key]
                for key in (
                    "schema", "transcript_view_sha256",
                    "fragment_contract_sha256", "fragment_map_sha256",
                )
            },
            "admission_arm": arm,
        },
    }
    # This is the existing note/2 evidence validator.  It replay-validates the
    # retained safe stage JSON, durable evidence graph, rendering, and locators.
    structured_artifact_citations(note, transcript)
    return note


def transcript_only(arm: str, code: str, receipt: dict) -> AdmissionResult:
    return AdmissionResult(
        arm=arm,
        outcome="transcript-only",
        code=code,
        note=None,
        receipt={"schema": ADMISSION_SCHEMA, "arm": arm, "outcome": "transcript-only", "code": code, **receipt},
    )


def run_control_arm(transcript: Transcript) -> AdmissionResult:
    """A fully deterministic cue baseline; useful as a protocol control only."""
    manifest = generate_manifest(transcript, STRATEGY_CUE)
    validate_manifest(manifest, transcript)
    fragments = {
        row["source_fragment_id"]: row for row in build_fragment_map(transcript)["fragments"]
    }
    rows = []
    used_anchors: set[str] = set()
    for candidate in manifest["candidates"]:
        if candidate["cue_type"] not in {"decision", "action", "proposal", "question"}:
            continue
        if candidate["anchor_fragment_id"] in used_anchors:
            continue
        used_anchors.add(candidate["anchor_fragment_id"])
        fragment = fragments[candidate["anchor_fragment_id"]]
        text = transcript.turns[fragment["turn"]].text[
            fragment["char_start"]:fragment["char_end"]
        ]
        rows.append({
            "source_fragment_ids": [candidate["anchor_fragment_id"]],
            "label": candidate["cue_type"].upper(),
            "claim": text,
        })
    if not rows:
        return transcript_only("control", "no-deterministic-candidates", {"manifest_sha256": manifest["manifest_sha256"]})
    identity = {
        "requested": "deterministic-candidate-control/1",
        "name": "deterministic-candidate-control/1",
        "digest": _sha256(_canonical_json(manifest)),
    }
    raw = _canonical_json({"items": rows})
    try:
        note = _note2_candidate(transcript, rows, model_identity=identity, arm="control")
    except Exception as exc:  # A control acceptance must be equally fail-closed.
        return transcript_only("control", "note2-validation-failed", {"error": type(exc).__name__})
    return AdmissionResult(
        arm="control",
        outcome="accepted-research-candidate",
        code=None,
        note=note,
        receipt={"schema": ADMISSION_SCHEMA, "arm": "control", "manifest_sha256": manifest["manifest_sha256"], "records": len(rows)},
    )


def run_model_arm(
    transcript: Transcript,
    provider: ModelProvider,
    *,
    expected_model_tree_sha256: str,
) -> AdmissionResult:
    """Run a supplied local provider and fail closed to canonical transcript-only."""
    manifest = generate_manifest(transcript, STRATEGY_CUE)
    request = model_request(transcript, manifest)
    started = time.monotonic()
    try:
        raw, observed = provider(request)
        runtime = _runtime_receipt(observed, expected_model_tree_sha256)
        rows = _decode_response(raw, manifest, transcript)
        if not rows:
            raise AdmissionRefused("no-model-candidates")
        identity = {
            "requested": MLX_RUNTIME["model"]["repository"] + "@" + MLX_RUNTIME["model"]["revision"],
            "name": MLX_RUNTIME["model"]["repository"],
            "digest": expected_model_tree_sha256,
        }
        note = _note2_candidate(transcript, rows, model_identity=identity, arm="mlx")
    except TimeoutError:
        return transcript_only("mlx", "timeout", {"manifest_sha256": manifest["manifest_sha256"]})
    except AdmissionRefused as exc:
        return transcript_only("mlx", exc.code, {"manifest_sha256": manifest["manifest_sha256"]})
    except Exception as exc:
        return transcript_only("mlx", "note2-validation-failed", {"error": type(exc).__name__, "manifest_sha256": manifest["manifest_sha256"]})
    return AdmissionResult(
        arm="mlx",
        outcome="accepted-research-candidate",
        code=None,
        note=note,
        receipt={
            "schema": ADMISSION_SCHEMA,
            "arm": "mlx",
            "manifest_sha256": manifest["manifest_sha256"],
            "runtime": runtime,
            "elapsed_s": round(time.monotonic() - started, 6),
            "records": len(rows),
        },
    )


def local_mlx_provider(model_directory: Path) -> ModelProvider:
    """Create an optional private MLX-LM provider; no download or HTTP service."""
    if not model_directory.is_dir():
        raise ValueError("model directory does not exist")

    def provider(request: dict) -> tuple[str, dict]:
        try:
            package = importlib.metadata.version("mlx-lm")
            from mlx_lm import generate, load
        except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
            raise AdmissionRefused("runtime-package-mismatch") from exc
        if f"mlx-lm=={package}" != MLX_RUNTIME["package"]:
            raise AdmissionRefused("runtime-package-mismatch")
        model, tokenizer = load(str(model_directory))
        messages = [{"role": "user", "content": _canonical_json(request)}]
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        raw = generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=MLX_RUNTIME["decoding"]["max_tokens"],
            verbose=False,
        )
        return raw, {
            "package": MLX_RUNTIME["package"],
            "model_tree_sha256": tree_sha256(model_directory),
        }

    return provider


def tree_sha256(root: Path) -> str:
    """Hash a local model tree deterministically after an explicit download."""
    if not root.is_dir():
        raise ValueError("model tree is missing")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def synthetic_transcript() -> Transcript:
    return Transcript(
        source="synthetic MLX admission fixture; not product evidence",
        attribution=NONE,
        turns=[
            Turn("We decided to use the compact battery."),
            Turn("I will send the test plan on Tuesday."),
            Turn("Could the supplier meet the revised date?"),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("only --self-test is available; this harness never opens product data")
    control = run_control_arm(synthetic_transcript())
    if control.outcome != "accepted-research-candidate":
        raise SystemExit(f"control arm failed: {control.code}")
    print(_canonical_json(control.receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
