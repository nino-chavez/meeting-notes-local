#!/usr/bin/env python3
"""Build and validate deterministic candidate-first extraction manifests.

This is the no-model half of the candidate-first architecture spike. Local code
enumerates evidence candidates before inference. A later classifier must return
exactly one KEEP or ABSTAIN decision for every offered candidate; it cannot decide
how many records exist.

The module deliberately does not write note/2 artifacts and does not call Ollama.
Its manifest is a research input, not a meeting note or a product result.

Usage:
    python notes/candidate_first.py notes/corpus/ES2004c.json --strip --compare
    python notes/candidate_first.py transcript.json --strategy broad \
      --out /private/tmp/candidates.json
    python notes/candidate_first.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

from summarize import (
    StructuredOutputError,
    build_fragment_map,
    resolve_fragment,
)
from transcript import NONE, Transcript, Turn, load
from transcript import _clean as clean_qmsum_text

MANIFEST_SCHEMA = "candidate-manifest/1"
GENERATOR_CONTRACT_SCHEMA = "candidate-generator/1"
CLASSIFIER_CONTRACT_SCHEMA = "candidate-classifier-response/1"
QMSUM_SPAN_SCHEMA = "qmsum-search-spans/1"
REGISTERED_RUN_SCHEMA = "candidate-classifier-registration/1"
CLASSIFIER_NUM_PREDICT_BASE = 32
CLASSIFIER_NUM_PREDICT_PER_ITEM = 96
CLASSIFIER_NUM_PREDICT_MAX = 4096

STRATEGY_BROAD = "broad"
STRATEGY_CUE = "cue"
STRATEGIES = (STRATEGY_BROAD, STRATEGY_CUE)

_CUE_PATTERNS = (
    (
        "decision",
        (
            r"\b(?:decid(?:e|ed|ing)|agree(?:d|ment)?|settled|go with|"
            r"choose|chosen|final(?:ly)?|conclusion)\b"
        ),
    ),
    (
        "action",
        (
            r"\b(?:(?:i|we|you|they|he|she)\s+(?:will|shall|plan to|"
            r"need to|have to|must|commit to)|action item|to-?do|follow-?up|"
            r"next step|send|prepare|deliver|check|look into|investigate|"
            r"schedule|assign)\b"
        ),
    ),
    (
        "proposal",
        (
            r"\b(?:maybe|perhaps|could|should|let'?s|how about|what if|"
            r"why don'?t|suggest(?:ion|ed|ing)?|recommend(?:ed|ation)?|"
            r"propos(?:e|ed|al)|prefer|idea|option)\b"
        ),
    ),
    (
        "question",
        r"\?|\b(?:question|not sure|don'?t know|whether)\b",
    ),
    (
        "request",
        r"\b(?:call upon|urge|request|please)\b",
    ),
)
_CUE_RE = re.compile(
    "|".join(f"(?P<c{index}>{pattern})" for index, (_name, pattern) in
             enumerate(_CUE_PATTERNS)),
    re.IGNORECASE,
)
_ASSENT_RE = re.compile(
    r"^(?:yes|yeah|yep|okay|ok|right|agreed|exactly|sure|"
    r"sounds good|that works|i agree)[.!?]?$",
    re.IGNORECASE,
)

GENERATOR_CONTRACT = {
    "schema": GENERATOR_CONTRACT_SCHEMA,
    "broad": "one candidate per canonical source fragment",
    "cue": "one candidate per non-overlapping cue hit plus bounded assent links",
    "cue_patterns": [
        {"family": family, "pattern": pattern}
        for family, pattern in _CUE_PATTERNS
    ],
    "assent_pattern": _ASSENT_RE.pattern,
    "assent_max_words": 8,
    "visible_context": "previous canonical fragment, anchor, next canonical fragment",
    "anchor_required": True,
    "source_text_retained": False,
    "candidate_order": "anchor fragment order, then cue character order",
}

CLASSIFIER_SYSTEM = """\
Classify deterministic evidence candidates from a meeting.

Return KEEP only when the anchor, read with its visible context, might directly
support at least one atomic:
- DECISION: something settled or explicitly agreed;
- ACTION: a person or group committed to do something;
- PROPOSAL: something suggested but not settled;
- QUESTION: a material question left unresolved in the visible context.

Return ABSTAIN for status facts, explanations, presentation content, social chatter,
repetition, or a backchannel that does not settle a nearby proposal. A question
answered in the visible context is not an unresolved question. Preserve recall when
the words genuinely could carry one of the four record types, but do not turn topic
relevance into a record.

