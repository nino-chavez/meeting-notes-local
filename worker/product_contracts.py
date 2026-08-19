"""Closed worker-side schemas for successor correction and note operations."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid


class ProductContractRefused(ValueError):
    pass


MAX_SOURCE_TURN_INDEX = (1 << 32) - 1
MAX_VOCABULARY_REPLACEMENTS = 64
MAX_VOCABULARY_REPLACEMENT_BYTES = 512


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


def validate_speaker_label_overrides(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) > 3:
        raise ProductContractRefused("speaker label overlay has too many source groups")
    previous = -1
    for override in value:
        override = _exact_object(
            override, {"source_speaker", "replacement"}, "speaker label overlay entry"
        )
        rank = {None: 0, "Me": 1, "Them": 2}.get(override["source_speaker"])
        if rank is None or rank <= previous:
            raise ProductContractRefused(
                "speaker label overlay source groups are not unique and ordered"
            )
        replacement = override["replacement"]
        if (
            not isinstance(replacement, str)
            or not replacement
            or len(replacement.encode("utf-8")) > 80
            or replacement != replacement.strip()
            or any(unicodedata.category(character) == "Cc" for character in replacement)
        ):
            raise ProductContractRefused("speaker label overlay replacement is invalid")
        previous = rank
    return value


def validate_vocabulary_replacements(value: object) -> list[dict]:
    """Close the prompt-only source-span vocabulary overlay.

    This admits structure and boundedness only. `note_validator` re-derives
    each scalar range and digest from the immutable transcript before a model
    sees any replacement, which is the point at which stale source text can be
    detected.
    """
    if not isinstance(value, list) or len(value) > MAX_VOCABULARY_REPLACEMENTS:
        raise ProductContractRefused("vocabulary overlay has too many replacements")
    previous: tuple[int, int, int] | None = None
    for replacement in value:
        replacement = _exact_object(
            replacement,
            {"turn", "char_start", "char_end", "source_sha256", "replacement"},
            "vocabulary overlay entry",
        )
        turn = replacement["turn"]
        start = replacement["char_start"]
        end = replacement["char_end"]
        text = replacement["replacement"]
        if (
            isinstance(turn, bool)
            or not isinstance(turn, int)
            or turn < 0
            or turn > MAX_SOURCE_TURN_INDEX
            or isinstance(start, bool)
            or not isinstance(start, int)
            or start < 0
            or isinstance(end, bool)
            or not isinstance(end, int)
            or end <= start
            or not isinstance(text, str)
            or not text
            or len(text.encode("utf-8")) > MAX_VOCABULARY_REPLACEMENT_BYTES
            or any(unicodedata.category(character) in {"Cc", "Cs"} for character in text)
        ):
            raise ProductContractRefused("vocabulary overlay replacement is invalid")
        _digest(replacement["source_sha256"], "vocabulary overlay source digest")
        position = (turn, start, end)
        if previous is not None and previous >= position:
            raise ProductContractRefused(
                "vocabulary overlay replacements are not source ordered"
            )
        previous = position
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


def validate_transcript_retry_arguments(value: object) -> dict:
    """Close a retry to the current transcript and retained capture bytes."""
    arguments = _exact_object(
        value,
        {
            "meeting_id",
            "source_transcript_sha256",
            "capture_session_sha256",
            "microphone_audio_sha256",
            "system_audio_sha256",
        },
        "transcript.retry arguments",
    )
    _uuid(arguments["meeting_id"], "meeting_id")
    _digest(arguments["source_transcript_sha256"], "source_transcript_sha256")
    _digest(arguments["capture_session_sha256"], "capture_session_sha256")
    _digest(arguments["microphone_audio_sha256"], "microphone_audio_sha256")
    _digest(arguments["system_audio_sha256"], "system_audio_sha256")
    return arguments


def validate_note_create_arguments(value: object) -> dict:
    """Admit both note.create shapes: bare, and carrying a generation payload.

    The bare shape keeps its original meaning — no admitted generator, so the
    adapter refuses — and the widened shape carries the sandboxed generate
    child's `note-generation/1` result for the deterministic assembler. Deep
    validation of the payload (manifest replay, anchor spans) is the
    assembler's job; this contract only closes the outer shape.
    """
    names = {"meeting_id", "source_transcript_sha256"}
    if isinstance(value, dict):
        names |= {
            key for key in (
                "generation", "speaker_label_overrides", "vocabulary_replacements"
            ) if key in value
        }
    arguments = _exact_object(value, names, "note.create arguments")
    _uuid(arguments["meeting_id"], "meeting_id")
    _digest(arguments["source_transcript_sha256"], "source_transcript_sha256")
    if "generation" in arguments:
        raw_generation = arguments["generation"]
        if not isinstance(raw_generation, dict):
            raise ProductContractRefused(
                "note.create generation payload does not match the closed schema")
        schema = raw_generation.get("schema")
        collection = "claims" if schema == "note-generation/2" else "points"
        generation = _exact_object(
            raw_generation,
            {"schema", "transcript_sha256", "manifest_sha256", "candidates",
             collection, "receipt"},
            "note.create generation payload",
        )
        if generation["schema"] not in {"note-generation/1", "note-generation/2"}:
            raise ProductContractRefused(
                "note.create generation payload schema is unsupported")
        _digest(generation["transcript_sha256"], "generation transcript_sha256")
        _digest(generation["manifest_sha256"], "generation manifest_sha256")
        if generation["transcript_sha256"] != arguments["source_transcript_sha256"]:
            raise ProductContractRefused(
                "generation payload names a different transcript")
        candidates = generation["candidates"]
        if (
            isinstance(candidates, bool)
            or not isinstance(candidates, int)
            or candidates < 1
        ):
            raise ProductContractRefused(
                "generation candidate count must be a positive integer")
        if not isinstance(generation[collection], list) or not generation[collection]:
            raise ProductContractRefused(
                f"generation payload must carry at least one {collection[:-1]}")
        receipt = _exact_object(
            generation["receipt"],
            {"responses", "response_bytes", "last_response_sha256", "elapsed_s"},
            "generation receipt",
        )
        if (
            isinstance(receipt["elapsed_s"], bool)
            or not isinstance(receipt["elapsed_s"], (int, float))
            or receipt["elapsed_s"] < 0
        ):
            raise ProductContractRefused(
                "generation receipt elapsed_s must be a nonnegative number")
    if "speaker_label_overrides" in arguments:
        validate_speaker_label_overrides(arguments["speaker_label_overrides"])
    if "vocabulary_replacements" in arguments:
        validate_vocabulary_replacements(arguments["vocabulary_replacements"])
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


def validate_transcript_retry_digests(
    value: object, arguments: object
) -> dict:
    requested = validate_transcript_retry_arguments(arguments)
    digests = _exact_object(
        value,
        {
            "candidate-transcript",
            "source-transcript",
            "capture-session",
            "capture-mic",
            "capture-system",
        },
        "transcript.retry result digests",
    )
    for name, digest in digests.items():
        _digest(digest, f"transcript.retry {name} digest")
    if digests["source-transcript"] != requested["source_transcript_sha256"]:
        raise ProductContractRefused(
            "transcript.retry result differs from its requested current transcript"
        )
    if digests["capture-session"] != requested["capture_session_sha256"]:
        raise ProductContractRefused(
            "transcript.retry result differs from its requested capture session"
        )
    if digests["capture-mic"] != requested["microphone_audio_sha256"]:
        raise ProductContractRefused(
            "transcript.retry result differs from its requested microphone audio"
        )
    if digests["capture-system"] != requested["system_audio_sha256"]:
        raise ProductContractRefused(
            "transcript.retry result differs from its requested system audio"
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


def validate_transcript_retry_join(
    arguments_value: object, digests_value: object
) -> tuple[dict, dict]:
    arguments = validate_transcript_retry_arguments(arguments_value)
    digests = validate_transcript_retry_digests(digests_value, arguments)
    return arguments, digests


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
