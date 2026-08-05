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
from worker import adapters
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
        self.assertEqual(
            [(turn.speaker, turn.text) for turn in document.turns],
            [("Me", "microphone words"), ("Them", "system words")],
        )
        self.assertTrue(document.capture_health["transcription"]["requested"])
        self.assertFalse((self.capture / "transcript.json").exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_partial_mic_bleed_withdraws_channel_attribution_during_overlap(self) -> None:
        def overlapping_transcribe(audio, _model, _language):
            if float(audio[0]) < 0.02:
                return [
                    {"start": 0.0, "end": 1.5, "text": "operator words"},
                    {"start": 1.5, "end": 3.0, "text": "returned system words"},
                ]
            return [{"start": 1.0, "end": 3.0, "text": "system words"}]

        def withhold_returned_system(segments, *_arguments):
            return [segment for segment in segments if segment["text"] != "returned system words"]

        _, path = create_transcript_revision(
            self.capture,
            self.root / "transcript",
            self.model,
            transcribe_audio=overlapping_transcribe,
            voicing_filter=self.keep,
            bleed_filter=withhold_returned_system,
        )

        document = load(path)
        self.assertEqual(document.attribution, "none")
        self.assertEqual(
            [(turn.speaker, turn.text, turn.start) for turn in document.turns],
            [(None, "operator words", 0.0), (None, "system words", 1.0)],
        )

    def test_gate_marks_the_operator_check_instead_of_deleting_it(self) -> None:
        """A gated turn survives on disk, out of the note, and says why.

        Three consumers depend on this exact shape and none of them can be
        reached from a hand-built fixture: `notes/transcript.py` splits the
        gated turns away from what a model may see, `library_read.rs` projects
        them as withheld and addresses restoration by their index in this list,
        and the copy formatter renders them as a withheld line. All three read
        the file this test writes.
        """
        def gate(segments, _mic, _acoustic, _label):
            marked = [
                {**segment, "gated": True, "gate_score": 0.41,
                 "gate_reason": "below threshold"}
                for segment in segments
            ]
            return marked, {"applied": True, "why": None, "threshold": 0.62,
                            "rejected": len(marked), "persistent_other": False}

        _, path = create_transcript_revision(
            self.capture,
            self.root / "transcript",
            self.model,
            transcribe_audio=self.fake_transcribe,
            voicing_filter=self.keep,
            bleed_filter=self.keep,
            gate_filter=gate,
        )

        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            [(turn.get("gated"), turn["text"]) for turn in raw["turns"]],
            [(True, "microphone words"), (None, "system words")],
        )
        self.assertEqual(raw["turns"][0]["gate_reason"], "below threshold")
        self.assertEqual(raw["voiceprint"]["applied"], True)

        document = load(path)
        self.assertEqual([turn.text for turn in document.turns], ["system words"])
        self.assertEqual(
            [turn.text for turn in document.gated_turns], ["microphone words"]
        )
        self.assertEqual(document.gate["threshold"], 0.62)

    def test_gate_is_asked_only_about_the_microphone_leg(self) -> None:
        seen: list[str] = []

        def gate(segments, _mic, _acoustic, label):
            seen.append(label)
            return segments, {"applied": False, "why": "fixture"}

        create_transcript_revision(
            self.capture,
            self.root / "transcript",
            self.model,
            transcribe_audio=self.fake_transcribe,
            voicing_filter=self.keep,
            bleed_filter=self.keep,
            gate_filter=gate,
        )
        self.assertEqual(seen, ["mic"])

    def test_no_profile_leaves_the_artifact_saying_none_was_supplied(self) -> None:
        # A null `voiceprint` is a claim, not an omission: it says no profile was
        # supplied. It must never appear on a transcript whose operator had one
        # installed — see _installed_voiceprint_gate.
        _, path = create_transcript_revision(
            self.capture,
            self.root / "transcript",
            self.model,
            transcribe_audio=self.fake_transcribe,
            voicing_filter=self.keep,
            bleed_filter=self.keep,
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(raw["voiceprint"])
        self.assertTrue(all("gated" not in turn for turn in raw["turns"]))

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


class InstalledVoiceprintGateTests(unittest.TestCase):
    """Which of the three profile states this runtime is in, and what it does."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # Resolved, because the app data root is compared by identity against a
        # resolved parent and macOS reaches a temporary directory through a
        # symlink.
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)
        self.meeting_id = "meeting-fixture"
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
        self.model = self.root / "model"
        self.model.mkdir(mode=0o700)
        for name in ("config.json", "weights.safetensors"):
            descriptor = os.open(
                self.model / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(b"fixture")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def install_profile(self) -> None:
        directory = self.root / "profile"
        directory.mkdir(mode=0o700)
        descriptor = os.open(
            directory / "voiceprint.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("{}\n")

    def test_no_installed_profile_asks_for_no_gate(self) -> None:
        self.assertIsNone(
            adapters._installed_voiceprint_gate(self.root, "e" * 64, None)
        )

    def test_installed_profile_without_an_admitted_encoder_refuses(self) -> None:
        # Fork 1, settled: on a placeholder-encoder build an installed profile
        # stops transcription rather than producing an artifact that would say
        # no profile was supplied. The cohort DMG ships the admitted encoder, so
        # this costs a real operator nothing; it costs a placeholder build the
        # ability to transcribe until the profile is discarded.
        self.install_profile()
        with self.assertRaisesRegex(
            adapters.AdapterRefused, "no admitted speaker encoder"
        ):
            adapters._installed_voiceprint_gate(self.root, "e" * 64, None)

    def test_the_refusal_reaches_the_operation(self) -> None:
        self.install_profile()
        with self.assertRaisesRegex(
            adapters.AdapterRefused, "no admitted speaker encoder"
        ):
            adapters.transcript_create(
                self.root,
                {"meeting_id": self.meeting_id},
                admission="internal-alpha",
                model_dir=self.model,
                encoder_digest="e" * 64,
                encoder_path=None,
            )


if __name__ == "__main__":
    unittest.main()
