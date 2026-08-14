# ruff: noqa: E501
"""Create and validate private candidate-exposure-reference/1 review drafts.

This module never calls a model and never accepts a classifier response. It turns
an operator-authored list of tentative event labels into a review ledger pinned to
a deterministic *broad* candidate manifest. The output is deliberately a DRAFT:
only a human can record approval outside this format.

Usage:
    python notes/candidate_exposure.py TRANSCRIPT MANIFEST EVENTS REGIONS --out DIR
    python notes/candidate_exposure.py TRANSCRIPT MANIFEST EVENTS REGIONS \
      --out FRESH_DIR --review-decisions EXPORTED.json \
      --ledger-out FRESH_DIR/events.json \
      --lock-out FRESH_DIR/candidate-exposure-lock.pending.json
    python notes/candidate_exposure.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from candidate_first import (
    REGISTERED_RUN,
    STRATEGY_BROAD,
    StructuredOutputError,
    _json_bytes,
    _json_sha256,
    qmsum_search_spans,
    registered_run_sha256,
    validate_manifest,
    validate_registered_inputs,
)
from summarize import build_fragment_map, resolve_fragment
from transcript import Transcript, Turn, load

SCHEMA = "candidate-exposure-reference/1"
EVENT_TYPES = ("DECISION", "ACTION", "PROPOSAL", "QUESTION")
DRAFT_STATUS = "DRAFT"
HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
REVIEW_DECISIONS_SCHEMA = "candidate-exposure-review-decisions/2"
REVIEW_REGIONS_SCHEMA = "candidate-exposure-review-regions/1"
RUNNER_LEDGER_SCHEMA = "candidate-exposure-runner-ledger/1"
LEDGER_LOCK_SCHEMA = "candidate-exposure-lock/1"
PENDING_LOCK_STATE = "pending-operator-approval"
SECTION_RESOLUTIONS = ("NO_MISSING_EVENT", "MISSING_EVENT_REPORTED")
REGISTERED_SHA256 = (
    "cbbb4e2448475ce5375b075d806581448936c81f7942c489c55c2e0a923d7a69"
)
KEEP_LIMIT = 64
COORDINATE_CONTRACT = {
    "schema": "candidate-exposure-coordinate-contract/1",
    "canonical_ordinals": "zero-based",
    "character_spans": "zero-based half-open",
    "display_labels": "one-based and noncanonical",
    "review_region_ranges": "zero-based raw-turn ordinals, inclusive",
}


def _sha256(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def normalize_retained_proposition(value: str) -> str:
    """Trim, collapse Unicode-whitespace runs to ASCII space, then Unicode-casefold."""
    return " ".join(value.split()).casefold()


def _read_json(path: Path, description: str) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise StructuredOutputError(
                    f"{description} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(), object_pairs_hook=reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StructuredOutputError(f"cannot read {description}: {exc}") from exc


def _inside_git_worktree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _private_target(directory: Path, name: str) -> Path:
    directory = directory.resolve()
    if _inside_git_worktree(directory):
        raise StructuredOutputError(
            "candidate exposure drafts contain transcript-derived data and must "
            "be written outside every Git worktree")
    if not directory.is_dir():
        raise StructuredOutputError(f"output directory does not exist: {directory}")
    os.chmod(directory, 0o700)
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise StructuredOutputError("output directory must be mode 0700")
    target = directory / name
    if target.exists():
        raise StructuredOutputError(
            f"output already exists: {target}; use a fresh private output directory")
    if target.exists() and target.is_dir():
        raise StructuredOutputError(f"output is a directory: {target}")
    return target


def _require_distinct_targets(targets: list[Path]) -> None:
    """Refuse output aliases before the first private artifact is written."""
    seen: set[Path] = set()
    for target in targets:
        resolved = target.resolve()
        if resolved in seen:
            raise StructuredOutputError(
                f"planned outputs must resolve to distinct files: {resolved}")
        seen.add(resolved)


def _write_private(target: Path, payload: bytes) -> Path:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        fd = -1
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise StructuredOutputError(
                f"output appeared during write: {target}") from exc
        temporary.unlink()
        os.chmod(target, 0o600)
        return target
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def _event_input(events: object) -> list[dict]:
    if not isinstance(events, list):
        raise StructuredOutputError("event input must be a JSON list")
    normalized: list[dict] = []
    ids: set[str] = set()
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict) or set(event) != {
            "event_id", "kind", "neutral_atomic_proposition",
            "type_specific", "acceptable_candidate_ids",
        }:
            raise StructuredOutputError(
                f"event input {index} has the wrong shape")
        event_id = event["event_id"]
        event_type = event["kind"]
        proposition = event["neutral_atomic_proposition"]
        type_specific = event["type_specific"]
        candidates = event["acceptable_candidate_ids"]
        if (not isinstance(event_id, str) or not event_id
                or event_id in ids):
            raise StructuredOutputError(f"event input {index} has a duplicate or invalid ID")
        if event_type not in EVENT_TYPES:
            raise StructuredOutputError(
                f"event {event_id} type must be one of {', '.join(EVENT_TYPES)}")
        if not isinstance(proposition, str) or not proposition.strip():
            raise StructuredOutputError(
                f"event {event_id} needs a neutral atomic proposition")
        expected_field = {
            "DECISION": "temporal_status",
            "ACTION": "commitment_status",
            "PROPOSAL": "proposal_status",
            "QUESTION": "resolution_status",
        }[event_type]
        if (
            not isinstance(type_specific, dict)
            or set(type_specific) != {expected_field}
            or type_specific[expected_field] != "PENDING_OPERATOR_REVIEW"
        ):
            raise StructuredOutputError(
                f"event {event_id} has invalid type-specific review state")
        if (not isinstance(candidates, list) or not candidates
                or len(candidates) != len(set(candidates))
                or not all(isinstance(item, str) and item for item in candidates)):
            raise StructuredOutputError(
                f"event {event_id} needs one or more distinct candidate IDs")
        ids.add(event_id)
        normalized.append({
            "event_id": event_id,
            "kind": event_type,
            "neutral_atomic_proposition": proposition.strip(),
            "type_specific": type_specific,
            "acceptable_candidate_ids": candidates,
        })
    return normalized


def qmsum_coordinates(path: Path, transcript: Transcript) -> list[dict]:
    """Map each cleaned QMSum turn back to its raw row and character offsets."""
    data = _read_json(path, "QMSum corpus")
    rows = data.get("meeting_transcripts") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise StructuredOutputError("raw coordinates require a QMSum transcript")
    output = []
    for raw_turn_ordinal, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("content"), str):
            raise StructuredOutputError("QMSum raw transcript row is invalid")
        raw = row["content"]
        replaced = raw
        for marker in ("{vocalsound}", "{gap}", "{disfmarker}", "{pause}",
                       "{nonvocalsound}", "{comment}"):
            replaced = replaced.replace(marker, " " * len(marker))
        words = list(re.finditer(r"\S+", replaced))
        if not words:
            continue
        clean = " ".join(match.group() for match in words)
        raw_offsets: list[int] = []
        for index, match in enumerate(words):
            if index:
                raw_offsets.append(words[index - 1].end())
            raw_offsets.extend(range(match.start(), match.end()))
        if len(clean) != len(raw_offsets):
            raise StructuredOutputError("raw/clean coordinate map is not exact")
        output.append({
            "raw_turn_ordinal": raw_turn_ordinal,
            "raw_text_sha256": _sha256(raw),
            "clean_text_sha256": _sha256(clean),
            "clean_to_raw": raw_offsets,
        })
    if len(output) != len(transcript.turns):
        raise StructuredOutputError("raw/clean coordinate map has the wrong turn count")
    for ordinal, (coordinate, turn) in enumerate(
        zip(output, transcript.turns, strict=True)
    ):
        if coordinate["clean_text_sha256"] != _sha256(turn.text):
            raise StructuredOutputError(
                f"raw/clean coordinate map disagrees at cleaned turn ordinal {ordinal}")
    return output


def review_regions(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema", "coordinate_contract", "regions"
    }:
        raise StructuredOutputError("review-region input has the wrong shape")
    if (
        value["schema"] != REVIEW_REGIONS_SCHEMA
        or value["coordinate_contract"] != COORDINATE_CONTRACT
        or not isinstance(value["regions"], list)
    ):
        raise StructuredOutputError("review-region input is not current")
    for index, region in enumerate(value["regions"], 1):
        if not isinstance(region, dict) or set(region) != {
            "region_id", "raw_start_ordinal", "raw_end_ordinal", "reason"
        }:
            raise StructuredOutputError(f"review region {index} has the wrong shape")
        start, end = region["raw_start_ordinal"], region["raw_end_ordinal"]
        if (
            not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or start < 0 or end < start
            or not isinstance(region["region_id"], str) or not region["region_id"]
            or not isinstance(region["reason"], str) or not region["reason"]
        ):
            raise StructuredOutputError(f"review region {index} is invalid")
    return value


def _is_high_risk(raw_turn_ordinal: int, regions: dict) -> bool:
    return any(
        row["raw_start_ordinal"] <= raw_turn_ordinal <= row["raw_end_ordinal"]
        for row in regions["regions"]
    )


def _type_specific_review(event_type: str) -> dict:
    field = {
        "DECISION": "live_or_retrospective_recap",
        "ACTION": "commitment_or_need_should_could",
        "PROPOSAL": "proposal_or_recommendation_fact",
        "QUESTION": "open_or_later_resolved",
    }[event_type]
    return {field: "OPERATOR_MUST_DECIDE"}


def _relationships() -> dict:
    return {
        "duplicate_of_event_ids": [],
        "supersedes_event_ids": [],
        "superseded_by_event_ids": [],
        "historical_recap_of_event_ids": [],
        "rejected_by_event_ids": [],
        "deferred_by_event_ids": [],
        "review_state": "OPERATOR_MUST_CLASSIFY_RELATIONSHIPS",
    }


def _source_context(
    transcript: Transcript,
    fragment_map: dict,
    candidate: dict,
    fragments: dict[str, dict],
    coordinates: list[dict],
) -> dict:
    evidence = []
    for fragment_id in candidate["visible_fragment_ids"]:
        fragment = fragments[fragment_id]
        coordinate = coordinates[fragment["turn"]]
        raw_offsets = coordinate["clean_to_raw"]
        clean_start, clean_end = fragment["char_start"], fragment["char_end"]
        evidence.append({
            "source_fragment_id": fragment_id,
            "clean_turn_ordinal": fragment["turn"],
            "clean_turn_display": fragment["turn"] + 1,
            "clean_char_start": fragment["char_start"],
            "clean_char_end": fragment["char_end"],
            "raw_turn_ordinal": coordinate["raw_turn_ordinal"],
            "raw_turn_display": coordinate["raw_turn_ordinal"] + 1,
            "raw_char_start": raw_offsets[clean_start],
            "raw_char_end": raw_offsets[clean_end - 1] + 1,
            "anchor": fragment_id == candidate["anchor_fragment_id"],
            "text": resolve_fragment(
                fragment, transcript, fragment_map["transcript_view_sha256"]),
        })
        evidence[-1]["excerpt_sha256"] = _sha256(evidence[-1]["text"])
    return {
        "candidate_id": candidate["candidate_id"],
        "broad_packet_candidate_id": candidate["candidate_id"],
        "anchor_fragment_id": candidate["anchor_fragment_id"],
        "anchor_clean_turn_ordinal": candidate["anchor_turn"],
        "anchor_clean_turn_display": candidate["anchor_turn"] + 1,
        "evidence": evidence,
    }


def _sections(transcript: Transcript, candidate_rows: list[dict], size: int) -> list[dict]:
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise StructuredOutputError("section size must be a positive integer")
    sections = []
    for start in range(0, len(transcript.turns), size):
        end = min(start + size, len(transcript.turns))
        rows = [row for row in candidate_rows if start <= row["anchor_turn"] < end]
        sections.append({
            "section_id": f"turns-{start + 1:04d}-{end:04d}",
            "clean_start_ordinal": start,
            "clean_end_ordinal": end - 1,
            "clean_start_display": start + 1,
            "clean_end_display": end,
            "exposed_anchor_candidate_ids": [row["candidate_id"] for row in rows],
        })
    return sections


def _minimum_hitting_set(events: list[dict], manifest: dict) -> list[str]:
    candidates = manifest["candidates"]
    event_options: list[set[str]] = []
    for event in events:
        options = set()
        for bundle in event["evidence_bundles"]:
            required = set(bundle["acceptable_fragment_ids"])
            options.update(
                row["candidate_id"] for row in candidates
                if required.issubset(row["visible_fragment_ids"])
            )
        if not options:
            raise StructuredOutputError(
                f"event {event['event_id']} is not exposed by any broad packet")
        event_options.append(options)
    candidate_masks: dict[str, int] = {}
    for event_index, options in enumerate(event_options):
        for candidate_id in options:
            candidate_masks[candidate_id] = (
                candidate_masks.get(candidate_id, 0) | (1 << event_index))
    full = (1 << len(events)) - 1
    best = [candidate_id for candidate_id in candidate_masks]
    memo: dict[int, int] = {}

    def search(covered: int, chosen: list[str]) -> None:
        nonlocal best
        if covered == full:
            if len(chosen) < len(best):
                best = list(chosen)
            return
        if len(chosen) >= len(best) or memo.get(covered, len(best) + 1) <= len(chosen):
            return
        memo[covered] = len(chosen)
        uncovered = [
            index for index in range(len(events))
            if not covered & (1 << index)
        ]
        target = min(
            uncovered,
            key=lambda index: len([
                candidate_id for candidate_id in event_options[index]
                if candidate_masks[candidate_id] & ~covered
            ]),
        )
        options = sorted(
            event_options[target],
            key=lambda candidate_id: (
                -(candidate_masks[candidate_id] & ~covered).bit_count(),
                candidate_id,
            ),
        )
        for candidate_id in options:
            search(covered | candidate_masks[candidate_id], [*chosen, candidate_id])

    search(0, [])
    return sorted(best)


def create_reference(
    transcript: Transcript,
    manifest: object,
    events: object,
    *,
    corpus_sha256: str,
    coordinates: list[dict],
    regions: object,
    section_size: int = 25,
    enforce_registered: bool = True,
) -> dict:
    manifest = validate_manifest(manifest, transcript)
    if manifest["strategy"] != STRATEGY_BROAD:
        raise StructuredOutputError("candidate exposure references require a broad manifest")
    expected = REGISTERED_RUN["corpus"]
    if enforce_registered and (
        registered_run_sha256() != REGISTERED_SHA256
        or corpus_sha256 != expected["raw_sha256"]
        or manifest["transcript_view_sha256"] != expected["transcript_view_sha256"]
        or manifest["manifest_sha256"] != expected["manifest_sha256"]
        or manifest["counts"]["candidates"] != expected["candidates"]
    ):
        raise StructuredOutputError(
            "corpus, stripped view, manifest, or registration is not the exact "
            "registered run")
    if not isinstance(corpus_sha256, str) or len(corpus_sha256) != 64:
        raise StructuredOutputError("corpus SHA-256 must be a 64-character hex digest")
    try:
        int(corpus_sha256, 16)
    except ValueError as exc:
        raise StructuredOutputError("corpus SHA-256 must be hexadecimal") from exc
    event_rows = _event_input(events)
    regions = review_regions(regions)
    candidates = {row["candidate_id"]: row for row in manifest["candidates"]}
    if any(candidate_id not in candidates for event in event_rows
           for candidate_id in event["acceptable_candidate_ids"]):
        raise StructuredOutputError("an event refers to a candidate absent from the manifest")
    fragment_map = build_fragment_map(transcript)
    if len(coordinates) != len(transcript.turns):
        raise StructuredOutputError("raw coordinate map has the wrong turn count")
    fragments = {row["source_fragment_id"]: row for row in fragment_map["fragments"]}
    enriched_events = []
    for event in event_rows:
        bundles = [
            _source_context(transcript, fragment_map, candidates[candidate_id], fragments,
                            coordinates)
            for candidate_id in event["acceptable_candidate_ids"]
        ]
        for bundle in bundles:
            bundle["acceptable_fragment_ids"] = [
                row["source_fragment_id"] for row in bundle["evidence"]
            ]
            bundle["bundle_sha256"] = _json_sha256({
                key: value for key, value in bundle.items() if key != "bundle_sha256"
            })
        enriched = {
            **event,
            "review_state": "UNREVIEWED",
            "relationships": _relationships(),
            "operator_decisions": [
                "Confirm whether any assent is scoped to this exact proposal.",
                "Classify conditional choices and later resolution.",
                "Classify repeated recaps, rejections, deferrals, and supersession.",
            ],
            "evidence_bundles": bundles,
        }
        enriched["event_sha256"] = _json_sha256({
            key: value for key, value in enriched.items() if key != "event_sha256"
        })
        enriched_events.append(enriched)
    sections = _sections(transcript, manifest["candidates"], section_size)
    candidate_to_events: dict[str, list[str]] = {}
    for event in enriched_events:
        for candidate_id in event["acceptable_candidate_ids"]:
            candidate_to_events.setdefault(candidate_id, []).append(event["event_id"])
    for section in sections:
        event_ids = sorted({
            event_id
            for candidate_id in section["exposed_anchor_candidate_ids"]
            for event_id in candidate_to_events.get(candidate_id, [])
        })
        section["event_ids"] = event_ids
        section["review_status"] = "NEEDS_HUMAN_REVIEW"
    turn_event_ids: dict[int, set[str]] = {
        ordinal: set() for ordinal in range(len(transcript.turns))
    }
    for event in enriched_events:
        for bundle in event["evidence_bundles"]:
            for evidence in bundle["evidence"]:
                turn_event_ids[evidence["clean_turn_ordinal"]].add(event["event_id"])
    turn_review = []
    for ordinal, coordinate in enumerate(coordinates):
        event_ids = sorted(turn_event_ids[ordinal])
        high_risk = _is_high_risk(coordinate["raw_turn_ordinal"], regions)
        turn_review.append({
            "clean_turn_ordinal": ordinal,
            "clean_turn_display": ordinal + 1,
            "raw_turn_ordinal": coordinate["raw_turn_ordinal"],
            "raw_turn_display": coordinate["raw_turn_ordinal"] + 1,
            "raw_text_sha256": coordinate["raw_text_sha256"],
            "clean_text_sha256": coordinate["clean_text_sha256"],
            "event_ids": event_ids,
            "agent_draft_state": ("LINKED_TO_DRAFT_EVENT" if event_ids
                                  else "UNLINKED_NOT_HUMAN_DISPOSED"),
            "review_priority": ("HIGH_RISK_NEEDS_HUMAN_REVIEW" if high_risk
                                else "NEEDS_HUMAN_REVIEW"),
        })
    hitting_set = _minimum_hitting_set(enriched_events, manifest)
    event_plan_sha256 = _json_sha256(event_rows)
    regions_sha256 = _json_sha256(regions)
    base = {
        "schema": SCHEMA,
        "status": DRAFT_STATUS,
        "human_approval": HUMAN_APPROVAL,
        "coordinate_contract": COORDINATE_CONTRACT,
        "source": {
            "corpus_sha256": corpus_sha256,
            "transcript_view_sha256": manifest["transcript_view_sha256"],
            "fragment_contract_sha256": manifest["fragment_contract_sha256"],
            "manifest_schema": manifest["schema"],
            "manifest_sha256": manifest["manifest_sha256"],
            "manifest_strategy": manifest["strategy"],
            "registration_sha256": registered_run_sha256(),
            "cleaned_turns": len(transcript.turns),
            "review_regions": regions,
            "review_regions_sha256": regions_sha256,
            "event_plan_sha256": event_plan_sha256,
        },
        "section_size": section_size,
        "counts": {
            "events": len(enriched_events),
            **{event_type.lower(): sum(
                event["kind"] == event_type for event in enriched_events)
                for event_type in EVENT_TYPES},
            "sections": len(sections),
            "linked_turns": sum(bool(row["event_ids"]) for row in turn_review),
            "unlinked_agent_draft_turns": sum(
                not row["event_ids"] for row in turn_review),
            "high_risk_turns": sum(
                row["review_priority"] == "HIGH_RISK_NEEDS_HUMAN_REVIEW"
                for row in turn_review),
        },
        "gate": {
            "maximum_keep": KEEP_LIMIT,
            "minimum_acceptable_anchor_hitting_set": hitting_set,
            "minimum_keep_required": len(hitting_set),
            "headroom_before_lock": KEEP_LIMIT - len(hitting_set),
            "within_keep_limit": len(hitting_set) <= KEEP_LIMIT,
        },
        "events": enriched_events,
        "sections": sections,
        "turn_review": turn_review,
    }
    return {**base, "reference_sha256": _json_sha256(base)}


def validate_reference(
    reference: object,
    transcript: Transcript,
    manifest: object,
    coordinates: list[dict],
    regions: object,
    *,
    enforce_registered: bool = True,
) -> dict:
    if not isinstance(reference, dict):
        raise StructuredOutputError("candidate exposure reference must be an object")
    expected_keys = {
        "schema", "status", "human_approval", "coordinate_contract", "source",
        "section_size", "counts", "gate", "events", "sections", "turn_review",
        "reference_sha256",
    }
    if set(reference) != expected_keys:
        raise StructuredOutputError("candidate exposure reference has the wrong shape")
    if reference["schema"] != SCHEMA or reference["status"] != DRAFT_STATUS:
        raise StructuredOutputError("candidate exposure reference is not a current draft")
    if reference["human_approval"] != HUMAN_APPROVAL:
        raise StructuredOutputError("an agent-authored reference cannot claim human approval")
    base = {key: value for key, value in reference.items() if key != "reference_sha256"}
    if reference["reference_sha256"] != _json_sha256(base):
        raise StructuredOutputError("candidate exposure reference digest does not re-derive")
    expected = create_reference(
        transcript, manifest,
        [{key: event[key] for key in (
            "event_id", "kind", "neutral_atomic_proposition",
            "type_specific", "acceptable_candidate_ids",
        )}
         for event in reference["events"]],
        corpus_sha256=reference["source"].get("corpus_sha256"),
        coordinates=coordinates,
        regions=regions,
        section_size=reference["section_size"],
        enforce_registered=enforce_registered,
    )
    if _json_bytes(reference) != _json_bytes(expected):
        raise StructuredOutputError("reference does not re-derive from its pinned inputs")
    return reference


def validate_review_decisions(decisions: object, reference: dict) -> dict:
    if not isinstance(decisions, dict) or set(decisions) != {
        "schema", "reference_sha256", "registration_sha256", "events", "sections"
    }:
        raise StructuredOutputError("review decisions have the wrong shape")
    if (
        decisions["schema"] != REVIEW_DECISIONS_SCHEMA
        or decisions["reference_sha256"] != reference["reference_sha256"]
        or decisions["registration_sha256"] != registered_run_sha256()
    ):
        raise StructuredOutputError("review decisions are bound to different inputs")
    expected_events = {row["event_id"]: row for row in reference["events"]}
    rows = decisions["events"]
    if (
        not isinstance(rows, list)
        or [row.get("event_id") for row in rows if isinstance(row, dict)]
        != list(expected_events)
        or len(rows) != len(expected_events)
    ):
        raise StructuredOutputError("review decisions do not cover every event exactly once")
    for row in rows:
        if set(row) != {
            "event_id", "disposition", "kind", "neutral_atomic_proposition",
            "selected_bundle_sha256", "ambiguity_reason", "notes",
        }:
            raise StructuredOutputError("an event review decision has the wrong shape")
        event = expected_events[row["event_id"]]
        available = {bundle["bundle_sha256"] for bundle in event["evidence_bundles"]}
        selected = row["selected_bundle_sha256"]
        if (
            row["disposition"] not in {"ACCEPT", "EDIT", "REJECT"}
            or row["kind"] not in EVENT_TYPES
            or not isinstance(row["neutral_atomic_proposition"], str)
            or not row["neutral_atomic_proposition"].strip()
            or not isinstance(selected, list) or len(selected) != len(set(selected))
            or any(bundle_id not in available for bundle_id in selected)
            or (
                row["disposition"] in {"ACCEPT", "EDIT"} and not selected
            )
            or (
                row["disposition"] == "ACCEPT"
                and (
                    row["kind"] != event["kind"]
                    or row["neutral_atomic_proposition"]
                    != event["neutral_atomic_proposition"]
                )
            )
            or not isinstance(row["ambiguity_reason"], str)
            or (
                row["disposition"] in {"EDIT", "REJECT"}
                and not row["ambiguity_reason"].strip()
            )
            or not isinstance(row["notes"], str)
        ):
            raise StructuredOutputError(
                f"event decision {row['event_id']} is incomplete or invalid")
    retained: dict[str, str] = {}
    for row in rows:
        if row["disposition"] not in {"ACCEPT", "EDIT"}:
            continue
        normalized = normalize_retained_proposition(
            row["neutral_atomic_proposition"])
        if normalized in retained:
            raise StructuredOutputError(
                "retained propositions are exact duplicates after trim, "
                "Unicode-whitespace collapse, and casefold: "
                f"{retained[normalized]} and {row['event_id']}")
        retained[normalized] = row["event_id"]
    expected_sections = {row["section_id"] for row in reference["sections"]}
    sections = decisions["sections"]
    if (
        not isinstance(sections, list)
        or [row.get("section_id") for row in sections if isinstance(row, dict)]
        != [row["section_id"] for row in reference["sections"]]
        or len(sections) != len(expected_sections)
        or any(
            not isinstance(row, dict)
            or set(row) != {
                "section_id", "reviewed", "resolution", "notes"}
            or row["reviewed"] is not True
            or row["resolution"] not in SECTION_RESOLUTIONS
            or not isinstance(row["notes"], str)
            or (
                row["resolution"] == "NO_MISSING_EVENT"
                and bool(row["notes"])
            )
            or (
                row["resolution"] == "MISSING_EVENT_REPORTED"
                and not row["notes"].strip()
            )
            for row in sections
        )
    ):
        raise StructuredOutputError(
            "every transcript section must be reviewed and explicitly resolved")
    return decisions


def build_runner_ledger(decisions: object, reference: dict) -> dict:
    decisions = validate_review_decisions(decisions, reference)
    missing_sections = [
        row["section_id"] for row in decisions["sections"]
        if row["resolution"] == "MISSING_EVENT_REPORTED"
    ]
    if missing_sections:
        raise StructuredOutputError(
            "review reports missing events in transcript sections "
            f"{', '.join(missing_sections)}; revise the event plan and repeat "
            "the complete human review before promotion")
    events_by_id = {row["event_id"]: row for row in reference["events"]}
    events = []
    for decision in decisions["events"]:
        if decision["disposition"] not in {"ACCEPT", "EDIT"}:
            continue
        event = events_by_id[decision["event_id"]]
        selected = set(decision["selected_bundle_sha256"])
        bundles = [
            bundle["acceptable_fragment_ids"]
            for bundle in event["evidence_bundles"]
            if bundle["bundle_sha256"] in selected
        ]
        events.append({
            "event_id": decision["event_id"],
            "kind": decision["kind"],
            "neutral_atomic_proposition_sha256": _sha256(
                normalize_retained_proposition(
                    decision["neutral_atomic_proposition"])
            ),
            "acceptable_evidence_bundles": bundles,
        })
    if not events:
        raise StructuredOutputError("review retained no events for the runner ledger")
    base = {
        "schema": RUNNER_LEDGER_SCHEMA,
        "registration_sha256": registered_run_sha256(),
        "transcript_view_sha256": reference["source"]["transcript_view_sha256"],
        "review_reference_sha256": reference["reference_sha256"],
        "review_decisions_sha256": _json_sha256(decisions),
        "events": events,
    }
    return {**base, "ledger_sha256": _json_sha256(base)}


def build_pending_ledger_lock(
    ledger: dict,
    manifest: dict,
    *,
    prepared_at: str | None = None,
) -> dict:
    """Create bytes the operator may approve; never self-assert approval."""
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != RUNNER_LEDGER_SCHEMA
        or not isinstance(ledger.get("ledger_sha256"), str)
        or not isinstance(ledger.get("review_reference_sha256"), str)
        or not isinstance(ledger.get("review_decisions_sha256"), str)
        or ledger.get("registration_sha256") != registered_run_sha256()
        or not isinstance(manifest, dict)
        or not isinstance(manifest.get("manifest_sha256"), str)
    ):
        raise StructuredOutputError(
            "pending operator lock inputs are incomplete or invalid")
    if prepared_at is None:
        prepared_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(prepared_at, str) or not prepared_at.strip():
        raise StructuredOutputError("pending operator lock needs a preparation time")
    return {
        "schema": LEDGER_LOCK_SCHEMA,
        "state": PENDING_LOCK_STATE,
        "ledger_sha256": ledger["ledger_sha256"],
        "review_reference_sha256": ledger["review_reference_sha256"],
        "review_decisions_sha256": ledger["review_decisions_sha256"],
        "registration_sha256": registered_run_sha256(),
        "manifest_sha256": manifest["manifest_sha256"],
        "prepared_at": prepared_at,
    }


def _render_review_script(reference: dict, data: str) -> str:
    return f'''<script>(()=>{{
const root=document.querySelector('#candidate-exposure-review-019fae7d'),binding={data};
const collect=()=>{{
 const events=[...root.querySelectorAll('.event')].map(a=>({{
  event_id:a.dataset.event,disposition:a.dataset.disposition||'',
  kind:a.querySelector('.kind').value,
  neutral_atomic_proposition:a.querySelector('.proposition').value,
  selected_bundle_sha256:[...a.querySelectorAll('.bundle:checked')].map(x=>x.value),
  ambiguity_reason:a.querySelector('.ambiguity-reason').value,
  notes:a.querySelector('.notes').value
 }}));
 const sections=[...root.querySelectorAll('.section')].map(a=>({{
  section_id:a.dataset.section,
  reviewed:a.querySelector('.section-reviewed').checked,
  resolution:a.querySelector('.section-resolution').value,
  notes:a.querySelector('.section-notes').value
 }}));
 return{{
  schema:binding.schema,
  reference_sha256:binding.reference_sha256,
  registration_sha256:binding.registration_sha256,
  events,sections
 }};
}};
const eventComplete=e=>
 ['ACCEPT','EDIT','REJECT'].includes(e.disposition)&&
 e.neutral_atomic_proposition.trim()&&
 (e.disposition==='REJECT'||e.selected_bundle_sha256.length)&&
 (e.disposition==='ACCEPT'||e.ambiguity_reason.trim())
;
const sectionComplete=s=>
 s.reviewed&&['NO_MISSING_EVENT','MISSING_EVENT_REPORTED'].includes(s.resolution)&&
 ((s.resolution==='NO_MISSING_EVENT'&&!s.notes)||
  (s.resolution==='MISSING_EVENT_REPORTED'&&s.notes.trim()));
const complete=o=>o.events.every(eventComplete)&&o.sections.every(sectionComplete);
const refresh=()=>{{
 const out=collect(),eventCount=out.events.filter(eventComplete).length;
 const sectionCount=out.sections.filter(sectionComplete).length;
 const missingCount=out.sections.filter(
  s=>s.resolution==='MISSING_EVENT_REPORTED').length,ok=complete(out);
 root.querySelector('#cer-progress').textContent=
  `Events resolved: ${{eventCount}} / {len(reference["events"])}; Sections resolved: ${{sectionCount}} / {len(reference["sections"])}; Missing events reported: ${{missingCount}}`;
 root.querySelector('#cer-send').disabled=!ok;
 root.querySelector('#cer-status').textContent=ok?
  (missingCount?
   ' Review complete with missing events reported. Submit to revise the draft; promotion will be refused.':
   ' All controls are ready. Export locally, then submit for validation.'):
  ' Resolve every event and section to enable handoff.';
}};
root.querySelectorAll('.dispositions button').forEach(b=>b.onclick=()=>{{
 const a=b.closest('.event');a.dataset.disposition=b.dataset.value;
 a.querySelectorAll('.dispositions button').forEach(x=>{{
  const active=x===b;x.setAttribute('aria-pressed',String(active));
  x.classList.toggle('btn-primary',active);x.classList.toggle('btn-ghost',!active);
 }});
 const accepting=b.dataset.value==='ACCEPT';
 a.querySelector('.review-detail').hidden=accepting;
 a.querySelector('.kind').disabled=accepting;
 a.querySelector('.proposition').disabled=accepting;
 if(accepting){{
  a.querySelector('.kind').value=a.querySelector('.kind').dataset.original;
  a.querySelector('.proposition').value=a.querySelector('.proposition').defaultValue;
 }}
 a.querySelector('output').textContent=b.dataset.value;refresh();
}});
root.querySelectorAll('.section-resolution').forEach(select=>{{
 select.onchange=()=>{{
  const section=select.closest('.section');
  const detail=section.querySelector('.section-missing-detail');
  const notes=section.querySelector('.section-notes');
  const missing=select.value==='MISSING_EVENT_REPORTED';
  detail.hidden=!missing;notes.required=missing;
  notes.setAttribute('aria-required',String(missing));
  if(!missing)notes.value='';
  refresh();
 }};
}});
root.addEventListener('change',refresh);root.addEventListener('input',refresh);
const download=()=>{{
 const out=collect(),blob=new Blob([JSON.stringify(out,null,2)+'\\n'],
  {{type:'application/json'}});
 const url=URL.createObjectURL(blob),link=document.createElement('a');
 link.href=url;link.download='candidate-exposure-review-decisions.json';link.click();
 URL.revokeObjectURL(url);return out;
}};
root.querySelector('#cer-export').onclick=()=>{{
 download();root.querySelector('#cer-status').textContent=
  ' Decisions exported locally. Run fail-closed validation before any lock.';
}};
root.querySelector('#cer-send').onclick=async()=>{{
 const out=collect();if(!complete(out))return;
 const prompt=`Candidate-exposure review controls were submitted for DRAFT reference ${{binding.reference_sha256}} and event plan ${{binding.event_plan_sha256}}. Event decisions: ${{JSON.stringify(out.events)}}. Transcript section reviews: ${{JSON.stringify(out.sections)}}. This submission is not approval. Validate the complete decision object. If any section has resolution MISSING_EVENT_REPORTED, do not promote a ledger or build a lock: use its note to draft the missing event, regenerate the reference, and return the entire revised review to me. If every section is NO_MISSING_EVENT, persist canonical decisions, produce the pending runner ledger, and build the PENDING-OPERATOR-APPROVAL lock file. Present the exact review_decisions_sha256, ledger_sha256, and raw lock-file SHA-256. I must separately approve or decline that exact lock-file digest before inference. The lock file does not claim approval; this host message is not persisted authority.`;
 if(!window.openai?.sendFollowUpMessage){{
  root.querySelector('#cer-status').textContent=
   ' Host follow-up API is unavailable; use the exported JSON.';return;
 }}
 await window.openai.sendFollowUpMessage({{prompt}});
}};
refresh();
}})();</script>'''


def _bundle_summary_excerpt(bundle: dict, limit: int = 110) -> str:
    anchor_rows = [row for row in bundle["evidence"] if row["anchor"]]
    text = (anchor_rows or bundle["evidence"])[0]["text"]
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return html.escape(text)


def _render_html(reference: dict, transcript: Transcript) -> str:
    event_html = []
    for event in reference["events"]:
        bundle_groups = []
        dom_id = f'cer-event-{event["event_sha256"][:12]}'
        for bundle_index, bundle in enumerate(event["evidence_bundles"], 1):
            bundle_id = f"{dom_id}-bundle-{bundle_index}"
            rows = bundle["evidence"]
            first, last = rows[0]["clean_turn_display"], rows[-1]["clean_turn_display"]
            evidence = "".join(
                f'<blockquote>{"<strong>Anchor — </strong>" if row["anchor"] else ""}'
                f'Clean {row["clean_turn_display"]} / raw '
                f'{row["raw_turn_display"]}: {html.escape(row["text"])}</blockquote>'
                for row in rows)
            bundle_groups.append(
                f'<fieldset class="bundle-group">'
                f'<legend><label class="form-check" for="{bundle_id}">'
                f'<input id="{bundle_id}" type="checkbox" '
                f'class="bundle form-check-input" '
                f'value="{bundle["bundle_sha256"]}"> '
                f'<span class="form-check-label">Bundle {bundle_index} · '
                f'anchor turn {bundle["anchor_clean_turn_display"]} · '
                f'turns {first}–{last}</span></label></legend>'
                f'<details><summary>{_bundle_summary_excerpt(bundle)}</summary>'
                f'{evidence}</details></fieldset>')
        event_id = html.escape(event["event_id"])
        proposition = html.escape(event["neutral_atomic_proposition"])
        event_html.append(f'''
<article class="event card" data-event="{event_id}">
 <h3>{event_id}: {event["kind"]}</h3>
 <label for="{dom_id}-proposition" class="form-label">Atomic proposition</label>
 <textarea id="{dom_id}-proposition" class="proposition form-control">{proposition}</textarea>
 <label for="{dom_id}-kind" class="form-label">Kind</label>
 <select id="{dom_id}-kind" class="kind form-select" data-original="{event["kind"]}">{''.join(f'<option{(" selected" if value == event["kind"] else "")}>{value}</option>' for value in EVENT_TYPES)}</select>
 <fieldset><legend>Decision</legend><div class="dispositions viz-row viz-controls">{''.join(f'<button type="button" class="btn btn-ghost" aria-pressed="false" data-value="{value}">{value.title()}</button>' for value in ("ACCEPT", "EDIT", "REJECT"))}</div> <output>Pending</output></fieldset>
 <div class="review-detail" hidden>
  <label for="{dom_id}-ambiguity" class="form-label">Ambiguity or override reason (required)</label>
  <textarea id="{dom_id}-ambiguity" class="ambiguity-reason form-control" required aria-required="true"></textarea>
  <label for="{dom_id}-notes" class="form-label">Optional review notes</label>
  <textarea id="{dom_id}-notes" class="notes form-control"></textarea>
 </div>
 <fieldset><legend>Acceptable evidence bundles — each group is one candidate's context window; check every bundle whose evidence supports the proposition</legend>{''.join(bundle_groups)}</fieldset>
</article>''')
    sections = []
    for section in reference["sections"]:
        lines = []
        for ordinal in range(
            section["clean_start_ordinal"], section["clean_end_ordinal"] + 1
        ):
            lines.append(
                f'{ordinal + 1:04d} | {transcript.turns[ordinal].text}')
        sections.append(f'''
<article class="section" data-section="{section["section_id"]}">
 <h3>{section["section_id"]}</h3><pre>{html.escape(chr(10).join(lines))}</pre>
 <label class="form-check" for="{section["section_id"]}-reviewed"><input id="{section["section_id"]}-reviewed" class="section-reviewed form-check-input" type="checkbox"> <span class="form-check-label">I reviewed every turn in this section</span></label>
 <label for="{section["section_id"]}-resolution" class="form-label">Did this section contain an event missing from the draft?</label>
 <select id="{section["section_id"]}-resolution" class="section-resolution form-select">
  <option value="">Choose one</option>
  <option value="NO_MISSING_EVENT">No missing event found</option>
  <option value="MISSING_EVENT_REPORTED">Missing event found</option>
 </select>
 <div class="section-missing-detail" hidden>
  <label for="{section["section_id"]}-notes" class="form-label">Describe every missing event and include the clean turn number</label>
  <textarea id="{section["section_id"]}-notes" class="section-notes form-control"></textarea>
 </div>
</article>''')
    data = json.dumps({
        "schema": REVIEW_DECISIONS_SCHEMA,
        "reference_sha256": reference["reference_sha256"],
        "registration_sha256": registered_run_sha256(),
        "event_plan_sha256": reference["source"]["event_plan_sha256"],
    }).replace("<", "\\u003c")
    rendered = f'''<div id="candidate-exposure-review-019fae7d" class="cer-root"><style>
#candidate-exposure-review-019fae7d pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style><section aria-label="Candidate exposure review">
<p><strong>DRAFT. Not human-approved.</strong> An agent read this transcript and drafted {len(reference["events"])} events — the decisions, actions, proposals, and open questions it believes this meeting produced. Your review turns that draft into the answer key a local model is graded against. The model must later recover every event you keep. An event you approve wrongly gets enforced; an event the draft missed goes unmeasured unless you report it.</p>
<p>The review is two passes. First, decide each event. <strong>Accept</strong>: true as worded, and the checked evidence shows it. <strong>Edit</strong>: real, but the wording or kind is wrong — fix it and give the reason. <strong>Reject</strong>: does not belong — give the reason. Checking an evidence bundle means a model that finds that passage has found this event. Second, read all {len(reference["sections"])} transcript sections below the events and say for each whether the draft missed an event. The sections exist to catch what the draft missed, not to re-approve its picks; a reported missing event stops promotion and returns the draft for revision.</p>
<p>Capacity: the model may keep at most {KEEP_LIMIT} passages. Covering every drafted event needs at least {reference["gate"]["minimum_keep_required"]}, leaving {reference["gate"]["headroom_before_lock"]} spare. Exported decisions still require command-line validation and a separate operator lock before any model call.</p>
<p id="cer-progress" aria-live="polite">Events resolved: 0 / {len(reference["events"])}; Sections resolved: 0 / {len(reference["sections"])}; Missing events reported: 0</p>
<section aria-label="Events"><p><strong>First pass — the drafted events.</strong> Decide every one. Accept locks the wording as shown; Edit and Reject require a reason.</p>{''.join(event_html)}</section><section aria-label="Transcript sections"><p><strong>Second pass — the completeness check.</strong> This is the part only you can do: read every turn and report any decision, action, proposal, or unresolved question the draft missed, with its turn number. Answering "no missing event" without reading is the failure this page exists to prevent.</p>{''.join(sections)}</section>
<div class="final-actions viz-row viz-controls"><button id="cer-export" class="btn btn-ghost" type="button">Export review-decisions JSON</button><button id="cer-send" class="btn btn-primary" type="button" disabled>Submit review controls for validation</button><output id="cer-status" aria-live="polite"> Resolve every event and section to enable handoff.</output></div></section>
<script></script></div>'''
    return (
        rendered[:rendered.index("<script>")]
        + _render_review_script(reference, data)
        + "</div>"
    )


def _self_test() -> int:
    transcript = Transcript(
        source="candidate exposure fixture", attribution="none", turns=[
            Turn(text="We decided to use the smaller battery."),
            Turn(text="I will send the costs tomorrow."),
            Turn(text="Could we record consent before release?"),
            Turn(text="Ordinary closing status with no target event."),
        ])
    from candidate_first import generate_manifest
    manifest = generate_manifest(transcript, STRATEGY_BROAD)
    events = [
        {
            "event_id": "draft-001", "kind": "DECISION",
            "neutral_atomic_proposition": "The smaller battery is selected.",
            "type_specific": {"temporal_status": "PENDING_OPERATOR_REVIEW"},
            "acceptable_candidate_ids": [manifest["candidates"][0]["candidate_id"]],
        },
        {
            "event_id": "draft-002", "kind": "ACTION",
            "neutral_atomic_proposition": "The costs will be sent tomorrow.",
            "type_specific": {"commitment_status": "PENDING_OPERATOR_REVIEW"},
            "acceptable_candidate_ids": [manifest["candidates"][1]["candidate_id"]],
        },
    ]
    coordinates = [{
        "raw_turn_ordinal": index,
        "raw_text_sha256": _sha256(turn.text),
        "clean_text_sha256": _sha256(turn.text),
        "clean_to_raw": list(range(len(turn.text))),
    } for index, turn in enumerate(transcript.turns)]
    regions = {
        "schema": REVIEW_REGIONS_SCHEMA,
        "coordinate_contract": COORDINATE_CONTRACT,
        "regions": [{
            "region_id": "synthetic-risk",
            "raw_start_ordinal": 1,
            "raw_end_ordinal": 1,
            "reason": "synthetic boundary exercise",
        }],
    }
    try:
        create_reference(
            transcript, manifest, events, corpus_sha256="a" * 64,
            coordinates=coordinates, regions=regions)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("non-registered corpus pins were accepted")
    reference = create_reference(
        transcript, manifest, events, corpus_sha256="a" * 64, coordinates=coordinates,
        regions=regions, section_size=2, enforce_registered=False)
    validate_reference(
        reference, transcript, manifest, coordinates, regions,
        enforce_registered=False)
    assert reference["human_approval"] == HUMAN_APPROVAL
    assert reference["coordinate_contract"]["canonical_ordinals"] == "zero-based"
    assert reference["turn_review"][3]["agent_draft_state"] == (
        "UNLINKED_NOT_HUMAN_DISPOSED")
    assert "NO_TARGET_EVENT" not in json.dumps(reference)
    assert reference["sections"][0]["clean_start_ordinal"] == 0
    assert reference["sections"][-1]["clean_end_ordinal"] == 3
    assert all(event["event_sha256"] for event in reference["events"])
    assert all(bundle["bundle_sha256"] for event in reference["events"]
               for bundle in event["evidence_bundles"])
    rendered = _render_html(reference, transcript)
    assert rendered.startswith('<div id="candidate-exposure-review-019fae7d"')
    assert "<!doctype" not in rendered.lower()
    assert "<html" not in rendered.lower()
    assert "<h1" not in rendered.lower()
    assert "<h2" not in rendered.lower()
    assert "fetch(" not in rendered
    assert "DEFER" not in rendered
    assert "event_plan_sha256:binding.event_plan_sha256" not in rendered
    assert "review_decisions_sha256, ledger_sha256, and raw lock-file SHA-256" in rendered
    assert "Did this section contain an event missing from the draft?" in rendered
    assert "MISSING_EVENT_REPORTED" in rendered
    assert "do not promote a ledger or build a lock" in rendered
    assert "sendFollowUpMessage" in rendered
    for mutate in (
        lambda value: value.__setitem__("human_approval", "HUMAN_APPROVED"),
        lambda value: value["events"][0].__setitem__("review_state", "APPROVED"),
        lambda value: value["sections"].pop(),
        lambda value: value["source"].__setitem__("registration_sha256", "0" * 64),
    ):
        broken = json.loads(json.dumps(reference))
        mutate(broken)
        try:
            validate_reference(
                broken, transcript, manifest, coordinates, regions,
                enforce_registered=False)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("tampered draft reference was accepted")
    try:
        create_reference(transcript, manifest, [{
            "event_id": "bad", "kind": "DECISION",
            "neutral_atomic_proposition": "A choice is made.",
            "type_specific": {"temporal_status": "PENDING_OPERATOR_REVIEW"},
            "acceptable_candidate_ids": ["missing"],
        }], corpus_sha256="a" * 64, coordinates=coordinates, regions=regions,
            enforce_registered=False)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("unknown anchor was accepted")
    event_decisions = []
    for event in reference["events"]:
        event_decisions.append({
            "event_id": event["event_id"],
            "disposition": "ACCEPT",
            "kind": event["kind"],
            "neutral_atomic_proposition": event["neutral_atomic_proposition"],
            "selected_bundle_sha256": [
                event["evidence_bundles"][0]["bundle_sha256"]
            ],
            "ambiguity_reason": "",
            "notes": "",
        })
    decisions = {
        "schema": REVIEW_DECISIONS_SCHEMA,
        "reference_sha256": reference["reference_sha256"],
        "registration_sha256": registered_run_sha256(),
        "events": event_decisions,
        "sections": [
            {
                "section_id": row["section_id"],
                "reviewed": True,
                "resolution": "NO_MISSING_EVENT",
                "notes": "",
            }
            for row in reference["sections"]
        ],
    }
    validate_review_decisions(decisions, reference)
    ledger = build_runner_ledger(decisions, reference)
    assert ledger["schema"] == "candidate-exposure-runner-ledger/1"
    assert ledger["review_decisions_sha256"] == _sha256(_json_bytes(decisions))
    assert ledger["events"][0]["neutral_atomic_proposition_sha256"] == _sha256(
        normalize_retained_proposition(
            decisions["events"][0]["neutral_atomic_proposition"]))
    assert normalize_retained_proposition("  MIXED\t Case  ") == "mixed case"
    assert set(ledger) == {
        "schema", "registration_sha256", "transcript_view_sha256",
        "review_reference_sha256", "review_decisions_sha256", "events",
        "ledger_sha256",
    }
    assert all(
        set(event) == {
            "event_id", "kind", "neutral_atomic_proposition_sha256",
            "acceptable_evidence_bundles",
        }
        for event in ledger["events"]
    )
    incomplete = json.loads(json.dumps(decisions))
    incomplete["sections"][0]["reviewed"] = False
    try:
        validate_review_decisions(incomplete, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("incomplete section review was accepted")
    unresolved = json.loads(json.dumps(decisions))
    unresolved["sections"][0]["resolution"] = ""
    try:
        validate_review_decisions(unresolved, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("unresolved section review was accepted")
    missing_without_note = json.loads(json.dumps(decisions))
    missing_without_note["sections"][0]["resolution"] = "MISSING_EVENT_REPORTED"
    try:
        validate_review_decisions(missing_without_note, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("missing-event report without a note was accepted")
    contradictory_note = json.loads(json.dumps(decisions))
    contradictory_note["sections"][0]["notes"] = "Turn 2 contains a missing action."
    try:
        validate_review_decisions(contradictory_note, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("no-missing-event resolution carried a note")
    missing_report = json.loads(json.dumps(decisions))
    missing_report["sections"][0]["resolution"] = "MISSING_EVENT_REPORTED"
    missing_report["sections"][0]["notes"] = "Clean turn 2 contains a missing action."
    validate_review_decisions(missing_report, reference)
    try:
        build_runner_ledger(missing_report, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("missing-event report was promoted into a runner ledger")
    for mutate in (
        lambda value: value["events"].reverse(),
        lambda value: value["events"][0].__setitem__(
            "neutral_atomic_proposition", "A changed proposition."),
        lambda value: value["events"][0]["selected_bundle_sha256"].append(
            "0" * 64),
        lambda value: value.__setitem__("registration_sha256", "0" * 64),
    ):
        broken = json.loads(json.dumps(decisions))
        mutate(broken)
        try:
            validate_review_decisions(broken, reference)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("adversarial review decisions were accepted")
    missing_reason = json.loads(json.dumps(decisions))
    missing_reason["events"][1]["disposition"] = "EDIT"
    missing_reason["events"][1]["neutral_atomic_proposition"] = (
        "The costs will be sent on the next day.")
    try:
        validate_review_decisions(missing_reason, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("an edit without an override reason was accepted")
    missing_reject_reason = json.loads(json.dumps(decisions))
    missing_reject_reason["events"][0]["disposition"] = "REJECT"
    missing_reject_reason["events"][0]["selected_bundle_sha256"] = []
    try:
        validate_review_decisions(missing_reject_reason, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("a rejection without an override reason was accepted")
    duplicate = json.loads(json.dumps(decisions))
    duplicate["events"][1]["disposition"] = "EDIT"
    duplicate["events"][1]["neutral_atomic_proposition"] = (
        "  THE\tSMALLER  BATTERY IS SELECTED.  ")
    duplicate["events"][1]["ambiguity_reason"] = (
        "Possible duplicate retained proposition.")
    try:
        validate_review_decisions(duplicate, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("a normalized duplicate retained proposition was accepted")
    rejected = json.loads(json.dumps(decisions))
    for row in rejected["events"]:
        row["disposition"] = "REJECT"
        row["selected_bundle_sha256"] = []
        row["ambiguity_reason"] = "Rejected during synthetic review."
    try:
        build_runner_ledger(rejected, reference)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("an empty runner ledger was accepted")
    pending_lock = build_pending_ledger_lock(
        ledger, manifest, prepared_at="2026-07-30T00:00:00+00:00")
    assert pending_lock == {
        "schema": LEDGER_LOCK_SCHEMA,
        "state": PENDING_LOCK_STATE,
        "ledger_sha256": ledger["ledger_sha256"],
        "review_reference_sha256": ledger["review_reference_sha256"],
        "review_decisions_sha256": ledger["review_decisions_sha256"],
        "registration_sha256": registered_run_sha256(),
        "manifest_sha256": manifest["manifest_sha256"],
        "prepared_at": "2026-07-30T00:00:00+00:00",
    }
    malformed_regions = json.loads(json.dumps(regions))
    malformed_regions["regions"][0]["raw_start_ordinal"] = 2
    try:
        review_regions(malformed_regions)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("reversed review region was accepted")
    with tempfile.TemporaryDirectory() as directory:
        target = _private_target(Path(directory), "draft.json")
        _write_private(target, _json_bytes(reference))
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(directory).stat().st_mode) == 0o700
        try:
            _private_target(Path(directory), "draft.json")
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("an existing private artifact could be overwritten")
        try:
            _require_distinct_targets([
                Path(directory) / "first.json",
                Path(directory) / "." / "first.json",
            ])
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("aliased planned outputs were accepted")
        duplicate_json = Path(directory) / "duplicate.json"
        duplicate_json.write_text('{"schema":"first","schema":"second"}\n')
        try:
            _read_json(duplicate_json, "duplicate-key fixture")
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("duplicate JSON keys were accepted")
    print("candidate exposure self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path, nargs="?")
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("events", type=Path, nargs="?")
    parser.add_argument("regions", type=Path, nargs="?")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--ledger-out", type=Path)
    parser.add_argument("--lock-out", type=Path)
    parser.add_argument("--section-size", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if not all((args.transcript, args.manifest, args.events, args.regions, args.out)):
        parser.error("transcript, manifest, events, regions, and --out are required")
    review_outputs = (args.review_decisions, args.ledger_out, args.lock_out)
    if any(review_outputs) and not all(review_outputs):
        parser.error(
            "--review-decisions, --ledger-out, and --lock-out must be supplied together")
    planned_targets = [
        args.out / "candidate-exposure-reference.json",
        args.out / "candidate-exposure-review.html",
    ]
    if args.review_decisions is not None:
        planned_targets.extend([
            args.ledger_out.parent
            / "candidate-exposure-review-decisions.validated.json",
            args.ledger_out,
            args.lock_out,
        ])
    try:
        _require_distinct_targets(planned_targets)
    except StructuredOutputError as exc:
        parser.error(str(exc))
    transcript = load(args.transcript).strip_attribution()
    manifest = _read_json(args.manifest, "candidate manifest")
    events = _read_json(args.events, "event input")
    regions = _read_json(args.regions, "review regions")
    corpus_sha256 = _sha256(args.transcript.read_bytes())
    coordinates = qmsum_coordinates(args.transcript, transcript)
    registry = qmsum_search_spans(args.transcript, transcript)
    validate_registered_inputs(args.transcript, transcript, manifest, registry)
    reference = create_reference(
        transcript, manifest, events, corpus_sha256=corpus_sha256,
        coordinates=coordinates,
        regions=regions,
        section_size=args.section_size)
    validate_reference(reference, transcript, manifest, coordinates, regions)
    json_target = _private_target(
        args.out, "candidate-exposure-reference.json")
    html_target = _private_target(
        args.out, "candidate-exposure-review.html")
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
            "candidate-exposure-review-decisions.validated.json",
        )
        ledger_target = _private_target(
            args.ledger_out.parent, args.ledger_out.name)
        pending_lock = build_pending_ledger_lock(ledger, manifest)
        lock_bytes = _json_bytes(pending_lock)
        lock_file_sha256 = _sha256(lock_bytes)
        lock_target = _private_target(
            args.lock_out.parent, args.lock_out.name)
    _write_private(json_target, _json_bytes(reference))
    _write_private(html_target, _render_html(reference, transcript).encode())
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
