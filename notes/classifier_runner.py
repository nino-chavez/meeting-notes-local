#!/usr/bin/env python3
"""Run and replay the registered candidate-first classifier experiment.

This module is the model-runner half of ``candidate_first.py``. It does not
generate claims or note artifacts. A successful result contains replayable
receipts for the semantic fixtures, two sabotaged controls, and every registered
corpus batch. A failed or incomplete run raises before any result is written.

The event ledger and its lock are inputs, never generated here. The runner
also requires the exact DRAFT review-reference and validated review-decisions
files. It re-runs ``candidate_exposure.py`` validation and promotion, then
requires the promoted ledger to match the supplied ledger exactly. The lock file
remains ``pending-operator-approval``; the separately supplied SHA-256 is the
trust-boundary binding. It proves byte identity, while the operator's explicit
out-of-band approval supplies authority.

Normal execution uses Ollama through the existing transport helpers:

    python notes/classifier_runner.py notes/corpus/ES2004c.json \
      --review-reference /private/path/candidate-exposure-reference.json \
      --review-decisions /private/path/candidate-exposure-review-decisions.validated.json \
      --event-ledger /private/path/events.json \
      --ledger-lock /private/path/candidate-exposure-lock.pending.json \
      --approved-lock-sha256 LOCK_FILE_SHA256 \
      --out /private/path/classifier-result.json

Replay does not contact Ollama:

    python notes/classifier_runner.py notes/corpus/ES2004c.json \
      --review-reference /private/path/candidate-exposure-reference.json \
      --review-decisions /private/path/candidate-exposure-review-decisions.validated.json \
      --event-ledger /private/path/events.json \
      --ledger-lock /private/path/candidate-exposure-lock.pending.json \
      --approved-lock-sha256 LOCK_FILE_SHA256 \
      --replay /private/path/classifier-result.json

The self-test uses only injected in-memory fakes:

    python notes/classifier_runner.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from candidate_exposure import (
    LEDGER_LOCK_SCHEMA,
    PENDING_LOCK_STATE,
    RUNNER_LEDGER_SCHEMA,
    build_runner_ledger,
    qmsum_coordinates,
    validate_reference,
    validate_review_decisions,
)
from candidate_exposure import SCHEMA as REVIEW_REFERENCE_SCHEMA
from candidate_first import (
    CLASSIFIER_FIXTURES,
    batch_locators,
    CLASSIFIER_SYSTEM,
    REGISTERED_RUN,
    SABOTAGED_ALWAYS_ABSTAIN_SYSTEM,
    SABOTAGED_ALWAYS_KEEP_SYSTEM,
    STRATEGY_BROAD,
    candidate_batches,
    classification_num_predict,
    classification_request,
    classifier_fixture_request,
    classifier_fixture_sha256,
    classifier_system_sha256,
    decode_classification,
    decode_fixture_classification,
    generate_manifest,
    qmsum_search_spans,
    qmsum_span_report,
    registered_run_sha256,
    validate_distinct_input_output,
    validate_registered_inputs,
    validate_registered_model_identity,
)
from candidate_first import validate_output_target as validate_private_output_target
from candidate_first import write_private_manifest as write_private_json
from summarize import (
    TRANSPORT_COMPLETION_PROOF,
    StructuredOutputError,
    check_one_context,
)
from transcript import Transcript, Turn, load

CALL_RECEIPT_SCHEMA = "candidate-classifier-call-receipt/1"
RESULT_SCHEMA = "candidate-classifier-result/1"
LEDGER_SCHEMA = RUNNER_LEDGER_SCHEMA
DETERMINISTIC_CONTROLS_SCHEMA = "candidate-classifier-deterministic-controls/1"

REGISTERED_SYSTEM = "registered-classifier"
SABOTAGED_KEEP_SYSTEM = "sabotaged-always-keep"
SABOTAGED_ABSTAIN_SYSTEM = "sabotaged-always-abstain"
SYSTEMS = {
    REGISTERED_SYSTEM: CLASSIFIER_SYSTEM,
    SABOTAGED_KEEP_SYSTEM: SABOTAGED_ALWAYS_KEEP_SYSTEM,
    SABOTAGED_ABSTAIN_SYSTEM: SABOTAGED_ALWAYS_ABSTAIN_SYSTEM,
}

FIXTURE_CALL = "semantic-fixtures"
SABOTAGED_KEEP_CALL = "model-sabotage-always-keep"
SABOTAGED_ABSTAIN_CALL = "model-sabotage-always-abstain"
CORPUS_CALL = "corpus-batch"

EXPECTED_CORPUS_DECISIONS = REGISTERED_RUN["gates"]["candidate_coverage"]
REGISTERED_BATCH_SIZE = REGISTERED_RUN["classifier"]["batch_size"]
EXPECTED_CORPUS_BATCHES = (
    EXPECTED_CORPUS_DECISIONS + REGISTERED_BATCH_SIZE - 1
) // REGISTERED_BATCH_SIZE
EXPECTED_FIXTURES = REGISTERED_RUN["gates"]["fixture_agreement"]
KEEP_LIMIT = REGISTERED_RUN["gates"]["maximum_keep"]
ELAPSED_LIMIT_SECONDS = float(REGISTERED_RUN["gates"]["maximum_elapsed_seconds"])
PROMPT_ESTIMATE_CHARS_PER_TOKEN = 3.7

RESPONSE_VALIDATION = (
    "strict replayable JSON covering every offered candidate locator exactly "
    "once; decode canonicalizes order and counts displacement"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ClassifierTransport(Protocol):
    """Minimal injectable transport boundary used by the registered runner."""

    def resolve_model(self, model: str, timeout: float) -> dict:
        """Resolve a mutable model tag to an immutable local identity."""

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        num_ctx: int,
        timeout: float,
        response_format: dict,
        num_predict: int,
    ) -> dict:
        """Return one non-streaming Ollama-compatible response envelope."""


class OllamaTransport:
    """Thin adapter over the historical Ollama helpers.

    Importing or constructing this adapter performs no network operation.
    """

    def resolve_model(self, model: str, timeout: float) -> dict:
        from summarize import resolve_ollama_model

        return resolve_ollama_model(model, timeout)

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        num_ctx: int,
        timeout: float,
        response_format: dict,
        num_predict: int,
    ) -> dict:
        from summarize import ollama_chat

        return ollama_chat(
            model,
            system,
            user,
            num_ctx,
            timeout,
            response_format,
            num_predict=num_predict,
        )


def _sha256(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _json_sha256(value: object) -> str:
    return _sha256(_json_bytes(value))


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _load_json(path: Path, label: str) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StructuredOutputError(f"cannot read {label}: {exc}") from exc

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        keys = [key for key, _value in pairs]
        if len(keys) != len(set(keys)):
            raise StructuredOutputError(f"{label} has duplicate JSON keys")
        return dict(pairs)

    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StructuredOutputError(f"cannot decode {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise StructuredOutputError(f"{label} must be a JSON object")
    return value, raw


def derive_registered_inputs(corpus_path: Path) -> tuple[Transcript, dict, dict, dict]:
    """Re-derive every registered no-model input from the raw corpus."""
    transcript = load(corpus_path).strip_attribution()
    first_manifest = generate_manifest(transcript, STRATEGY_BROAD)
    second_manifest = generate_manifest(transcript, STRATEGY_BROAD)
    if _json_bytes(first_manifest) != _json_bytes(second_manifest):
        raise StructuredOutputError(
            "registered candidate manifest changed between two local generations"
        )
    registry = qmsum_search_spans(corpus_path, transcript)
    authority = validate_registered_inputs(
        corpus_path,
        transcript,
        first_manifest,
        registry,
    )
    if classifier_system_sha256() != REGISTERED_RUN["classifier"]["system_sha256"]:
        raise StructuredOutputError("registered classifier system prompt changed")
    if classifier_fixture_sha256() != REGISTERED_RUN["classifier"]["fixture_sha256"]:
        raise StructuredOutputError("registered classifier fixtures changed")
    if registered_run_sha256() != (
        "94e8cfecb2404fe5295cde5b18e9ab3accdbc1df32da9f59afe52f2d099a1e10"
    ):
        raise StructuredOutputError("candidate classifier registration changed")
    return transcript, first_manifest, registry, authority


def _validate_ledger_shape(ledger: object, manifest: dict) -> dict:
    draft_keys = {
        "status",
        "human_approval",
        "source",
        "reference_sha256",
    }
    if (
        isinstance(ledger, dict)
        and ledger.get("schema") == REVIEW_REFERENCE_SCHEMA
        and draft_keys.issubset(ledger)
    ):
        raise StructuredOutputError(
            "candidate_exposure DRAFT references are not runner ledgers; "
            "candidate_exposure.build_runner_ledger must explicitly promote "
            "completed review decisions"
        )
    expected_keys = {
        "schema",
        "registration_sha256",
        "transcript_view_sha256",
        "review_reference_sha256",
        "review_decisions_sha256",
        "events",
        "ledger_sha256",
    }
    if not isinstance(ledger, dict) or set(ledger) != expected_keys:
        raise StructuredOutputError("candidate event ledger has the wrong shape")
    base = {key: value for key, value in ledger.items() if key != "ledger_sha256"}
    if (
        ledger["schema"] != LEDGER_SCHEMA
        or ledger["registration_sha256"] != registered_run_sha256()
        or ledger["transcript_view_sha256"] != manifest["transcript_view_sha256"]
        or not _valid_sha256(ledger["review_reference_sha256"])
        or not _valid_sha256(ledger["review_decisions_sha256"])
        or not _valid_sha256(ledger["ledger_sha256"])
        or ledger["ledger_sha256"] != _json_sha256(base)
    ):
        raise StructuredOutputError(
            "candidate event ledger schema, registration, or digest changed"
        )
    events = ledger["events"]
    if not isinstance(events, list) or not events:
        raise StructuredOutputError("candidate event ledger must contain target events")
    fragment_ids = {
        fragment_id
        for candidate in manifest["candidates"]
        for fragment_id in candidate["visible_fragment_ids"]
    }
    event_ids: list[str] = []
    for event_index, event in enumerate(events, 1):
        if not isinstance(event, dict) or set(event) != {
            "event_id",
            "kind",
            "neutral_atomic_proposition_sha256",
            "acceptable_evidence_bundles",
        }:
            raise StructuredOutputError(
                f"candidate event ledger event {event_index} has the wrong shape"
            )
        event_id = event["event_id"]
        bundles = event["acceptable_evidence_bundles"]
        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or event["kind"] not in {"DECISION", "ACTION", "PROPOSAL", "QUESTION"}
            or not _valid_sha256(event["neutral_atomic_proposition_sha256"])
            or not isinstance(bundles, list)
            or not bundles
        ):
            raise StructuredOutputError(f"candidate event ledger event {event_index} is incomplete")
        event_ids.append(event_id)
        for bundle_index, bundle in enumerate(bundles, 1):
            if (
                not isinstance(bundle, list)
                or not 1 <= len(bundle) <= 3
                or any(
                    not isinstance(fragment_id, str) or not fragment_id for fragment_id in bundle
                )
                or len(bundle) != len(set(bundle))
                or any(fragment_id not in fragment_ids for fragment_id in bundle)
            ):
                raise StructuredOutputError(
                    f"candidate event ledger event {event_index} bundle {bundle_index} is invalid"
                )
    if len(event_ids) != len(set(event_ids)):
        raise StructuredOutputError("candidate event ledger has duplicate event IDs")
    return ledger


def validate_promoted_runner_ledger(ledger: object, manifest: dict) -> dict:
    """Schema seam for candidate_exposure.build_runner_ledger output only."""
    return _validate_ledger_shape(ledger, manifest)


def load_operator_locked_ledger(
    ledger_path: Path,
    lock_path: Path,
    manifest: dict,
    approved_lock_sha256: str | None,
) -> tuple[dict, dict, dict]:
    """Bind pending lock bytes to an operator-supplied approval digest.

    The file deliberately remains pending. The caller's real approval process,
    not a field inside the JSON, gives the exact supplied digest authority.
    """
    if not _valid_sha256(approved_lock_sha256):
        raise StructuredOutputError("an exact out-of-band approved lock-file SHA-256 is required")
    ledger, ledger_bytes = _load_json(ledger_path, "candidate event ledger")
    lock, lock_bytes = _load_json(lock_path, "candidate event-ledger lock")
    lock_file_sha256 = _sha256(lock_bytes)
    if lock_file_sha256 != approved_lock_sha256:
        raise StructuredOutputError(
            "candidate event-ledger lock bytes do not match the operator-supplied approved SHA-256"
        )
    validate_promoted_runner_ledger(ledger, manifest)
    if set(lock) != {
        "schema",
        "state",
        "ledger_sha256",
        "review_reference_sha256",
        "review_decisions_sha256",
        "registration_sha256",
        "manifest_sha256",
        "prepared_at",
    }:
        raise StructuredOutputError("candidate event-ledger lock has the wrong shape")
    if (
        lock["schema"] != LEDGER_LOCK_SCHEMA
        or lock["state"] != PENDING_LOCK_STATE
        or lock["ledger_sha256"] != ledger["ledger_sha256"]
        or lock["review_reference_sha256"] != ledger["review_reference_sha256"]
        or lock["review_decisions_sha256"] != ledger["review_decisions_sha256"]
        or lock["registration_sha256"] != registered_run_sha256()
        or lock["manifest_sha256"] != manifest["manifest_sha256"]
        or not isinstance(lock["prepared_at"], str)
        or not lock["prepared_at"].strip()
    ):
        raise StructuredOutputError(
            "candidate event ledger is absent, not pending exact approval, or "
            "bound to different registered inputs"
        )
    binding = {
        "ledger_sha256": ledger["ledger_sha256"],
        "review_reference_sha256": ledger["review_reference_sha256"],
        "review_decisions_sha256": ledger["review_decisions_sha256"],
        "ledger_file_sha256": _sha256(ledger_bytes),
        "lock_file_sha256": lock_file_sha256,
        "operator_supplied_approved_lock_sha256": approved_lock_sha256,
        "state": "operator-locked",
        "lock_file_state": lock["state"],
        "lock_prepared_at": lock["prepared_at"],
        "approval_binding": (
            "effective lock derives from an operator-supplied exact file "
            "digest; the pending file does not self-assert approval"
        ),
    }
    return ledger, lock, binding


def validate_review_artifact_promotion(
    corpus_path: Path,
    reference_path: Path,
    decisions_path: Path,
    transcript: Transcript,
    manifest: dict,
    ledger: dict,
    *,
    enforce_registered: bool = True,
    coordinates: list[dict] | None = None,
) -> dict:
    """Re-run the canonical review validators and require exact promotion.

    Coordinates default to the registered QMSum raw-row derivation. A private
    capture lane supplies its own identity coordinates; every validator
    downstream of that derivation is unchanged.
    """
    reference, reference_bytes = _load_json(
        reference_path,
        "candidate exposure review reference",
    )
    decisions, decisions_bytes = _load_json(
        decisions_path,
        "candidate exposure review decisions",
    )
    if coordinates is None:
        coordinates = qmsum_coordinates(corpus_path, transcript)
    source = reference.get("source")
    if not isinstance(source, dict):
        raise StructuredOutputError("candidate exposure reference source is malformed")
    validated_reference = validate_reference(
        reference,
        transcript,
        manifest,
        coordinates,
        source.get("review_regions"),
        enforce_registered=enforce_registered,
    )
    validated_decisions = validate_review_decisions(
        decisions,
        validated_reference,
    )
    promoted = build_runner_ledger(
        validated_decisions,
        validated_reference,
    )
    validate_promoted_runner_ledger(promoted, manifest)
    if _json_bytes(promoted) != _json_bytes(ledger):
        raise StructuredOutputError(
            "candidate event ledger does not exactly re-derive from the "
            "validated review reference and decisions"
        )
    reference_sha256 = validated_reference["reference_sha256"]
    decisions_sha256 = _json_sha256(validated_decisions)
    if (
        ledger["review_reference_sha256"] != reference_sha256
        or ledger["review_decisions_sha256"] != decisions_sha256
    ):
        raise StructuredOutputError(
            "candidate event ledger semantic review bindings do not re-derive"
        )
    return {
        "schema": "candidate-review-artifact-binding/1",
        "review_reference_raw_file_sha256": _sha256(reference_bytes),
        "review_reference_canonical_file_sha256": _sha256(_json_bytes(validated_reference)),
        "review_reference_sha256": reference_sha256,
        "review_decisions_raw_file_sha256": _sha256(decisions_bytes),
        "review_decisions_canonical_file_sha256": _sha256(_json_bytes(validated_decisions)),
        "review_decisions_sha256": decisions_sha256,
        "promoted_ledger_sha256": promoted["ledger_sha256"],
        "validation": (
            "candidate_exposure reference and review-decision validation plus "
            "exact deterministic runner-ledger promotion"
        ),
    }


def load_locked_review_preflight(
    corpus_path: Path,
    reference_path: Path,
    decisions_path: Path,
    ledger_path: Path,
    lock_path: Path,
    transcript: Transcript,
    manifest: dict,
    approved_lock_sha256: str | None,
    *,
    enforce_registered: bool = True,
    coordinates: list[dict] | None = None,
) -> tuple[dict, dict, dict, dict]:
    """Finish all review and packet gates before model transport is resolved."""
    ledger, lock, ledger_binding = load_operator_locked_ledger(
        ledger_path,
        lock_path,
        manifest,
        approved_lock_sha256,
    )
    review_binding = validate_review_artifact_promotion(
        corpus_path,
        reference_path,
        decisions_path,
        transcript,
        manifest,
        ledger,
        enforce_registered=enforce_registered,
        coordinates=coordinates,
    )
    ledger_binding = {
        **ledger_binding,
        "review_artifacts": review_binding,
    }
    packet_exposure = event_packet_exposure_report(ledger, manifest)
    return ledger, lock, ledger_binding, packet_exposure


def _expected_options(candidate_count: int) -> dict:
    classifier = REGISTERED_RUN["classifier"]
    return {
        "num_ctx": classifier["num_ctx"],
        "temperature": classifier["temperature"],
        "num_predict": classification_num_predict(candidate_count),
    }


def _completion_proof(response: object, num_predict: int) -> dict:
    if not isinstance(response, dict):
        raise StructuredOutputError("classifier transport response is not an object")
    if response.get("done") is not True:
        raise StructuredOutputError("classifier response did not prove completion")
    if response.get("done_reason") == "length":
        raise StructuredOutputError(f"classifier reached its {num_predict}-token output limit")
    if response.get("done_reason") != "stop":
        raise StructuredOutputError("classifier response has no recognized completion reason")
    return dict(TRANSPORT_COMPLETION_PROOF)


def _positive_int(value: object, label: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise StructuredOutputError(f"classifier response has invalid {label}")
    return value


def _context_proof(
    prompt: str,
    prompt_eval_count: object,
    eval_count: object,
    options: dict,
) -> dict:
    counted = _positive_int(prompt_eval_count, "prompt_eval_count")
    generated = _positive_int(eval_count, "eval_count", allow_zero=True)
    num_ctx = options["num_ctx"]
    num_predict = options["num_predict"]
    prompt_check = check_one_context(
        {"prompt_eval_count": counted},
        prompt,
        num_ctx,
    )
    if prompt_check["ok"] is not True:
        raise StructuredOutputError(
            f"classifier prompt was not read in full: {prompt_check['reason']}"
        )
    if generated > num_predict:
        raise StructuredOutputError("classifier eval_count exceeds its registered output bound")
    total = counted + generated
    if total >= num_ctx:
        raise StructuredOutputError(
            "classifier prompt and completion do not fit the registered context"
        )
    return {
        "estimated_prompt_tokens": prompt_check["estimated"],
        "prompt_not_truncated": True,
        "total_tokens": total,
        "num_ctx": num_ctx,
        "total_below_num_ctx": True,
    }


def _response_content(response: dict) -> str:
    message = response.get("message")
    if not isinstance(message, dict) or set(message) not in (
        {"content"},
        {"role", "content"},
    ):
        raise StructuredOutputError("classifier response has a malformed assistant message")
    if "role" in message and message["role"] != "assistant":
        raise StructuredOutputError("classifier response message is not from the assistant")
    raw = message["content"]
    if not isinstance(raw, str):
        raise StructuredOutputError("classifier response content is not text")
    return raw


def _receipt_digest(receipt: dict) -> str:
    return _json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def _active_timeout(
    configured_timeout: int | float,
    deadline: float,
    monotonic: Callable[[], float],
    *,
    ceiling: int | float | None = None,
) -> float:
    """Return an operation timeout bounded by the live outer-run deadline."""
    if (
        isinstance(configured_timeout, bool)
        or not isinstance(configured_timeout, (int, float))
        or not math.isfinite(configured_timeout)
        or configured_timeout <= 0
    ):
        raise StructuredOutputError("classifier transport timeout must be positive and finite")
    remaining = deadline - monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise StructuredOutputError("registered classifier active deadline is exhausted")
    bounded = min(float(configured_timeout), remaining)
    if ceiling is not None:
        bounded = min(bounded, float(ceiling))
    if bounded <= 0:
        raise StructuredOutputError("registered classifier active deadline is exhausted")
    return bounded


def _require_active_deadline(
    deadline: float,
    monotonic: Callable[[], float],
) -> None:
    remaining = deadline - monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise StructuredOutputError("registered classifier active deadline is exhausted")


def _resolve_model_identity(
    transport: ClassifierTransport,
    model: str,
    timeout: int | float,
    deadline: float,
    monotonic: Callable[[], float],
) -> dict:
    operation_timeout = _active_timeout(
        timeout,
        deadline,
        monotonic,
        ceiling=30,
    )
    observed = _validate_identity(transport.resolve_model(model, operation_timeout))
    _require_active_deadline(deadline, monotonic)
    return observed


def _resolve_transport_identity(
    transport: ClassifierTransport,
    identity: dict,
    timeout: int | float,
    deadline: float,
    monotonic: Callable[[], float],
) -> dict:
    observed = _resolve_model_identity(
        transport,
        identity["requested"],
        timeout,
        deadline,
        monotonic,
    )
    if observed != identity:
        raise StructuredOutputError("classifier model identity changed at a per-call boundary")
    return observed


def perform_call(
    transport: ClassifierTransport,
    *,
    identity: dict,
    timeout: int | float,
    call_ordinal: int,
    call_kind: str,
    batch_ordinal: int | None,
    system_contract: str,
    system: str,
    user: str,
    schema: dict,
    candidate_ids: list[str],
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[dict, dict]:
    """Make one bounded call and retain only its validated decision JSON."""
    if deadline is None:
        deadline = monotonic() + ELAPSED_LIMIT_SECONDS
    options = _expected_options(len(candidate_ids))
    identity_before = _resolve_transport_identity(
        transport,
        identity,
        timeout,
        deadline,
        monotonic,
    )
    started = monotonic()
    chat_timeout = _active_timeout(timeout, deadline, monotonic)
    response = transport.chat(
        identity["requested"],
        system,
        user,
        options["num_ctx"],
        chat_timeout,
        schema,
        options["num_predict"],
    )
    elapsed = monotonic() - started
    _require_active_deadline(deadline, monotonic)
    identity_after = _resolve_transport_identity(
        transport,
        identity,
        timeout,
        deadline,
        monotonic,
    )
    completion = _completion_proof(response, options["num_predict"])
    if response.get("model") not in {identity["requested"], identity["name"]}:
        raise StructuredOutputError("classifier response reports a different model identity")
    raw = _response_content(response)
    decoded = decode_classification(raw, candidate_ids)
    context = _context_proof(
        system + "\n" + user,
        response.get("prompt_eval_count"),
        response.get("eval_count"),
        options,
    )
    base = {
        "schema_contract": CALL_RECEIPT_SCHEMA,
        "call_ordinal": call_ordinal,
        "call_kind": call_kind,
        "batch_ordinal": batch_ordinal,
        "candidate_ids": list(candidate_ids),
        "candidate_ids_sha256": _json_sha256(candidate_ids),
        "model": identity["requested"],
        "resolved_model": identity["name"],
        "model_digest": identity["digest"],
        "model_identity_before_call": identity_before,
        "model_identity_after_call": identity_after,
        "options": options,
        "schema": schema,
        "schema_sha256": _json_sha256(schema),
        "system_contract": system_contract,
        "system_prompt_sha256": _sha256(system),
        "input_prompt_sha256": _sha256(user),
        "validated_response_json": raw,
        "validated_response_sha256": _sha256(raw),
        "response_validation": RESPONSE_VALIDATION,
        "response_counts": decoded["counts"],
        "transport_completion": completion,
        "prompt_eval_count": response["prompt_eval_count"],
        "eval_count": response["eval_count"],
        "total_context_proof": context,
        "elapsed_seconds": elapsed,
    }
    return {**base, "receipt_sha256": _json_sha256(base)}, decoded


def validate_call_receipt(
    receipt: object,
    *,
    identity: dict,
    call_ordinal: int,
    call_kind: str,
    batch_ordinal: int | None,
    system_contract: str,
    system: str,
    user: str,
    schema: dict,
    candidate_ids: list[str],
) -> dict:
    expected_keys = {
        "schema_contract",
        "call_ordinal",
        "call_kind",
        "batch_ordinal",
        "candidate_ids",
        "candidate_ids_sha256",
        "model",
        "resolved_model",
        "model_digest",
        "model_identity_before_call",
        "model_identity_after_call",
        "options",
        "schema",
        "schema_sha256",
        "system_contract",
        "system_prompt_sha256",
        "input_prompt_sha256",
        "validated_response_json",
        "validated_response_sha256",
        "response_validation",
        "response_counts",
        "transport_completion",
        "prompt_eval_count",
        "eval_count",
        "total_context_proof",
        "elapsed_seconds",
        "receipt_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise StructuredOutputError("classifier call receipt has the wrong shape")
    options = _expected_options(len(candidate_ids))
    decoded = decode_classification(
        receipt["validated_response_json"],
        candidate_ids,
    )
    expected_context = _context_proof(
        system + "\n" + user,
        receipt["prompt_eval_count"],
        receipt["eval_count"],
        options,
    )
    elapsed = receipt["elapsed_seconds"]
    if (
        receipt["schema_contract"] != CALL_RECEIPT_SCHEMA
        or receipt["call_ordinal"] != call_ordinal
        or receipt["call_kind"] != call_kind
        or receipt["batch_ordinal"] != batch_ordinal
        or receipt["candidate_ids"] != candidate_ids
        or receipt["candidate_ids_sha256"] != _json_sha256(candidate_ids)
        or receipt["model"] != identity["requested"]
        or receipt["resolved_model"] != identity["name"]
        or receipt["model_digest"] != identity["digest"]
        or receipt["model_identity_before_call"] != identity
        or receipt["model_identity_after_call"] != identity
        or receipt["options"] != options
        or receipt["schema"] != schema
        or receipt["schema_sha256"] != _json_sha256(schema)
        or receipt["system_contract"] != system_contract
        or receipt["system_prompt_sha256"] != _sha256(system)
        or receipt["input_prompt_sha256"] != _sha256(user)
        or receipt["validated_response_sha256"] != _sha256(receipt["validated_response_json"])
        or receipt["response_validation"] != RESPONSE_VALIDATION
        or receipt["response_counts"] != decoded["counts"]
        or receipt["transport_completion"] != TRANSPORT_COMPLETION_PROOF
        or receipt["total_context_proof"] != expected_context
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
        or receipt["receipt_sha256"] != _receipt_digest(receipt)
    ):
        raise StructuredOutputError(f"classifier call receipt {call_ordinal} does not re-derive")
    return decoded


def deterministic_sabotage_controls() -> dict:
    """Prove locally that the two trivial fixed patterns fail semantics."""
    fixture_ids = [row["candidate_id"] for row in CLASSIFIER_FIXTURES]
    fixture_locators = batch_locators(fixture_ids)
    rows = []
    for verdict in ("KEEP", "ABSTAIN"):
        raw = json.dumps(
            {
                "items": [
                    {"candidate_id": locator, "verdict": verdict}
                    for locator in fixture_locators
                ]
            },
            separators=(",", ":"),
        )
        decode_classification(raw, fixture_ids)
        rejected = False
        try:
            decode_fixture_classification(raw)
        except StructuredOutputError:
            rejected = True
        if not rejected:
            raise StructuredOutputError(
                f"deterministic all-{verdict} sabotage passed semantic fixtures"
            )
        rows.append(
            {
                "verdict": verdict,
                "validated_response_sha256": _sha256(raw),
                "semantic_disagreement_rejected": True,
            }
        )
    return {
        "schema": DETERMINISTIC_CONTROLS_SCHEMA,
        "fixture_sha256": classifier_fixture_sha256(),
        "rows": rows,
    }


def _assert_fixture_semantics(decoded: dict) -> None:
    expected = [row["expected"] for row in CLASSIFIER_FIXTURES]
    actual = [row["verdict"] for row in decoded["items"]]
    if actual != expected:
        raise StructuredOutputError("classifier semantic fixture call did not agree 12 of 12")


def _assert_sabotaged_semantics(decoded: dict, verdict: str) -> None:
    if any(row["verdict"] != verdict for row in decoded["items"]):
        raise StructuredOutputError(
            f"sabotaged model call did not produce the commanded all-{verdict} pattern"
        )
    fixture_locators = batch_locators(
        [row["candidate_id"] for row in CLASSIFIER_FIXTURES])
    raw = json.dumps(
        {"items": [
            {"candidate_id": locator, "verdict": row["verdict"]}
            for locator, row in zip(
                fixture_locators, decoded["items"], strict=True)
        ]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        decode_fixture_classification(raw)
    except StructuredOutputError:
        return
    raise StructuredOutputError(
        f"sabotaged all-{verdict} model call was not rejected for semantic disagreement"
    )


def _preflight_specs() -> tuple[dict, str, list[str], tuple[tuple, ...]]:
    schema, fixture_system, user, _expected = classifier_fixture_request()
    candidate_ids = [row["candidate_id"] for row in CLASSIFIER_FIXTURES]
    specs = (
        (FIXTURE_CALL, REGISTERED_SYSTEM, fixture_system, None),
        (
            SABOTAGED_KEEP_CALL,
            SABOTAGED_KEEP_SYSTEM,
            SABOTAGED_ALWAYS_KEEP_SYSTEM,
            "KEEP",
        ),
        (
            SABOTAGED_ABSTAIN_CALL,
            SABOTAGED_ABSTAIN_SYSTEM,
            SABOTAGED_ALWAYS_ABSTAIN_SYSTEM,
            "ABSTAIN",
        ),
    )
    return schema, user, candidate_ids, specs


def _validate_preflight_semantics(decoded: dict, sabotage_verdict: str | None) -> None:
    if sabotage_verdict is None:
        _assert_fixture_semantics(decoded)
    else:
        _assert_sabotaged_semantics(decoded, sabotage_verdict)


def validate_preflight_receipts(receipts: object, identity: dict) -> float:
    schema, user, candidate_ids, specs = _preflight_specs()
    if not isinstance(receipts, list) or len(receipts) != len(specs):
        raise StructuredOutputError(
            "classifier result does not retain all three preflight model calls"
        )
    elapsed = 0.0
    for call_ordinal, (receipt, spec) in enumerate(
        zip(receipts, specs, strict=True),
        1,
    ):
        call_kind, system_contract, system, sabotage_verdict = spec
        decoded = validate_call_receipt(
            receipt,
            identity=identity,
            call_ordinal=call_ordinal,
            call_kind=call_kind,
            batch_ordinal=None,
            system_contract=system_contract,
            system=system,
            user=user,
            schema=schema,
            candidate_ids=candidate_ids,
        )
        _validate_preflight_semantics(decoded, sabotage_verdict)
        elapsed += receipt["elapsed_seconds"]
    return elapsed


def validate_corpus_receipts(
    receipts: object,
    transcript: Transcript,
    manifest: dict,
    identity: dict,
    *,
    first_call_ordinal: int = 4,
    expected_batches: int | None = None,
    expected_decisions: int | None = None,
) -> tuple[list[dict], float]:
    """Re-derive every registered ordered batch and durable decision.

    The expected counts default to the registered ES2004c corpus. A private
    capture lane passes its own manifest-derived counts; every other check —
    ordered coverage, receipt binding, exact response identity — is the same.
    """
    if expected_batches is None:
        expected_batches = EXPECTED_CORPUS_BATCHES
    if expected_decisions is None:
        expected_decisions = EXPECTED_CORPUS_DECISIONS
    batch_size = REGISTERED_BATCH_SIZE
    batches = candidate_batches(manifest["candidates"], batch_size)
    if len(batches) != expected_batches:
        raise StructuredOutputError(
            f"registered corpus does not produce {expected_batches} batches"
        )
    if not isinstance(receipts, list) or len(receipts) != expected_batches:
        raise StructuredOutputError(
            "classifier result does not retain exactly "
            f"{expected_batches} corpus batch receipts"
        )
    decisions: list[dict] = []
    elapsed = 0.0
    for batch_ordinal, (batch, receipt) in enumerate(
        zip(batches, receipts, strict=True),
        1,
    ):
        schema, system, user = classification_request(
            transcript,
            manifest,
            batch,
            batch_size,
        )
        candidate_ids = [row["candidate_id"] for row in batch]
        decoded = validate_call_receipt(
            receipt,
            identity=identity,
            call_ordinal=first_call_ordinal + batch_ordinal - 1,
            call_kind=CORPUS_CALL,
            batch_ordinal=batch_ordinal,
            system_contract=REGISTERED_SYSTEM,
            system=system,
            user=user,
            schema=schema,
            candidate_ids=candidate_ids,
        )
        decisions.extend(decoded["items"])
        elapsed += receipt["elapsed_seconds"]
    expected_ids = [row["candidate_id"] for row in manifest["candidates"]]
    actual_ids = [row["candidate_id"] for row in decisions]
    if (
        len(decisions) != expected_decisions
        or actual_ids != expected_ids
        or len(actual_ids) != len(set(actual_ids))
    ):
        raise StructuredOutputError(
            "classifier receipts do not retain all "
            f"{expected_decisions} decisions once and in order"
        )
    return decisions, elapsed


def event_packet_exposure_report(ledger: dict, manifest: dict) -> dict:
    """Require every acceptable bundle inside at least one canonical broad packet."""
    validate_promoted_runner_ledger(ledger, manifest)
    if manifest["strategy"] != STRATEGY_BROAD:
        raise StructuredOutputError("candidate event ledger requires the registered broad manifest")
    candidates = manifest["candidates"]
    rows = []
    for event in ledger["events"]:
        bundle_rows = []
        for bundle_ordinal, bundle in enumerate(
            event["acceptable_evidence_bundles"],
            1,
        ):
            required = set(bundle)
            matching = [
                candidate["candidate_id"]
                for candidate in candidates
                if required.issubset(candidate["visible_fragment_ids"])
            ]
            if not matching:
                raise StructuredOutputError(
                    f"event {event['event_id']} acceptable bundle "
                    f"{bundle_ordinal} is not wholly contained in any "
                    "registered broad packet"
                )
            bundle_rows.append(
                {
                    "bundle_ordinal": bundle_ordinal,
                    "acceptable_fragment_ids": bundle,
                    "containing_candidate_ids": matching,
                }
            )
        rows.append(
            {
                "event_id": event["event_id"],
                "kind": event["kind"],
                "neutral_atomic_proposition_sha256": event["neutral_atomic_proposition_sha256"],
                "bundles": bundle_rows,
                "all_bundles_packet_exposed": True,
            }
        )
    return {
        "schema": "candidate-packet-exposure-report/1",
        "ledger_sha256": ledger["ledger_sha256"],
        "review_reference_sha256": ledger["review_reference_sha256"],
        "review_decisions_sha256": ledger["review_decisions_sha256"],
        "events": len(rows),
        "acceptable_bundles": sum(len(row["bundles"]) for row in rows),
        "all_bundles_packet_exposed": True,
        "rows": rows,
    }


def event_ledger_report(
    ledger: dict,
    manifest: dict,
    decisions: list[dict],
    *,
    packet_exposure: dict | None = None,
) -> dict:
    """Measure packet exposure and retained acceptable anchors from the lock."""
    expected_exposure = event_packet_exposure_report(ledger, manifest)
    if packet_exposure is not None and packet_exposure != expected_exposure:
        raise StructuredOutputError("preflight packet exposure does not re-derive during replay")
    packet_exposure = expected_exposure
    verdicts = {row["candidate_id"]: row["verdict"] for row in decisions}
    rows = []
    for event, exposure_row in zip(
        ledger["events"],
        packet_exposure["rows"],
        strict=True,
    ):
        acceptable_candidates = [
            candidate_id
            for bundle in exposure_row["bundles"]
            for candidate_id in bundle["containing_candidate_ids"]
        ]
        acceptable_candidates = list(dict.fromkeys(acceptable_candidates))
        kept = [
            candidate_id
            for candidate_id in acceptable_candidates
            if verdicts.get(candidate_id) == "KEEP"
        ]
        rows.append(
            {
                "event_id": event["event_id"],
                "kind": event["kind"],
                "neutral_atomic_proposition_sha256": event["neutral_atomic_proposition_sha256"],
                "acceptable_bundles": len(event["acceptable_evidence_bundles"]),
                "exposed_bundles": len(exposure_row["bundles"]),
                "acceptable_candidate_ids": acceptable_candidates,
                "kept_acceptable_candidate_ids": kept,
                "packet_exposed": bool(acceptable_candidates),
                "classifier_recalled": bool(kept),
            }
        )
    exposed = sum(row["packet_exposed"] for row in rows)
    recalled = sum(row["classifier_recalled"] for row in rows)
    if recalled != len(rows):
        raise StructuredOutputError(
            "classifier did not retain an acceptable anchor for every locked event"
        )
    return {
        "schema": "candidate-exposure-report/1",
        "ledger_sha256": ledger["ledger_sha256"],
        "review_reference_sha256": ledger["review_reference_sha256"],
        "review_decisions_sha256": ledger["review_decisions_sha256"],
        "events": len(rows),
        "packet_exposed": exposed,
        "classifier_recalled": recalled,
        "packet_exposure": packet_exposure,
        "rows": rows,
    }


def _input_binding(
    manifest: dict,
    registry: dict,
    authority: dict,
) -> dict:
    observed = authority["observed"]
    return {
        "registration_sha256": authority["registration_sha256"],
        "raw_corpus_sha256": observed["raw_sha256"],
        "transcript_view_sha256": observed["transcript_view_sha256"],
        "manifest_sha256": observed["manifest_sha256"],
        "span_registry_sha256": observed["span_registry_sha256"],
        "generator_contract_sha256": observed["generator_contract_sha256"],
        "fragment_contract_sha256": observed["fragment_contract_sha256"],
        "classifier_system_sha256": observed["classifier_system_sha256"],
        "classifier_fixture_sha256": observed["classifier_fixture_sha256"],
        "manifest_candidates": manifest["counts"]["candidates"],
        "diagnostic_spans": len(registry["spans"]),
        "manifest_generations": 2,
        "manifest_byte_identical": True,
    }


def _summary(
    decisions: list[dict],
    preflight_elapsed: float,
    corpus_elapsed: float,
    authoritative_run_elapsed_seconds: float | None,
    exposure: dict,
) -> dict:
    keep = sum(row["verdict"] == "KEEP" for row in decisions)
    abstain = sum(row["verdict"] == "ABSTAIN" for row in decisions)
    transport_elapsed = preflight_elapsed + corpus_elapsed
    if keep > KEEP_LIMIT:
        raise StructuredOutputError(
            f"classifier kept {keep} candidates; registered maximum is {KEEP_LIMIT}"
        )
    if authoritative_run_elapsed_seconds is not None and (
        isinstance(authoritative_run_elapsed_seconds, bool)
        or not isinstance(authoritative_run_elapsed_seconds, (int, float))
        or not math.isfinite(authoritative_run_elapsed_seconds)
        or authoritative_run_elapsed_seconds < transport_elapsed
        or authoritative_run_elapsed_seconds > ELAPSED_LIMIT_SECONDS
    ):
        raise StructuredOutputError(
            "authoritative outer run time is invalid, shorter than retained "
            "transport time, or above the registered limit"
        )
    return {
        "fixture_agreement": EXPECTED_FIXTURES,
        "model_sabotage_calls_rejected": 2,
        "corpus_batches": EXPECTED_CORPUS_BATCHES,
        "decisions": EXPECTED_CORPUS_DECISIONS,
        "decision_order_sha256": _json_sha256(decisions),
        "keep": keep,
        "abstain": abstain,
        "all_abstentions_retained": keep + abstain == EXPECTED_CORPUS_DECISIONS,
        "maximum_keep": KEEP_LIMIT,
        "preflight_transport_elapsed_seconds": preflight_elapsed,
        "corpus_transport_elapsed_seconds": corpus_elapsed,
        "receipt_transport_elapsed_seconds": transport_elapsed,
        "authoritative_run_elapsed_seconds": authoritative_run_elapsed_seconds,
        "maximum_elapsed_seconds": ELAPSED_LIMIT_SECONDS,
        "event_packet_exposure": exposure["packet_exposed"],
        "event_classifier_recall": exposure["classifier_recalled"],
        "event_targets": exposure["events"],
    }


def _validate_identity(identity: object) -> dict:
    validated = validate_registered_model_identity(identity)
    if not isinstance(validated, dict):
        raise StructuredOutputError("registered model identity validation failed")
    return validated


def build_registered_result(
    *,
    transcript: Transcript,
    manifest: dict,
    registry: dict,
    authority: dict,
    ledger: dict,
    ledger_binding: dict,
    identity_start: dict,
    identity_end: dict,
    deterministic_controls: dict,
    fixture_receipts: list[dict],
    corpus_receipts: list[dict],
    packet_exposure: dict,
    authoritative_run_elapsed_seconds: float | None,
) -> dict:
    if identity_end != identity_start:
        raise StructuredOutputError("classifier model identity changed during the registered run")
    preflight_elapsed = validate_preflight_receipts(
        fixture_receipts,
        identity_start,
    )

    decisions, corpus_elapsed = validate_corpus_receipts(
        corpus_receipts,
        transcript,
        manifest,
        identity_start,
    )
    exposure = event_ledger_report(
        ledger,
        manifest,
        decisions,
        packet_exposure=packet_exposure,
    )
    diagnostic = qmsum_span_report(registry, manifest, decisions)
    summary = _summary(
        decisions,
        preflight_elapsed,
        corpus_elapsed,
        authoritative_run_elapsed_seconds,
        exposure,
    )
    base = {
        "schema_contract": RESULT_SCHEMA,
        "registration_sha256": registered_run_sha256(),
        "inputs": _input_binding(manifest, registry, authority),
        "ledger_lock": ledger_binding,
        "deterministic_controls": deterministic_controls,
        "model_identity_start": identity_start,
        "model_identity_end": identity_end,
        "model_identity_provenance": {
            "checks": (
                "pinned digest at run start, immediately before and after every "
                "model call, and at run end"
            ),
            "limit": (
                "Ollama calls still address a mutable tag; boundary checks cannot "
                "rule out a transient retag during one call that returns to the "
                "pinned digest before the post-call check"
            ),
        },
        "options": {
            "batch_size": REGISTERED_BATCH_SIZE,
            "num_ctx": REGISTERED_RUN["classifier"]["num_ctx"],
            "temperature": REGISTERED_RUN["classifier"]["temperature"],
            "num_predict": REGISTERED_RUN["classifier"]["num_predict"],
        },
        "timing_provenance": {
            "authoritative": (
                "outer monotonic wall time from registered input derivation and "
                "ledger preflight through final identity resolution and "
                "deterministic result construction"
            ),
            "active_deadline": (
                "every model-resolution and chat timeout is capped to the "
                "remaining outer registered budget; an exhausted or overrun "
                "operation fails the run"
            ),
            "receipt_elapsed": ("per-call transport.chat time only; retained as a diagnostic"),
            "replay_limit": (
                "replay validates the retained type, bounds, and consistency "
                "but cannot re-time a historical run"
            ),
        },
        "preflight_receipts": fixture_receipts,
        "corpus_receipts": corpus_receipts,
        "summary": summary,
        "event_ledger_report": exposure,
        "qmsum_span_diagnostic": diagnostic,
        "passed": True,
        "meaning": (
            "registered classifier feasibility measurement; not a scored note "
            "or claim-generation result"
        ),
    }
    return {**base, "result_sha256": _json_sha256(base)}


def _finalize_live_elapsed(
    result: dict,
    started: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Insert outer wall time after deterministic result construction."""
    elapsed = monotonic() - started
    transport_elapsed = result["summary"]["receipt_transport_elapsed_seconds"]
    if not math.isfinite(elapsed) or elapsed < transport_elapsed or elapsed > ELAPSED_LIMIT_SECONDS:
        raise StructuredOutputError(
            "authoritative outer run time is shorter than retained transport "
            "time or above the registered limit"
        )
    result["summary"]["authoritative_run_elapsed_seconds"] = elapsed
    base = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = _json_sha256(base)
    return result


