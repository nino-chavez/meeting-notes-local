from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
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

    def test_an_empty_profile_directory_asks_for_no_gate(self) -> None:
        (self.root / "profile").mkdir(mode=0o700)
        self.assertIsNone(
            adapters._installed_voiceprint_gate(self.root, "e" * 64, None)
        )

    def test_a_zero_byte_profile_is_absent_because_that_is_what_rust_writes(
        self,
    ) -> None:
        """The state of every fresh install, and of every reset.

        Rust never unlinks this file. `initialize_or_open` creates it at zero
        bytes on every macOS startup before any capture, and a reset swaps the
        live profile for a zero-length file rather than removing it;
        `profile_present` is `profile_size != 0`. Reading existence instead of
        size refused transcription for every operator who had never enrolled —
        on both lanes, on a fresh install, for the whole product.
        """
        directory = self.root / "profile"
        directory.mkdir(mode=0o700)
        os.close(
            os.open(
                directory / "voiceprint.json",
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        )
        self.assertEqual((directory / "voiceprint.json").stat().st_size, 0)
        self.assertIsNone(
            adapters._installed_voiceprint_gate(self.root, "e" * 64, None)
        )
        # And the operation it guards reaches transcription asking for no gate,
        # which is the part that actually broke.
        asked: list[object] = []

        def record(*_arguments, gate_filter=None, **_keywords):
            asked.append(gate_filter)
            return "digest", self.root / "unused.json"

        with unittest.mock.patch(
            "worker.transcription.create_transcript_revision", record
        ):
            adapters.transcript_create(
                self.root,
                {"meeting_id": self.meeting_id},
                admission="internal-alpha",
                model_dir=self.model,
                encoder_digest="e" * 64,
                encoder_path=None,
            )
        self.assertEqual(asked, [None])

    def test_installed_profile_without_an_admitted_encoder_refuses(self) -> None:
        # Fork 1, settled: on a placeholder-encoder build an installed profile
        # stops transcription rather than producing an artifact that would say
        # no profile was supplied. The cohort DMG ships the admitted encoder, so
        # this costs a real operator nothing; it costs a placeholder build the
        # ability to transcribe until the operator resets the profile.
        # Reset, not discard: profile.discard targets profile-candidates, and
        # never touches the live file.
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


class RealProfileGateTests(unittest.TestCase):
    """The gate closure, run for real, with a real profile file.

    Everything else in this file injects a fake gate or stops at a refusal, so
    the closure `_installed_voiceprint_gate` returns — `Voiceprint`,
    `drop_offprint`, `voiceprint_provenance` — had no coverage whatever. Its
    first execution would otherwise have been on a cohort machine, after a real
    meeting, on audio that cannot be recaptured.

    The profile here is genuine: built by `enroll`, written by the canonical
    `save_profile`, and read back by the canonical `load_profile` with the
    fingerprint binding live. Only the ONNX session is substituted, because no
    development machine packages onnxruntime and the 20 MB encoder.
    """

    def setUp(self) -> None:
        import numpy as np
        import speaker_gate as sg

        self.sg = sg
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)

        rng = np.random.default_rng(11)
        directions = sg._speaker_directions(rng, 3)
        self.embed = sg._fixture_encoder(directions, within=0.05)

        # Speaker 0 is the operator. Twenty-four enrolment segments over two
        # sittings, which is what save_profile's own contract requires.
        audio, segments = sg._fixture_audio(
            sg._spans(12, 0, 1.0) + sg._spans(12, 0, 70.0), rng
        )
        embeddings = sg.embed_segments(audio, segments, self.embed)
        durations = [s["end"] - s["start"] for s in segments]
        profile = sg.enroll(embeddings, durations)

        # A stand-in for the packaged encoder artifact. Its digest is the
        # manifest digest AND the profile's recorded fingerprint, so both
        # bindings the adapter checks are real.
        self.encoder_path = self.root / "encoder.onnx"
        descriptor = os.open(
            self.encoder_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(b"packaged encoder stand-in")
        self.encoder_digest = adapters.sha256(self.encoder_path)

        directory = self.root / "profile"
        directory.mkdir(mode=0o700)
        sg.save_profile(
            directory / "voiceprint.json",
            profile,
            selected_target=0.05,
            operator_scores=np.linspace(0.60, 0.90, 100).tolist(),
            negative_scores=np.linspace(0.20, 0.50, 20).tolist(),
            held_out="leave-one-sitting-out",
            sittings=[
                {"audio": "a.wav", "audio_sha256": "a" * 64,
                 "captured_at": "2026-07-20T09:00:00+0000"},
                {"audio": "b.wav", "audio_sha256": "b" * 64,
                 "captured_at": "2026-07-22T14:00:00+0000"},
            ],
            negative_sources=[{
                "source_class": "public-or-licensed",
                "audio": "negative.wav",
                "segments": "negative-segments.json",
                "audio_sha256": "c" * 64,
                "audio_samples": 1_280_000,
                "segments_sha256": "d" * 64,
                "segments_schema": "mic-segments/1",
                "captured_at": "2026-07-22T15:00:00+0000",
                "scorable_segments": 20,
                "scorable_seconds": 80.0,
            }],
            encoder_fingerprint_value=self.encoder_digest,
        )
        os.chmod(directory / "voiceprint.json", 0o600)

        # One turn from the operator, one from somebody else beside the
        # microphone — the case the gate exists for, and the one drop_unvoiced
        # and drop_bled are both blind to.
        self.audio, self.segments = sg._fixture_audio(
            [(1.0, 5.0, 0), (7.0, 11.0, 1)], rng
        )
        self.segments[0]["text"] = "the operator speaking"
        self.segments[1]["text"] = "somebody at the next desk"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build_gate(self):
        gate = adapters._installed_voiceprint_gate(
            self.root,
            self.encoder_digest,
            self.encoder_path,
            embedder=self.embed,
        )
        self.assertIsNotNone(gate)
        return gate

    def test_the_other_voice_is_marked_and_the_operator_is_not(self) -> None:
        marked, gating = self.build_gate()(
            self.segments, self.audio, None, "mic"
        )
        self.assertEqual(
            [(segment.get("gated"), segment["text"]) for segment in marked],
            [(None, "the operator speaking"), (True, "somebody at the next desk")],
        )
        rejected = marked[1]
        self.assertIsInstance(rejected["gate_score"], float)
        self.assertTrue(rejected["gate_reason"])
        self.assertTrue(gating["applied"])
        self.assertEqual(gating["rejected"], 1)
        self.assertEqual(gating["n_sittings"], 2)
        self.assertEqual(gating["encoder_fingerprint"], self.encoder_digest)
        self.assertIsInstance(gating["threshold"], float)

    def test_high_bleed_skips_the_gate_and_says_so(self) -> None:
        # Where the far end is coming back through the room the labels are
        # already gone and the gate is measured to reject the operator too.
        # Skipping is the measured choice; recording that it skipped is the
        # part the artifact needs.
        contaminated = {"peak_r": 0.99, "positive_r": 0.99, "analysed_s": 60.0}
        marked, gating = self.build_gate()(
            self.segments, self.audio, contaminated, "mic"
        )
        self.assertTrue(all("gated" not in segment for segment in marked))
        self.assertFalse(gating["applied"])
        self.assertEqual(gating["why"], "bleed above the attribution cut")

    def test_the_whole_chain_writes_a_gated_artifact(self) -> None:
        from transcript import load

        capture = self.root / "capture"
        capture.mkdir(mode=0o700)
        write_wav(capture / "mic.wav", 500)
        write_wav(capture / "system.wav", 900)
        finalize_session(
            capture,
            "2000-01-01T00:00:00+0000",
            build_capture_health(
                mic_samples=3_200,
                system_samples=3_200,
                capture_elapsed_samples=3_200,
                dropouts={"mic": [], "system": []},
                tap_errors=[],
                transcription_requested=False,
                transcript_written=False,
            ),
        )
        model = self.root / "model"
        model.mkdir(mode=0o700)
        for name in ("config.json", "weights.safetensors"):
            descriptor = os.open(
                model / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(b"fixture")

        # The capture WAVs are constant tones; the gate needs the fixture audio
        # whose amplitude encodes the speaker, so the transcriber hands back the
        # fixture segments and the gate scores against the fixture leg.
        gate = self.build_gate()
        fixture_audio = self.audio

        def transcribe(audio, _model, _language):
            if float(audio[0]) < 0.02:
                return [dict(segment) for segment in self.segments]
            return [{"start": 6.0, "end": 9.0, "text": "the far end"}]

        _, path = create_transcript_revision(
            capture,
            self.root / "transcript",
            model,
            transcribe_audio=transcribe,
            voicing_filter=lambda segments, *_rest: segments,
            bleed_filter=lambda segments, *_rest: segments,
            gate_filter=lambda segments, _mic, acoustic, label: gate(
                segments, fixture_audio, acoustic, label
            ),
        )

        document = load(path)
        self.assertEqual(
            [turn.text for turn in document.turns],
            ["the operator speaking", "the far end"],
        )
        self.assertEqual(
            [turn.text for turn in document.gated_turns],
            ["somebody at the next desk"],
        )
        self.assertTrue(document.gate["applied"])
        self.assertEqual(document.gate["encoder"], self.sg.ECAPA_SOURCE)


if __name__ == "__main__":
    unittest.main()
