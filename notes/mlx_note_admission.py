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
import platform
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
HARNESS_BASE_REVISION = "bf95c063000eb4e6829c13f1383f188ee9445774"

# This is a research pin, not a release manifest.  The revision pins the MLX
# conversion before download.  The measured local model-tree digest binds the
# exact downloaded inventory; it remains a rejected research artifact.
MLX_RUNTIME = {
    "schema": "mlx-note-runtime/1",
    "role": "research-only",
    "python": "3.14.6",
    "package": "mlx-lm==0.30.4",
    "package_license": "MIT",
    "runtime_identity": {
        "python": "3.14.6",
        "implementation": "CPython",
        "mlx": "0.32.0",
        "transformers": "5.0.0rc1",
        # `METADATA` only. `RECORD` was pinned here until 2026-08-07 and is
        # dropped rather than repaired: it is written by the installer, not
        # shipped by the wheel, so it varies with the installer and with
        # byte-compilation. Measured across three environments on one machine
        # with matching Python and matching package versions, `METADATA` matched
        # 9 of 9 and `RECORD` 1 of 9. See MLX_NOTE_ADMISSION.md, "the registered
        # runtime cannot be rebuilt".
        "package_metadata_sha256": {
            "mlx-lm": {
                "metadata": "7a0f3dc672bd6feae79e225f3b0f5947b04e4e7fc36b615462f1fff876a96f8b",
            },
            "mlx": {
                "metadata": "d41601d7dc5acdd43978f4afedacae9cf825b872cd82ff4012ee19a9eb1d19f8",
            },
            "transformers": {
                "metadata": "a2af7da550d233d50ead4db003f71522a5084fab6124564892ba5cde4996f7b0",
            },
        },
    },
    "model": {
        "repository": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
        "revision": "8b403126fc14f14cfc99bb4cfa72ecbc129ea677",
        "license": "Apache-2.0",
        "base_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "expected_download_bytes": 880172064,
        "expected_model_safetensors_sha256": "0979f33d1bc58afcf696d13f57977644e7b11a6f0eec3e631d8e9463d18c0717",
        "expected_tree_sha256": "3aaeeac4e5bffd4308187dac1b34d5145bc697f589255ff57d04cc53381ddb95",
        "status": "corrective-probe-rejected-not-admitted",
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
            raise AdmissionRefused("response-contract")
        return tuple(items)

    if not isinstance(raw, str) or not raw.strip():
        raise AdmissionRefused("response-json-syntax")
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise AdmissionRefused("response-json-syntax") from exc


def _object(value: object, names: tuple[str, ...]) -> dict:
    if not isinstance(value, tuple) or tuple(name for name, _ in value) != names:
        raise AdmissionRefused("response-contract")
    return dict(value)


# Terms whose disappearance between the cited slice and the claim reverses the
# meaning rather than shortening it. Registered 2026-08-07 as intervention four,
# after the semantic-support sheet found `negation-proposal` claiming "merge the
# red branch" from evidence reading "I propose that we do not merge the red
# branch" — an inversion no gate refused, because the only thing failing that
# fixture was the unrelated identifier truncation.
#
# This is the rule's one owner. `read_semantic_support.py` imports it rather than
# keeping a second copy, because two copies of a list like this is the drift the
# amendment discipline exists to prevent.
POLARITY_TERMS = ("not", "no", "never", "cannot", "can't", "don't", "doesn't", "without")


def polarity_words(text: str) -> set[str]:
    return {
        "".join(character for character in token if character.isalnum() or character == "'")
        .lower()
        for token in text.split()
    }


def dropped_polarity_terms(cited: str, claim: str) -> list[str]:
    """Polarity terms present in the evidence and absent from the claim.

    A word-presence test, and deliberately no more. It cannot see a paraphrase
    that carries the polarity by other words — "we are keeping the red branch"
    for "do not merge" — and would refuse one wrongly. If that appears, this gate
    is too crude and must be replaced; the finding it was built for stands either
    way, because the harness needs some polarity check and had none.
    """
    in_evidence = polarity_words(cited)
    in_claim = polarity_words(claim)
    return [term for term in POLARITY_TERMS if term in in_evidence and term not in in_claim]


def response_contract(manifest: dict) -> dict:
    """Exact strict root, item ordering, and every rule ``_decode_response`` enforces.

    Preregistered amendment 2026-08-06. Before it, this advertised `min_items` and
    `max_items` for `source_fragment_ids` and nothing else, while the parser
    enforced seven rules — five stated nowhere and two only in `SYSTEM_PROMPT`
    prose. A candidate refused for breaking a rule it was never given is not
    measured, whatever the verdict, so the rules are written down here.

    **No rule is added or relaxed.** Every entry below already had a matching
    refusal in `_decode_response`; keep them in step, because a rule advertised
    and not enforced is the same defect facing the other way.
    """
    return {
        "schema": MODEL_RESPONSE_SCHEMA,
        "root": {
            "type": "object",
            "ordered_fields": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    # One item per candidate at most, and items follow the order the
                    # request offers its candidates in.
                    "unique_by": ["candidate_id"],
                    "order": "ascending by the position of candidate_id in candidates",
                    # A source fragment may be the first, citing entry of one item only.
                    "unique_by_first_source_fragment_id": True,
                    "item": {
                        "type": "object",
                        "ordered_fields": [
                            "candidate_id", "source_fragment_ids", "citation", "label", "claim",
                        ],
                        "properties": {
                            "candidate_id": {"type": "string", "enum": [row["candidate_id"] for row in _admission_candidates(manifest)]},
                            "source_fragment_ids": {
                                "type": "array",
                                "min_items": 1,
                                "max_items": 3,
                                "unique_items": True,
                                "members_of": "the source_fragment_id values the named candidate offers",
                                "order": "ascending by the position the named candidate offers them in",
                                # Preregistered intervention two, 2026-08-06. The
                                # enumerated `candidate_id` is reproduced 10/10 and this
                                # field 1/10; the exposure measurement says the difference
                                # is that one has a complete instance beside the generation
                                # point and the other does not. Enumerating removes the
                                # transcription task rather than explaining it — recorded
                                # in MLX_NOTE_ADMISSION.md, which registered the predicted
                                # shift before this line existed.
                                "item": {
                                    "type": "string",
                                    "enum": [
                                        fragment["source_fragment_id"]
                                        for row in _admission_candidates(manifest)
                                        for fragment in [{"source_fragment_id": row["anchor_fragment_id"]}]
                                    ],
                                },
                            },
                            "citation": {
                                "type": "string",
                                # Preregistered intervention three, 2026-08-06. This
                                # key was `equals`, and three of ten fixtures emitted
                                # its value verbatim as the citation — the only
                                # value-shaped key in this contract whose value is
                                # prose rather than a literal the model should emit.
                                # `rule` describes instead of asserting equality. The
                                # prose is unchanged; the key name is the variable.
                                "rule": "the exact text of the fragment named first in source_fragment_ids",
                            },
                            "label": {"type": "string", "enum": ["DECISION", "ACTION", "PROPOSAL", "QUESTION"]},
                            "claim": {
                                "type": "string",
                                "min_length": 1,
                                "max_length": 160,
                                "no_control_characters": True,
                                # Registered 2026-08-07. A polarity term in the
                                # canonical cited slice must appear in the claim.
                                "must_not_drop_polarity_terms": list(POLARITY_TERMS),
                            },
                        },
                    },
                },
            },
        },
        "empty_response": {"items": []},
    }