def validate_registered_result(
    result: object,
    *,
    transcript: Transcript,
    manifest: dict,
    registry: dict,
    authority: dict,
    ledger: dict,
    ledger_binding: dict,
) -> dict:
    expected_keys = {
        "schema_contract",
        "registration_sha256",
        "inputs",
        "ledger_lock",
        "deterministic_controls",
        "model_identity_start",
        "model_identity_end",
        "model_identity_provenance",
        "options",
        "timing_provenance",
        "preflight_receipts",
        "corpus_receipts",
        "summary",
        "event_ledger_report",
        "qmsum_span_diagnostic",
        "passed",
        "meaning",
        "result_sha256",
    }
    if not isinstance(result, dict) or set(result) != expected_keys:
        raise StructuredOutputError("candidate classifier result has the wrong shape")
    authoritative_elapsed = (
        result["summary"].get("authoritative_run_elapsed_seconds")
        if isinstance(result.get("summary"), dict)
        else None
    )
    if (
        isinstance(authoritative_elapsed, bool)
        or not isinstance(authoritative_elapsed, (int, float))
        or not math.isfinite(authoritative_elapsed)
    ):
        raise StructuredOutputError("replay requires the retained authoritative outer run time")
    identity_start = _validate_identity(result["model_identity_start"])
    identity_end = _validate_identity(result["model_identity_end"])
    rebuilt = build_registered_result(
        transcript=transcript,
        manifest=manifest,
        registry=registry,
        authority=authority,
        ledger=ledger,
        ledger_binding=ledger_binding,
        identity_start=identity_start,
        identity_end=identity_end,
        deterministic_controls=deterministic_sabotage_controls(),
        fixture_receipts=result["preflight_receipts"],
        corpus_receipts=result["corpus_receipts"],
        packet_exposure=result["event_ledger_report"]["packet_exposure"],
        authoritative_run_elapsed_seconds=authoritative_elapsed,
    )
    if result != rebuilt:
        raise StructuredOutputError(
            "candidate classifier result does not replay from registered inputs"
        )
    return result


