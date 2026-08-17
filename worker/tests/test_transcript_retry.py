from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
import uuid
import wave
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "spike"))
sys.path.insert(0, str(REPO / "notes"))

from capture_health import build as build_capture_health
from dual_capture import finalize_session
from worker.adapters import AdapterRefused, transcript_retry
from worker.product_contracts import (
    ProductContractRefused,
    validate_transcript_retry_arguments,
    validate_transcript_retry_digests,
    validate_transcript_retry_join,
)


def private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_wav(path: Path, value: int, samples: int = 3_200) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        with wave.open(handle, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(
                int(value).to_bytes(2, "little", signed=True) * samples
            )


class TranscriptRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)
        self.meeting_id = str(uuid.uuid4())
        self.capture = self.root / "meetings" / self.meeting_id / "capture"
        self.capture.mkdir(mode=0o700, parents=True)
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
        self.transcript_dir = self.capture.parent / "transcript"
        self.transcript_dir.mkdir(mode=0o700)
        self.source = self.transcript_dir / ("a" * 64 + ".json")
        private_file(self.source, b'{"fixture":"current transcript"}\n')
        self.source_digest = digest(self.source)
        self.source.rename(self.transcript_dir / f"{self.source_digest}.json")
        self.source = self.transcript_dir / f"{self.source_digest}.json"
        self._write_meeting()
        self.model = self.root / "model"
        self.model.mkdir(mode=0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _arguments(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "source_transcript_sha256": self.source_digest,
            "capture_session_sha256": digest(self.capture / "session.json"),
            "microphone_audio_sha256": digest(self.capture / "mic.wav"),
            "system_audio_sha256": digest(self.capture / "system.wav"),
        }

    def _write_meeting(self, *, state: str = "retained") -> None:
        source_digest = self.source_digest
        document = {
            "schema": "meeting/2",
            "meeting_id": self.meeting_id,
            "lifecycle": "transcript-ready",
            "retention": {
                "rule": {"kind": "until-manual-deletion"},
                "policy_sha256": "0" * 64,
                "next_deletion_at_epoch_seconds": None,
                "state": state,
                "deletion_receipt": None,
            },
            "artifacts": {
                "attempt": {"relative_path": "attempt.json", "sha256": "1" * 64},
                "ownership": None,
                "capture_session": {
                    "relative_path": "capture/session.json",
                    "sha256": digest(self.capture / "session.json"),
                },
                "microphone_audio": {
                    "relative_path": "capture/mic.wav",
                    "sha256": digest(self.capture / "mic.wav"),
                },
                "system_audio": {
                    "relative_path": "capture/system.wav",
                    "sha256": digest(self.capture / "system.wav"),
                },
                "current_transcript": {
                    "relative_path": f"transcript/{source_digest}.json",
                    "sha256": source_digest,
                },
                "current_note": None,
            },
            "pending_storage_operation": None,
        }
        private_file(
            self.capture.parent / "meeting.json",
            json.dumps(document, indent=2).encode("utf-8"),
        )

    def _candidate_writer(self, calls: list[tuple[Path, Path]]) -> mock.Mock:
        candidate_bytes = b'{"fixture":"retry candidate"}\n'
        candidate_digest = hashlib.sha256(candidate_bytes).hexdigest()

        def create(capture_dir: Path, transcript_dir: Path, _model: Path, **_kwargs):
            calls.append((capture_dir, transcript_dir))
            candidate = transcript_dir / f"{candidate_digest}.json"
            if candidate.exists():
                self.assertEqual(candidate.read_bytes(), candidate_bytes)
            else:
                private_file(candidate, candidate_bytes)
            return candidate_digest, candidate

        return mock.Mock(side_effect=create)

    def test_retry_is_closed_source_bound_idempotent_and_uncommitted(self) -> None:
        arguments = self._arguments()
        source_bytes = {
            path: path.read_bytes()
            for path in (
                self.capture.parent / "meeting.json",
                self.source,
                self.capture / "session.json",
                self.capture / "mic.wav",
                self.capture / "system.wav",
            )
        }
        calls: list[tuple[Path, Path]] = []
        writer = self._candidate_writer(calls)
        with mock.patch("worker.transcription.create_transcript_revision", writer):
            first = transcript_retry(
                self.root,
                arguments,
                admission="internal-alpha",
                model_dir=self.model,
                encoder_digest="e" * 64,
            )
            second = transcript_retry(
                self.root,
                arguments,
                admission="internal-alpha",
                model_dir=self.model,
                encoder_digest="e" * 64,
            )

        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "candidate-transcript",
                "source-transcript",
                "capture-session",
                "capture-mic",
                "capture-system",
            },
        )
        self.assertEqual(first["source-transcript"], arguments["source_transcript_sha256"])
        self.assertEqual(first["capture-session"], arguments["capture_session_sha256"])
        self.assertEqual(first["capture-mic"], arguments["microphone_audio_sha256"])
        self.assertEqual(first["capture-system"], arguments["system_audio_sha256"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(
            (self.transcript_dir / f"{first['candidate-transcript']}.json").is_file()
        )
        for path, expected in source_bytes.items():
            self.assertEqual(path.read_bytes(), expected)
        meeting = json.loads((self.capture.parent / "meeting.json").read_text())
        self.assertEqual(
            meeting["artifacts"]["current_transcript"]["sha256"], self.source_digest
        )
        self.assertIsNone(meeting["artifacts"]["current_note"])
        self.assertFalse((self.capture.parent / "notes").exists())

    def test_retry_refuses_missing_released_or_mismatched_sources_before_creation(self) -> None:
        for label in ("missing", "released", "mismatched"):
            with self.subTest(label=label):
                self.temporary.cleanup()
                self.setUp()
                arguments = self._arguments()
                if label == "missing":
                    (self.capture / "mic.wav").unlink()
                elif label == "released":
                    (self.capture.parent / "meeting.json").unlink()
                    self._write_meeting(state="released")
                else:
                    arguments["system_audio_sha256"] = "f" * 64
                writer = mock.Mock()
                with mock.patch("worker.transcription.create_transcript_revision", writer):
                    with self.assertRaises(AdapterRefused):
                        transcript_retry(
                            self.root,
                            arguments,
                            admission="internal-alpha",
                            model_dir=self.model,
                            encoder_digest="e" * 64,
                        )
                writer.assert_not_called()


class TranscriptRetryWireContractTests(unittest.TestCase):
    def test_exact_wire_shape_and_unknown_fields_refuse(self) -> None:
        arguments = {
            "meeting_id": str(uuid.uuid4()),
            "source_transcript_sha256": "a" * 64,
            "capture_session_sha256": "b" * 64,
            "microphone_audio_sha256": "c" * 64,
            "system_audio_sha256": "d" * 64,
        }
        digests = {
            "candidate-transcript": "e" * 64,
            "source-transcript": "a" * 64,
            "capture-session": "b" * 64,
            "capture-mic": "c" * 64,
            "capture-system": "d" * 64,
        }
        self.assertEqual(validate_transcript_retry_arguments(arguments), arguments)
        self.assertEqual(validate_transcript_retry_digests(digests, arguments), digests)
        self.assertEqual(validate_transcript_retry_join(arguments, digests), (arguments, digests))
        for source, validator in (
            (arguments, validate_transcript_retry_arguments),
            (digests, lambda value: validate_transcript_retry_digests(value, arguments)),
        ):
            changed = dict(source)
            changed["unexpected"] = True
            with self.subTest(validator=validator):
                with self.assertRaises(ProductContractRefused):
                    validator(changed)