Return JSON matching the supplied schema and nothing else. Return every candidate
exactly once, in the offered order."""

SABOTAGED_ALWAYS_KEEP_SYSTEM = """\
Return KEEP for every candidate without reading it. Return JSON matching the schema."""

SABOTAGED_ALWAYS_ABSTAIN_SYSTEM = """\
Return ABSTAIN for every candidate without reading it. Return JSON matching the schema."""

CLASSIFIER_FIXTURES = [
    {
        "candidate_id": "fixture-decision",
        "fragments": [
            {"anchor": True, "text": "Okay, let's use the smaller battery."},
        ],
        "expected": "KEEP",
    },
    {
        "candidate_id": "fixture-action",
        "fragments": [
            {"anchor": True, "text": "I will send the cost table tomorrow."},
        ],
        "expected": "KEEP",
    },
    {
        "candidate_id": "fixture-proposal",
        "fragments": [
            {"anchor": True, "text": "Maybe we should use rubber for the case."},
        ],
        "expected": "KEEP",
    },
    {
        "candidate_id": "fixture-open-question",
        "fragments": [
            {"anchor": True, "text": "Do we need consent for the recordings?"},
            {"anchor": False, "text": "The next topic is storage."},
        ],
        "expected": "KEEP",
    },
    {
        "candidate_id": "fixture-adjacent-assent",
        "fragments": [
            {"anchor": False, "text": "We could archive the old project files."},
            {"anchor": True, "text": "Yes, let's do that."},
        ],
        "expected": "KEEP",
    },
    {
        "candidate_id": "fixture-ambiguous-commitment",
        "fragments": [
            {"anchor": True, "text": "We need to check the supplier before Friday."},
        ],
        "expected": "KEEP",
    },
    {
        "candidate_id": "fixture-status",
        "fragments": [
            {"anchor": True, "text": "The build compiled successfully this morning."},
        ],
        "expected": "ABSTAIN",
    },
    {
        "candidate_id": "fixture-presentation-fact",
        "fragments": [
            {"anchor": True, "text": "Lithium batteries have high energy density."},
        ],
        "expected": "ABSTAIN",
    },
    {
        "candidate_id": "fixture-social",
        "fragments": [
            {"anchor": True, "text": "Good morning, everybody."},
        ],
        "expected": "ABSTAIN",
    },
    {
        "candidate_id": "fixture-empty-backchannel",
        "fragments": [
            {"anchor": False, "text": "The test ran for twenty minutes."},
            {"anchor": True, "text": "Mm-hmm."},
        ],
        "expected": "ABSTAIN",
    },
    {
        "candidate_id": "fixture-answered-question",
        "fragments": [
            {"anchor": True, "text": "What time is lunch?"},
            {"anchor": False, "text": "Lunch is at noon."},
        ],
        "expected": "ABSTAIN",
    },
    {
        "candidate_id": "fixture-opinion",
        "fragments": [
            {"anchor": True, "text": "The blue sample looks brighter."},
        ],
        "expected": "ABSTAIN",
    },
]

_WORKTREE_ROOT = Path(__file__).resolve().parent.parent


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


def _generator_contract_sha256() -> str:
    return _json_sha256(GENERATOR_CONTRACT)


def classifier_fixture_sha256() -> str:
    return _json_sha256(CLASSIFIER_FIXTURES)


def classifier_system_sha256() -> str:
    return _sha256(CLASSIFIER_SYSTEM)


REGISTERED_RUN = {
    "schema": REGISTERED_RUN_SCHEMA,
    "corpus": {
        "name": "ES2004c",
        "raw_sha256": (
            "31815196407111dba01f8b8cbfa31cd07fb8a682e4005bae7846893ab93a6778"
        ),
        "transform": "strip-attribution",
        "transcript_view_sha256": (
            "d10d60293f503724820957b95f7da0bf2aaa3513edee879cfcd03a0b5cca7940"
        ),
        "manifest_sha256": (
            "bd33f6da6b3aa9a2a76b203b53de56c7adc8854f10a047e00086d2bae48872df"
        ),
        "span_registry_sha256": (
            "00e770f6fc26a0f1664f0f4f440bd07ce43c24fc3054c09531f29cbe10f624c1"
        ),
        "candidates": 645,
    },
    "generator": {
        "strategy": STRATEGY_BROAD,
        "contract_sha256": (
            "4716a81374fa0311dd62ee6de59ab94b72c083336d99eb250d499d512e6486e0"
        ),
        "fragment_contract_sha256": (
            "2ea37109a924fb26bcc070836417c6fd822c8318c0b428d8dcf5cb5600ec727c"
        ),
    },
    "classifier": {
        "system_sha256": (
            "8dcacef1d52991e0972e1522e85617b1dec31a1b4a6cae2beb8522bbaf770119"
        ),
        "fixture_sha256": (
            "52bb4ac93d1dc5e9a384c78b2801fca22865640304301510031ec16ab1e4fb91"
        ),
        "model": "gemma3:27b",
        "model_digest": (
            "a418f5838eaf7fe2cfe0a3046c8384b68ba43a4435542c942f9db00a5f342203"
        ),
        "batch_size": 32,
        "num_ctx": 16384,
        "temperature": 0.0,
        "num_predict": "min(4096, 32 + 96 * candidates)",
        "model_facing_candidate_ids": (
            "batch-positional locators c01..cNN; local decode maps each "
            "locator to its registered candidate ID, requires exact "
            "single coverage, canonicalizes order, and counts "
            "displacement as a diagnostic"
        ),
    },
    "gates": {
        "fixture_agreement": 12,
        "candidate_coverage": 645,
        "maximum_keep": 64,
        "maximum_elapsed_seconds": 900,
        "packet_exposure": "all human-locked target events",
        "classifier_recall": "all human-locked target events",
        "event_ledger_required_before_inference": True,
    },
}


def registered_run_sha256() -> str:
    return _json_sha256(REGISTERED_RUN)


def validate_registered_model_identity(identity: object) -> dict:
    if not isinstance(identity, dict) or set(identity) != {
        "requested", "name", "digest"
    }:
        raise StructuredOutputError(
            "registered classifier model identity has the wrong shape")
    expected = REGISTERED_RUN["classifier"]
    if (
        identity["requested"] != expected["model"]
        or identity["name"] != expected["model"]
        or identity["digest"] != expected["model_digest"]
    ):
        raise StructuredOutputError(
            "registered classifier model tag no longer resolves to its pinned digest")
    return identity


def _candidate_id(descriptor: dict) -> str:
    return f"cf-{_json_sha256(descriptor)}"


def _fragment_index(fragment_map: dict) -> tuple[list[dict], dict[str, int]]:
    fragments = fragment_map["fragments"]
    return fragments, {
        fragment["source_fragment_id"]: index
        for index, fragment in enumerate(fragments)
    }


def _visible_fragment_ids(fragments: list[dict], anchor_index: int) -> list[str]:
    start = max(0, anchor_index - 1)
    end = min(len(fragments), anchor_index + 2)
    return [row["source_fragment_id"] for row in fragments[start:end]]


def _candidate(
    fragment_map: dict,
    strategy: str,
    ordinal: int,
    anchor_index: int,
    *,
    cue_type: str | None,
    cue_start: int | None,
    cue_end: int | None,
) -> dict:
    fragments, _lookup = _fragment_index(fragment_map)
    anchor = fragments[anchor_index]
    descriptor = {
        "schema": GENERATOR_CONTRACT_SCHEMA,
        "strategy": strategy,
        "transcript_view_sha256": fragment_map["transcript_view_sha256"],
        "anchor_fragment_id": anchor["source_fragment_id"],
        "cue_type": cue_type,
        "cue_start": cue_start,
        "cue_end": cue_end,
    }
    return {
        "candidate_id": _candidate_id(descriptor),
        "ordinal": ordinal,
        "anchor_fragment_id": anchor["source_fragment_id"],
        "anchor_turn": anchor["turn"],
        "anchor_char_start": anchor["char_start"],
        "anchor_char_end": anchor["char_end"],
        "cue_type": cue_type,
        "cue_start": cue_start,
        "cue_end": cue_end,
        "visible_fragment_ids": _visible_fragment_ids(fragments, anchor_index),
    }


def _broad_candidates(fragment_map: dict) -> list[dict]:
    fragments, _lookup = _fragment_index(fragment_map)
    return [
        _candidate(
            fragment_map,
            STRATEGY_BROAD,
            ordinal,
            anchor_index,
            cue_type=None,
            cue_start=None,
            cue_end=None,
        )
        for ordinal, anchor_index in enumerate(range(len(fragments)), 1)
    ]


def _cue_name(match: re.Match) -> str:
    group = match.lastgroup
    if group is None or not group.startswith("c"):
        raise StructuredOutputError("cue match has no deterministic family")
    return _CUE_PATTERNS[int(group[1:])][0]


def _fragment_for_offset(turn_fragments: list[dict], offset: int) -> dict:
    containing = [
        fragment
        for fragment in turn_fragments
        if fragment["char_start"] <= offset < fragment["char_end"]
    ]
    if containing:
        # Overlapping canonical fragments can both contain the cue. Choosing the
        # rightmost start gives one stable anchor closest to the cue.
        return max(containing, key=lambda row: row["char_start"])
    # Punctuation can sit exactly at a span boundary. The nearest preceding
    # canonical fragment is the stable fallback.
    preceding = [
        fragment for fragment in turn_fragments
        if fragment["char_start"] <= offset
    ]
    if preceding:
        return max(preceding, key=lambda row: row["char_start"])
    return turn_fragments[0]


def _cue_candidates(transcript: Transcript, fragment_map: dict) -> list[dict]:
    fragments, fragment_indices = _fragment_index(fragment_map)
    by_turn: dict[int, list[dict]] = {}
    for fragment in fragments:
        by_turn.setdefault(fragment["turn"], []).append(fragment)

    rows: list[tuple[int, str, int, int]] = []
    cue_turns: set[int] = set()
    for turn_index, turn in enumerate(transcript.turns):
        turn_fragments = by_turn.get(turn_index, [])
        if not turn_fragments:
            continue
        for match in _CUE_RE.finditer(turn.text):
            anchor = _fragment_for_offset(turn_fragments, match.start())
            rows.append((
                fragment_indices[anchor["source_fragment_id"]],
                _cue_name(match),
                match.start(),
                match.end(),
            ))
            cue_turns.add(turn_index)

    for turn_index, turn in enumerate(transcript.turns):
        if turn_index == 0 or turn_index in cue_turns:
            continue
        if len(turn.text.split()) > 8 or not _ASSENT_RE.fullmatch(turn.text.strip()):
            continue
        if turn_index - 1 not in cue_turns:
            continue
        turn_fragments = by_turn.get(turn_index, [])
        if not turn_fragments:
            continue
        anchor = turn_fragments[0]
        rows.append((
            fragment_indices[anchor["source_fragment_id"]],
            "assent-link",
            0,
            len(turn.text),
        ))

    rows.sort(key=lambda row: (row[0], row[2], row[3], row[1]))
    return [
        _candidate(
            fragment_map,
            STRATEGY_CUE,
            ordinal,
            anchor_index,
            cue_type=cue_type,
            cue_start=cue_start,
            cue_end=cue_end,
        )
        for ordinal, (anchor_index, cue_type, cue_start, cue_end)
        in enumerate(rows, 1)
    ]


def generate_manifest(transcript: Transcript, strategy: str) -> dict:
    if strategy not in STRATEGIES:
        raise StructuredOutputError(
            f"candidate strategy must be one of {', '.join(STRATEGIES)}")
    fragment_map = build_fragment_map(transcript)
    candidates = (
        _broad_candidates(fragment_map)
        if strategy == STRATEGY_BROAD
        else _cue_candidates(transcript, fragment_map)
    )
    base = {
        "schema": MANIFEST_SCHEMA,
        "strategy": strategy,
        "source": transcript.source,
        "attribution": transcript.attribution,
        "transcript_view_sha256": fragment_map["transcript_view_sha256"],
        "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
        "generator_contract": dict(GENERATOR_CONTRACT),
        "generator_contract_sha256": _generator_contract_sha256(),
        "counts": {
            "turns": len(transcript.turns),
            "source_fragments": len(fragment_map["fragments"]),
            "candidates": len(candidates),
        },
        "candidates": candidates,
    }
    return {**base, "manifest_sha256": _json_sha256(base)}


def validate_manifest(manifest: object, transcript: Transcript) -> dict:
    if not isinstance(manifest, dict):
        raise StructuredOutputError("candidate manifest must be a JSON object")
    expected_keys = {
        "schema", "strategy", "source", "attribution",
        "transcript_view_sha256", "fragment_contract_sha256",
        "generator_contract", "generator_contract_sha256",
        "counts", "candidates", "manifest_sha256",
    }
    if set(manifest) != expected_keys:
        raise StructuredOutputError("candidate manifest has the wrong shape")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise StructuredOutputError("candidate manifest schema is not current")
    strategy = manifest.get("strategy")
    if strategy not in STRATEGIES:
        raise StructuredOutputError("candidate manifest strategy is invalid")
    received_base = {
        key: value for key, value in manifest.items()
        if key != "manifest_sha256"
    }
    if manifest.get("manifest_sha256") != _json_sha256(received_base):
        raise StructuredOutputError(
            "candidate manifest digest does not re-derive")
    expected = generate_manifest(transcript, strategy)
    if _json_bytes(manifest) != _json_bytes(expected):
        raise StructuredOutputError(
            "candidate manifest does not re-derive from the transcript")

    candidates = manifest["candidates"]
    ids = [row["candidate_id"] for row in candidates]
    if len(ids) != len(set(ids)):
        raise StructuredOutputError("candidate manifest has duplicate IDs")
    if [row["ordinal"] for row in candidates] != list(
            range(1, len(candidates) + 1)):
        raise StructuredOutputError("candidate manifest order is not contiguous")

    fragment_map = build_fragment_map(transcript)
    lookup = {
        row["source_fragment_id"]: row
        for row in fragment_map["fragments"]
    }
    for row in candidates:
        anchor_id = row["anchor_fragment_id"]
        visible = row["visible_fragment_ids"]
        if (
            anchor_id not in lookup
            or not isinstance(visible, list)
            or not 1 <= len(visible) <= 3
            or anchor_id not in visible
            or len(visible) != len(set(visible))
            or any(fragment_id not in lookup for fragment_id in visible)
        ):
            raise StructuredOutputError(
                f"candidate {row['candidate_id']} has invalid evidence references")
        for fragment_id in visible:
            resolve_fragment(
                lookup[fragment_id],
                transcript,
                fragment_map["transcript_view_sha256"],
            )
    return manifest


def qmsum_search_spans(path: Path, transcript: Transcript) -> dict:
    """Bind human search regions to the cleaned transcript coordinate system.

    QMSum's spans use zero-based, inclusive raw-row ordinals. The product loader
    drops rows that contain only non-speech markers, so raw ordinals cannot be
    used as transcript turn ordinals.
    """
    try:
        corpus_bytes = path.read_bytes()
    except OSError as exc:
        raise StructuredOutputError(f"cannot read QMSum search spans: {exc}") from exc
    try:
        data = json.loads(corpus_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StructuredOutputError(f"cannot read QMSum search spans: {exc}") from exc
    if not isinstance(data, dict):
        raise StructuredOutputError(
            "QMSum search-span input must be a JSON object")
    raw_rows = data.get("meeting_transcripts")
    queries = data.get("specific_query_list")
    if not isinstance(raw_rows, list) or not isinstance(queries, list):
        raise StructuredOutputError(
            "QMSum search-span input has no transcript rows or specific queries")

    raw_to_clean: list[int | None] = []
    cleaned_rows: list[tuple[str, str | None]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise StructuredOutputError("QMSum transcript row is not an object")
        content = raw.get("content")
        speaker = raw.get("speaker")
        if not isinstance(content, str) or not isinstance(speaker, str):
            raise StructuredOutputError(
                "QMSum transcript row has invalid content or speaker")
        cleaned = clean_qmsum_text(content)
        if not cleaned:
            raw_to_clean.append(None)
            continue
        raw_to_clean.append(len(cleaned_rows))
        cleaned_rows.append((cleaned, speaker))

    visible = [(turn.text, turn.speaker) for turn in transcript.turns]
    expected_text = [text for text, _speaker in cleaned_rows]
    if [text for text, _speaker in visible] != expected_text:
        raise StructuredOutputError(
            "QMSum raw-to-clean mapping does not reproduce the transcript view")
    if transcript.attribution != NONE:
        expected_speakers = [speaker for _text, speaker in cleaned_rows]
        if [speaker for _text, speaker in visible] != expected_speakers:
            raise StructuredOutputError(
                "QMSum raw-to-clean mapping does not reproduce speaker labels")

    mapping = {
        "raw_rows": len(raw_rows),
        "cleaned_turns": len(cleaned_rows),
        "raw_to_clean": raw_to_clean,
    }
    spans = []
    for query_index, query in enumerate(queries, 1):
        if not isinstance(query, dict):
            raise StructuredOutputError("QMSum specific query is not an object")
        raw_spans = query.get("relevant_text_span")
        if not isinstance(raw_spans, list) or not raw_spans:
            raise StructuredOutputError(
                f"QMSum specific query {query_index} has no search span")
        for span_index, raw_span in enumerate(raw_spans, 1):
            if (
                not isinstance(raw_span, list)
                or len(raw_span) != 2
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (str, int))
                    for value in raw_span
                )
            ):
                raise StructuredOutputError(
                    f"QMSum query {query_index} span {span_index} is malformed")
            try:
                start, end = (int(value) for value in raw_span)
            except ValueError as exc:
                raise StructuredOutputError(
                    f"QMSum query {query_index} span {span_index} is not numeric"
                ) from exc
            if not 0 <= start <= end < len(raw_rows):
                raise StructuredOutputError(
                    f"QMSum query {query_index} span {span_index} is out of range")
            clean_turns = sorted({
                clean_turn
                for clean_turn in raw_to_clean[start:end + 1]
                if clean_turn is not None
            })
            if not clean_turns:
                raise StructuredOutputError(
                    f"QMSum query {query_index} span {span_index} has no visible words")
            spans.append({
                "span_id": f"specific-{query_index:03d}-span-{span_index:02d}",
                "raw_start_inclusive": start,
                "raw_end_inclusive": end,
                "clean_turns": clean_turns,
            })

    base = {
        "schema": QMSUM_SPAN_SCHEMA,
        "coordinate_contract": (
            "QMSum zero-based inclusive raw meeting_transcripts row ordinals, "
            "mapped through the canonical non-speech cleaner"
        ),
        "corpus_sha256": _sha256(corpus_bytes),
        "transcript_view_sha256": build_fragment_map(
            transcript)["transcript_view_sha256"],
        "mapping": mapping,
        "mapping_sha256": _json_sha256(mapping),
        "spans": spans,
        "spans_sha256": _json_sha256(spans),
    }
    return {**base, "registry_sha256": _json_sha256(base)}


def validate_registered_inputs(
    path: Path,
    transcript: Transcript,
    manifest: dict,
    registry: dict,
) -> dict:
    """Refuse corpus or contract drift before the registered run can start."""
    validate_manifest(manifest, transcript)
    derived_registry = qmsum_search_spans(path, transcript)
    if _json_bytes(registry) != _json_bytes(derived_registry):
        raise StructuredOutputError(
            "registered QMSum span registry does not re-derive from the corpus")

    expected_corpus = REGISTERED_RUN["corpus"]
    expected_generator = REGISTERED_RUN["generator"]
    observed = {
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
    }
    expected = {
        "raw_sha256": expected_corpus["raw_sha256"],
        "transcript_view_sha256": expected_corpus["transcript_view_sha256"],
        "manifest_sha256": expected_corpus["manifest_sha256"],
        "span_registry_sha256": expected_corpus["span_registry_sha256"],
        "candidates": expected_corpus["candidates"],
        "strategy": expected_generator["strategy"],
        "generator_contract_sha256": expected_generator["contract_sha256"],
        "fragment_contract_sha256": expected_generator[
            "fragment_contract_sha256"
        ],
        "classifier_system_sha256": REGISTERED_RUN[
            "classifier"
        ]["system_sha256"],
        "classifier_fixture_sha256": REGISTERED_RUN[
            "classifier"
        ]["fixture_sha256"],
    }
    if observed != expected:
        raise StructuredOutputError(
            "registered corpus, generator, or classifier authority changed")
    return {
        "registration_sha256": registered_run_sha256(),
        "observed": observed,
    }


def qmsum_span_report(
    registry: dict,
    manifest: dict,
    decisions: list[dict],
) -> dict:
    registry_keys = {
        "schema", "coordinate_contract", "corpus_sha256",
        "transcript_view_sha256", "mapping", "mapping_sha256",
        "spans", "spans_sha256", "registry_sha256",
    }
    if not isinstance(registry, dict) or set(registry) != registry_keys:
        raise StructuredOutputError("QMSum span registry has the wrong shape")
    registry_base = {
        key: value for key, value in registry.items()
        if key != "registry_sha256"
    }
    if (
        registry.get("schema") != QMSUM_SPAN_SCHEMA
        or registry.get("mapping_sha256") != _json_sha256(registry.get("mapping"))
        or registry.get("spans_sha256") != _json_sha256(registry.get("spans"))
        or registry.get("registry_sha256") != _json_sha256(registry_base)
    ):
        raise StructuredOutputError(
            "QMSum span registry schema or digest is missing or changed")
    if not isinstance(manifest, dict) or manifest.get("manifest_sha256") != (
        _json_sha256({
            key: value for key, value in manifest.items()
            if key != "manifest_sha256"
        })
    ):
        raise StructuredOutputError("candidate manifest digest does not re-derive")
    if (
        registry.get("transcript_view_sha256")
        != manifest.get("transcript_view_sha256")
    ):
        raise StructuredOutputError(
            "QMSum search spans and candidate manifest use different transcript views")
    candidates = manifest.get("candidates")
    if (
        not isinstance(candidates, list)
        or any(
            not isinstance(row, dict)
            or not isinstance(row.get("candidate_id"), str)
            or not isinstance(row.get("anchor_turn"), int)
            for row in candidates
        )
    ):
        raise StructuredOutputError("candidate manifest has no candidates")
    expected_ids = [row["candidate_id"] for row in candidates]
    if (
        not isinstance(decisions, list)
        or any(
            not isinstance(row, dict)
            or set(row) != {"candidate_id", "verdict"}
            for row in decisions
        )
        or len(decisions) != len(expected_ids)
        or [row["candidate_id"] for row in decisions] != expected_ids
        or any(row.get("verdict") not in {"KEEP", "ABSTAIN"} for row in decisions)
    ):
        raise StructuredOutputError(
            "QMSum span report requires one ordered decision per candidate")
    kept_turns = {
        candidate["anchor_turn"]
        for candidate, decision in zip(candidates, decisions, strict=True)
        if decision["verdict"] == "KEEP"
    }
    rows = []
    for span in registry["spans"]:
        hit = bool(kept_turns.intersection(span["clean_turns"]))
        rows.append({"span_id": span["span_id"], "hit": hit})
    return {
        "schema": "qmsum-search-span-report/1",
        "registry_sha256": registry["registry_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "spans": len(rows),
        "hit": sum(row["hit"] for row in rows),
        "missed": [row["span_id"] for row in rows if not row["hit"]],
        "rows": rows,
        "meaning": "search-region smoke test; not event recall",
    }


def candidate_batches(candidates: list[dict], batch_size: int) -> list[list[dict]]:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise StructuredOutputError("candidate batch size must be a positive integer")
    return [
        candidates[index:index + batch_size]
        for index in range(0, len(candidates), batch_size)
    ]


def classification_num_predict(candidate_count: int) -> int:
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count <= 0
    ):
        raise StructuredOutputError(
            "classifier token budget requires a positive candidate count")
    return min(
        CLASSIFIER_NUM_PREDICT_MAX,
        CLASSIFIER_NUM_PREDICT_BASE
        + CLASSIFIER_NUM_PREDICT_PER_ITEM * candidate_count,
    )


def batch_locators(candidate_ids: list[str]) -> list[str]:
    """Short model-facing labels for one batch, mapped locally by position.

    Measured 2026-08-14 on the pinned gemma3:12b: echoing 64-hex candidate
    IDs cost 75 output tokens per item and produced duplicated and dropped
    IDs in 2 of 6 live batches. The model never sees the hex IDs in the
    response contract; it sees c01..cNN, and only local code maps them back.
    """
    if (
        not isinstance(candidate_ids, list)
        or not candidate_ids
        or len(candidate_ids) > 99
        or any(not isinstance(value, str) or not value for value in candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
    ):
        raise StructuredOutputError(
            "classifier schema requires up to 99 unique nonblank candidate IDs")
    return [f"c{index:02d}" for index in range(1, len(candidate_ids) + 1)]


def classification_format(candidate_ids: list[str]) -> dict:
    locators = batch_locators(candidate_ids)
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidate_id", "verdict"],
        "properties": {
            "candidate_id": {"type": "string", "enum": locators},
            "verdict": {"type": "string", "enum": ["KEEP", "ABSTAIN"]},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": item,
                "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids),
            },
        },
    }


class _OrderedObject:
    def __init__(self, pairs: list[tuple[str, object]]):
        self.pairs = pairs


def _strict_json(raw: str) -> object:
    if not isinstance(raw, str) or not raw.strip():
        raise StructuredOutputError("empty classifier response")

    def ordered(pairs: list[tuple[str, object]]) -> _OrderedObject:
        keys = [key for key, _value in pairs]
        if len(keys) != len(set(keys)):
            raise StructuredOutputError(
                f"classifier response has duplicate JSON key(s): {keys!r}")
        return _OrderedObject(pairs)

    try:
        return json.loads(raw, object_pairs_hook=ordered)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"malformed classifier JSON: {exc.msg}") from exc


def decode_classification(raw: str, expected_candidate_ids: list[str]) -> dict:
    classification_format(expected_candidate_ids)
    decoded = _strict_json(raw)
    if not isinstance(decoded, _OrderedObject):
        raise StructuredOutputError("classifier response must be a JSON object")
    if tuple(key for key, _value in decoded.pairs) != ("items",):
        raise StructuredOutputError(
            "classifier response must contain only items, in that order")
    rows = decoded.pairs[0][1]
    if not isinstance(rows, list):
        raise StructuredOutputError("classifier items must be a JSON array")
    if len(rows) != len(expected_candidate_ids):
        raise StructuredOutputError(
            "classifier response cardinality does not match its offered candidates")

    locators = batch_locators(expected_candidate_ids)
    position = {locator: index for index, locator in enumerate(locators)}
    seen: set[str] = set()
    returned: list[tuple[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, _OrderedObject):
            raise StructuredOutputError(
                f"classifier item {index} must be a JSON object")
        keys = tuple(key for key, _value in row.pairs)
        if keys != ("candidate_id", "verdict"):
            raise StructuredOutputError(
                f"classifier item {index} keys are missing, extra, or reordered")
        values = dict(row.pairs)
        locator = values["candidate_id"]
        verdict = values["verdict"]
        if not isinstance(locator, str) or not isinstance(verdict, str):
            raise StructuredOutputError(
                f"classifier item {index} values must be strings")
        if locator not in position:
            raise StructuredOutputError(
                f"classifier item {index} names an unknown candidate locator")
        if locator in seen:
            raise StructuredOutputError(
                f"classifier item {index} duplicates candidate locator {locator}")
        if verdict not in {"KEEP", "ABSTAIN"}:
            raise StructuredOutputError(
                f"classifier item {index} has an invalid verdict")
        seen.add(locator)
        returned.append((locator, verdict))
    if len(returned) != len(locators):
        raise StructuredOutputError(
            "classifier response does not cover the offered candidates exactly once")
    # Order carries no information the locator does not already carry, and no
    # JSON schema can constrain it. Decode canonicalizes to registered order
    # deterministically and counts the displacement as a replayable diagnostic.
    out_of_order = sum(
        1 for index, (locator, _verdict) in enumerate(returned)
        if position[locator] != index)
    safe_rows = [
        {
            "candidate_id": expected_candidate_ids[position[locator]],
            "verdict": verdict,
        }
        for locator, verdict in sorted(
            returned, key=lambda pair: position[pair[0]])
    ]
    return {
        "schema": CLASSIFIER_CONTRACT_SCHEMA,
        "items": safe_rows,
        "counts": {
            "expected": len(expected_candidate_ids),
            "returned": len(safe_rows),
            "keep": sum(row["verdict"] == "KEEP" for row in safe_rows),
            "abstain": sum(row["verdict"] == "ABSTAIN" for row in safe_rows),
            "out_of_order_positions": out_of_order,
        },
    }


def decode_fixture_classification(raw: str) -> dict:
    """Require exact semantic fixture agreement, not merely valid transport."""
    candidate_ids = [row["candidate_id"] for row in CLASSIFIER_FIXTURES]
    expected = [row["expected"] for row in CLASSIFIER_FIXTURES]
    decoded = decode_classification(raw, candidate_ids)
    actual = [row["verdict"] for row in decoded["items"]]
    if actual != expected:
        raise StructuredOutputError(
            "classifier semantic fixtures did not match all expected verdicts")
    return {
        **decoded,
        "fixture_sha256": classifier_fixture_sha256(),
        "agreement": len(expected),
        "expected": len(expected),
    }


def _classification_user(packets: list[dict]) -> str:
    return (
        "Classify every candidate below.\n\n"
        + json.dumps(packets, ensure_ascii=False, separators=(",", ":"))
    )


def classifier_fixture_request() -> tuple[dict, str, str, list[str]]:
    candidate_ids = [row["candidate_id"] for row in CLASSIFIER_FIXTURES]
    locators = batch_locators(candidate_ids)
    packets = [
        {
            "candidate_id": locator,
            "fragments": row["fragments"],
        }
        for locator, row in zip(locators, CLASSIFIER_FIXTURES, strict=True)
    ]
    expected = [row["expected"] for row in CLASSIFIER_FIXTURES]
    return (
        classification_format(candidate_ids),
        CLASSIFIER_SYSTEM,
        _classification_user(packets),
        expected,
    )


def classification_request(
    transcript: Transcript,
    manifest: dict,
    batch: list[dict],
    batch_size: int,
) -> tuple[dict, str, str]:
    validate_manifest(manifest, transcript)
    if (
        not isinstance(batch, list)
        or not batch
        or any(not isinstance(row, dict) for row in batch)
    ):
        raise StructuredOutputError(
            "classifier batch is empty or malformed")
    expected_batches = candidate_batches(manifest["candidates"], batch_size)
    if not any(
        _json_bytes(batch) == _json_bytes(expected)
        for expected in expected_batches
    ):
        raise StructuredOutputError(
            "classifier batch is not one registered contiguous batch")
    manifest_rows = {
        row["candidate_id"]: row for row in manifest["candidates"]
    }
    manifest_positions = {
        row["candidate_id"]: index
        for index, row in enumerate(manifest["candidates"])
    }
    candidate_ids = [row.get("candidate_id") for row in batch]
    positions = [
        manifest_positions.get(candidate_id)
        for candidate_id in candidate_ids
    ]
    if (
        any(candidate_id not in manifest_rows for candidate_id in candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
        or positions != list(range(positions[0], positions[0] + len(positions)))
        or any(
            row != manifest_rows[candidate_id]
            for row, candidate_id in zip(batch, candidate_ids, strict=True)
        )
    ):
        raise StructuredOutputError(
            "classifier batch is duplicated, altered, or outside the manifest")

    fragment_map = build_fragment_map(transcript)
    lookup = {
        row["source_fragment_id"]: row
        for row in fragment_map["fragments"]
    }
    locators = batch_locators(candidate_ids)
    packets = []
    for candidate in batch:
        rows = []
        for fragment_id in candidate["visible_fragment_ids"]:
            fragment = lookup[fragment_id]
            row = {
                "source_fragment_id": fragment_id,
                "anchor": fragment_id == candidate["anchor_fragment_id"],
                "text": resolve_fragment(
                    fragment,
                    transcript,
                    fragment_map["transcript_view_sha256"],
                ),
            }
            speaker = transcript.turns[fragment["turn"]].speaker
            if transcript.attribution != NONE and speaker:
                row["speaker"] = speaker
            rows.append(row)
        cue = None
        cue_start = candidate["cue_start"]
        cue_end = candidate["cue_end"]
        if candidate["cue_type"] is not None:
            anchor_turn = transcript.turns[candidate["anchor_turn"]].text
            if (
                not isinstance(cue_start, int)
                or not isinstance(cue_end, int)
                or not 0 <= cue_start < cue_end <= len(anchor_turn)
            ):
                raise StructuredOutputError(
                    f"candidate {candidate['candidate_id']} has an invalid cue span")
            cue = {
                "type": candidate["cue_type"],
                "char_start": cue_start,
                "char_end": cue_end,
                "text": anchor_turn[cue_start:cue_end],
            }
        packets.append({
            "candidate_id": locators[len(packets)],
            "cue": cue,
            "fragments": rows,
        })
    return (
        classification_format(candidate_ids),
        CLASSIFIER_SYSTEM,
        _classification_user(packets),
    )


def _resolved_target(path: Path) -> Path:
    return path.parent.resolve() / path.name


def _inside_git_worktree(target: Path) -> bool:
    """Reject every repository, not only the worktree running this module."""
    return any((parent / ".git").exists() for parent in (
        target.parent,
        *target.parent.parents,
    ))


def validate_output_target(path: Path, *, replace: bool = False) -> Path:
    target = _resolved_target(path)
    if _inside_git_worktree(target):
        raise StructuredOutputError(
            "candidate manifests contain meeting-derived provenance and must be "
            "written outside the repository")
    if not target.parent.exists() or not target.parent.is_dir():
        raise StructuredOutputError(
            f"candidate manifest parent does not exist: {target.parent}")
    if target.exists():
        if target.is_dir():
            raise StructuredOutputError(
                f"candidate manifest output is a directory: {target}")
        if not replace:
            raise StructuredOutputError(
                f"candidate manifest already exists: {target}; use --replace")
    return target


def validate_distinct_input_output(input_path: Path, output_path: Path) -> None:
    input_target = input_path.resolve()
    output_target = _resolved_target(output_path)
    same_inode = (
        output_target.exists()
        and input_target.exists()
        and os.path.samefile(input_target, output_target)
    )
    if input_target == output_target or same_inode:
        raise StructuredOutputError(
            "candidate manifest output must not overwrite its transcript input")


def write_private_manifest(
    path: Path,
    manifest: dict,
    *,
    replace: bool = False,
) -> Path:
    target = validate_output_target(path, replace=replace)
    payload = _json_bytes(manifest)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".partial",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        fd = -1
        if replace:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise StructuredOutputError(
                    f"candidate manifest appeared during write: {target}") from exc
            temporary.unlink()
        os.chmod(target, 0o600)
        return target
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def _self_test_transcript() -> Transcript:
    return Transcript(
        source="candidate synthetic fixture",
        attribution=NONE,
        turns=[
            # Long enough to exercise overlapping canonical fragments.
            # The words are synthetic and belong to no meeting.
            Turn(text=text)
            for text in (
                "The opening is ordinary status chatter with no commitment.",
                "Maybe we should choose the smaller battery for the first build?",
                "Yes.",
                "I will send the cost table tomorrow and check the supplier.",
                "The closing is more ordinary status chatter without a commitment.",
                " ".join(f"token{index}" for index in range(70)),
            )
        ],
    )


def run_self_test() -> int:
    transcript = _self_test_transcript()
    assert REGISTERED_RUN["classifier"]["system_sha256"] == (
        classifier_system_sha256()
    )
    assert REGISTERED_RUN["classifier"]["fixture_sha256"] == (
        classifier_fixture_sha256()
    )
    registered_identity = {
        "requested": REGISTERED_RUN["classifier"]["model"],
        "name": REGISTERED_RUN["classifier"]["model"],
        "digest": REGISTERED_RUN["classifier"]["model_digest"],
    }
    assert validate_registered_model_identity(registered_identity) == (
        registered_identity
    )
    changed_identity = dict(registered_identity)
    changed_identity["digest"] = "0" * 64
    try:
        validate_registered_model_identity(changed_identity)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("a changed classifier model digest was accepted")

    broad = generate_manifest(transcript, STRATEGY_BROAD)
    cue = generate_manifest(transcript, STRATEGY_CUE)
    validate_manifest(broad, transcript)
    validate_manifest(cue, transcript)
    assert broad == generate_manifest(transcript, STRATEGY_BROAD)
    assert cue == generate_manifest(transcript, STRATEGY_CUE)
    assert broad["counts"]["candidates"] == broad["counts"]["source_fragments"]
    assert cue["counts"]["candidates"] > 0
    assert len({
        row["candidate_id"] for row in cue["candidates"]
    }) == cue["counts"]["candidates"]

    broken = json.loads(json.dumps(broad))
    broken["candidates"][0]["candidate_id"] = "changed"
    try:
        validate_manifest(broken, transcript)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("tampered manifest was accepted")
    for substituted_ordinal in (True, 1.0):
        broken = json.loads(json.dumps(broad))
        broken["candidates"][0]["ordinal"] = substituted_ordinal
        try:
            validate_manifest(broken, transcript)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(
                "type-substituted manifest bytes were accepted")

    for invalid in (True, 0, -1, 1.5, "2"):
        try:
            candidate_batches(broad["candidates"], invalid)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(f"invalid batch size was accepted: {invalid!r}")
        try:
            classification_num_predict(invalid)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(
                f"invalid classifier token count was accepted: {invalid!r}")
    assert classification_num_predict(32) == 3104

    batch = candidate_batches(broad["candidates"], 3)[0]
    ids = [row["candidate_id"] for row in batch]
    schema = classification_format(ids)
    bounds = schema["properties"]["items"]
    assert bounds["minItems"] == bounds["maxItems"] == len(ids)
    locators = batch_locators(ids)
    raw = json.dumps({
        "items": [
            {"candidate_id": locators[0], "verdict": "KEEP"},
            {"candidate_id": locators[1], "verdict": "ABSTAIN"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]
    }, separators=(",", ":"))
    decoded = decode_classification(raw, ids)
    assert decoded["counts"] == {
        "expected": 3,
        "returned": 3,
        "keep": 2,
        "abstain": 1,
        "out_of_order_positions": 0,
    }
    assert [row["candidate_id"] for row in decoded["items"]] == ids
    reordered = json.dumps({
        "items": [
            {"candidate_id": locators[1], "verdict": "ABSTAIN"},
            {"candidate_id": locators[0], "verdict": "KEEP"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]
    }, separators=(",", ":"))
    canonical = decode_classification(reordered, ids)
    assert canonical["counts"]["out_of_order_positions"] == 2
    assert [row["candidate_id"] for row in canonical["items"]] == ids
    assert [row["verdict"] for row in canonical["items"]] == [
        "KEEP", "ABSTAIN", "KEEP"]
    all_abstain = json.dumps({
        "items": [
            {"candidate_id": locator, "verdict": "ABSTAIN"}
            for locator in locators
        ]
    }, separators=(",", ":"))
    assert decode_classification(all_abstain, ids)["counts"]["abstain"] == 3
    all_keep = json.dumps({
        "items": [
            {"candidate_id": locator, "verdict": "KEEP"}
            for locator in locators
        ]
    }, separators=(",", ":"))
    assert decode_classification(all_keep, ids)["counts"]["keep"] == 3

    invalid_responses = [
        "",
        "{}",
        '{"items":[]}',
        json.dumps({"items": [
            {"candidate_id": locators[0], "verdict": "KEEP"},
            {"candidate_id": locators[0], "verdict": "ABSTAIN"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]}, separators=(",", ":")),
        json.dumps({"items": [
            {"candidate_id": ids[0], "verdict": "KEEP"},
            {"candidate_id": ids[1], "verdict": "ABSTAIN"},
            {"candidate_id": ids[2], "verdict": "KEEP"},
        ]}, separators=(",", ":")),
        json.dumps({"items": [
            {"verdict": "KEEP", "candidate_id": locators[0]},
            {"candidate_id": locators[1], "verdict": "ABSTAIN"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]}, separators=(",", ":")),
        json.dumps({"items": [
            {"candidate_id": locators[0], "verdict": "MAYBE"},
            {"candidate_id": locators[1], "verdict": "ABSTAIN"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]}, separators=(",", ":")),
        json.dumps({"items": [
            {"candidate_id": locators[0], "verdict": []},
            {"candidate_id": locators[1], "verdict": "ABSTAIN"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]}, separators=(",", ":")),
        (
            '{"items":[{"candidate_id":"' + locators[0]
            + '","candidate_id":"' + locators[0] + '","verdict":"KEEP"}]}'
        ),
        json.dumps({"items": [
            {"candidate_id": locators[0], "verdict": "KEEP", "extra": True},
            {"candidate_id": locators[1], "verdict": "ABSTAIN"},
            {"candidate_id": locators[2], "verdict": "KEEP"},
        ]}, separators=(",", ":")),
    ]
    for raw_invalid in invalid_responses:
        try:
            decode_classification(raw_invalid, ids)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(
                f"invalid classifier response was accepted: {raw_invalid[:80]!r}")

    request_schema, system, user = classification_request(
        transcript, broad, batch, 3)
    assert request_schema == schema
    assert system == CLASSIFIER_SYSTEM
    assert all(locator in user for locator in locators)
    assert all(candidate_id not in user for candidate_id in ids)
    assert all(row["anchor_fragment_id"] in row["visible_fragment_ids"] for row in batch)
    altered_batch = json.loads(json.dumps(batch))
    altered_batch[0]["visible_fragment_ids"] = altered_batch[0][
        "visible_fragment_ids"
    ][::-1]
    reordered_batch = [batch[1], batch[0], batch[2]]
    for invalid_batch in (altered_batch, reordered_batch, batch[:2]):
        try:
            classification_request(transcript, broad, invalid_batch, 3)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(
                "an altered or noncanonical classifier batch was accepted")

    fixture_schema, fixture_system, fixture_user, fixture_expected = (
        classifier_fixture_request()
    )
    fixture_ids = [row["candidate_id"] for row in CLASSIFIER_FIXTURES]
    assert fixture_schema == classification_format(fixture_ids)
    assert fixture_system == CLASSIFIER_SYSTEM
    fixture_locators = batch_locators(fixture_ids)
    assert all(locator in fixture_user for locator in fixture_locators)
    assert all(candidate_id not in fixture_user for candidate_id in fixture_ids)
    assert set(fixture_expected) == {"KEEP", "ABSTAIN"}
    assert classifier_fixture_sha256() == _json_sha256(CLASSIFIER_FIXTURES)
    fixture_raw = json.dumps({
        "items": [
            {"candidate_id": locator, "verdict": expected}
            for locator, expected in zip(
                fixture_locators, fixture_expected, strict=True)
        ]
    }, separators=(",", ":"))
    assert decode_fixture_classification(
        fixture_raw)["agreement"] == len(CLASSIFIER_FIXTURES)
    for sabotaged_verdict in ("KEEP", "ABSTAIN"):
        sabotaged_raw = json.dumps({
            "items": [
                {
                    "candidate_id": locator,
                    "verdict": sabotaged_verdict,
                }
                for locator in fixture_locators
            ]
        }, separators=(",", ":"))
        try:
            decode_fixture_classification(sabotaged_raw)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError(
                f"all-{sabotaged_verdict.lower()} fixture sabotage was accepted")
    always_keep_agreement = sum(
        expected == "KEEP" for expected in fixture_expected)
    always_abstain_agreement = sum(
        expected == "ABSTAIN" for expected in fixture_expected)
    assert always_keep_agreement < len(fixture_expected)
    assert always_abstain_agreement < len(fixture_expected)

    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / "input.json"
        input_path.write_text("{}")
        alias_path = Path(directory) / "input-alias.json"
        os.link(input_path, alias_path)
        for output_path in (input_path, alias_path):
            try:
                validate_distinct_input_output(input_path, output_path)
            except StructuredOutputError:
                pass
            else:
                raise AssertionError(
                    "transcript input could be overwritten through an alias")

        target = Path(directory) / "manifest.json"
        wrote = write_private_manifest(target, broad)
        assert json.loads(wrote.read_text()) == broad
        assert stat.S_IMODE(wrote.stat().st_mode) == 0o600
        try:
            write_private_manifest(target, broad)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("existing manifest was overwritten without --replace")
        write_private_manifest(target, cue, replace=True)
        assert json.loads(target.read_text()) == cue

        qmsum_path = Path(directory) / "qmsum.json"
        qmsum_path.write_text(json.dumps({
            "meeting_transcripts": [
                {"speaker": "A", "content": "The opening status is complete."},
                {"speaker": "B", "content": "{gap}"},
                {"speaker": "A", "content": "Maybe we should archive the files."},
                {"speaker": "B", "content": "Yes."},
            ],
            "specific_query_list": [
                {
                    "query": "What was proposed?",
                    "answer": "Archiving the files was proposed.",
                    "relevant_text_span": [["1", "3"]],
                },
                {
                    "query": "What status was given?",
                    "answer": "The opening status was complete.",
                    "relevant_text_span": [["0", "0"]],
                },
            ],
        }))
        qmsum_transcript = load(qmsum_path).strip_attribution()
        qmsum_manifest = generate_manifest(qmsum_transcript, STRATEGY_BROAD)
        registry = qmsum_search_spans(qmsum_path, qmsum_transcript)
        assert registry["mapping"]["raw_to_clean"] == [0, None, 1, 2]
        keep_decisions = [
            {"candidate_id": row["candidate_id"], "verdict": "KEEP"}
            for row in qmsum_manifest["candidates"]
        ]
        abstain_decisions = [
            {"candidate_id": row["candidate_id"], "verdict": "ABSTAIN"}
            for row in qmsum_manifest["candidates"]
        ]
        assert qmsum_span_report(
            registry, qmsum_manifest, keep_decisions)["hit"] == 2
        assert qmsum_span_report(
            registry, qmsum_manifest, abstain_decisions)["hit"] == 0
        qmsum_path.write_text("[]")
        try:
            qmsum_search_spans(qmsum_path, qmsum_transcript)
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("a non-object QMSum corpus was accepted")

    inside_repo = _WORKTREE_ROOT / "notes" / "candidate-manifest.json"
    try:
        validate_output_target(inside_repo)
    except StructuredOutputError:
        pass
    else:
        raise AssertionError("repository output target was accepted")
    main_checkout = _WORKTREE_ROOT.parent.parent
    if (main_checkout / ".git").exists():
        try:
            validate_output_target(
                main_checkout / "notes" / "candidate-manifest.json")
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("a sibling checkout output target was accepted")

    print("all candidate-first controls behaved as specified")
    return 0


def _transformed(args: argparse.Namespace) -> Transcript:
    transcript = load(args.transcript)
    if args.simulate_bleed:
        return transcript.simulate_bleed()
    if args.as_channel:
        return transcript.as_channel(
            None if args.as_channel is True else args.as_channel)
    if args.strip:
        return transcript.strip_attribution()
    return transcript


def _print_manifest(manifest: dict, batch_size: int) -> None:
    counts = manifest["counts"]
    batches = candidate_batches(manifest["candidates"], batch_size)
    ratio = (
        counts["candidates"] / counts["source_fragments"]
        if counts["source_fragments"] else 0.0
    )
    repeated_visible = (
        counts["candidates"]
        - len({
            tuple(row["visible_fragment_ids"])
            for row in manifest["candidates"]
        })
    )
    print(
        f"{manifest['strategy']:>5s}  "
        f"{counts['turns']:5d} turns  "
        f"{counts['source_fragments']:5d} fragments  "
        f"{counts['candidates']:5d} candidates  "
        f"{len(batches):3d} batches  "
        f"{ratio:6.1%} of fragments  "
        f"{repeated_visible:4d} repeated visible set(s)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("transcript", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--strategy", choices=STRATEGIES, default=STRATEGY_BROAD)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--replace", action="store_true")
    transform = parser.add_mutually_exclusive_group()
    transform.add_argument("--strip", action="store_true")
    transform.add_argument("--simulate-bleed", action="store_true")
    transform.add_argument(
        "--as-channel", metavar="SPEAKER", nargs="?", const=True)
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if args.transcript is None:
        parser.error("a transcript is required (or --self-test)")
    if args.replace and args.out is None:
        parser.error("--replace requires --out")
    if args.compare and args.out is not None:
        parser.error("--compare cannot write one strategy's manifest; omit --out")
    try:
        candidate_batches([], args.batch_size)
    except StructuredOutputError as exc:
        parser.error(str(exc))
    if not args.transcript.exists():
        raise SystemExit(f"transcript not found: {args.transcript}")
    if args.out:
        try:
            validate_output_target(args.out, replace=args.replace)
            validate_distinct_input_output(args.transcript, args.out)
        except StructuredOutputError as exc:
            raise SystemExit(str(exc)) from exc

    transcript = _transformed(args)
    strategies = STRATEGIES if args.compare else (args.strategy,)
    manifests = [generate_manifest(transcript, strategy) for strategy in strategies]
    for manifest in manifests:
        validate_manifest(manifest, transcript)
        _print_manifest(manifest, args.batch_size)

    if args.out:
        target = write_private_manifest(
            args.out,
            manifests[0],
            replace=args.replace,
        )
        print(f"wrote private candidate manifest {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
