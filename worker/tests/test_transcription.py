from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "spike"))
sys.path.insert(0, str(REPO / "notes"))

from capture_health import build as build_capture_health
from dual_capture import finalize_session, open_private_binary
from transcript import load
from worker.transcription import TranscriptionRefused, create_transcript_revision


def write_wav(path: Path, value: int, samples: int = 3_200) -> None:
    with open_private_binary(path) as handle:
        with wave.open(handle, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(int(value).to_bytes(2, "little", signed=True) * samples)


class TranscriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.capture = self.root / "capture"
        self.capture.mkdir(mode=0o700)
        write_wav(self.capture / "mic.wav", 500)
        write_wav(self.capture / "system.wav", 900)
        health = build_capture_health(
            mic_samples=3_200,
            system_samples=3_200,
            capture_elapsed_samples=3_200,
            dropouts={"mic": [], "system": []},
            tap_errors=[],
            transcription_requested=False,
            transcript_written=False,
        )
        finalize_session(self.capture, "2000-01-01T00:00:00+0000", health)
        self.model = self.root / "model"
        self.model.mkdir(mode=0o700)
        for name in ("config.json", "weights.safetensors"):
            descriptor = os.open(self.model / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(b"fixture")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def fake_transcribe(audio, _model, _language):
        text = "microphone words" if float(audio[0]) < 0.02 else "system words"
        return [{"start": 0.0, "end": 0.2, "text": text}]

    @staticmethod
    def keep(segments, *_arguments):
        return segments

    def test_creates_immutable_revision_outside_capture(self) -> None:
        transcript_dir = self.root / "transcript"
        digest, path = create_transcript_revision(
            self.capture,
            transcript_dir,
            self.model,
            transcribe_audio=self.fake_transcribe,
            voicing_filter=self.keep,
            bleed_filter=self.keep,
        )
        document = load(path)
        self.assertEqual(path.name, f"{digest}.json")
        self.assertEqual(document.attribution, "channel")
        self.assertEqual([turn.text for turn in document.turns], [
            "microphone words",
            "system words",
        ])
        self.assertTrue(document.capture_health["transcription"]["requested"])
        self.assertFalse((self.capture / "transcript.json").exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_refuses_symlinked_model_file(self) -> None:
        (self.model / "weights.safetensors").unlink()
        (self.model / "weights.safetensors").symlink_to(self.model / "config.json")
        with self.assertRaises(TranscriptionRefused):
            create_transcript_revision(
                self.capture,
                self.root / "transcript",
                self.model,
                transcribe_audio=self.fake_transcribe,
                voicing_filter=self.keep,
                bleed_filter=self.keep,
            )


if __name__ == "__main__":
    unittest.main()
