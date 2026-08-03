"""Load the registered LibriSpeech parity fixtures, verifying every digest.

The manifest written by `select_librispeech_fixtures.py` is the authority: a
fixture whose bytes do not match its registered sha256 refuses loudly instead
of silently entering a measurement. Returns float32 mono audio at 16 kHz, the
same contract `fixtures.synthetic_clips()` provides, so both fixture sets flow
through identical downstream code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile

SAMPLE_RATE = 16_000
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures-librispeech"


def load_public_clips(fixtures_dir: Path = FIXTURES_DIR) -> list[tuple[str, np.ndarray]]:
    manifest = json.loads((fixtures_dir / "manifest.json").read_text())
    if manifest["schema"] != "librispeech-parity-fixtures/1":
        raise SystemExit("unrecognized fixtures manifest schema")
    clips = []
    for entry in manifest["fixtures"]:
        path = fixtures_dir / entry["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise SystemExit(f"fixture {entry['file']} does not match its registered digest")
        audio, samplerate = soundfile.read(str(path), dtype="float32")
        if samplerate != SAMPLE_RATE or audio.ndim != 1:
            raise SystemExit(f"fixture {entry['file']} is not 16 kHz mono")
        clips.append((entry["file"], audio))
    if len(clips) != 12:
        raise SystemExit(f"expected 12 registered fixtures, found {len(clips)}")
    return clips


if __name__ == "__main__":
    for name, audio in load_public_clips():
        print(name, audio.shape, float(audio.min()), float(audio.max()))
