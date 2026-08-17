from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "spike"))

from capture_health import (  # noqa: E402
    build as build_capture_health,
    build_microphone_identity,
    build_quality_evidence,
    validate_quality_evidence,
)
from dual_capture import finalize_session, open_private_binary, sha256  # noqa: E402
from verify_capture import VerificationError, verify_acquisition  # noqa: E402


def write_wav(path: Path, values: list[int]) -> None:
    with open_private_binary(path) as handle, wave.open(handle, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(
            b"".join(
                int(value).to_bytes(2, "little", signed=True) for value in values
            )
        )


class CaptureQualityTests(unittest.TestCase):
    def test_observations_and_metrics_are_deterministic_and_separate_from_integrity(self) -> None:
        values = [int(0.04 * 32768)] * 3_200
        first = build_quality_evidence(value / 32768.0 for value in values)
        second = build_quality_evidence(value / 32768.0 for value in values)
        self.assertEqual(first, second)
        self.assertEqual(first["observations"]["silence"]["status"], "not_observed")
        self.assertEqual(first["observations"]["clipping"]["status"], "not_observed")
        self.assertEqual(first["observations"]["low_input"]["status"], "not_observed")
        self.assertEqual(first["observations"]["background_noise"]["status"], "observed")

        health = build_capture_health(
            mic_samples=3_200,
            system_samples=3_200,
            capture_elapsed_samples=3_200,
            dropouts={"mic": [], "system": []},
            tap_errors=[],
            transcription_requested=False,
            transcript_written=False,
        )
        self.assertTrue(health["usable"])

    def test_clipping_and_low_input_are_bounded_observations(self) -> None:
        clipped = [1.0] * 20 + [0.02] * 3_180
        evidence = build_quality_evidence(clipped)
        self.assertEqual(evidence["observations"]["clipping"]["status"], "observed")
        self.assertEqual(evidence["metrics"]["samples"], 3_200)
        self.assertLessEqual(evidence["metrics"]["clipped_fraction"], 1.0)
        low = build_quality_evidence([0.005] * 3_200)
        self.assertEqual(low["observations"]["low_input"]["status"], "observed")

    def test_short_audio_is_explicitly_unknown(self) -> None:
        evidence = build_quality_evidence([0.1] * 100)
        self.assertTrue(
            all(
                observation["status"] == "unknown"
                for observation in evidence["observations"].values()
            )
        )
        validate_quality_evidence(evidence)

    def test_finalized_receipt_persists_quality_and_microphone_without_changing_status(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)
            capture.chmod(0o700)
            write_wav(capture / "mic.wav", [0] * 3_200)
            write_wav(capture / "system.wav", [1] * 3_200)
            health = build_capture_health(
                mic_samples=3_200,
                system_samples=3_200,
                capture_elapsed_samples=3_200,
                dropouts={"mic": [], "system": []},
                tap_errors=[],
                transcription_requested=False,
                transcript_written=False,
            )
            finalize_session(
                capture,
                "2000-01-01T00:00:00+0000",
                health,
                microphone=build_microphone_identity(
                    index=4, name="Built-in Microphone", hostapi=0
                ),
            )
            receipt = verify_acquisition(capture)
            self.assertEqual(receipt["status"], "complete")
            self.assertEqual(receipt["quality"]["observations"]["silence"]["status"], "observed")
            self.assertEqual(receipt["microphone"]["name"], "Built-in Microphone")
            self.assertEqual(receipt["quality"]["source"]["sha256"], sha256(capture / "mic.wav"))

    def test_legacy_receipt_without_quality_remains_valid_but_reports_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)
            capture.chmod(0o700)
            write_wav(capture / "mic.wav", [1] * 3_200)
            write_wav(capture / "system.wav", [1] * 3_200)
            health = build_capture_health(
                mic_samples=3_200,
                system_samples=3_200,
                capture_elapsed_samples=3_200,
                dropouts={"mic": [], "system": []},
                tap_errors=[],
                transcription_requested=False,
                transcript_written=False,
            )
            finalize_session(capture, "2000-01-01T00:00:00+0000", health)
            session_path = capture / "session.json"
            session = json.loads(session_path.read_text())
            session.pop("quality")
            session.pop("microphone")
            descriptor = os.open(session_path, os.O_WRONLY | os.O_TRUNC)
            with os.fdopen(descriptor, "w") as handle:
                json.dump(session, handle)
            session_path.chmod(0o600)
            receipt = verify_acquisition(capture)
            self.assertEqual(receipt["quality"]["observations"]["silence"]["status"], "unknown")
            self.assertIsNone(receipt["microphone"])

    def test_tampered_or_unknown_quality_shape_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)
            capture.chmod(0o700)
            write_wav(capture / "mic.wav", [1] * 3_200)
            write_wav(capture / "system.wav", [1] * 3_200)
            health = build_capture_health(
                mic_samples=3_200,
                system_samples=3_200,
                capture_elapsed_samples=3_200,
                dropouts={"mic": [], "system": []},
                tap_errors=[],
                transcription_requested=False,
                transcript_written=False,
            )
            finalize_session(
                capture,
                "2000-01-01T00:00:00+0000",
                health,
                microphone=build_microphone_identity(index=1, name="Fixture mic"),
            )
            session_path = capture / "session.json"
            original = json.loads(session_path.read_text())
            for mutation in ("tampered", "unknown", "microphone"):
                session = copy.deepcopy(original)
                if mutation == "tampered":
                    session["quality"]["metrics"]["rms"] = 0.99
                elif mutation == "unknown":
                    session["quality"]["schema"] = "capture-quality/999"
                else:
                    session["microphone"]["schema"] = "capture-microphone/999"
                session_path.write_text(json.dumps(session))
                session_path.chmod(0o600)
                with self.assertRaises(VerificationError):
                    verify_acquisition(capture)


if __name__ == "__main__":
    unittest.main()
