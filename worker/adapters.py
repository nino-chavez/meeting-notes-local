"""Thin app-safe adapters around the repository's canonical validators."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .product_contracts import (
    ProductContractRefused,
    transcript_view_digest,
    validate_note_create_arguments,
    validate_note_create_join,
    validate_transcript_restore_arguments,
    validate_transcript_restore_join,
    validate_transcript_view,
)
from .storage import (
    StorageRefused,
    durable_create_new,
    opaque_id,
    private_directory,
    require_private_root,
    resolve_below,
)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "spike"))
sys.path.insert(0, str(REPO / "notes"))


class AdapterRefused(ValueError):
    pass


@dataclass(frozen=True)
class _ResolvedTranscript:
    """One immutable transcript revision, resolved back to its capture source."""

    base_path: Path
    base_sha256: str
    base_document: dict
    restored_source_turn_indices: tuple[int, ...]


NoteGenerator = Callable[[object], dict]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_digest_id(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AdapterRefused(f"{label} must be a lowercase SHA-256 digest")
    return value


def _exact_arguments(arguments: object, names: set[str]) -> dict:
    if not isinstance(arguments, dict) or set(arguments) != names:
        raise AdapterRefused("operation arguments do not match the closed schema")
    return arguments


def _private_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise AdapterRefused(f"{label} is missing or unsafe")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise AdapterRefused(f"{label} is not private")


def _transcript_path(root: Path, meeting_id: str, transcript_sha256: str) -> Path:
    return resolve_below(
        root, "meetings", meeting_id, "transcript", f"{transcript_sha256}.json"
    )


def _current_transcript_sha256(root: Path, meeting_id: str) -> str:
    """Read only the immutable-current binding the worker needs to enforce."""
    meeting_path = resolve_below(root, "meetings", meeting_id, "meeting.json")
    _private_regular_file(meeting_path, "meeting receipt")
    try:
        meeting = json.loads(meeting_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterRefused("meeting receipt is not valid UTF-8 JSON") from exc
    if (
        not isinstance(meeting, dict)
        or meeting.get("schema") != "meeting/2"
        or meeting.get("meeting_id") != meeting_id
        or not isinstance(meeting.get("artifacts"), dict)
    ):
        raise AdapterRefused("meeting receipt does not bind this meeting")
    current = meeting["artifacts"].get("current_transcript")
    if not isinstance(current, dict) or set(current) != {"relative_path", "sha256"}:
        raise AdapterRefused("meeting receipt has no exact current transcript")
    digest = content_digest_id(current["sha256"], "current transcript digest")
    if current["relative_path"] != f"transcript/{digest}.json":
        raise AdapterRefused("meeting receipt current transcript path is not canonical")
    return digest


def _base_gated_turn_indices(document: dict) -> set[int]:
    turns = document.get("turns")
    if not isinstance(turns, list):
        raise AdapterRefused("base transcript has no turn list")
    gated: set[int] = set()
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise AdapterRefused("base transcript has a malformed turn")
        if "gated" in turn and type(turn["gated"]) is not bool:
            raise AdapterRefused("base transcript turn gate is not boolean")
        if turn.get("gated") is True:
            gated.add(index)
    return gated


def _resolve_transcript_revision(
    root: Path,
    meeting_id: str,
    transcript_sha256: str,
    *,
    ancestors: frozenset[str] = frozenset(),
) -> _ResolvedTranscript:
    """Resolve a base transcript or a closed transcript-view/1 chain."""
    transcript_sha256 = content_digest_id(transcript_sha256, "transcript digest")
    if transcript_sha256 in ancestors:
        raise AdapterRefused("transcript view chain is cyclic")
    path = _transcript_path(root, meeting_id, transcript_sha256)
    _private_regular_file(path, "transcript revision")
    if sha256(path) != transcript_sha256:
        raise AdapterRefused("transcript revision changed from its content address")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterRefused("transcript revision is not valid UTF-8 JSON") from exc

    if isinstance(document, dict) and document.get("schema") == "transcript-view/1":
        try:
            view = validate_transcript_view(document)
        except ProductContractRefused as exc:
            raise AdapterRefused(str(exc)) from None
        if view["meeting_id"] != meeting_id:
            raise AdapterRefused("transcript view belongs to another meeting")
        if transcript_view_digest(view) != transcript_sha256:
            raise AdapterRefused("transcript view bytes disagree with its content address")
        parent = _resolve_transcript_revision(
            root,
            meeting_id,
            view["parent_transcript_sha256"],
            ancestors=ancestors | {transcript_sha256},
        )
        if parent.base_sha256 != view["base_transcript_sha256"]:
            raise AdapterRefused("transcript view base differs from its parent chain")
        restored = tuple(view["restored_source_turn_indices"])
        parent_restored = set(parent.restored_source_turn_indices)
        if (
            not parent_restored < set(restored)
            or len(set(restored) - parent_restored) != 1
            or not set(restored).issuperset(parent_restored)
        ):
            raise AdapterRefused("transcript view is not a one-turn successor")
        if not set(restored).issubset(_base_gated_turn_indices(parent.base_document)):
            raise AdapterRefused("transcript view restores a source turn that was not withheld")
        return _ResolvedTranscript(
            base_path=parent.base_path,
            base_sha256=parent.base_sha256,
            base_document=parent.base_document,
            restored_source_turn_indices=restored,
        )

    # `load` remains the canonical capture-transcript parser. It is deliberately
    # invoked only for base bytes; a view stores no meeting words of its own.
    from transcript import load

    try:
        load(path)
    except (KeyError, ValueError, TypeError) as exc:
        raise AdapterRefused(f"base transcript is invalid: {exc}") from None
    _base_gated_turn_indices(document)
    return _ResolvedTranscript(
        base_path=path,
        base_sha256=transcript_sha256,
        base_document=document,
        restored_source_turn_indices=(),
    )


def resolve_transcript(root: Path, meeting_id: str, transcript_sha256: str):
    """Materialize a view for validators without copying text into the view file."""
    root = require_private_root(root)
    meeting_id = opaque_id(meeting_id, "meeting_id")
    resolved = _resolve_transcript_revision(root, meeting_id, transcript_sha256)
    from transcript import Transcript, Turn, load

    base = load(resolved.base_path)
    restored = set(resolved.restored_source_turn_indices)
    visible: list[Turn] = []
    still_withheld: list[Turn] = []
    for index, turn in enumerate(resolved.base_document["turns"]):
        rendered = Turn(
            text=turn["text"], speaker=turn.get("speaker"), start=turn.get("start")
        )
        if turn.get("gated") is True and index not in restored:
            still_withheld.append(rendered)
        else:
            visible.append(rendered)
    return Transcript(
        source=base.source,
        attribution=base.attribution,
        turns=visible,
        gated_turns=still_withheld,
        gate=base.gate,
        capture_health=base.capture_health,
        capture_integrity_unknown=base.capture_integrity_unknown,
    )


def transcript_restore(root: Path, arguments: object) -> dict[str, str]:
    """Create one immutable transcript-view/1 successor for a withheld turn."""
    root = require_private_root(root)
    try:
        values = validate_transcript_restore_arguments(arguments)
    except ProductContractRefused as exc:
        raise AdapterRefused(str(exc)) from None
    meeting_id = values["meeting_id"]
    source_sha256 = values["source_transcript_sha256"]
    if _current_transcript_sha256(root, meeting_id) != source_sha256:
        raise AdapterRefused("requested transcript is not this meeting's current revision")
    parent = _resolve_transcript_revision(root, meeting_id, source_sha256)
    turn_index = values["source_turn_index"]
    if turn_index not in _base_gated_turn_indices(parent.base_document):
        raise AdapterRefused("requested source turn was not withheld")
    if turn_index in parent.restored_source_turn_indices:
        raise AdapterRefused("requested source turn is already restored")
    view = {
        "schema": "transcript-view/1",
        "meeting_id": meeting_id,
        "base_transcript_sha256": parent.base_sha256,
        "parent_transcript_sha256": source_sha256,
        "restored_source_turn_indices": sorted(
            (*parent.restored_source_turn_indices, turn_index)
        ),
    }
    view_sha256 = transcript_view_digest(view)
    target = _transcript_path(root, meeting_id, view_sha256)
    try:
        durable_create_new(
            target, json.dumps(view, ensure_ascii=False, indent=2).encode("utf-8")
        )
    except StorageRefused as exc:
        raise AdapterRefused(str(exc)) from None
    digests = {
        "base-transcript": parent.base_sha256,
        "parent-transcript": source_sha256,
        "transcript": view_sha256,
    }
    try:
        validate_transcript_restore_join(values, view, digests)
    except ProductContractRefused as exc:
        raise AdapterRefused(str(exc)) from None
    return digests


def _meeting_capture(root: Path, meeting_id: str) -> Path:
    meeting_id = opaque_id(meeting_id, "meeting_id")
    return resolve_below(root, "meetings", meeting_id, "capture")


def capture_inspect(root: Path, arguments: object) -> dict[str, str]:
    values = _exact_arguments(arguments, {"meeting_id"})
    capture_dir = _meeting_capture(root, values["meeting_id"])
    from verify_capture import verify_acquisition

    verify_acquisition(capture_dir)
    return {
        "capture-session": sha256(capture_dir / "session.json"),
        "capture-mic": sha256(capture_dir / "mic.wav"),
        "capture-system": sha256(capture_dir / "system.wav"),
    }


def _wav_samples(path: Path) -> int:
    if path.is_symlink() or not path.is_file():
        raise AdapterRefused(f"{path.name} is missing or unsafe")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise AdapterRefused(f"{path.name} is not private")
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 16_000
                or audio.getcomptype() != "NONE"
            ):
                raise AdapterRefused(
                    f"{path.name} is not mono 16 kHz 16-bit PCM"
                )
            frames = audio.getnframes()
            encoded = audio.readframes(frames)
    except (EOFError, OSError, wave.Error) as exc:
        raise AdapterRefused(f"{path.name} is not a readable WAV ({exc})") from None
    if len(encoded) != frames * 2:
        raise AdapterRefused(f"{path.name} is truncated")
    return frames


def capture_finalize(root: Path, arguments: object) -> dict[str, str]:
    values = _exact_arguments(
        arguments,
        {"meeting_id", "started_at_epoch_seconds", "capture_elapsed_samples"},
    )
    meeting_id = opaque_id(values["meeting_id"], "meeting_id")
    started_at = values["started_at_epoch_seconds"]
    elapsed = values["capture_elapsed_samples"]
    if (
        isinstance(started_at, bool)
        or not isinstance(started_at, int)
        or started_at <= 0
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, int)
        or elapsed <= 0
        or elapsed > 16_000 * 60 * 60 * 24
    ):
        raise AdapterRefused("capture timing is outside the closed schema")

    capture_dir = _meeting_capture(root, meeting_id)
    names = {path.name for path in capture_dir.iterdir()}
    if names != {"mic.wav", "system.wav"}:
        raise AdapterRefused("capture finalization requires exactly two WAV legs")
    mic_samples = _wav_samples(capture_dir / "mic.wav")
    system_samples = _wav_samples(capture_dir / "system.wav")

    from capture_health import build as build_capture_health
    from dual_capture import finalize_session
    from verify_capture import verify_acquisition

    health = build_capture_health(
        mic_samples=mic_samples,
        system_samples=system_samples,
        capture_elapsed_samples=elapsed,
        dropouts={"mic": [], "system": []},
        tap_errors=[],
        transcription_requested=False,
        transcript_written=False,
    )
    if not health["usable"]:
        raise AdapterRefused("capture did not pass its integrity floor")
    timestamp = datetime.fromtimestamp(started_at, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )
    finalize_session(
        capture_dir,
        timestamp,
        health,
        no_overwrite=True,
    )
    verify_acquisition(capture_dir)
    return {
        "capture-session": sha256(capture_dir / "session.json"),
        "capture-mic": sha256(capture_dir / "mic.wav"),
        "capture-system": sha256(capture_dir / "system.wav"),
    }


def transcript_create(
    root: Path,
    arguments: object,
    *,
    admission: str,
    model_dir: Path | None,
) -> dict[str, str]:
    values = _exact_arguments(arguments, {"meeting_id"})
    meeting_id = opaque_id(values["meeting_id"], "meeting_id")
    capture_dir = _meeting_capture(root, meeting_id)
    target_dir = resolve_below(root, "meetings", meeting_id, "transcript")
    private_directory(target_dir)
    if admission == "boundary-test":
        source = capture_dir / "transcript.json"
        from verify_capture import verify_capture

        verify_capture(capture_dir)

        from transcript import load

        load(source)
        transcript_digest = sha256(source)
        target = resolve_below(
            root, "meetings", meeting_id, "transcript", f"{transcript_digest}.json"
        )
        if target.exists():
            if not target.is_file() or sha256(target) != transcript_digest:
                raise AdapterRefused(
                    "existing transcript revision disagrees with its name"
                )
        else:
            durable_create_new(target, source.read_bytes())
        return {"transcript": transcript_digest}

    if admission not in {"internal-alpha", "product"} or model_dir is None:
        raise AdapterRefused("runtime admission lacks the fixed transcript model")
    from .transcription import create_transcript_revision

    transcript_digest, _ = create_transcript_revision(
        capture_dir,
        target_dir,
        model_dir,
    )
    return {"transcript": transcript_digest}


def profile_inspect(root: Path, arguments: object, encoder_digest: str) -> dict[str, str]:
    values = _exact_arguments(arguments, {"profile_id"})
    profile_id = opaque_id(values["profile_id"], "profile_id")
    profile = resolve_below(root, "profile-candidates", profile_id, "voiceprint.json")
    if not profile.is_file():
        raise AdapterRefused("profile candidate is missing")

    from speaker_gate import load_profile

    load_profile(profile, expected_encoder_fingerprint=encoder_digest)
    return {"profile": sha256(profile)}


def profile_adopt(root: Path, arguments: object, encoder_digest: str) -> dict[str, str]:
    values = _exact_arguments(arguments, {"profile_id"})
    profile_id = opaque_id(values["profile_id"], "profile_id")
    digest = profile_inspect(root, values, encoder_digest)["profile"]
    source = resolve_below(root, "profile-candidates", profile_id, "voiceprint.json")
    profile_dir = resolve_below(root, "profile")
    private_directory(profile_dir)
    target = resolve_below(root, "profile", "voiceprint.json")
    durable_create_new(target, source.read_bytes())
    if sha256(target) != digest:
        raise AdapterRefused("adopted profile changed during the durable write")
    return {"profile": digest}


def note_inspect(root: Path, arguments: object) -> dict[str, str]:
    values = _exact_arguments(arguments, {"meeting_id", "note_id", "transcript_id"})
    meeting_id = opaque_id(values["meeting_id"], "meeting_id")
    note_id = content_digest_id(values["note_id"], "note_id")
    transcript_id = content_digest_id(values["transcript_id"], "transcript_id")
    artifact = resolve_below(root, "meetings", meeting_id, "notes", f"{note_id}.json")
    transcript_path = resolve_below(
        root, "meetings", meeting_id, "transcript", f"{transcript_id}.json"
    )
    if not artifact.is_file() or not transcript_path.is_file():
        raise AdapterRefused("note pair or retained transcript is missing")

    from summarize import structured_artifact_citations, validate_artifact_pair

    document = json.loads(artifact.read_text(encoding="utf-8"))
    if document.get("schema") != "note/2":
        raise AdapterRefused("product note inspection requires note/2")
    if document.get("passed") is not True:
        raise AdapterRefused("rejected note output has no product authority")
    if document.get("meeting", {}).get("id") != meeting_id:
        raise AdapterRefused("note belongs to another meeting")
    if document.get("transcript") != f"../transcript/{transcript_id}.json":
        raise AdapterRefused("note does not name the requested retained transcript")
    if sha256(artifact) != note_id or sha256(transcript_path) != transcript_id:
        raise AdapterRefused("content-addressed note or transcript changed")
    transcript = resolve_transcript(root, meeting_id, transcript_id)
    markdown = validate_artifact_pair(document, artifact, transcript)
    if markdown is None:
        raise AdapterRefused("note/2 is missing its Markdown rendering")
    citations = structured_artifact_citations(document, transcript)
    if document.get("checks", {}).get("citations") != citations:
        raise AdapterRefused("note claim locators disagree with retained checks")
    markdown_digest = sha256(markdown)
    if markdown.name != f"{markdown_digest}.md":
        raise AdapterRefused("note Markdown is not content-addressed")
    return {
        "note": note_id,
        "note-markdown": markdown_digest,
        "transcript": transcript_id,
    }


def note_create(
    root: Path,
    arguments: object,
    *,
    generator: NoteGenerator | None,
) -> dict[str, str]:
    """Publish one already-passing product note from an injected generator.

    This adapter intentionally has no model default. Choosing and admitting an
    automatic generator remains a product decision; the bounded fixture seam is
    sufficient to exercise the immutable publication and validation path.
    """
    root = require_private_root(root)
    try:
        values = validate_note_create_arguments(arguments)
    except ProductContractRefused as exc:
        raise AdapterRefused(str(exc)) from None
    if generator is None or not callable(generator):
        raise AdapterRefused("note.create has no admitted note generator")
    meeting_id = values["meeting_id"]
    transcript_id = values["source_transcript_sha256"]
    if _current_transcript_sha256(root, meeting_id) != transcript_id:
        raise AdapterRefused("requested transcript is not this meeting's current revision")
    transcript_path = _transcript_path(root, meeting_id, transcript_id)
    _private_regular_file(transcript_path, "current transcript")
    transcript = resolve_transcript(root, meeting_id, transcript_id)
    try:
        document = generator(transcript)
    except AdapterRefused:
        raise
    except Exception as exc:
        raise AdapterRefused("injected note generator did not produce a candidate") from exc
    if not isinstance(document, dict):
        raise AdapterRefused("injected note generator did not produce a JSON object")
    if document.get("schema") != "note/2" or document.get("passed") is not True:
        raise AdapterRefused("only passing note/2 output has product authority")
    if document.get("meeting", {}).get("id") != meeting_id:
        raise AdapterRefused("note candidate belongs to another meeting")
    if document.get("transcript") != f"../transcript/{transcript_id}.json":
        raise AdapterRefused("note candidate does not bind the current transcript")

    from summarize import (
        StructuredOutputError,
        reconcile_capture_provenance,
        structured_artifact_citations,
        validate_artifact_pair,
        validate_note_render,
        validate_stored_verdict,
    )

    try:
        # Preflight the canonical validator's semantic gates before committing
        # durable bytes. The pair validator below then rechecks the exact files.
        validate_stored_verdict(document.get("checks"), document.get("passed"), "note candidate")
        reconcile_capture_provenance(document, transcript, where="note candidate")
        canonical_markdown = validate_note_render(document)
        citations = structured_artifact_citations(document, transcript)
    except StructuredOutputError as exc:
        raise AdapterRefused(str(exc)) from None
    if document.get("checks", {}).get("citations") != citations:
        raise AdapterRefused("note claim locators disagree with retained checks")
    markdown_sha256 = hashlib.sha256(canonical_markdown.encode("utf-8")).hexdigest()
    if document.get("render", {}).get("path") != f"{markdown_sha256}.md":
        raise AdapterRefused("note Markdown filename is not its content digest")
    notes_dir = resolve_below(root, "meetings", meeting_id, "notes")
    private_directory(notes_dir)
    markdown_path = resolve_below(root, "meetings", meeting_id, "notes", f"{markdown_sha256}.md")
    document_bytes = (
        json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    note_sha256 = hashlib.sha256(document_bytes).hexdigest()
    note_path = resolve_below(root, "meetings", meeting_id, "notes", f"{note_sha256}.json")
    # The independent Markdown identity is known before the JSON references it.
    # Each final name is exclusive: a retry may inspect an existing pair but may
    # never replace it.
    try:
        durable_create_new(markdown_path, canonical_markdown.encode("utf-8"))
        durable_create_new(note_path, document_bytes)
    except StorageRefused as exc:
        raise AdapterRefused(str(exc)) from None
    try:
        markdown = validate_artifact_pair(document, note_path, transcript)
    except StructuredOutputError as exc:
        raise AdapterRefused(str(exc)) from None
    if markdown != markdown_path or sha256(note_path) != note_sha256 or sha256(markdown_path) != markdown_sha256:
        raise AdapterRefused("published note pair changed during validation")
    digests = {
        "note": note_sha256,
        "note-markdown": markdown_sha256,
        "transcript": transcript_id,
    }
    try:
        validate_note_create_join(
            values,
            digests,
            note_sha256=note_sha256,
            markdown_sha256=markdown_sha256,
        )
    except ProductContractRefused as exc:
        raise AdapterRefused(str(exc)) from None
    return digests


def dispatch(
    root: Path,
    operation: str,
    arguments: object,
    *,
    encoder_digest: str,
    admission: str = "boundary-test",
    model_dir: Path | None = None,
) -> dict[str, str]:
    adapters = {
        "profile.inspect": lambda: profile_inspect(root, arguments, encoder_digest),
        "profile.adopt": lambda: profile_adopt(root, arguments, encoder_digest),
        "capture.inspect": lambda: capture_inspect(root, arguments),
        "transcript.create": lambda: transcript_create(
            root,
            arguments,
            admission=admission,
            model_dir=model_dir,
        ),
        "note.inspect": lambda: note_inspect(root, arguments),
        "capture.finalize": lambda: capture_finalize(root, arguments),
    }
    try:
        return adapters[operation]()
    except KeyError:
        raise AdapterRefused("operation is outside the fixed registry") from None
    except (OSError, ValueError, SystemExit, StorageRefused) as exc:
        raise AdapterRefused(str(exc)) from None
