"""Thin app-safe adapters around the repository's canonical validators."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

from .storage import (
    StorageRefused,
    durable_create_new,
    opaque_id,
    private_directory,
    resolve_below,
)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "spike"))
sys.path.insert(0, str(REPO / "notes"))


class AdapterRefused(ValueError):
    pass


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
    from transcript import load

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
    transcript = load(transcript_path)
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
