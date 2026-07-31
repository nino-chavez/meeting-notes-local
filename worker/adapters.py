"""Thin app-safe adapters around the repository's canonical validators."""

from __future__ import annotations

import hashlib
import json
import sys
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


def transcript_create(root: Path, arguments: object) -> dict[str, str]:
    values = _exact_arguments(arguments, {"meeting_id"})
    meeting_id = opaque_id(values["meeting_id"], "meeting_id")
    capture_dir = _meeting_capture(root, meeting_id)
    source = capture_dir / "transcript.json"

    # Boundary fixtures still carry a precomputed transcript. Product capture
    # validates acquisition independently; the real ASR adapter will replace
    # this strict combined-packet bridge when its frozen runtime lands.
    from verify_capture import verify_capture

    verify_capture(capture_dir)

    from transcript import load

    load(source)
    transcript_digest = sha256(source)
    target_dir = resolve_below(root, "meetings", meeting_id, "transcript")
    private_directory(target_dir)
    target = resolve_below(
        root, "meetings", meeting_id, "transcript", f"{transcript_digest}.json"
    )
    if target.exists():
        if not target.is_file() or sha256(target) != transcript_digest:
            raise AdapterRefused("existing transcript revision disagrees with its name")
    else:
        durable_create_new(target, source.read_bytes())
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
    note_id = opaque_id(values["note_id"], "note_id")
    transcript_id = opaque_id(values["transcript_id"], "transcript_id")
    artifact = resolve_below(root, "meetings", meeting_id, "notes", f"{note_id}.json")
    transcript_path = resolve_below(
        root, "meetings", meeting_id, "transcript", f"{transcript_id}.json"
    )
    if not artifact.is_file() or not transcript_path.is_file():
        raise AdapterRefused("note pair or retained transcript is missing")

    from summarize import validate_artifact_pair
    from transcript import load

    document = json.loads(artifact.read_text(encoding="utf-8"))
    validate_artifact_pair(document, artifact, load(transcript_path))
    return {
        "note": sha256(artifact),
        "note-markdown": sha256(artifact.parent / document["render"]["path"]),
        "transcript": sha256(transcript_path),
    }


def unavailable(_root: Path, arguments: object) -> dict[str, str]:
    _exact_arguments(arguments, {"meeting_id"})
    raise AdapterRefused("operation requires the later hardware or model slice")


def dispatch(
    root: Path,
    operation: str,
    arguments: object,
    *,
    encoder_digest: str,
) -> dict[str, str]:
    adapters = {
        "profile.inspect": lambda: profile_inspect(root, arguments, encoder_digest),
        "profile.adopt": lambda: profile_adopt(root, arguments, encoder_digest),
        "capture.inspect": lambda: capture_inspect(root, arguments),
        "transcript.create": lambda: transcript_create(root, arguments),
        "note.inspect": lambda: note_inspect(root, arguments),
        "capture.start": lambda: unavailable(root, arguments),
        "capture.stop": lambda: unavailable(root, arguments),
        "note.create": lambda: unavailable(root, arguments),
    }
    try:
        return adapters[operation]()
    except KeyError:
        raise AdapterRefused("operation is outside the fixed registry") from None
    except (OSError, ValueError, SystemExit, StorageRefused) as exc:
        raise AdapterRefused(str(exc)) from None