def _admission_candidates(manifest: dict) -> list[dict]:
    """Bound the first experiment to one exact anchor per source fragment."""
    selected = []
    anchors: set[str] = set()
    for row in manifest["candidates"]:
        if row["cue_type"] not in {"decision", "action", "proposal", "question"}:
            continue
        anchor = row["anchor_fragment_id"]
        if anchor in anchors:
            continue
        anchors.add(anchor)
        selected.append(row)
    return selected


def model_request(transcript: Transcript, manifest: dict) -> dict:
    """Build a source-ID-only request; no product artifact leaves this function."""
    validate_manifest(manifest, transcript)
    fragments = {
        row["source_fragment_id"]: row
        for row in build_fragment_map(transcript)["fragments"]
    }
    candidates = []
    for row in _admission_candidates(manifest):
        fragment_id = row["anchor_fragment_id"]
        fragment = fragments[fragment_id]
        candidates.append({
            "candidate_id": row["candidate_id"],
            "cue_type": row["cue_type"],
            "source_fragments": [{
                "source_fragment_id": fragment_id,
                "text": transcript.turns[fragment["turn"]].text[
                    fragment["char_start"]:fragment["char_end"]
                ],
            }],
        })
    return {
        "schema": "mlx-note-request/1",
        "system": SYSTEM_PROMPT,
        "response_contract": response_contract(manifest),
        "candidates": candidates,
    }


