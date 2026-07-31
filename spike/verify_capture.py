#!/usr/bin/env python3
"""Verify a transferred capture without printing private meeting content."""

from __future__ import annotations

import argparse
import json
import stat
import tempfile
import wave
from pathlib import Path

from capture_health import TRANSCRIPT_SCHEMA
from capture_health import build as build_capture_health
from capture_health import validate as validate_capture_health
from dual_capture import (
    finalize_session,
    open_private_binary,
    reconcile_capture_artifacts,
    sha256,
    write_private_text,
)

SESSION_SCHEMA = "capture-session/2"
REQUIRED_CAPTURE_FILES = frozenset(
    {
        "mic-segments.json",
        "mic.wav",
        "session.json",
        "system-segments.json",
        "system.wav",
        "transcript.json",
    }
)


class VerificationError(ValueError):
    """The packet does not match its stored capture evidence."""


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{path.name} is not readable JSON ({exc})") from None
    if not isinstance(value, dict):
        raise VerificationError(f"{path.name} must contain one JSON object")
    return value


def _mode(path: Path) -> str:
    return f"{stat.S_IMODE(path.stat().st_mode):04o}"


def _artifact_receipt(path: Path) -> dict:
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "mode": _mode(path),
    }


def verify_capture(capture_dir: Path, *, interaction_canary: bool = False) -> dict:
    """Reconcile one owner-only capture directory against its final receipt."""
    supplied = capture_dir.expanduser()
    if supplied.is_symlink():
        raise VerificationError("capture directory may not be a symlink")
    capture_dir = supplied.resolve()
    if not capture_dir.is_dir():
        raise VerificationError(f"capture directory does not exist: {capture_dir}")
    if _mode(capture_dir) != "0700":
        raise VerificationError(
            f"capture directory mode is {_mode(capture_dir)}, expected 0700"
        )

    session_path = capture_dir / "session.json"
    if session_path.is_symlink() or not session_path.is_file():
        raise VerificationError("session.json is missing or is a symlink")
    if _mode(session_path) != "0600":
        raise VerificationError(
            f"session.json mode is {_mode(session_path)}, expected 0600"
        )
    session = _load_json(session_path)
    if session.get("schema") != SESSION_SCHEMA:
        raise VerificationError("session.json has no recognized current schema")
    if session.get("status") != "complete":
        raise VerificationError(
            f"capture status is {session.get('status')!r}, expected 'complete'"
        )

    health = session.get("health")
    try:
        usable = validate_capture_health(health, transcript_context=True)
    except ValueError as exc:
        raise VerificationError(f"capture health is invalid ({exc})") from None
    if not usable:
        raise VerificationError("capture health does not permit a complete session")

    actual_paths = sorted(
        path for path in capture_dir.iterdir() if path.name != "session.json"
    )
    if any(path.is_symlink() or not path.is_file() for path in actual_paths):
        raise VerificationError("capture directory contains a symlink or non-file entry")
    if any(_mode(path) != "0600" for path in actual_paths):
        raise VerificationError("every capture artifact must have mode 0600")

    actual_names = {path.name for path in actual_paths} | {"session.json"}
    missing = sorted(REQUIRED_CAPTURE_FILES - actual_names)
    if missing:
        raise VerificationError(
            "capture is missing required artifact(s): " + ", ".join(missing)
        )

    stored_artifacts = session.get("artifacts")
    if not isinstance(stored_artifacts, list):
        raise VerificationError("session artifact receipt is missing")
    current_artifacts = [_artifact_receipt(path) for path in actual_paths]
    if stored_artifacts != current_artifacts:
        raise VerificationError("artifact bytes, modes, names, or sizes changed")

    try:
        reconciliation = reconcile_capture_artifacts(capture_dir, health)
    except ValueError as exc:
        raise VerificationError(f"capture artifacts do not reconcile ({exc})") from None
    if session.get("reconciliation") != reconciliation:
        raise VerificationError("session reconciliation receipt does not match the files")

    transcript = _load_json(capture_dir / "transcript.json")
    if transcript.get("schema") != TRANSCRIPT_SCHEMA:
        raise VerificationError("transcript.json has no recognized current schema")
    if interaction_canary:
        if transcript.get("attribution") != "channel":
            raise VerificationError(
                "interaction canary requires channel-attributed headphone audio"
            )
        if transcript.get("voiceprint") is not None:
            raise VerificationError("interaction canary must be the ungated capture")

    return {
        "schema": session["schema"],
        "status": session["status"],
        "started_at": session.get("started_at"),
        "attribution": transcript.get("attribution"),
        "artifact_count": len(current_artifacts) + 1,
        "interaction_canary": interaction_canary,
    }


def _write_wav(path: Path, samples: int) -> None:
    with open_private_binary(path) as handle, wave.open(handle, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\0\0" * samples)


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        capture_dir = Path(temporary) / "capture"
        capture_dir.mkdir(mode=0o700)
        capture_dir.chmod(0o700)
        samples = 3_200
        _write_wav(capture_dir / "mic.wav", samples)
        _write_wav(capture_dir / "system.wav", samples)
        health = build_capture_health(
            mic_samples=samples,
            system_samples=samples,
            capture_elapsed_samples=samples,
            dropouts={"mic": [], "system": []},
            tap_errors=[],
            transcription_requested=True,
            transcript_written=True,
        )
        transcript = {
            "schema": TRANSCRIPT_SCHEMA,
            "source": "mechanical verifier fixture",
            "attribution": "channel",
            "bleed": None,
            "voiceprint": None,
            "capture_health": health,
            "turns": [],
        }
        write_private_text(
            capture_dir / "transcript.json",
            json.dumps(transcript, indent=2) + "\n",
        )
        for leg in ("mic", "system"):
            write_private_text(
                capture_dir / f"{leg}-segments.json",
                json.dumps(
                    {
                        "schema": "mic-segments/1",
                        "timeline": f"{leg}-local",
                        "leg": leg,
                        "duration_s": samples / 16_000,
                        "filtered": ["voicing"],
                        "labels": None,
                        "audio_sha256": sha256(capture_dir / f"{leg}.wav"),
                        "audio_samples": samples,
                        "captured_at": "2000-01-01T00:00:00+0000",
                        "segments": [],
                    },
                    indent=2,
                )
                + "\n",
            )
        finalize_session(capture_dir, "2000-01-01T00:00:00+0000", health)
        valid = verify_capture(capture_dir, interaction_canary=True)
        with (capture_dir / "mic-segments.json").open("ab") as handle:
            handle.write(b" ")
        try:
            verify_capture(capture_dir, interaction_canary=True)
        except VerificationError:
            tamper_refused = True
        else:
            tamper_refused = False

    if valid["status"] == "complete" and tamper_refused:
        print("capture verifier self-test: OK (valid packet passes; tamper refused)")
        return 0
    print("capture verifier self-test: FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", nargs="?", type=Path)
    parser.add_argument("--interaction-canary", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.capture_dir is None:
        parser.error("capture_dir is required unless --self-test is used")
    try:
        receipt = verify_capture(
            args.capture_dir,
            interaction_canary=args.interaction_canary,
        )
    except VerificationError as exc:
        print(f"capture verification: REFUSED — {exc}")
        return 1
    print(
        "capture verification: OK "
        f"({receipt['status']}, {receipt['attribution']}, "
        f"{receipt['artifact_count']} files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