def run_registered_classifier(
    corpus_path: Path,
    reference_path: Path,
    decisions_path: Path,
    ledger_path: Path,
    lock_path: Path,
    approved_lock_sha256: str | None,
    *,
    transport: ClassifierTransport,
    timeout: int | float,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Run the fixed experiment; return only a complete passing result."""
    run_started = monotonic()
    if not math.isfinite(run_started):
        raise StructuredOutputError("classifier monotonic clock returned a non-finite value")
    active_deadline = run_started + ELAPSED_LIMIT_SECONDS
    transcript, manifest, registry, authority = derive_registered_inputs(corpus_path)

    # This guard deliberately precedes model resolution, semantic fixtures, and
    # every corpus call. The runner has no path that classifies first and locks later.
    ledger, _lock, ledger_binding, packet_exposure = load_locked_review_preflight(
        corpus_path,
        reference_path,
        decisions_path,
        ledger_path,
        lock_path,
        transcript,
        manifest,
        approved_lock_sha256,
    )
    deterministic_controls = deterministic_sabotage_controls()

    classifier = REGISTERED_RUN["classifier"]
    identity_start = _resolve_model_identity(
        transport,
        classifier["model"],
        timeout,
        active_deadline,
        monotonic,
    )
    fixture_schema, fixture_user, fixture_ids, preflight_specs = _preflight_specs()
    preflight_receipts = []
    for call_ordinal, spec in enumerate(preflight_specs, 1):
        call_kind, system_contract, system, sabotage_verdict = spec
        receipt, decoded = perform_call(
            transport,
            identity=identity_start,
            timeout=timeout,
            call_ordinal=call_ordinal,
            call_kind=call_kind,
            batch_ordinal=None,
            system_contract=system_contract,
            system=system,
            user=fixture_user,
            schema=fixture_schema,
            candidate_ids=fixture_ids,
            deadline=active_deadline,
            monotonic=monotonic,
        )
        _validate_preflight_semantics(decoded, sabotage_verdict)
        preflight_receipts.append(receipt)

    corpus_receipts = []
    batch_size = REGISTERED_BATCH_SIZE
    batches = candidate_batches(manifest["candidates"], batch_size)
    for batch_ordinal, batch in enumerate(batches, 1):
        schema, system, user = classification_request(
            transcript,
            manifest,
            batch,
            batch_size,
        )
        candidate_ids = [row["candidate_id"] for row in batch]
        receipt, _decoded = perform_call(
            transport,
            identity=identity_start,
            timeout=timeout,
            call_ordinal=3 + batch_ordinal,
            call_kind=CORPUS_CALL,
            batch_ordinal=batch_ordinal,
            system_contract=REGISTERED_SYSTEM,
            system=system,
            user=user,
            schema=schema,
            candidate_ids=candidate_ids,
            deadline=active_deadline,
            monotonic=monotonic,
        )
        corpus_receipts.append(receipt)

    identity_end = _resolve_model_identity(
        transport,
        classifier["model"],
        timeout,
        active_deadline,
        monotonic,
    )
    result = build_registered_result(
        transcript=transcript,
        manifest=manifest,
        registry=registry,
        authority=authority,
        ledger=ledger,
        ledger_binding=ledger_binding,
        identity_start=identity_start,
        identity_end=identity_end,
        deterministic_controls=deterministic_controls,
        fixture_receipts=preflight_receipts,
        corpus_receipts=corpus_receipts,
        packet_exposure=packet_exposure,
        authoritative_run_elapsed_seconds=None,
    )
    result = _finalize_live_elapsed(result, run_started, monotonic)
    return validate_registered_result(
        result,
        transcript=transcript,
        manifest=manifest,
        registry=registry,
        authority=authority,
        ledger=ledger,
        ledger_binding=ledger_binding,
    )


def replay_registered_result(
    corpus_path: Path,
    reference_path: Path,
    decisions_path: Path,
    ledger_path: Path,
    lock_path: Path,
    approved_lock_sha256: str | None,
    result_path: Path,
) -> dict:
    transcript, manifest, registry, authority = derive_registered_inputs(corpus_path)
    ledger, _lock, ledger_binding, _packet_exposure = load_locked_review_preflight(
        corpus_path,
        reference_path,
        decisions_path,
        ledger_path,
        lock_path,
        transcript,
        manifest,
        approved_lock_sha256,
    )
    result, _result_bytes = _load_json(
        result_path,
        "candidate classifier result",
    )
    return validate_registered_result(
        result,
        transcript=transcript,
        manifest=manifest,
        registry=registry,
        authority=authority,
        ledger=ledger,
        ledger_binding=ledger_binding,
    )


def validate_result_target(
    path: Path,
    input_paths: list[Path],
) -> Path:
    target = validate_private_output_target(path)
    for input_path in input_paths:
        validate_distinct_input_output(input_path, target)
    return target


def write_private_result(
    path: Path,
    result: dict,
    input_paths: list[Path],
) -> Path:
    validate_result_target(path, input_paths)
    return write_private_json(path, result)


def produce_and_write_private_result(
    path: Path,
    input_paths: list[Path],
    producer: Callable[[], dict],
) -> Path:
    """Install nothing unless the complete result producer returns successfully."""
    validate_result_target(path, input_paths)
    result = producer()
    return write_private_json(path, result)


class _FakeClock:
    """Deterministic monotonic clock for active-deadline tests."""

    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeTransport:
    """No-network transport used only by self-tests."""

    def __init__(
        self,
        *,
        mode: str = "valid",
        drift: bool = False,
        resolution_delay_seconds: float = 0.0,
        clock: _FakeClock | None = None,
        resolution_cost_seconds: float = 0.0,
        chat_cost_seconds: float = 0.0,
    ):
        self.mode = mode
        self.drift = drift
        self.resolution_delay_seconds = resolution_delay_seconds
        self.clock = clock
        self.resolution_cost_seconds = resolution_cost_seconds
        self.chat_cost_seconds = chat_cost_seconds
        self.resolutions = 0
        self.calls = 0
        self.resolution_timeouts: list[float] = []
        self.chat_timeouts: list[float] = []

    def resolve_model(self, model: str, timeout: float) -> dict:
        self.resolution_timeouts.append(timeout)
        if self.resolution_delay_seconds:
            time.sleep(self.resolution_delay_seconds)
        self.resolutions += 1
        if self.clock is not None:
            self.clock.advance(self.resolution_cost_seconds)
        digest = REGISTERED_RUN["classifier"]["model_digest"]
        if self.drift and self.resolutions > 1:
            digest = "0" * 64
        return {"requested": model, "name": model, "digest": digest}

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        num_ctx: int,
        timeout: float,
        response_format: dict,
        num_predict: int,
    ) -> dict:
        self.chat_timeouts.append(timeout)
        self.calls += 1
        if self.clock is not None:
            self.clock.advance(self.chat_cost_seconds)
        candidate_ids = response_format_candidate_ids(response_format)
        if system == CLASSIFIER_SYSTEM and candidate_ids == batch_locators(
            [row["candidate_id"] for row in CLASSIFIER_FIXTURES]
        ) and len(candidate_ids) == len(CLASSIFIER_FIXTURES):
            verdicts = [row["expected"] for row in CLASSIFIER_FIXTURES]
        elif system == SABOTAGED_ALWAYS_KEEP_SYSTEM:
            verdicts = ["KEEP"] * len(candidate_ids)
        elif system == SABOTAGED_ALWAYS_ABSTAIN_SYSTEM:
            verdicts = ["ABSTAIN"] * len(candidate_ids)
        else:
            verdicts = [
                "KEEP" if index < min(2, len(candidate_ids)) else "ABSTAIN"
                for index in range(len(candidate_ids))
            ]
        items = [
            {"candidate_id": candidate_id, "verdict": verdict}
            for candidate_id, verdict in zip(
                candidate_ids,
                verdicts,
                strict=True,
            )
        ]
        if self.mode == "missing-decision":
            items = items[:-1]
        elif self.mode == "duplicate-decision":
            items[1]["candidate_id"] = items[0]["candidate_id"]
        elif self.mode == "reordered-decisions":
            items[0], items[1] = items[1], items[0]
        raw = json.dumps({"items": items}, separators=(",", ":"))
        estimated = int(len(system + "\n" + user) / PROMPT_ESTIMATE_CHARS_PER_TOKEN)
        response = {
            "model": model,
            "message": {"content": raw},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": max(1, estimated),
            "eval_count": min(num_predict, max(1, len(candidate_ids) * 4)),
        }
        if self.mode == "malformed":
            response["message"]["content"] = "{"
        elif self.mode == "length":
            response["done_reason"] = "length"
        elif self.mode == "missing-completion":
            del response["done"]
        elif self.mode == "context":
            response["prompt_eval_count"] = num_ctx - 32
        return response


def response_format_candidate_ids(response_format: dict) -> list[str]:
    try:
        values = response_format["properties"]["items"]["items"]["properties"]["candidate_id"][
            "enum"
        ]
    except (KeyError, TypeError) as exc:
        raise StructuredOutputError("fake received a malformed classifier schema") from exc
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise StructuredOutputError("fake received invalid candidate ID enums")
    return values


def _expect_refusal(label: str, function, *args, **kwargs) -> None:
    try:
        function(*args, **kwargs)
    except StructuredOutputError:
        return
    raise AssertionError(f"{label} was accepted")


def _synthetic_registered_shape() -> tuple[Transcript, dict]:
    transcript = Transcript(
        source="synthetic classifier receipt fixture",
        attribution="none",
        turns=[
            Turn(text=f"Synthetic status fragment {index}.")
            for index in range(EXPECTED_CORPUS_DECISIONS)
        ],
    )
    manifest = generate_manifest(transcript, STRATEGY_BROAD)
    assert manifest["counts"]["candidates"] == EXPECTED_CORPUS_DECISIONS
    return transcript, manifest


def _write_synthetic_qmsum(path: Path, transcript: Transcript) -> None:
    path.write_text(
        json.dumps(
            {
                "meeting_transcripts": [
                    {"speaker": "A", "content": turn.text} for turn in transcript.turns
                ],
                "specific_query_list": [
                    {
                        "query": "What happened first?",
                        "answer": "Synthetic fixture content.",
                        "relevant_text_span": [["0", "0"]],
                    }
                ],
            }
        )
    )


def _synthetic_review_artifacts(
    corpus_path: Path,
    transcript: Transcript,
    manifest: dict,
    *,
    proposition: str = "The first synthetic status is recorded.",
) -> tuple[dict, dict, dict]:
    from candidate_exposure import (
        COORDINATE_CONTRACT,
        REVIEW_DECISIONS_SCHEMA,
        REVIEW_REGIONS_SCHEMA,
        create_reference,
    )

    coordinates = qmsum_coordinates(corpus_path, transcript)
    regions = {
        "schema": REVIEW_REGIONS_SCHEMA,
        "coordinate_contract": COORDINATE_CONTRACT,
        "regions": [],
    }
    reference = create_reference(
        transcript,
        manifest,
        [
            {
                "event_id": "synthetic-event-001",
                "kind": "ACTION",
                "neutral_atomic_proposition": proposition,
                "type_specific": {
                    "commitment_status": "PENDING_OPERATOR_REVIEW",
                },
                "acceptable_candidate_ids": [manifest["candidates"][0]["candidate_id"]],
            }
        ],
        corpus_sha256=_sha256(corpus_path.read_bytes()),
        coordinates=coordinates,
        regions=regions,
        section_size=len(transcript.turns),
        enforce_registered=False,
    )
    event = reference["events"][0]
    decisions = {
        "schema": REVIEW_DECISIONS_SCHEMA,
        "reference_sha256": reference["reference_sha256"],
        "registration_sha256": registered_run_sha256(),
        "events": [
            {
                "event_id": event["event_id"],
                "disposition": "ACCEPT",
                "kind": event["kind"],
                "neutral_atomic_proposition": event["neutral_atomic_proposition"],
                "selected_bundle_sha256": [event["evidence_bundles"][0]["bundle_sha256"]],
                "ambiguity_reason": "",
                "notes": "",
            }
        ],
        "sections": [
            {
                "section_id": section["section_id"],
                "reviewed": True,
                "resolution": "NO_MISSING_EVENT",
                "notes": "",
            }
            for section in reference["sections"]
        ],
    }
    validate_reference(
        reference,
        transcript,
        manifest,
        coordinates,
        regions,
        enforce_registered=False,
    )
    validate_review_decisions(decisions, reference)
    return reference, decisions, build_runner_ledger(decisions, reference)


def _ledger_with_bundles(ledger: dict, bundles: list[list[str]]) -> dict:
    updated = deepcopy(ledger)
    updated["events"][0]["acceptable_evidence_bundles"] = bundles
    base = {key: value for key, value in updated.items() if key != "ledger_sha256"}
    updated["ledger_sha256"] = _json_sha256(base)
    return updated


def _synthetic_preflight_receipts(
    transport: _FakeTransport,
    identity: dict,
) -> list[dict]:
    schema, user, candidate_ids, specs = _preflight_specs()
    receipts = []
    for call_ordinal, spec in enumerate(specs, 1):
        call_kind, system_contract, system, sabotage_verdict = spec
        receipt, decoded = perform_call(
            transport,
            identity=identity,
            timeout=1,
            call_ordinal=call_ordinal,
            call_kind=call_kind,
            batch_ordinal=None,
            system_contract=system_contract,
            system=system,
            user=user,
            schema=schema,
            candidate_ids=candidate_ids,
        )
        _validate_preflight_semantics(decoded, sabotage_verdict)
        receipts.append(receipt)
    return receipts


def _synthetic_corpus_receipts(
    transcript: Transcript,
    manifest: dict,
    transport: _FakeTransport,
    identity: dict,
) -> list[dict]:
    receipts = []
    batch_size = REGISTERED_BATCH_SIZE
    for batch_ordinal, batch in enumerate(
        candidate_batches(manifest["candidates"], batch_size),
        1,
    ):
        schema, system, user = classification_request(
            transcript,
            manifest,
            batch,
            batch_size,
        )
        receipt, _decoded = perform_call(
            transport,
            identity=identity,
            timeout=1,
            call_ordinal=3 + batch_ordinal,
            call_kind=CORPUS_CALL,
            batch_ordinal=batch_ordinal,
            system_contract=REGISTERED_SYSTEM,
            system=system,
            user=user,
            schema=schema,
            candidate_ids=[row["candidate_id"] for row in batch],
        )
        receipts.append(receipt)
    return receipts


def run_self_test() -> int:
    """Exercise the runner and replay trust boundaries without network access."""
    identity = _validate_identity(
        {
            "requested": REGISTERED_RUN["classifier"]["model"],
            "name": REGISTERED_RUN["classifier"]["model"],
            "digest": REGISTERED_RUN["classifier"]["model_digest"],
        }
    )
    transcript, manifest = _synthetic_registered_shape()
    fixture_schema, fixture_system, fixture_user, _expected = classifier_fixture_request()
    fixture_ids = [row["candidate_id"] for row in CLASSIFIER_FIXTURES]

    for mode in (
        "malformed",
        "missing-decision",
        "duplicate-decision",
        "length",
        "missing-completion",
        "context",
    ):
        transport = _FakeTransport(mode=mode)
        _expect_refusal(
            f"{mode} transport response",
            perform_call,
            transport,
            identity=identity,
            timeout=1,
            call_ordinal=1,
            call_kind=FIXTURE_CALL,
            batch_ordinal=None,
            system_contract=REGISTERED_SYSTEM,
            system=fixture_system,
            user=fixture_user,
            schema=fixture_schema,
            candidate_ids=fixture_ids,
        )

    reordered_transport = _FakeTransport(mode="reordered-decisions")
    _receipt, reordered_decoded = perform_call(
        reordered_transport,
        identity=identity,
        timeout=1,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
    )
    assert reordered_decoded["counts"]["out_of_order_positions"] == 2
    assert [row["candidate_id"] for row in reordered_decoded["items"]] == fixture_ids

    controls = deterministic_sabotage_controls()
    assert len(controls["rows"]) == 2
    assert all(row["semantic_disagreement_rejected"] for row in controls["rows"])

    valid_transport = _FakeTransport()
    preflight_receipts = _synthetic_preflight_receipts(
        valid_transport,
        identity,
    )
    validate_preflight_receipts(preflight_receipts, identity)
    tampered = deepcopy(preflight_receipts[0])
    tampered["validated_response_sha256"] = "0" * 64
    _expect_refusal(
        "tampered classifier receipt",
        validate_call_receipt,
        tampered,
        identity=identity,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
    )

    drift_transport = _FakeTransport(drift=True)
    _expect_refusal(
        "per-call model drift",
        perform_call,
        drift_transport,
        identity=identity,
        timeout=1,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
    )
    assert drift_transport.calls == 1

    deadline_clock = _FakeClock(100.0)
    bounded_transport = _FakeTransport(
        clock=deadline_clock,
        resolution_cost_seconds=0.5,
        chat_cost_seconds=0.5,
    )
    bounded_receipt, _decoded = perform_call(
        bounded_transport,
        identity=identity,
        timeout=180,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
        deadline=102.5,
        monotonic=deadline_clock,
    )
    assert bounded_receipt["elapsed_seconds"] == 0.5
    assert bounded_transport.resolution_timeouts == [2.5, 1.5]
    assert bounded_transport.chat_timeouts == [2.0]

    exhausted_clock = _FakeClock(5.0)
    exhausted_transport = _FakeTransport(clock=exhausted_clock)
    _expect_refusal(
        "exhausted active deadline before model resolution",
        perform_call,
        exhausted_transport,
        identity=identity,
        timeout=180,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
        deadline=5.0,
        monotonic=exhausted_clock,
    )
    assert exhausted_transport.resolutions == exhausted_transport.calls == 0

    overrun_clock = _FakeClock()
    overrun_transport = _FakeTransport(
        clock=overrun_clock,
        resolution_cost_seconds=0.25,
        chat_cost_seconds=1.0,
    )
    _expect_refusal(
        "transport ignored remaining active deadline",
        perform_call,
        overrun_transport,
        identity=identity,
        timeout=180,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
        deadline=1.0,
        monotonic=overrun_clock,
    )
    assert overrun_transport.resolution_timeouts == [1.0]
    assert overrun_transport.chat_timeouts == [0.75]
    assert overrun_transport.resolutions == overrun_transport.calls == 1

    slow_transport = _FakeTransport(resolution_delay_seconds=0.01)
    slow_started = time.monotonic()
    slow_receipt, _decoded = perform_call(
        slow_transport,
        identity=identity,
        timeout=1,
        call_ordinal=1,
        call_kind=FIXTURE_CALL,
        batch_ordinal=None,
        system_contract=REGISTERED_SYSTEM,
        system=fixture_system,
        user=fixture_user,
        schema=fixture_schema,
        candidate_ids=fixture_ids,
    )
    slow_result = _finalize_live_elapsed(
        {
            "summary": {
                "receipt_transport_elapsed_seconds": slow_receipt["elapsed_seconds"],
                "authoritative_run_elapsed_seconds": None,
            },
            "result_sha256": "",
        },
        slow_started,
    )
    assert slow_result["summary"]["authoritative_run_elapsed_seconds"] >= (
        slow_receipt["elapsed_seconds"] + 0.015
    )

    corpus_receipts = _synthetic_corpus_receipts(
        transcript,
        manifest,
        valid_transport,
        identity,
    )
    decisions, elapsed = validate_corpus_receipts(
        corpus_receipts,
        transcript,
        manifest,
        identity,
    )
    assert len(decisions) == EXPECTED_CORPUS_DECISIONS
    assert elapsed <= ELAPSED_LIMIT_SECONDS
    _expect_refusal(
        "missing corpus batch",
        validate_corpus_receipts,
        corpus_receipts[:-1],
        transcript,
        manifest,
        identity,
    )
    duplicated = deepcopy(corpus_receipts)
    duplicated[1] = deepcopy(duplicated[0])
    _expect_refusal(
        "duplicate corpus batch",
        validate_corpus_receipts,
        duplicated,
        transcript,
        manifest,
        identity,
    )
    reordered = deepcopy(corpus_receipts)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    _expect_refusal(
        "reordered corpus batches",
        validate_corpus_receipts,
        reordered,
        transcript,
        manifest,
        identity,
    )
    _expect_refusal(
        "over-keep aggregate",
        _summary,
        [
            {"candidate_id": row["candidate_id"], "verdict": "KEEP"}
            for row in manifest["candidates"]
        ],
        0.0,
        0.0,
        0.0,
        {
            "packet_exposed": 1,
            "classifier_recalled": 1,
            "events": 1,
        },
    )
    _expect_refusal(
        "over-time authoritative run",
        _summary,
        decisions,
        0.0,
        0.0,
        ELAPSED_LIMIT_SECONDS + 1,
        {
            "packet_exposed": 1,
            "classifier_recalled": 1,
            "events": 1,
        },
    )

    drifted = dict(identity)
    drifted["digest"] = "0" * 64
    _expect_refusal(
        "model drift",
        build_registered_result,
        transcript=transcript,
        manifest=manifest,
        registry={},
        authority={},
        ledger={},
        ledger_binding={},
        identity_start=identity,
        identity_end=drifted,
        deterministic_controls=controls,
        fixture_receipts=[],
        corpus_receipts=[],
        packet_exposure={},
        authoritative_run_elapsed_seconds=0.0,
    )

    with tempfile.TemporaryDirectory() as directory:
        temporary_root = Path(directory)
        qmsum_path = temporary_root / "synthetic-qmsum.json"
        _write_synthetic_qmsum(qmsum_path, transcript)
        reference, review_decisions, ledger = _synthetic_review_artifacts(
            qmsum_path,
            transcript,
            manifest,
        )
        assert ledger["schema"] == LEDGER_SCHEMA
        reference_path = temporary_root / "review-reference.json"
        decisions_path = temporary_root / "review-decisions.json"
        ledger_path = temporary_root / "ledger.json"
        lock_path = temporary_root / "lock.json"
        reference_path.write_text(json.dumps(reference, indent=2) + "\n")
        decisions_path.write_bytes(_json_bytes(review_decisions))
        ledger_path.write_bytes(_json_bytes(ledger))
        valid_lock = {
            "schema": LEDGER_LOCK_SCHEMA,
            "state": PENDING_LOCK_STATE,
            "ledger_sha256": ledger["ledger_sha256"],
            "review_reference_sha256": ledger["review_reference_sha256"],
            "review_decisions_sha256": ledger["review_decisions_sha256"],
            "registration_sha256": registered_run_sha256(),
            "manifest_sha256": manifest["manifest_sha256"],
            "prepared_at": "2026-07-30T00:00:00-05:00",
        }
        lock_path.write_bytes(_json_bytes(valid_lock))
        approved_lock_sha256 = _sha256(lock_path.read_bytes())

        zero_transport = _FakeTransport()
        _expect_refusal(
            "missing out-of-band lock approval digest",
            load_operator_locked_ledger,
            ledger_path,
            lock_path,
            manifest,
            None,
        )
        _expect_refusal(
            "mismatched out-of-band lock approval digest",
            load_operator_locked_ledger,
            ledger_path,
            lock_path,
            manifest,
            "0" * 64,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0

        loaded, _lock, binding, packet_exposure = load_locked_review_preflight(
            qmsum_path,
            reference_path,
            decisions_path,
            ledger_path,
            lock_path,
            transcript,
            manifest,
            approved_lock_sha256,
            enforce_registered=False,
        )
        assert binding["ledger_sha256"] == ledger["ledger_sha256"]
        assert binding["operator_supplied_approved_lock_sha256"] == (approved_lock_sha256)
        review_binding = binding["review_artifacts"]
        assert review_binding["review_reference_sha256"] == (reference["reference_sha256"])
        assert review_binding["review_decisions_sha256"] == (ledger["review_decisions_sha256"])
        assert (
            review_binding["review_reference_raw_file_sha256"]
            != (review_binding["review_reference_canonical_file_sha256"])
        )
        assert (
            review_binding["review_decisions_raw_file_sha256"]
            == (review_binding["review_decisions_canonical_file_sha256"])
        )

        forged_ledger = deepcopy(ledger)
        forged_ledger["events"][0]["neutral_atomic_proposition_sha256"] = "0" * 64
        forged_base = {key: value for key, value in forged_ledger.items() if key != "ledger_sha256"}
        forged_ledger["ledger_sha256"] = _json_sha256(forged_base)
        forged_lock = {
            **valid_lock,
            "ledger_sha256": forged_ledger["ledger_sha256"],
        }
        ledger_path.write_bytes(_json_bytes(forged_ledger))
        lock_path.write_bytes(_json_bytes(forged_lock))
        forged_lock_sha256 = _sha256(lock_path.read_bytes())
        _expect_refusal(
            "forged proposition digest before model resolution",
            load_locked_review_preflight,
            qmsum_path,
            reference_path,
            decisions_path,
            ledger_path,
            lock_path,
            transcript,
            manifest,
            forged_lock_sha256,
            enforce_registered=False,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0
        ledger_path.write_bytes(_json_bytes(ledger))
        lock_path.write_bytes(_json_bytes(valid_lock))

        changed_decisions = deepcopy(review_decisions)
        changed_decisions["events"][0]["notes"] = "changed after the lock"
        decisions_path.write_bytes(_json_bytes(changed_decisions))
        _expect_refusal(
            "changed review decisions before model resolution",
            load_locked_review_preflight,
            qmsum_path,
            reference_path,
            decisions_path,
            ledger_path,
            lock_path,
            transcript,
            manifest,
            approved_lock_sha256,
            enforce_registered=False,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0
        decisions_path.write_bytes(_json_bytes(review_decisions))

        changed_reference, _changed_review, _changed_ledger = _synthetic_review_artifacts(
            qmsum_path,
            transcript,
            manifest,
            proposition="A changed synthetic proposition.",
        )
        reference_path.write_bytes(_json_bytes(changed_reference))
        _expect_refusal(
            "changed review reference before model resolution",
            load_locked_review_preflight,
            qmsum_path,
            reference_path,
            decisions_path,
            ledger_path,
            lock_path,
            transcript,
            manifest,
            approved_lock_sha256,
            enforce_registered=False,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0
        reference_path.write_text(json.dumps(reference, indent=2) + "\n")

        malformed_semantics = deepcopy(ledger)
        malformed_semantics["events"][0]["neutral_atomic_proposition_sha256"] = "not-a-digest"
        _expect_refusal(
            "malformed approved semantic digest",
            _validate_ledger_shape,
            malformed_semantics,
            manifest,
        )
        report = event_ledger_report(
            loaded,
            manifest,
            decisions,
            packet_exposure=packet_exposure,
        )
        assert report["packet_exposed"] == report["classifier_recalled"] == 1

        first_fragment = manifest["candidates"][0]["anchor_fragment_id"]
        last_fragment = manifest["candidates"][-1]["anchor_fragment_id"]
        impossible = _ledger_with_bundles(
            ledger,
            [[first_fragment, last_fragment]],
        )
        _expect_refusal(
            "first-plus-last fragment bundle",
            event_packet_exposure_report,
            impossible,
            manifest,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0

        draft_reference = {
            "schema": REVIEW_REFERENCE_SCHEMA,
            "status": "DRAFT",
            "human_approval": "PENDING_HUMAN_APPROVAL",
            "source": {},
            "reference_sha256": "4" * 64,
        }
        _expect_refusal(
            "unpromoted candidate exposure draft",
            _validate_ledger_shape,
            draft_reference,
            manifest,
        )

        _expect_refusal(
            "absent event ledger",
            load_operator_locked_ledger,
            temporary_root / "absent.json",
            lock_path,
            manifest,
            approved_lock_sha256,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0

        unapproved = dict(valid_lock)
        unapproved["state"] = "operator-locked"
        lock_path.write_bytes(_json_bytes(unapproved))
        unapproved_lock_sha256 = _sha256(lock_path.read_bytes())
        _expect_refusal(
            "unapproved event ledger",
            load_operator_locked_ledger,
            ledger_path,
            lock_path,
            manifest,
            unapproved_lock_sha256,
        )
        assert zero_transport.calls == zero_transport.resolutions == 0
        lock_path.write_bytes(_json_bytes(valid_lock))

        registry = qmsum_search_spans(qmsum_path, transcript)
        authority = {
            "registration_sha256": registered_run_sha256(),
            "observed": {
                "raw_sha256": registry["corpus_sha256"],
                "transcript_view_sha256": manifest["transcript_view_sha256"],
                "manifest_sha256": manifest["manifest_sha256"],
                "span_registry_sha256": registry["registry_sha256"],
                "candidates": manifest["counts"]["candidates"],
                "strategy": manifest["strategy"],
                "generator_contract_sha256": manifest["generator_contract_sha256"],
                "fragment_contract_sha256": manifest["fragment_contract_sha256"],
                "classifier_system_sha256": classifier_system_sha256(),
                "classifier_fixture_sha256": classifier_fixture_sha256(),
            },
        }
        transport_elapsed = sum(
            receipt["elapsed_seconds"] for receipt in [*preflight_receipts, *corpus_receipts]
        )
        complete_result = build_registered_result(
            transcript=transcript,
            manifest=manifest,
            registry=registry,
            authority=authority,
            ledger=loaded,
            ledger_binding=binding,
            identity_start=identity,
            identity_end=identity,
            deterministic_controls=controls,
            fixture_receipts=preflight_receipts,
            corpus_receipts=corpus_receipts,
            packet_exposure=packet_exposure,
            authoritative_run_elapsed_seconds=transport_elapsed + 0.01,
        )
        assert len(complete_result["preflight_receipts"]) == 3
        assert len(complete_result["corpus_receipts"]) == (EXPECTED_CORPUS_BATCHES)
        validate_registered_result(
            complete_result,
            transcript=transcript,
            manifest=manifest,
            registry=registry,
            authority=authority,
            ledger=loaded,
            ledger_binding=binding,
        )
        missing_wall_time = deepcopy(complete_result)
        missing_wall_time["summary"]["authoritative_run_elapsed_seconds"] = None
        missing_wall_base = {
            key: value for key, value in missing_wall_time.items() if key != "result_sha256"
        }
        missing_wall_time["result_sha256"] = _json_sha256(missing_wall_base)
        _expect_refusal(
            "replay without authoritative outer time",
            validate_registered_result,
            missing_wall_time,
            transcript=transcript,
            manifest=manifest,
            registry=registry,
            authority=authority,
            ledger=loaded,
            ledger_binding=binding,
        )
        tampered_result = deepcopy(complete_result)
        tampered_result["corpus_receipts"][0]["validated_response_sha256"] = "0" * 64
        _expect_refusal(
            "tampered full classifier replay",
            validate_registered_result,
            tampered_result,
            transcript=transcript,
            manifest=manifest,
            registry=registry,
            authority=authority,
            ledger=loaded,
            ledger_binding=binding,
        )

        input_path = temporary_root / "input.json"
        input_path.write_text("{}")
        alias_path = temporary_root / "input-alias.json"
        os.link(input_path, alias_path)
        _expect_refusal(
            "aliased classifier result target",
            validate_result_target,
            alias_path,
            [input_path],
        )

        target = temporary_root / "result.json"
        wrote = write_private_result(target, complete_result, [input_path])
        assert wrote.read_bytes() == _json_bytes(complete_result)
        assert stat.S_IMODE(wrote.stat().st_mode) == 0o600
        _expect_refusal(
            "existing classifier result",
            write_private_result,
            target,
            complete_result,
            [input_path],
        )

        failed_target = temporary_root / "failed-result.json"

        def fail_result() -> dict:
            raise StructuredOutputError("synthetic incomplete run")

        _expect_refusal(
            "failed run result installation",
            produce_and_write_private_result,
            failed_target,
            [input_path],
            fail_result,
        )
        assert not failed_target.exists()

    print("all classifier runner controls behaved as specified; no network used")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("corpus", type=Path, nargs="?")
    parser.add_argument("--review-reference", type=Path)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--event-ledger", type=Path)
    parser.add_argument("--ledger-lock", type=Path)
    parser.add_argument("--approved-lock-sha256")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    required = {
        "corpus": args.corpus,
        "--review-reference": args.review_reference,
        "--review-decisions": args.review_decisions,
        "--event-ledger": args.event_ledger,
        "--ledger-lock": args.ledger_lock,
        "--approved-lock-sha256": args.approved_lock_sha256,
    }
    missing = [label for label, value in required.items() if value is None]
    if missing:
        parser.error(f"required for a registered run: {', '.join(missing)}")
    if isinstance(args.timeout, bool) or not isinstance(args.timeout, int) or args.timeout <= 0:
        parser.error("--timeout must be a positive integer")
    if args.replay is not None and args.out is not None:
        parser.error("--replay validates an existing result and cannot use --out")
    if args.replay is None and args.out is None:
        parser.error("--out is required for a live registered run")
    corpus_path = args.corpus
    reference_path = args.review_reference
    decisions_path = args.review_decisions
    ledger_path = args.event_ledger
    lock_path = args.ledger_lock
    assert corpus_path is not None
    assert reference_path is not None
    assert decisions_path is not None
    assert ledger_path is not None
    assert lock_path is not None
    try:
        if args.replay is not None:
            result = replay_registered_result(
                corpus_path,
                reference_path,
                decisions_path,
                ledger_path,
                lock_path,
                args.approved_lock_sha256,
                args.replay,
            )
            print(f"replayed registered classifier result {result['result_sha256']}: passed")
            return 0

        assert args.out is not None
        input_paths = [
            corpus_path,
            reference_path,
            decisions_path,
            ledger_path,
            lock_path,
        ]
        target = produce_and_write_private_result(
            args.out,
            input_paths,
            lambda: run_registered_classifier(
                corpus_path,
                reference_path,
                decisions_path,
                ledger_path,
                lock_path,
                args.approved_lock_sha256,
                transport=OllamaTransport(),
                timeout=args.timeout,
            ),
        )
    except StructuredOutputError as exc:
        raise SystemExit(f"registered classifier refused: {exc}") from exc
    print(f"wrote private passing classifier result {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
