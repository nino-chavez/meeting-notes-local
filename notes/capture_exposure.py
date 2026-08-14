# ruff: noqa: E501
"""Create and validate private candidate-exposure review drafts for a Yawn capture.

Same human-review contract as candidate_exposure.py, minus the registered-QMSum
pins: the source is a private channel-attributed capture, the review view keeps
the Me/Them speakers, and there are no independent annotation regions unless a
regions file is supplied. Every output is private (mode 0600) and must stay
outside Git; the capture content never becomes repository evidence.

Usage:
    python notes/capture_exposure.py TRANSCRIPT EVENTS --out DIR
    python notes/capture_exposure.py TRANSCRIPT EVENTS \
      --out FRESH_DIR --review-decisions EXPORTED.json \
      --ledger-out FRESH_DIR/events.json \
      --lock-out FRESH_DIR/capture-exposure-lock.pending.json
    python notes/capture_exposure.py --self-test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from candidate_exposure import (
    COORDINATE_CONTRACT,
    REVIEW_REGIONS_SCHEMA,
    _json_bytes,
    _private_target,
    _read_json,
    _render_html,
    _sha256,
    _write_private,
    build_pending_ledger_lock,
    build_runner_ledger,
    create_reference,
    validate_review_decisions,
    validate_reference,
)
from candidate_first import STRATEGY_BROAD, generate_manifest
from summarize import StructuredOutputError
from transcript import Transcript, Turn, load


def capture_review_view(transcript: Transcript) -> Transcript:
    """Compose the reviewable view: speakers kept, withheld turns fail closed.

    A withheld turn must never silently vanish from a review that claims to
    expose the whole record. This lane refuses rather than renders around it;
    restoring or acknowledging the withheld turn is the operator's decision on
    the transcript surface, not this tool's.
    """
    if transcript.gated_turns:
        raise StructuredOutputError(
            f"capture transcript withholds {len(transcript.gated_turns)} turn(s); "
            "a review that exposes every turn cannot be built around a withheld "
            "one. Resolve the withheld turns first."
        )
    # A speaker prefix is shown only when the transcript distinguishes more
    # than one speaker. An in-person capture lands every voice on the mic leg,
    # so all turns read "Me" while half of them belong to the other person;
    # printing that uniform label would assert an attribution the record does
    # not carry.
    distinct_speakers = {turn.speaker for turn in transcript.turns if turn.speaker}
    prefix = len(distinct_speakers) > 1
    turns = [
        Turn(text=(f"{turn.speaker}: {turn.text}" if prefix and turn.speaker else turn.text))
        for turn in transcript.turns
    ]
    return Transcript(
        source=f"{transcript.source} (capture review view)",
        attribution=transcript.attribution,
        turns=turns,
    )


def identity_coordinates(view: Transcript) -> list[dict]:
    """The review view is its own raw record: clean and raw coincide."""
    return [
        {
            "raw_turn_ordinal": index,
            "raw_text_sha256": _sha256(turn.text),
            "clean_text_sha256": _sha256(turn.text),
            "clean_to_raw": list(range(len(turn.text))),
        }
        for index, turn in enumerate(view.turns)
    ]


def empty_regions() -> dict:
    """A private capture carries no independent annotation spans."""
    return {
        "schema": REVIEW_REGIONS_SCHEMA,
        "coordinate_contract": COORDINATE_CONTRACT,
        "regions": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path, nargs="?")
    parser.add_argument("events", type=Path, nargs="?")
    parser.add_argument("--regions", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--ledger-out", type=Path)
    parser.add_argument("--lock-out", type=Path)
    parser.add_argument("--section-size", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if not all((args.transcript, args.events, args.out)):
        parser.error("transcript, events, and --out are required")
    review_outputs = (args.review_decisions, args.ledger_out, args.lock_out)
    if any(review_outputs) and not all(review_outputs):
        parser.error(
            "--review-decisions, --ledger-out, and --lock-out must be supplied together")
    view = capture_review_view(load(args.transcript))
    manifest = generate_manifest(view, STRATEGY_BROAD)
    events = _read_json(args.events, "event input")
    regions = (
        _read_json(args.regions, "review regions")
        if args.regions is not None else empty_regions()
    )
    coordinates = identity_coordinates(view)
    reference = create_reference(
        view, manifest, events,
        corpus_sha256=_sha256(args.transcript.read_bytes()),
        coordinates=coordinates,
        regions=regions,
        section_size=args.section_size,
        enforce_registered=False)
    validate_reference(
        reference, view, manifest, coordinates, regions,
        enforce_registered=False)
    json_target = _private_target(args.out, "capture-exposure-reference.json")
    html_target = _private_target(args.out, "capture-exposure-review.html")
    manifest_target = _private_target(args.out, "capture-candidate-manifest.json")
    validated_target = None
    validated_bytes = None
    ledger_target = None
    ledger = None
    lock_target = None
    lock_bytes = None
    lock_file_sha256 = None
    if args.review_decisions:
        decisions = _read_json(args.review_decisions, "review decisions")
        decisions = validate_review_decisions(decisions, reference)
        validated_bytes = _json_bytes(decisions)
        ledger = build_runner_ledger(decisions, reference)
        if ledger["review_decisions_sha256"] != _sha256(validated_bytes):
            raise StructuredOutputError(
                "runner ledger does not bind the canonical review-decision bytes")
        validated_target = _private_target(
            args.ledger_out.parent,
            "capture-exposure-review-decisions.validated.json",
        )
        ledger_target = _private_target(args.ledger_out.parent, args.ledger_out.name)
        pending_lock = build_pending_ledger_lock(ledger, manifest)
        lock_bytes = _json_bytes(pending_lock)
        lock_file_sha256 = _sha256(lock_bytes)
        lock_target = _private_target(args.lock_out.parent, args.lock_out.name)
    _write_private(json_target, _json_bytes(reference))
    _write_private(html_target, _render_html(reference, view).encode())
    _write_private(manifest_target, _json_bytes(manifest))
    if validated_target is not None:
        _write_private(validated_target, validated_bytes)
        _write_private(ledger_target, _json_bytes(ledger))
        _write_private(lock_target, lock_bytes)
        print(
            "wrote canonical validated review decisions "
            f"{validated_target} sha256={ledger['review_decisions_sha256']}")
        print(f"wrote review-complete pending-lock runner ledger {ledger_target}")
        print(f"runner ledger sha256={ledger['ledger_sha256']}")
        print(
            "wrote pending-operator-approval lock "
            f"{lock_target} raw-file-sha256={lock_file_sha256}")
        print(
            "the pending lock does not grant authority; the operator must "
            "approve that exact raw-file SHA-256 before inference")
    print(f"wrote private draft {json_target}")
    print(f"wrote private review {html_target}")
    print(f"wrote private candidate manifest {manifest_target}")
    return 0


def _self_test() -> int:
    withheld = Transcript(
        source="capture exposure fixture", attribution="channel",
        turns=[Turn(text="We agreed to ship on Friday.", speaker="Me")],
        gated_turns=[Turn(text="withheld", speaker="Them")])
    try:
        capture_review_view(withheld)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("a withheld turn did not fail the review view closed")
    transcript = Transcript(
        source="capture exposure fixture", attribution="channel", turns=[
            Turn(text="We agreed to ship on Friday.", speaker="Me"),
            Turn(text="I will draft the announcement.", speaker="Them"),
            Turn(text="Should we tell the pilot group first?", speaker="Me"),
            Turn(text="Ordinary closing chatter.", speaker="Them"),
        ])
    view = capture_review_view(transcript)
    assert all(
        turn.text.startswith(("Me: ", "Them: ")) for turn in view.turns
    ), "the review view must keep channel attribution visible"
    uniform = Transcript(
        source="capture exposure fixture", attribution="channel", turns=[
            Turn(text="Both people share this leg.", speaker="Me"),
            Turn(text="So a uniform label names nobody.", speaker="Me"),
        ])
    assert all(
        not turn.text.startswith("Me: ")
        for turn in capture_review_view(uniform).turns
    ), "a single-speaker capture must not assert a per-person attribution"
    manifest = generate_manifest(view, STRATEGY_BROAD)
    events = [{
        "event_id": "draft-001", "kind": "DECISION",
        "neutral_atomic_proposition": "The ship date is Friday.",
        "type_specific": {"temporal_status": "PENDING_OPERATOR_REVIEW"},
        "acceptable_candidate_ids": [manifest["candidates"][0]["candidate_id"]],
    }]
    coordinates = identity_coordinates(view)
    regions = empty_regions()
    reference = create_reference(
        view, manifest, events, corpus_sha256="b" * 64,
        coordinates=coordinates, regions=regions, section_size=2,
        enforce_registered=False)
    validate_reference(
        reference, view, manifest, coordinates, regions,
        enforce_registered=False)
    assert reference["counts"]["high_risk_turns"] == 0
    rendered = _render_html(reference, view)
    assert "Me: We agreed to ship on Friday." in rendered
    decisions = {
        "schema": "candidate-exposure-review-decisions/2",
        "reference_sha256": reference["reference_sha256"],
        "registration_sha256": reference["source"]["registration_sha256"],
        "events": [{
            "event_id": "draft-001", "disposition": "ACCEPT", "kind": "DECISION",
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
    lock = build_pending_ledger_lock(ledger, manifest, prepared_at="fixture")
    assert lock["state"] == "pending-operator-approval"
    print("capture exposure self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
