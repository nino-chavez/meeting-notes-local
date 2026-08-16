# ruff: noqa: E501
"""Official product-lane runner: MLX constrained verdicts at batch size 1, pruned.

Implements the product registration (candidate_first.PRODUCT_RUN, digest
pinned below): the adopted two-fragment window, the gemma3 two-turn prompt
rendering, one greedy KEEP/ABSTAIN choice per candidate, the registered
contiguous-run pruning stage, and the ship gates applied to the pruned set.
Every artifact binds product_run_sha256(); the research registration and its
consumers are untouched.

Usage:
    python notes/product_run.py cycle TRANSCRIPT EVENTS --out DIR
    python notes/product_run.py run TRANSCRIPT --cycle DIR \
      --approved-lock-sha256 HEX --model-dir SNAPSHOT --out RESULT.json
    python notes/product_run.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Protocol

from candidate_exposure import (
    _private_target,
    _read_json,
    _write_private,
    build_pending_ledger_lock,
    build_runner_ledger,
    create_reference,
    validate_reference,
    validate_review_decisions,
)
from candidate_first import (
    PRODUCT_CONTRACT,
    PRODUCT_RUN,
    STRATEGY_BROAD,
    _json_bytes,
    _json_sha256,
    _sha256,
    candidate_batches,
    classification_num_predict,
    classification_request,
    offered_candidates,
    decode_classification,
    generate_manifest,
    product_run_sha256,
    prune_keeps,
    validate_manifest,
)
from capture_exposure import capture_review_view, empty_regions, identity_coordinates
from summarize import StructuredOutputError
from transcript import Transcript, Turn, load

PRODUCT_REGISTRATION_SHA256 = (
    "baaac5aadf61eb3700b4e2cd8127ec5340998856621da11f0579f46fd9f459a9"
)

RESULT_SCHEMA = "product-run-result/1"
ELAPSED_LIMIT_SECONDS = PRODUCT_RUN["gates"]["maximum_elapsed_seconds"]
KEEP_LIMIT = PRODUCT_RUN["gates"]["maximum_keep_after_prune"]


def _require_current_registration() -> None:
    if product_run_sha256() != PRODUCT_REGISTRATION_SHA256:
        raise StructuredOutputError(
            "the product registration changed; re-pin PRODUCT_REGISTRATION_SHA256 "
            "only through a preregistered amendment")


class VerdictTransport(Protocol):
    """One registered verdict per offered candidate locator."""

    def identity(self) -> dict:
        """Resolve and verify the model identity; refuse on any drift."""

    def decide(self, system: str, user: str, locators: list[str]) -> list[str]:
        """Return one KEEP/ABSTAIN per locator, in offered order."""


class MLXVerdictTransport:
    """The registered mlx-constrained-verdict/1 transport.

    Deterministic response skeleton in the registered shape and offered
    order; the model contributes one greedy first-token KEEP/ABSTAIN choice
    per candidate, scored with the full prompt and all prior forced tokens
    in context, under the gemma3-two-turn/1 rendering.
    """

    def __init__(self, model_dir: Path):
        self._model_dir = Path(model_dir)
        self._model = None
        self._tokenizer = None

    def identity(self) -> dict:
        from mlx_note_admission import tree_sha256

        pinned = PRODUCT_RUN["classifier"]
        observed_tree = tree_sha256(self._model_dir)
        if observed_tree != pinned["model_tree_sha256"]:
            raise StructuredOutputError(
                "product model tree digest does not match the registration")
        if self._model_dir.name != pinned["model_snapshot"]:
            raise StructuredOutputError(
                "product model snapshot does not match the registration")
        return {
            "model": pinned["model"],
            "model_snapshot": self._model_dir.name,
            "model_tree_sha256": observed_tree,
            "transport": pinned["transport"],
            "prompt_rendering": pinned["prompt_rendering"],
        }

    def _load(self):
        if self._model is None:
            from mlx_lm import load as mlx_load

            self._model, self._tokenizer = mlx_load(str(self._model_dir))
        return self._model, self._tokenizer

    def decide(self, system: str, user: str, locators: list[str]) -> list[str]:
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache

        model, tok = self._load()
        keep_first = tok.encode("KEEP", add_special_tokens=False)[0]
        abstain_first = tok.encode("ABSTAIN", add_special_tokens=False)[0]
        if keep_first == abstain_first:
            raise StructuredOutputError(
                "verdict options do not diverge at the first token")
        text = (
            "<start_of_turn>user\n" + system + "<end_of_turn>\n"
            + "<start_of_turn>user\n" + user + "<end_of_turn>\n"
            + "<start_of_turn>model\n"
        )
        tokens = [tok.bos_token_id] + tok.encode(text, add_special_tokens=False)
        cache = make_prompt_cache(model)

        def feed(chunk_tokens: list[int], chunk: int = 2048):
            last = None
            for start in range(0, len(chunk_tokens), chunk):
                logits = model(
                    mx.array([chunk_tokens[start:start + chunk]]), cache=cache)
                last = logits[0, -1, :]
                mx.eval(last)
            return last

        last = feed(tokens)
        verdicts = []
        for index, locator in enumerate(locators):
            prefix = ("" if index == 0 else ", ") + \
                '{"candidate_id": ' + json.dumps(locator) + ', "verdict": "'
            last = feed(tok.encode(prefix, add_special_tokens=False))
            verdict = (
                "KEEP" if last[keep_first].item() > last[abstain_first].item()
                else "ABSTAIN"
            )
            verdicts.append(verdict)
            last = feed(tok.encode(verdict + '"}', add_special_tokens=False))
        # The registered batch size is 1, so this runs once per candidate and a
        # real meeting offers up to a few hundred — mlx's allocator caches freed
        # scratch buffers for reuse rather than returning them to the OS, and
        # nothing here ever reuses a cache across calls (each call builds its
        # own above), so without this the cache grows unbounded across the run
        # instead of staying near one batch's peak.
        mx.clear_cache()
        return verdicts


def _assemble_contract_response(locators: list[str], verdicts: list[str]) -> str:
    items = ", ".join(
        '{"candidate_id": ' + json.dumps(locator) + ', "verdict": "' + verdict + '"}'
        for locator, verdict in zip(locators, verdicts, strict=True)
    )
    return '{"items": [' + items + "]}"


def accept_all_decisions(reference: dict, *, provenance_note: str) -> dict:
    """Bulk-ratification decisions; the caller records who authorized them."""
    if not provenance_note.strip():
        raise StructuredOutputError(
            "bulk acceptance requires a recorded provenance note")
    return {
        "schema": "candidate-exposure-review-decisions/2",
        "reference_sha256": reference["reference_sha256"],
        "registration_sha256": reference["source"]["registration_sha256"],
        "events": [{
            "event_id": event["event_id"],
            "disposition": "ACCEPT",
            "kind": event["kind"],
            "neutral_atomic_proposition": event["neutral_atomic_proposition"],
            "selected_bundle_sha256": [
                bundle["bundle_sha256"] for bundle in event["evidence_bundles"]
            ],
            "ambiguity_reason": "",
            "notes": "",
        } for event in reference["events"]],
        "sections": [
            {"section_id": row["section_id"], "reviewed": True,
             "resolution": "NO_MISSING_EVENT", "notes": ""}
            for row in reference["sections"]
        ],
    }


def build_product_cycle(
    transcript_path: Path,
    events: object,
    out_dir: Path,
    *,
    provenance_note: str,
) -> dict:
    """Reference -> bulk decisions -> ledger -> pending lock, product-bound."""
    _require_current_registration()
    view = capture_review_view(load(transcript_path))
    manifest = generate_manifest(view, STRATEGY_BROAD, contract=PRODUCT_CONTRACT)
    coordinates = identity_coordinates(view)
    regions = empty_regions()
    reference = create_reference(
        view, manifest, events,
        corpus_sha256=_sha256(transcript_path.read_bytes()),
        coordinates=coordinates,
        regions=regions,
        enforce_registered=False,
        registration_sha256=product_run_sha256(),
    )
    validate_reference(
        reference, view, manifest, coordinates, regions,
        enforce_registered=False)
    decisions = validate_review_decisions(
        accept_all_decisions(reference, provenance_note=provenance_note),
        reference, registration_sha256=product_run_sha256())
    ledger = build_runner_ledger(
        decisions, reference, registration_sha256=product_run_sha256())
    pending_lock = build_pending_ledger_lock(
        ledger, manifest, registration_sha256=product_run_sha256())
    lock_bytes = _json_bytes(pending_lock)
    _write_private(
        _private_target(out_dir, "PROVENANCE.md"),
        ("# Cycle provenance\n\n" + provenance_note.strip() + "\n").encode())
    _write_private(_private_target(out_dir, "product-reference.json"), _json_bytes(reference))
    _write_private(_private_target(out_dir, "product-manifest.json"), _json_bytes(manifest))
    _write_private(
        _private_target(out_dir, "product-review-decisions.validated.json"),
        _json_bytes(decisions))
    _write_private(_private_target(out_dir, "product-events.json"), _json_bytes(ledger))
    _write_private(
        _private_target(out_dir, "product-lock.pending.json"), lock_bytes)
    return {
        "ledger_sha256": ledger["ledger_sha256"],
        "lock_file_sha256": _sha256(lock_bytes),
        "registration_sha256": product_run_sha256(),
    }


def _event_recall(ledger: dict, manifest: dict, keep_ids: set[str]) -> dict:
    visible = {
        row["candidate_id"]: set(row["visible_fragment_ids"])
        for row in manifest["candidates"]
    }
    rows = []
    for event in ledger["events"]:
        recalled = any(
            set(bundle).issubset(visible[cid])
            for bundle in event["acceptable_evidence_bundles"]
            for cid in keep_ids
        )
        rows.append({"event_id": event["event_id"], "recalled": recalled})
    recalled_count = sum(row["recalled"] for row in rows)
    total = len(rows)
    return {
        "events": total,
        "recalled": recalled_count,
        "gate": "recalled * 13 >= 11 * events",
        "gate_pass": recalled_count * 13 >= 11 * total,
        "rows": rows,
    }


def _refusal_diagnostics(
    decisions_rows: list[dict], pruned: dict, recall: dict, elapsed: float,
) -> None:
    """Report gate numbers before a refusal; a refused run must still say how far it missed.

    The optional dump carries candidate ids and verdicts only, never
    transcript text.
    """
    diagnostic = {
        "schema": "product-run-refusal-diagnostic/1",
        "counts": {
            "candidates": len(decisions_rows),
            "keep": sum(row["verdict"] == "KEEP" for row in decisions_rows),
            "pruned_keep": pruned["counts"]["pruned_keep"],
            "runs": pruned["counts"]["runs"],
        },
        "recall": recall,
        "elapsed_seconds": round(elapsed, 3),
    }
    dump_path = os.environ.get("YAWN_DECISIONS_DUMP")
    if dump_path:
        Path(dump_path).write_text(json.dumps(
            {"diagnostic": diagnostic, "decisions": decisions_rows},
            indent=1) + "\n")
    if (
        pruned["counts"]["pruned_keep"] > KEEP_LIMIT
        or not recall["gate_pass"]
        or elapsed > ELAPSED_LIMIT_SECONDS
    ):
        print(json.dumps(diagnostic, indent=1), file=sys.stderr)


def run_product_classifier(
    transcript_path: Path,
    cycle_dir: Path,
    approved_lock_sha256: str,
    transport: VerdictTransport,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Run the registered product pipeline under an approved lock; gate or refuse."""
    _require_current_registration()
    started = monotonic()
    deadline = started + ELAPSED_LIMIT_SECONDS
    view = capture_review_view(load(transcript_path))
    manifest = generate_manifest(view, STRATEGY_BROAD, contract=PRODUCT_CONTRACT)
    validate_manifest(manifest, view)

    stored_manifest = _read_json(cycle_dir / "product-manifest.json", "product manifest")
    if _json_bytes(stored_manifest) != _json_bytes(manifest):
        raise StructuredOutputError(
            "the stored product manifest does not re-derive from the transcript")
    reference = _read_json(cycle_dir / "product-reference.json", "product reference")
    coordinates = identity_coordinates(view)
    regions = empty_regions()
    validate_reference(
        reference, view, manifest, coordinates, regions, enforce_registered=False)
    decisions = _read_json(
        cycle_dir / "product-review-decisions.validated.json", "review decisions")
    decisions = validate_review_decisions(
        decisions, reference, registration_sha256=product_run_sha256())
    ledger = _read_json(cycle_dir / "product-events.json", "runner ledger")
    expected_ledger = build_runner_ledger(
        decisions, reference, registration_sha256=product_run_sha256())
    if _json_bytes(ledger) != _json_bytes(expected_ledger):
        raise StructuredOutputError("the runner ledger does not re-derive")
    lock_bytes = (cycle_dir / "product-lock.pending.json").read_bytes()
    if _sha256(lock_bytes) != approved_lock_sha256:
        raise StructuredOutputError(
            "the approved lock digest does not match the stored lock bytes")
    lock = json.loads(lock_bytes)
    if (
        lock.get("ledger_sha256") != ledger["ledger_sha256"]
        or lock.get("registration_sha256") != product_run_sha256()
    ):
        raise StructuredOutputError("the approved lock does not bind this ledger")

    identity = transport.identity()
    decisions_rows: list[dict] = []
    offered = offered_candidates(
        manifest["candidates"], PRODUCT_RUN["classifier"]["offer_stride"])
    for batch in candidate_batches(
            offered, PRODUCT_RUN["classifier"]["batch_size"]):
        if monotonic() > deadline:
            raise StructuredOutputError(
                "the product run exceeded its registered time budget")
        _schema, system, user = classification_request(
            view, manifest, batch, PRODUCT_RUN["classifier"]["batch_size"],
            offer_stride=PRODUCT_RUN["classifier"]["offer_stride"])
        candidate_ids = [row["candidate_id"] for row in batch]
        from candidate_first import batch_locators

        locators = batch_locators(candidate_ids)
        verdicts = transport.decide(system, user, locators)
        if len(verdicts) != len(locators) or any(
                verdict not in {"KEEP", "ABSTAIN"} for verdict in verdicts):
            raise StructuredOutputError(
                "the verdict transport returned an invalid verdict set")
        decoded = decode_classification(
            _assemble_contract_response(locators, verdicts), candidate_ids)
        decisions_rows.extend(decoded["items"])
    if len(decisions_rows) != len(offered):
        raise StructuredOutputError(
            "the product run did not decide every offered candidate exactly once")

    pruned = prune_keeps(
        offered, decisions_rows,
        budget=PRODUCT_RUN["pruner"]["budget"],
        stride_floor=PRODUCT_RUN["pruner"]["stride_floor"],
        max_gap=PRODUCT_RUN["pruner"]["max_gap"])
    recall = _event_recall(ledger, manifest, set(pruned["pruned_candidate_ids"]))
    elapsed = monotonic() - started
    _refusal_diagnostics(decisions_rows, pruned, recall, elapsed)
    if pruned["counts"]["pruned_keep"] > KEEP_LIMIT:
        raise StructuredOutputError(
            "the pruned keep set exceeds the registered budget")
    if not recall["gate_pass"]:
        raise StructuredOutputError(
            "the pruned keep set does not meet the registered recall gate")
    if elapsed > ELAPSED_LIMIT_SECONDS:
        raise StructuredOutputError(
            "the product run exceeded its registered time budget")
    base = {
        "schema": RESULT_SCHEMA,
        "registration_sha256": product_run_sha256(),
        "ledger_sha256": ledger["ledger_sha256"],
        "approved_lock_sha256": approved_lock_sha256,
        "model_identity": identity,
        "counts": {
            "candidates": manifest["counts"]["candidates"],
            "offered": len(offered),
            "keep": sum(row["verdict"] == "KEEP" for row in decisions_rows),
            "pruned_keep": pruned["counts"]["pruned_keep"],
            "runs": pruned["counts"]["runs"],
        },
        "pruned_candidate_ids": pruned["pruned_candidate_ids"],
        "recall": recall,
        "elapsed_seconds": round(elapsed, 3),
    }
    return {**base, "result_sha256": _json_sha256(base)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("cycle", "run"))
    parser.add_argument("transcript", type=Path, nargs="?")
    parser.add_argument("events", type=Path, nargs="?")
    parser.add_argument("--cycle", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--approved-lock-sha256")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--provenance-note", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if args.mode == "cycle":
        if not all((args.transcript, args.events, args.out)):
            parser.error("cycle requires transcript, events, and --out")
        summary = build_product_cycle(
            args.transcript, _read_json(args.events, "event input"), args.out,
            provenance_note=args.provenance_note)
        print(json.dumps(summary, indent=1))
        return 0
    if args.mode == "run":
        if not all((args.transcript, args.cycle, args.approved_lock_sha256,
                    args.model_dir, args.out)):
            parser.error(
                "run requires transcript, --cycle, --approved-lock-sha256, "
                "--model-dir, and --out")
        result = run_product_classifier(
            args.transcript, args.cycle, args.approved_lock_sha256,
            MLXVerdictTransport(args.model_dir))
        _write_private(
            _private_target(args.out.parent, args.out.name), _json_bytes(result))
        print(json.dumps({key: result[key] for key in (
            "counts", "recall", "elapsed_seconds", "result_sha256")}, indent=1))
        return 0
    parser.error("mode is required")
    return 2


class _StubTransport:
    """Self-test transport: verdicts from a fixed map, identity canned."""

    def __init__(self, keep_ordinals: set[int], manifest: dict):
        self._keep_ids = {
            row["candidate_id"] for row in manifest["candidates"]
            if row["ordinal"] in keep_ordinals
        }
        # The run offers the registered strided subset; the stub's cursor
        # must walk the same sequence the runner batches.
        self._offer = offered_candidates(
            manifest["candidates"], PRODUCT_RUN["classifier"]["offer_stride"])

    def identity(self) -> dict:
        return {"model": "stub", "model_tree_sha256": "0" * 64}

    def decide(self, system: str, user: str, locators: list[str]) -> list[str]:
        # locators arrive one per call at the registered batch size; map the
        # single offered candidate through the request order.
        verdicts = []
        offset = getattr(self, "_cursor", 0)
        for index, _locator in enumerate(locators):
            row = self._offer[offset + index]
            verdicts.append(
                "KEEP" if row["candidate_id"] in self._keep_ids else "ABSTAIN")
        self._cursor = offset + len(locators)
        return verdicts


def _self_test() -> int:
    import tempfile

    _require_current_registration()
    turns = [
        Turn(text=f"Row {index} carries meeting speech content number {index}.")
        for index in range(12)
    ]
    turns[3] = Turn(text="We agreed the launch moves to Friday after review.")
    turns[9] = Turn(text="I will send the revised budget to the group tomorrow.")
    transcript = Transcript(
        source="product run fixture", attribution="channel", turns=turns)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        transcript_path = tmp_path / "fixture-transcript.json"
        transcript_path.write_text(json.dumps({
            "attribution": "channel",
            "turns": [{"speaker": "Me", "text": turn.text} for turn in turns],
        }))
        view = capture_review_view(load(transcript_path))
        manifest = generate_manifest(view, STRATEGY_BROAD, contract=PRODUCT_CONTRACT)
        by_turn = {}
        for row in manifest["candidates"]:
            by_turn.setdefault(row["anchor_turn"], []).append(row["candidate_id"])
        events = [
            {"event_id": "ev-001", "kind": "DECISION",
             "neutral_atomic_proposition": "The launch moves to Friday.",
             "type_specific": {"temporal_status": "PENDING_OPERATOR_REVIEW"},
             "acceptable_candidate_ids": by_turn[3]},
            {"event_id": "ev-002", "kind": "ACTION",
             "neutral_atomic_proposition": "The revised budget is sent tomorrow.",
             "type_specific": {"commitment_status": "PENDING_OPERATOR_REVIEW"},
             "acceptable_candidate_ids": by_turn[9]},
        ]
        cycle_dir = tmp_path / "cycle"
        cycle_dir.mkdir(mode=0o700)
        summary = build_product_cycle(
            transcript_path, events, cycle_dir,
            provenance_note="self-test fixture ratification")
        assert summary["registration_sha256"] == PRODUCT_REGISTRATION_SHA256

        # An event's anchor candidate may fall outside the strided offer;
        # recall only needs some KEPT offered candidate whose visible window
        # covers the event's anchor fragment, so pick those.
        offered = offered_candidates(
            manifest["candidates"], PRODUCT_RUN["classifier"]["offer_stride"])
        anchor_of = {row["candidate_id"]: row["anchor_fragment_id"]
                     for row in manifest["candidates"]}

        def covering_ordinal(turn: int) -> int:
            target = anchor_of[by_turn[turn][0]]
            return next(
                row["ordinal"] for row in offered
                if target in row["visible_fragment_ids"])

        keep_ordinals = {covering_ordinal(3), covering_ordinal(9)}
        result = run_product_classifier(
            transcript_path, cycle_dir, summary["lock_file_sha256"],
            _StubTransport(keep_ordinals, manifest))
        assert result["recall"]["gate_pass"] and result["recall"]["recalled"] == 2
        assert result["counts"]["pruned_keep"] <= KEEP_LIMIT
        assert result["registration_sha256"] == PRODUCT_REGISTRATION_SHA256

        try:
            run_product_classifier(
                transcript_path, cycle_dir, "0" * 64,
                _StubTransport(keep_ordinals, manifest))
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("a wrong approved lock digest was accepted")

        try:
            run_product_classifier(
                transcript_path, cycle_dir, summary["lock_file_sha256"],
                _StubTransport(set(), manifest))
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(
                "an all-abstain run passed the recall gate")
    print("product run self-test: OK; no model loaded; no network used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
