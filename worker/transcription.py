"""Offline transcript creation for one validated dual-leg acquisition."""

from __future__ import annotations

import json
import os
import uuid
import wave
from pathlib import Path
from typing import Callable

import numpy as np

from .storage import StorageRefused, durable_create_new, private_directory


class TranscriptionRefused(ValueError):
    """The capture or fixed offline model cannot produce a canonical transcript."""


def _read_leg(path: Path) -> np.ndarray:
    if path.is_symlink() or not path.is_file():
        raise TranscriptionRefused(f"{path.name} is missing or unsafe")
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 16_000
                or audio.getcomptype() != "NONE"
            ):
                raise TranscriptionRefused(
                    f"{path.name} is not mono 16 kHz 16-bit PCM"
                )
            frames = audio.getnframes()
            encoded = audio.readframes(frames)
    except (EOFError, OSError, wave.Error) as exc:
        raise TranscriptionRefused(f"{path.name} is not a readable WAV ({exc})") from None
    if len(encoded) != frames * 2:
        raise TranscriptionRefused(f"{path.name} is truncated")
    return np.frombuffer(encoded, dtype="<i2").astype(np.float32) / 32768.0


def _transcript_health(acquisition_health: dict) -> dict:
    from capture_health import build

    try:
        legs = acquisition_health["legs"]
        return build(
            mic_samples=legs["mic"]["samples"],
            system_samples=legs["system"]["samples"],
            capture_elapsed_samples=acquisition_health["timing"][
                "capture_elapsed_samples"
            ],
            dropouts={
                "mic": legs["mic"]["dropouts"],
                "system": legs["system"]["dropouts"],
            },
            tap_errors=legs["system"]["tap_errors"],
            transcription_requested=True,
            transcript_written=True,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TranscriptionRefused(f"capture health cannot be carried forward ({exc})") from None


def require_whisper_model(model_dir: Path) -> Path:
    supplied = model_dir.expanduser()
    if supplied.is_symlink():
        raise TranscriptionRefused("offline transcript model may not be a symlink")
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise TranscriptionRefused(f"offline transcript model is missing ({exc})") from None
    if not resolved.is_dir():
        raise TranscriptionRefused("offline transcript model is not a directory")
    for name in ("config.json", "weights.safetensors"):
        resource = resolved / name
        if resource.is_symlink() or not resource.is_file():
            raise TranscriptionRefused(f"offline transcript model lacks safe {name}")
    return resolved


def create_transcript_revision(
    capture_dir: Path,
    transcript_dir: Path,
    model_dir: Path,
    *,
    transcribe_audio: Callable[[np.ndarray, str, str], list[dict]] | None = None,
    voicing_filter: Callable[[list[dict], np.ndarray, str], list[dict]] | None = None,
    bleed_filter: Callable[
        [list[dict], np.ndarray, np.ndarray, dict | None, str], list[dict]
    ]
    | None = None,
) -> tuple[str, Path]:
    """Create one immutable transcript revision without mutating capture bytes."""
    from verify_capture import verify_acquisition
    from dual_capture import (
        MergedTurn,
        bleed,
        drop_bled,
        drop_unvoiced,
        sha256,
        transcribe,
        write_transcript,
    )
    from transcript import load

    verify_acquisition(capture_dir)
    model_dir = require_whisper_model(model_dir)
    try:
        session = json.loads((capture_dir / "session.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranscriptionRefused(f"capture session is unreadable ({exc})") from None
    health = _transcript_health(session.get("health"))
    mic = _read_leg(capture_dir / "mic.wav")
    system = _read_leg(capture_dir / "system.wav")
    acoustic = bleed(mic, system)

    transcribe_audio = transcribe_audio or transcribe
    voicing_filter = voicing_filter or drop_unvoiced
    bleed_filter = bleed_filter or drop_bled
    mic_segments = voicing_filter(
        transcribe_audio(mic, str(model_dir), "en"), mic, "mic"
    )
    mic_segments = bleed_filter(mic_segments, mic, system, acoustic, "mic")
    system_segments = voicing_filter(
        transcribe_audio(system, str(model_dir), "en"), system, "system"
    )

    merged = [
        MergedTurn(
            segment["start"],
            segment["end"],
            label,
            segment["text"],
            segment.get("gated", False),
            segment.get("gate_score"),
            segment.get("gate_reason"),
        )
        for segments, label in ((mic_segments, "Me"), (system_segments, "Them"))
        for segment in segments
    ]
    merged.sort(key=lambda turn: (turn.start, turn.end, turn.label))

    private_directory(transcript_dir)
    temporary = transcript_dir / f".candidate-{uuid.uuid4()}.json"
    try:
        write_transcript(
            temporary,
            merged,
            acoustic,
            gating=None,
            capture_health=health,
            quiet=True,
        )
        encoded = temporary.read_bytes()
        digest = sha256(temporary)
        target = transcript_dir / f"{digest}.json"
        if target.exists():
            if target.is_symlink() or not target.is_file() or sha256(target) != digest:
                raise TranscriptionRefused(
                    "existing transcript revision disagrees with its digest"
                )
        else:
            durable_create_new(target, encoded)
        load(target)
        return digest, target
    except (OSError, StorageRefused, ValueError) as exc:
        if isinstance(exc, TranscriptionRefused):
            raise
        raise TranscriptionRefused(str(exc)) from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            directory = os.open(transcript_dir, os.O_RDONLY)
        except OSError:
            pass
        else:
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
