"""Closed worker-side schemas for successor correction and note operations."""

from __future__ import annotations

import hashlib
import json
import uuid


class ProductContractRefused(ValueError):
    pass


MAX_SOURCE_TURN_INDEX = (1 << 32) - 1


def _exact_object(value: object, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ProductContractRefused(f"{label} does not match the closed schema")
    return value


def _uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ProductContractRefused(f"{label} must be a UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ProductContractRefused(f"{label} must be a UUID") from None
    if str(parsed) != value:
        raise ProductContractRefused(f"{label} must use canonical lowercase UUID syntax")
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProductContractRefused(f"{label} must be a lowercase SHA-256 digest")
    return value


def validate_transcript_restore_arguments(value: object) -> dict:
    arguments = _exact_object(
        value,
        {"meeting_id", "source_transcript_sha256", "source_turn_index"},
        "transcript.restore arguments",
    )
    _uuid(arguments["meeting_id"], "meeting_id")
    _digest(arguments["source_transcript_sha256"], "source_transcript_sha256")
    turn_index = arguments["source_turn_index"]
    if (
        isinstance(turn_index, bool)
        or not isinstance(turn_index, int)
        or turn_index < 0
        or turn_index > MAX_SOURCE_TURN_INDEX
    ):
        raise ProductContractRefused("source_turn_index must be an unsigned 32-bit integer")
    return arguments


def validate_note_create_arguments(value: object) -> dict:
    arguments = _exact_object(
        value,
        {"meeting_id", "source_transcript_sha256"},
        "note.create arguments",
    )
    _uuid(arguments["meeting_id"], "meeting_id")
    _digest(arguments["source_transcript_sha256"], "source_transcript_sha256")
    return arguments


def validate_transcript_view(value: object) -> dict:
    view = _exact_object(
        value,
        {
            "schema",
            "meeting_id",
            "base_transcript_sha256",
            "parent_transcript_sha256",
            "restored_source_turn_indices",
        },
        "transcript view",
    )
    if view["schema"] != "transcript-view/1":
        raise ProductContractRefused("transcript view schema is unsupported")
    _uuid(view["meeting_id"], "meeting_id")
    _digest(view["base_transcript_sha256"], "base_transcript_sha256")
    _digest(view["parent_transcript_sha256"], "parent_transcript_sha256")
    indices = view["restored_source_turn_indices"]
    if (
        not isinstance(indices, list)
        or not indices
        or any(
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index > MAX_SOURCE_TURN_INDEX
            for index in indices
        )
        or indices != sorted(set(indices))
    ):
        raise ProductContractRefused(
            "restored_source_turn_indices must be nonempty, unique, and sorted"
        )
    # This order is the cross-language content-addressing order owned by the
    # Rust TranscriptView struct. Callers hash this normalized object, never
    # caller-controlled dictionary order.
    return {
        "schema": view["schema"],
        "meeting_id": view["meeting_id"],
        "base_transcript_sha256": view["base_transcript_sha256"],
        "parent_transcript_sha256": view["parent_transcript_sha256"],
        "restored_source_turn_indices": indices,
    }


def transcript_view_digest(value: object) -> str:
    view = validate_transcript_view(value)
    encoded = json.dumps(view, indent=2, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_transcript_restore_digests(
    value: object, source_transcript_sha256: str
) -> dict:
    digests = _exact_object(
        value,
        {"base-transcript", "parent-transcript", "transcript"},
        "transcript.restore result digests",
    )
    for name, digest in digests.items():
        _digest(digest, name)
    if digests["parent-transcript"] != source_transcript_sha256:
        raise ProductContractRefused(
            "transcript.restore parent differs from its requested source"
        )
    return digests


def validate_note_create_digests(value: object, source_transcript_sha256: str) -> dict:
    digests = _exact_object(
        value,
        {"note", "note-markdown", "transcript"},
        "note.create result digests",
    )
    for name, digest in digests.items():
        _digest(digest, name)
    if digests["transcript"] != source_transcript_sha256:
        raise ProductContractRefused("note.create result differs from its requested source")
    return digests


def validate_transcript_restore_join(
    arguments_value: object, view_value: object, digests_value: object
) -> tuple[dict, dict, dict]:
    arguments = validate_transcript_restore_arguments(arguments_value)
    view = validate_transcript_view(view_value)
    digests = validate_transcript_restore_digests(
        digests_value, arguments["source_transcript_sha256"]
    )
    if (
        view["meeting_id"] != arguments["meeting_id"]
        or view["parent_transcript_sha256"]
        != arguments["source_transcript_sha256"]
        or view["base_transcript_sha256"] != digests["base-transcript"]
        or view["parent_transcript_sha256"] != digests["parent-transcript"]
        or transcript_view_digest(view) != digests["transcript"]
        or arguments["source_turn_index"]
        not in view["restored_source_turn_indices"]
    ):
        raise ProductContractRefused(
            "transcript.restore digests disagree with authoritative artifacts"
        )
    return arguments, view, digests


def validate_note_create_join(
    arguments_value: object,
    digests_value: object,
    *,
    note_sha256: str,
    markdown_sha256: str,
) -> tuple[dict, dict]:
    arguments = validate_note_create_arguments(arguments_value)
    digests = validate_note_create_digests(
        digests_value, arguments["source_transcript_sha256"]
    )
    _digest(note_sha256, "authoritative note digest")
    _digest(markdown_sha256, "authoritative note Markdown digest")
    if (
        digests["note"] != note_sha256
        or digests["note-markdown"] != markdown_sha256
    ):
        raise ProductContractRefused(
            "note.create digests disagree with authoritative artifacts"
        )
    return arguments, digests


def validate_note_create_error(value: object) -> str:
    error = _exact_object(
        value,
        {"code", "recoverable", "artifact_digests"},
        "note.create error",
    )
    if (
        error["code"] != "note_rejected"
        or error["recoverable"] is not True
        or error["artifact_digests"] != {}
    ):
        raise ProductContractRefused(
            "rejected note worker result must be recoverable and artifact-free"
        )
    return "note-rejected"
