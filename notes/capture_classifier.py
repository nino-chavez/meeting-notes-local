# ruff: noqa: E501
"""Run the candidate-first classifier against a private capture ledger.

The private counterpart of classifier_runner.py. The classifier contract is
identical — same system prompt, fixtures, sabotage controls, model pin, batch
size, decoding, receipts, and 900-second outer budget. What changes is the
corpus: instead of the registered public ES2004c transcript, the inputs are a
Yawn capture transcript and the operator-locked ledger produced by
capture_exposure.py, validated with the registered-corpus pins off. Expected
batch and decision counts derive from the capture's own manifest.

This lane has no replay validator yet; the live run retains the same replayable
receipts as the registered lane, and a replay mode is deliberately deferred
until one is needed. Every output is private (mode 0600) and stays outside Git.

Usage:
    python notes/capture_classifier.py TRANSCRIPT REFERENCE DECISIONS LEDGER LOCK \
      --approved-lock-sha256 SHA256 --out RESULT.json
    python notes/capture_classifier.py --self-test
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Callable

import hashlib

from candidate_first import (
    REGISTERED_RUN,
    STRATEGY_BROAD,
    _json_bytes,
    _json_sha256,
    classification_request,
    classifier_fixture_sha256,
    classifier_system_sha256,
    generate_manifest,
    registered_run_sha256,
)
from capture_exposure import capture_review_view, identity_coordinates
from classifier_runner import (
    CORPUS_CALL,
    ELAPSED_LIMIT_SECONDS,
    EXPECTED_FIXTURES,
    KEEP_LIMIT,
    OllamaTransport,
    REGISTERED_BATCH_SIZE,
    REGISTERED_SYSTEM,
    ClassifierTransport,
    _finalize_live_elapsed,
    _preflight_specs,
    _resolve_model_identity,
    _validate_preflight_semantics,
    candidate_batches,
    deterministic_sabotage_controls,
    event_ledger_report,
    load_locked_review_preflight,
    perform_call,
    produce_and_write_private_result,
    validate_corpus_receipts,
    validate_preflight_receipts,
)
from summarize import StructuredOutputError
from transcript import Transcript, load


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

RESULT_SCHEMA = "capture-classifier-result/1"
HARNESS_REGISTRATION_SHA256 = (
    "cf377030002773496ce98c221a6f15120028e258bace236b2ba260e9175744e4"
)


def derive_capture_inputs(corpus_path: Path) -> tuple[Transcript, dict]:
    """Re-derive every no-model input from the private capture transcript."""
    view = capture_review_view(load(corpus_path))
    first_manifest = generate_manifest(view, STRATEGY_BROAD)
    second_manifest = generate_manifest(view, STRATEGY_BROAD)
    if _json_bytes(first_manifest) != _json_bytes(second_manifest):
        raise StructuredOutputError(
            "capture candidate manifest changed between two local generations"
        )
    # The corpus is private, but the harness version is still the ratcheted
    # registration: a changed prompt, fixture, or contract refuses here rather
    # than silently producing incomparable results.
    if classifier_system_sha256() != REGISTERED_RUN["classifier"]["system_sha256"]:
        raise StructuredOutputError("registered classifier system prompt changed")
    if classifier_fixture_sha256() != REGISTERED_RUN["classifier"]["fixture_sha256"]:
        raise StructuredOutputError("registered classifier fixtures changed")
    if registered_run_sha256() != HARNESS_REGISTRATION_SHA256:
        raise StructuredOutputError("candidate classifier registration changed")
    return view, first_manifest


def _capture_summary(
    decisions: list[dict],
    preflight_elapsed: float,
    corpus_elapsed: float,
    exposure: dict,
    expected_decisions: int,
    expected_batches: int,
) -> dict:
    keep = sum(row["verdict"] == "KEEP" for row in decisions)
    abstain = sum(row["verdict"] == "ABSTAIN" for row in decisions)
    if keep > KEEP_LIMIT:
        raise StructuredOutputError(
            f"classifier kept {keep} candidates; registered maximum is {KEEP_LIMIT}"
        )
    return {
        "fixture_agreement": EXPECTED_FIXTURES,
        "model_sabotage_calls_rejected": 2,
        "corpus_batches": expected_batches,
        "decisions": expected_decisions,
        "decision_order_sha256": _json_sha256(decisions),
        "keep": keep,
        "abstain": abstain,
        "all_abstentions_retained": keep + abstain == expected_decisions,
        "maximum_keep": KEEP_LIMIT,
        "preflight_transport_elapsed_seconds": preflight_elapsed,
        "corpus_transport_elapsed_seconds": corpus_elapsed,
        "receipt_transport_elapsed_seconds": preflight_elapsed + corpus_elapsed,
        "authoritative_run_elapsed_seconds": None,
        "maximum_elapsed_seconds": ELAPSED_LIMIT_SECONDS,
        "event_packet_exposure": exposure["packet_exposed"],
        "event_classifier_recall": exposure["classifier_recalled"],
        "event_targets": exposure["events"],
    }


def run_capture_classifier(
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
    """Run the fixed classifier on a capture ledger; return only a passing result."""
    run_started = monotonic()
    if not math.isfinite(run_started):
        raise StructuredOutputError("classifier monotonic clock returned a non-finite value")
    active_deadline = run_started + ELAPSED_LIMIT_SECONDS
    view, manifest = derive_capture_inputs(corpus_path)
    expected_decisions = manifest["counts"]["candidates"]
    expected_batches = len(candidate_batches(manifest["candidates"], REGISTERED_BATCH_SIZE))

    # Ledger, lock, approval, and packet exposure precede any model resolution.
    ledger, _lock, ledger_binding, packet_exposure = load_locked_review_preflight(
        corpus_path,
        reference_path,
        decisions_path,
        ledger_path,
        lock_path,
        view,
        manifest,
        approved_lock_sha256,
        enforce_registered=False,
        coordinates=identity_coordinates(view),
    )
    deterministic_controls = deterministic_sabotage_controls()

    classifier = REGISTERED_RUN["classifier"]
    identity_start = _resolve_model_identity(
        transport, classifier["model"], timeout, active_deadline, monotonic)
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
    batches = candidate_batches(manifest["candidates"], REGISTERED_BATCH_SIZE)
    for batch_ordinal, batch in enumerate(batches, 1):
        schema, system, user = classification_request(
            view, manifest, batch, REGISTERED_BATCH_SIZE)
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
        transport, classifier["model"], timeout, active_deadline, monotonic)
    if identity_end != identity_start:
        raise StructuredOutputError("classifier model identity changed during the capture run")

    preflight_elapsed = validate_preflight_receipts(preflight_receipts, identity_start)
    decisions, corpus_elapsed = validate_corpus_receipts(
        corpus_receipts,
        view,
        manifest,
        identity_start,
        expected_batches=expected_batches,
        expected_decisions=expected_decisions,
    )
    exposure = event_ledger_report(
        ledger, manifest, decisions, packet_exposure=packet_exposure)
    summary = _capture_summary(
        decisions, preflight_elapsed, corpus_elapsed, exposure,
        expected_decisions, expected_batches)
    base = {
        "schema_contract": RESULT_SCHEMA,
        "registration_sha256": registered_run_sha256(),
        "inputs": {
            "corpus": "private capture (content not recorded here)",
            "raw_corpus_sha256": _file_sha256(corpus_path),
            "transcript_view_sha256": manifest["transcript_view_sha256"],
            "manifest_sha256": manifest["manifest_sha256"],
            "generator_contract_sha256": manifest["generator_contract_sha256"],
            "fragment_contract_sha256": manifest["fragment_contract_sha256"],
            "classifier_system_sha256": classifier_system_sha256(),
            "classifier_fixture_sha256": classifier_fixture_sha256(),
            "manifest_candidates": manifest["counts"]["candidates"],
            "manifest_generations": 2,
            "manifest_byte_identical": True,
        },
        "ledger_lock": ledger_binding,
        "deterministic_controls": deterministic_controls,
        "model_identity_start": identity_start,
        "model_identity_end": identity_end,
        "options": {
            "batch_size": REGISTERED_BATCH_SIZE,
            "num_ctx": classifier["num_ctx"],
            "temperature": classifier["temperature"],
            "num_predict": classifier["num_predict"],
        },
        "preflight_receipts": preflight_receipts,
        "corpus_receipts": corpus_receipts,
        "summary": summary,
        "event_ledger_report": exposure,
        "passed": True,
        "meaning": (
            "private-capture classifier feasibility measurement against an "
            "operator-locked ledger; not a scored note, a claim-generation "
            "result, or evidence about any other meeting"
        ),
    }
    result = {**base, "result_sha256": _json_sha256(base)}
    return _finalize_live_elapsed(result, run_started, monotonic)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, nargs="?")
    parser.add_argument("review_reference", type=Path, nargs="?")
    parser.add_argument("review_decisions", type=Path, nargs="?")
    parser.add_argument("event_ledger", type=Path, nargs="?")
    parser.add_argument("ledger_lock", type=Path, nargs="?")
    parser.add_argument("--approved-lock-sha256")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    required = (
        args.corpus, args.review_reference, args.review_decisions,
        args.event_ledger, args.ledger_lock, args.approved_lock_sha256, args.out,
    )
    if not all(required):
        parser.error(
            "corpus, review reference, review decisions, ledger, lock, "
            "--approved-lock-sha256, and --out are required")
    input_paths = [
        args.corpus, args.review_reference, args.review_decisions,
        args.event_ledger, args.ledger_lock,
    ]
    try:
        target = produce_and_write_private_result(
            args.out,
            input_paths,
            lambda: run_capture_classifier(
                args.corpus,
                args.review_reference,
                args.review_decisions,
                args.event_ledger,
                args.ledger_lock,
                args.approved_lock_sha256,
                transport=OllamaTransport(),
                timeout=args.timeout,
            ),
        )
    except StructuredOutputError as exc:
        raise SystemExit(f"capture classifier refused: {exc}") from exc
    print(f"wrote private passing capture classifier result {target}")
    return 0


def _self_test() -> int:
    """Exercise the capture-specific trust boundaries without network access."""
    from transcript import Turn

    # The harness-version ratchet holds for this module's own constants.
    if registered_run_sha256() != HARNESS_REGISTRATION_SHA256:
        raise AssertionError("module registration pin does not match the live registration")

    # Manifest determinism and count derivation on a fixture view.
    fixture = Transcript(
        source="capture classifier fixture", attribution="channel", turns=[
            Turn(text="We agreed to ship on Friday.", speaker="Me"),
            Turn(text="I will draft the announcement.", speaker="Them"),
        ])
    view = capture_review_view(fixture)
    manifest = generate_manifest(view, STRATEGY_BROAD)
    expected = manifest["counts"]["candidates"]
    batches = candidate_batches(manifest["candidates"], REGISTERED_BATCH_SIZE)
    assert sum(len(batch) for batch in batches) == expected
    assert len(batches) == (expected + REGISTERED_BATCH_SIZE - 1) // REGISTERED_BATCH_SIZE

    # The summary refuses a keep count above the registered limit.
    decisions = [
        {"candidate_id": f"cf-{index:03d}", "verdict": "KEEP"}
        for index in range(KEEP_LIMIT + 1)
    ]
    try:
        _capture_summary(
            decisions, 0.0, 0.0,
            {"packet_exposed": True, "classifier_recalled": True, "events": 1},
            len(decisions), 1)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("an over-limit keep count was accepted")

    # The one seam that differs from the registered lane — preflight with
    # identity coordinates on a capture-shaped corpus — is exercised end to
    # end: fixture corpus file, reference, decisions, ledger, and approved
    # lock, through load_locked_review_preflight itself.
    import hashlib as _hashlib
    import json as _json
    import tempfile

    from candidate_exposure import (
        build_pending_ledger_lock,
        build_runner_ledger,
        create_reference,
        validate_review_decisions,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        corpus_file = tmpdir / "transcript.json"
        corpus_file.write_text(_json.dumps({
            "source": "capture classifier preflight fixture",
            "attribution": "channel",
            "turns": [
                {"text": turn.text, "speaker": turn.speaker}
                for turn in fixture.turns
            ],
        }))
        file_view = capture_review_view(load(corpus_file))
        file_manifest = generate_manifest(file_view, STRATEGY_BROAD)
        events = [{
            "event_id": "draft-001", "kind": "DECISION",
            "neutral_atomic_proposition": "The ship date is Friday.",
            "type_specific": {"temporal_status": "PENDING_OPERATOR_REVIEW"},
            "acceptable_candidate_ids": [
                file_manifest["candidates"][0]["candidate_id"]],
        }]
        coordinates = identity_coordinates(file_view)
        regions = {
            "schema": "candidate-exposure-review-regions/1",
            "coordinate_contract": {
                "schema": "candidate-exposure-coordinate-contract/1",
                "canonical_ordinals": "zero-based",
                "character_spans": "zero-based half-open",
                "display_labels": "one-based and noncanonical",
                "review_region_ranges": "zero-based raw-turn ordinals, inclusive",
            },
            "regions": [],
        }
        reference = create_reference(
            file_view, file_manifest, events,
            corpus_sha256=_file_sha256(corpus_file),
            coordinates=coordinates, regions=regions, section_size=2,
            enforce_registered=False)
        decisions = {
            "schema": "candidate-exposure-review-decisions/2",
            "reference_sha256": reference["reference_sha256"],
            "registration_sha256": reference["source"]["registration_sha256"],
            "events": [{
                "event_id": "draft-001", "disposition": "ACCEPT",
                "kind": "DECISION",
                "neutral_atomic_proposition": "The ship date is Friday.",
                "selected_bundle_sha256": [
                    reference["events"][0]["evidence_bundles"][0]["bundle_sha256"]],
                "ambiguity_reason": "", "notes": "",
            }],
            "sections": [
                {"section_id": row["section_id"], "reviewed": True,
                 "resolution": "NO_MISSING_EVENT", "notes": ""}
                for row in reference["sections"]
            ],
        }
        ledger = build_runner_ledger(
            validate_review_decisions(decisions, reference), reference)
        lock = build_pending_ledger_lock(
            ledger, file_manifest, prepared_at="fixture")
        reference_file = tmpdir / "reference.json"
        decisions_file = tmpdir / "decisions.json"
        ledger_file = tmpdir / "ledger.json"
        lock_file = tmpdir / "lock.json"
        reference_file.write_bytes(_json_bytes(reference))
        decisions_file.write_bytes(_json_bytes(decisions))
        ledger_file.write_bytes(_json_bytes(ledger))
        lock_bytes = _json_bytes(lock)
        lock_file.write_bytes(lock_bytes)
        approved = _hashlib.sha256(lock_bytes).hexdigest()
        loaded_ledger, _lock, binding, exposure = load_locked_review_preflight(
            corpus_file, reference_file, decisions_file, ledger_file, lock_file,
            file_view, file_manifest, approved,
            enforce_registered=False,
            coordinates=coordinates,
        )
        assert loaded_ledger["events"][0]["event_id"] == "draft-001"
        assert exposure["all_bundles_packet_exposed"] is True
        assert binding["review_artifacts"]["review_reference_sha256"] == (
            reference["reference_sha256"])

    # Constructing the adapter performs no network operation by contract; the
    # protocol surface is checked structurally.
    transport = OllamaTransport()
    assert callable(transport.resolve_model) and callable(transport.chat)
    print("capture classifier self-test: OK; no network used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