def _decode_response(raw: str, request: dict, transcript: Transcript) -> list[dict]:
    root = _object(_strict_json(raw), ("items",))
    rows = root["items"]
    if not isinstance(rows, list):
        raise AdmissionRefused("response-contract")
    candidate_rows = request["candidates"]
    candidates = {row["candidate_id"]: row for row in candidate_rows}
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
            raise AdmissionRefused("citation-locator")
        if candidate_id in seen:
            raise AdmissionRefused("response-contract")
        seen.add(candidate_id)
        candidate_position = candidate_rows.index(candidates[candidate_id])
        if candidate_position <= last_candidate_position:
            raise AdmissionRefused("response-contract")
        last_candidate_position = candidate_position
        source_ids = row["source_fragment_ids"]
        if (
            not isinstance(source_ids, list)
            or not 1 <= len(source_ids) <= 3
            or any(not isinstance(value, str) for value in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            raise AdmissionRefused("response-contract")
        allowed = [
            fragment["source_fragment_id"]
            for fragment in candidates[candidate_id]["source_fragments"]
        ]
        if any(value not in allowed or value not in fragments for value in source_ids):
            raise AdmissionRefused("citation-locator")
        positions = [allowed.index(value) for value in source_ids]
        if positions != sorted(positions):
            raise AdmissionRefused("citation-locator")
        citation = row["citation"]
        if not isinstance(citation, str):
            raise AdmissionRefused("response-contract")
        primary = fragments[source_ids[0]]
        if source_ids[0] in used_primary_fragments:
            raise AdmissionRefused("citation-locator")
        used_primary_fragments.add(source_ids[0])
        canonical_citation = transcript.turns[primary["turn"]].text[
            primary["char_start"]:primary["char_end"]
        ]
        if citation != canonical_citation:
            raise AdmissionRefused("citation-locator")
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
            raise AdmissionRefused("response-contract")
        # A claim that drops its evidence's polarity asserts the opposite of the
        # words it cites. Checked against the canonical slice rather than the
        # model's echoed citation, because the echo was already required to match
        # it and the canonical text is the one the transcript actually holds.
        if dropped_polarity_terms(canonical_citation, claim):
            raise AdmissionRefused("claim-polarity")
        selected.append({
            "source_fragment_ids": source_ids,
            "label": label,
            "claim": claim.strip(),
        })
    return selected


def _harness_identity() -> dict:
    return {
        "base_revision": HARNESS_BASE_REVISION,
        "source_sha256": _sha256(Path(__file__).read_bytes()),
    }


def _refusal_category(code: str) -> str:
    if code == "response-json-syntax":
        return "json-syntax"
    if code == "response-contract":
        return "root-schema-field-order-or-type"
    if code == "citation-locator":
        return "citation-source-or-locator"
    if code == "response-length-truncation":
        return "length-or-truncation"
    if code == "claim-polarity":
        return "claim-contradicts-cited-evidence"
    return "other-refusal"


def _runtime_receipt(observed: dict, expected_request_sha256: str) -> dict:
    required = {
        "model_tree_sha256", "runtime_identity", "request_sha256",
        "rendered_template_sha256", "generation",
        # Which decoder produced the response. Closed-set, like the rest: a
        # receipt that cannot say whether the sampler was masked cannot be
        # compared with one from the other arm, and this experiment exists
        # entirely to compare the two.
        "decoder",
    }
    if not isinstance(observed, dict) or set(observed) != required:
        raise AdmissionRefused("model-digest-mismatch")
    if not isinstance(observed["decoder"], str) or not observed["decoder"]:
        raise AdmissionRefused("model-digest-mismatch")
    if observed["runtime_identity"] != MLX_RUNTIME["runtime_identity"]:
        raise AdmissionRefused("runtime-package-mismatch")
    if observed["model_tree_sha256"] != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise AdmissionRefused("model-digest-mismatch")
    if observed["request_sha256"] != expected_request_sha256:
        raise AdmissionRefused("response-contract")
    generation = observed["generation"]
    if not isinstance(generation, dict) or set(generation) != {
        "call_elapsed_s", "prompt_tokens", "generated_tokens", "finish_reason",
    }:
        raise AdmissionRefused("response-contract")
    return {
        "registered_runtime": deepcopy(MLX_RUNTIME),
        "observed": dict(observed),
        "harness": _harness_identity(),
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
        receipt={
            "schema": ADMISSION_SCHEMA,
            "arm": arm,
            "outcome": "transcript-only",
            "code": code,
            "refusal_category": _refusal_category(code),
            **receipt,
        },
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
) -> AdmissionResult:
    """Run a supplied local provider and fail closed to canonical transcript-only."""
    manifest = generate_manifest(transcript, STRATEGY_CUE)
    request = model_request(transcript, manifest)
    started = time.monotonic()
    response_receipt: dict[str, object] = {}
    # Read before the call, so a provider that throws mid-generation still names
    # its sampler. `MaskRefused` arrives on the path below, and a mask refusal is
    # the one failure whose attribution is not in question — which made a receipt
    # that could not identify the mask the least useful one in the set.
    decoder = getattr(provider, "decoder_identity", "unavailable")
    try:
        raw, observed = provider(request)
    except TimeoutError:
        return transcript_only("mlx", "timeout", {
            "manifest_sha256": manifest["manifest_sha256"],
            "elapsed_s": round(time.monotonic() - started, 6),
            "decoder": decoder,
        })
    except Exception as exc:
        return transcript_only("mlx", "provider-generation-failure", {
            "error_type": type(exc).__name__,
            "manifest_sha256": manifest["manifest_sha256"],
            "elapsed_s": round(time.monotonic() - started, 6),
            "decoder": decoder,
        })
    try:
        response_receipt = {
            "response_sha256": _sha256(raw),
            "response_bytes": len(raw.encode("utf-8")),
            "generation": observed.get("generation") if isinstance(observed, dict) else None,
        }
        expected_request_sha256 = _sha256(_canonical_json({
            "system": request["system"],
            "user": {key: value for key, value in request.items() if key != "system"},
        }))
        runtime = _runtime_receipt(observed, expected_request_sha256)
        response_receipt["identity"] = {
            "model_tree_sha256": observed["model_tree_sha256"],
            "request_sha256": observed["request_sha256"],
            "rendered_template_sha256": observed["rendered_template_sha256"],
            "runtime_identity": observed["runtime_identity"],
            # `_runtime_receipt` makes this mandatory and then it was dropped
            # here, so no receipt ever carried it. For the constrained arm it is
            # the sha256 of `structured_decoding.py` — the only thing pinning
            # *which* mask ran, and the mask has already been revised once. The
            # top-level "decoding" key is the argparse flag, not an observation.
            "decoder": observed["decoder"],
            "harness": runtime["harness"],
        }
        if observed["generation"].get("finish_reason") == "length":
            raise AdmissionRefused("response-length-truncation")
        rows = _decode_response(raw, request, transcript)
        if not rows:
            raise AdmissionRefused("no-model-candidates")
        identity = {
            "requested": MLX_RUNTIME["model"]["repository"] + "@" + MLX_RUNTIME["model"]["revision"],
            "name": MLX_RUNTIME["model"]["repository"],
            "digest": MLX_RUNTIME["model"]["expected_tree_sha256"],
        }
        note = _note2_candidate(transcript, rows, model_identity=identity, arm="mlx")
    except TimeoutError:
        return transcript_only("mlx", "timeout", {
            "manifest_sha256": manifest["manifest_sha256"],
            "elapsed_s": round(time.monotonic() - started, 6),
            **response_receipt,
        })
    except AdmissionRefused as exc:
        return transcript_only("mlx", exc.code, {
            "manifest_sha256": manifest["manifest_sha256"],
            "elapsed_s": round(time.monotonic() - started, 6),
            **response_receipt,
        })
    except Exception as exc:
        return transcript_only("mlx", "note2-validation-failed", {
            "error_type": type(exc).__name__,
            "manifest_sha256": manifest["manifest_sha256"],
            "elapsed_s": round(time.monotonic() - started, 6),
            **response_receipt,
        })
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
            # Every refusal path already carries these. Acceptance did not, so
            # the one outcome worth reproducing was the only one whose response
            # digest, byte length and streaming metadata went unrecorded — and
            # the registered repeatability gate is stated in terms of "raw
            # response SHA-256 ... identical across the three cold runs", which
            # an accepted run could not evidence at all.
            **response_receipt,
        },
    )


def local_mlx_provider(
    model_directory: Path, *, constrained: bool = False
) -> ModelProvider:
    """Create an optional private MLX-LM provider; no download or HTTP service.

    `constrained` enables the structure-only mask registered in
    `MLX_NOTE_ADMISSION.md` § "Preregistered amendment — 2026-08-05". It is
    opt-in and off by default so the unconstrained arm stays exactly what the
    2026-08-02 corrective probe ran; the two are different experiments and a
    receipt has to say which one produced it.
    """
    if not model_directory.is_dir():
        raise ValueError("model directory does not exist")

    preflight_tree_sha256 = tree_sha256(model_directory)
    if preflight_tree_sha256 != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise AdmissionRefused("model-digest-mismatch")
    try:
        package = importlib.metadata.version("mlx-lm")
        import mlx
        import mlx.core as mx
        from mlx_lm import load, stream_generate
        from mlx_lm.sample_utils import make_sampler
    except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
        raise AdmissionRefused("runtime-package-mismatch") from exc

    def package_sha256(name: str, filename: str) -> str:
        """Hash one file the wheel itself ships, so the digest is the wheel's.

        Only `METADATA` is pinned. It travels inside the wheel, so every
        installer writes the same bytes and the digest identifies the artifact
        rather than the act of installing it.

        `RECORD` was pinned alongside it until 2026-08-07, and is gone rather
        than narrowed. It is written by the installer at install time, and it
        varies with things that say nothing about package identity: the
        installer (uv reproduced none of three, pip one), byte-compilation
        (`mlx`'s carries 31 `.pyc` rows generated on install), and at least one
        further cause never identified. Three environments on one machine with
        matching Python and matching package versions produced `METADATA` 9 of 9
        and `RECORD` 1 of 9, which stranded the whole 12-fixture matrix on the
        one environment that made it.

        Two earlier narrowings of `RECORD` were each believed to have fixed it.
        The 2026-08-02 pin hashed it whole and was reproducible only inside one
        disposable directory. The 2026-08-05 fix excluded the `../`-relative
        console-script rows, whose shebangs embed an absolute interpreter path,
        and was "verified across those same three paths" — a check that varied
        the directory while holding the installer and the install method fixed,
        so it could not have caught either. **A check that varies one dimension
        does not establish independence from the others.** That is the reason
        this is a removal and not a third narrowing.

        `filename` is still a parameter because the pin should grow to carry the
        wheel's own distribution hash once a lockfile supplies one; that value is
        not derivable from an installed environment, which is why `METADATA` is
        the strongest wheel-shipped identity available here.
        """
        distribution = importlib.metadata.distribution(name)
        target = next(
            (item for item in distribution.files or () if item.name == filename),
            None,
        )
        if target is None:
            raise AdmissionRefused("runtime-package-mismatch")
        return _sha256(distribution.locate_file(target).read_bytes())

    runtime_identity = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "mlx": mlx.__version__ if hasattr(mlx, "__version__") else importlib.metadata.version("mlx"),
        "transformers": importlib.metadata.version("transformers"),
        "package_metadata_sha256": {
            name: {
                "metadata": package_sha256(name, "METADATA"),
            }
            for name in ("mlx-lm", "mlx", "transformers")
        },
    }
    if f"mlx-lm=={package}" != MLX_RUNTIME["package"] or runtime_identity != MLX_RUNTIME["runtime_identity"]:
        raise AdmissionRefused("runtime-package-mismatch")

    loaded_started = time.monotonic()
    model, tokenizer = load(str(model_directory))
    load_elapsed_s = round(time.monotonic() - loaded_started, 6)

    logits_processors = None
    decoder_identity = "unconstrained"
    if constrained:
        from structured_decoding import make_contract_logits_processor

        # Built once, outside every call's timing, because decoding the whole
        # vocabulary is setup rather than generation and folding it into the
        # per-call number is the mistake the 2026-08-02 measurement made with
        # tree hashing.
        logits_processors = [make_contract_logits_processor(tokenizer)]
        decoder_identity = _sha256(
            Path(__file__).with_name("structured_decoding.py").read_bytes()
        )

    def provider(request: dict) -> tuple[str, dict]:
        mx.random.seed(MLX_RUNTIME["decoding"]["seed"])
        # The selected model's documented chat template receives the instruction separately;
        # keep it out of the canonical user payload so an instruction-like
        # string inside transcript material cannot alter its role.
        user_request = {key: value for key, value in request.items() if key != "system"}
        messages = [
            {"role": "system", "content": request["system"]},
            {"role": "user", "content": _canonical_json(user_request)},
        ]
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        rendered_template_sha256 = _sha256(_canonical_json(prompt))
        started = time.monotonic()
        chunks: list[str] = []
        prompt_tokens: object = "unavailable"
        generated_tokens: object = "unavailable"
        finish_reason: object = None
        finish_reason_available = False
        for response in stream_generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=MLX_RUNTIME["decoding"]["max_tokens"],
            max_kv_size=MLX_RUNTIME["decoding"]["max_kv_size"],
            sampler=make_sampler(temp=MLX_RUNTIME["decoding"]["temperature"]),
            **({"logits_processors": logits_processors} if logits_processors else {}),
        ):
            chunks.append(response.text)
            response_prompt_tokens = getattr(response, "prompt_tokens", None)
            if isinstance(response_prompt_tokens, int):
                prompt_tokens = response_prompt_tokens
            response_generated_tokens = getattr(response, "generation_tokens", None)
            if isinstance(response_generated_tokens, int):
                generated_tokens = response_generated_tokens
            response_finish_reason = getattr(response, "finish_reason", None)
            if response_finish_reason is not None:
                finish_reason = response_finish_reason
                finish_reason_available = True
        raw = "".join(chunks)
        return raw, {
            "model_tree_sha256": preflight_tree_sha256,
            "runtime_identity": runtime_identity,
            # Which experiment this is. A receipt that does not say whether the
            # decoder was masked cannot be compared with one that was.
            "decoder": decoder_identity,
            "request_sha256": _sha256(_canonical_json({"system": request["system"], "user": user_request})),
            "rendered_template_sha256": rendered_template_sha256,
            "generation": {
                "call_elapsed_s": round(time.monotonic() - started, 6),
                "prompt_tokens": prompt_tokens,
                "generated_tokens": generated_tokens,
                "finish_reason": finish_reason if finish_reason_available else "unavailable",
            },
        }

    setattr(provider, "load_receipt", {
        "model_load_elapsed_s": load_elapsed_s,
        "preflight_model_tree_sha256": preflight_tree_sha256,
        "runtime_identity": runtime_identity,
    })
    # Exposed separately from any call because the provider can throw before it
    # returns an `observed` dict at all: `MaskRefused` is raised inside the
    # logits processor, inside `stream_generate`, inside this closure. That
    # failure is by construction the *mask's* and not the model's, and it was
    # the one receipt with no way to name which mask produced it. The value is
    # known at construction, so it survives a throw.
    setattr(provider, "decoder_identity", decoder_identity)
    return provider


def tree_sha256(root: Path) -> str:
    """Hash a local model tree deterministically after an explicit download."""
    if not root.is_dir():
        raise ValueError("model tree is missing")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative_path = path.relative_to(root)
        # Hugging Face keeps mutable locks and transfer metadata below .cache.
        # They are not model bytes and must not change the identity we measure.
        if ".cache" in relative_path.parts:
            continue
        relative = relative_path.as_posix().encode("utf-8")
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


def synthetic_measurement_fixtures() -> tuple[tuple[str, Transcript, str, tuple[str, ...]], ...]:
    """Public/synthetic-only fixture plan for the registered research candidate.

    The tuple is (identifier, transcript, expected outcome, required citation
    terms).  Receipts retain only identifiers, hashes, and boolean checks.
    """
    return (
        ("ordinary-decision", Transcript("synthetic", NONE, [Turn("Dana decided that Battery 7 ships on Tuesday.")]), "accepted-research-candidate", ("Dana", "7", "Tuesday")),
        ("ordinary-action", Transcript("synthetic", NONE, [Turn("Marco will send invoice 2048 by June 14.")]), "accepted-research-candidate", ("Marco", "2048", "June 14")),
        ("ordinary-proposal", Transcript("synthetic", NONE, [Turn("Priya proposed moving the renewal to Q4.")]), "accepted-research-candidate", ("Priya", "Q4")),
        ("ordinary-question", Transcript("synthetic", NONE, [Turn("Could Aisha confirm whether the North room is available?")]), "accepted-research-candidate", ("Aisha", "North")),
        ("locator-canonical-order", Transcript("synthetic", NONE, [Turn("We decided that the Harbor release uses build 17."), Turn("I will notify Omar after the release.")]), "accepted-research-candidate", ("Harbor", "17")),
        ("locator-second-turn", Transcript("synthetic", NONE, [Turn("The agenda is unchanged."), Turn("Leah decided that the South launch moves to Friday.")]), "accepted-research-candidate", ("Leah", "South", "Friday")),
        ("name-number-decision", Transcript("synthetic", NONE, [Turn("Nora decided that Case 481 is not ready for closure.")]), "accepted-research-candidate", ("Nora", "481", "not")),
        ("name-number-action", Transcript("synthetic", NONE, [Turn("Dev will send version 3.14 to Mei on July 9.")]), "accepted-research-candidate", ("Dev", "3.14", "Mei", "July 9")),
        ("negation-decision", Transcript("synthetic", NONE, [Turn("We decided not to cancel Project Atlas.")]), "accepted-research-candidate", ("not", "Atlas")),
        ("negation-proposal", Transcript("synthetic", NONE, [Turn("I propose that we do not merge the red branch.")]), "accepted-research-candidate", ("not", "red branch")),
        ("abstain-chitchat", Transcript("synthetic", NONE, [Turn("The weather was pleasant and the coffee was warm.")]), "transcript-only", ()),
        # Both abstention fixtures above build the byte-identical request, and so
        # would any other zero-candidate transcript: only candidates reach the
        # model. They are one experiment run twice, kept as a cross-fixture
        # determinism control rather than as two units of coverage.
        ("abstain-plain", Transcript("synthetic", NONE, [Turn("The window is open.")]), "transcript-only", ()),
        # Added 2026-08-07, intervention seven. A hypothetical: it carries a
        # decision cue and states no decision. The deterministic arm accepts it,
        # measured — it is word-presence and cannot see a counterfactual. What
        # the model does is recorded rather than graded, because grading it would
        # score "behaved better than its reference" as a failure.
        ("hypothetical-decision", Transcript("synthetic", NONE, [Turn("If we decided to ship Tuesday, we would need Dana.")]), "arms-recorded", ("Dana", "Tuesday")),
    )


def synthetic_corrective_probe_fixtures() -> tuple[tuple[str, Transcript, str, tuple[str, ...]], ...]:
    fixtures = {fixture[0]: fixture for fixture in synthetic_measurement_fixtures()}
    return (fixtures["ordinary-decision"], fixtures["abstain-chitchat"])


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
