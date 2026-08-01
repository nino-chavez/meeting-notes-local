from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
import wave
from pathlib import Path
from unittest import mock

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "spike"))
sys.path.insert(0, str(REPO / "notes"))

from capture_health import TRANSCRIPT_SCHEMA, build as build_capture_health
from dual_capture import finalize_session, open_private_binary, sha256, write_private_text
from verify_capture import verify_acquisition, verify_capture
from summarize import validate_artifact_pair
from speaker_gate import Profile, load_profile, save_profile
from transcript import load
from worker.product_contracts import (
    ProductContractRefused,
    transcript_view_digest,
    validate_note_create_arguments,
    validate_note_create_digests,
    validate_note_create_error,
    validate_note_create_join,
    validate_transcript_restore_arguments,
    validate_transcript_restore_digests,
    validate_transcript_restore_join,
    validate_transcript_view,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def build_capture(capture_dir: Path) -> None:
    capture_dir.mkdir(mode=0o700, parents=True)
    # Cross the model adapter's half-second floor so packaged-runtime tests
    # exercise real transcription and its data-dependent filter output.
    samples = 16_000
    for leg in ("mic", "system"):
        with open_private_binary(capture_dir / f"{leg}.wav") as handle:
            with wave.open(handle, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16_000)
                wav.writeframes(b"\x01\0" * samples)
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
        "source": "mechanical worker fixture",
        "attribution": "channel",
        "bleed": None,
        "voiceprint": None,
        "capture_health": health,
        "turns": [
            {"speaker": "Me", "start": 0.0, "end": 0.08, "text": "fixture one"},
            {"speaker": "Them", "start": 0.1, "end": 0.18, "text": "fixture two"},
        ],
    }
    write_private_text(
        capture_dir / "transcript.json", json.dumps(transcript, indent=2) + "\n"
    )
    for leg in ("mic", "system"):
        segments = {
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
        }
        write_private_text(
            capture_dir / f"{leg}-segments.json",
            json.dumps(segments, indent=2) + "\n",
        )
    finalize_session(capture_dir, "2000-01-01T00:00:00+0000", health)


class WorkerProcess:
    def __init__(self, root: Path, manifest: Path):
        read_fd, self.write_fd = os.pipe()
        packaged_root_value = os.environ.get("LMN_PACKAGED_RUNTIME_ROOT")
        if packaged_root_value:
            packaged_root = Path(packaged_root_value)
            executable = packaged_root / "python-runtime/bin/python3.12"
            prefix = [str(executable), "-E", "-s", "-B", "-m", "worker.main"]
            cwd = packaged_root
        else:
            prefix = [sys.executable, "-m", "worker.main"]
            cwd = REPO
        self.process = subprocess.Popen(
            prefix
            + [
                "--app-data-root",
                str(root),
                "--runtime-manifest",
                str(manifest),
                "--parent-liveness-fd",
                str(read_fd),
            ],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(read_fd,),
            text=True,
        )
        os.close(read_fd)
        self.closed = False
        self.ready = json.loads(self.process.stdout.readline())

    def request(self, operation: str, arguments: dict) -> dict:
        request_id = str(uuid.uuid4())
        command = {
            "schema": "worker-command/2",
            "request_id": request_id,
            "operation": operation,
            "arguments": arguments,
        }
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        result = json.loads(self.process.stdout.readline())
        self.assert_result_id(result, request_id)
        return result

    @staticmethod
    def assert_result_id(result: dict, request_id: str) -> None:
        if result["request_id"] != request_id:
            raise AssertionError("worker result request ID mismatch")

    def close(self) -> None:
        if not self.closed:
            os.close(self.write_fd)
            self.closed = True
        self.process.wait(timeout=3)
        error = self.process.stderr.read()
        self.process.stdin.close()
        self.process.stdout.close()
        self.process.stderr.close()
        if self.process.returncode != 0:
            raise AssertionError(error)


class WorkerProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "app"
        self.root.mkdir(mode=0o700)
        resources = self.base / "resources"
        resources.mkdir(mode=0o700)
        self.resources = resources
        for name in ("runtime", "worker", "tap", "encoder"):
            private_file(resources / name, name.encode())
        manifest = {
            "schema": "app-runtime/1",
            "admission": "boundary-test",
            "runtime": {"path": "runtime", "sha256": digest(resources / "runtime")},
            "worker": {"path": "worker", "sha256": digest(resources / "worker")},
            "tap": {"path": "tap", "sha256": digest(resources / "tap")},
            "encoder": {"path": "encoder", "sha256": digest(resources / "encoder")},
            "models": [],
        }
        self.base_manifest = manifest
        self.admission = "boundary-test"
        packaged_root = os.environ.get("LMN_PACKAGED_RUNTIME_ROOT")
        if packaged_root:
            self.manifest = Path(packaged_root) / "app-runtime.json"
            packaged_manifest = json.loads(self.manifest.read_text())
            self.admission = packaged_manifest["admission"]
            self.encoder_digest = packaged_manifest["encoder"]["sha256"]
        else:
            self.manifest = resources / "manifest.json"
            private_file(self.manifest, (json.dumps(manifest) + "\n").encode())
            self.encoder_digest = manifest["encoder"]["sha256"]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_capture_and_transcript_match_direct_validators(self) -> None:
        meeting_id = str(uuid.uuid4())
        capture = self.root / "meetings" / meeting_id / "capture"
        build_capture(capture)
        direct = verify_capture(capture)
        acquisition = verify_acquisition(capture)
        session_digest = digest(capture / "session.json")
        mic_digest = digest(capture / "mic.wav")
        system_digest = digest(capture / "system.wav")
        transcript_digest = digest(capture / "transcript.json")

        worker = WorkerProcess(self.root, self.manifest)
        try:
            self.assertEqual(worker.ready["schema"], "worker-event/2")
            self.assertEqual(worker.ready["protocol"], 2)
            self.assertEqual(worker.ready["admission"], self.admission)
            expected_operations = {
                "capture.finalize",
                "capture.inspect",
                "transcript.create",
            }
            if self.admission != "internal-alpha":
                expected_operations |= {
                    "profile.inspect",
                    "profile.adopt",
                    "note.inspect",
                }
            self.assertEqual(set(worker.ready["operations"]), expected_operations)
            inspected = worker.request("capture.inspect", {"meeting_id": meeting_id})
            self.assertTrue(inspected["ok"])
            self.assertEqual(
                inspected["artifact_digests"],
                {
                    "capture-session": session_digest,
                    "capture-mic": mic_digest,
                    "capture-system": system_digest,
                },
            )
            created = worker.request("transcript.create", {"meeting_id": meeting_id})
            self.assertTrue(created["ok"])
            created_digest = created["artifact_digests"]["transcript"]
            if self.admission == "boundary-test":
                self.assertEqual(created_digest, transcript_digest)
            retained = self.root / "meetings" / meeting_id / "transcript" / (
                created_digest + ".json"
            )
            self.assertEqual(digest(retained), created_digest)
            load(retained)
            self.assertEqual(direct["status"], "complete")
            self.assertEqual(acquisition["status"], "complete")
        finally:
            worker.close()

    def test_internal_alpha_manifest_selects_the_fixed_model_directory(self) -> None:
        from worker.main import load_manifest, transcript_model_dir

        model_dir = self.resources / "models" / "whisper-large-v3-turbo"
        model_dir.mkdir(mode=0o700, parents=True)
        private_file(model_dir / "config.json", b"config")
        private_file(model_dir / "weights.safetensors", b"weights")
        document = json.loads(json.dumps(self.base_manifest))
        document["admission"] = "internal-alpha"
        document["models"] = [
            {
                "id": "whisper-large-v3-turbo-config",
                "path": "models/whisper-large-v3-turbo/config.json",
                "sha256": digest(model_dir / "config.json"),
            },
            {
                "id": "whisper-large-v3-turbo-weights",
                "path": "models/whisper-large-v3-turbo/weights.safetensors",
                "sha256": digest(model_dir / "weights.safetensors"),
            },
        ]
        alpha_manifest = self.resources / "internal-alpha.json"
        private_file(alpha_manifest, (json.dumps(document) + "\n").encode())

        loaded = load_manifest(alpha_manifest)
        self.assertEqual(transcript_model_dir(alpha_manifest, loaded), model_dir.resolve())

    def test_capture_finalize_creates_exact_receipt_without_overwrite(self) -> None:
        meeting_id = str(uuid.uuid4())
        capture = self.root / "meetings" / meeting_id / "capture"
        capture.mkdir(mode=0o700, parents=True)
        samples = 3_200
        for leg in ("mic", "system"):
            with open_private_binary(capture / f"{leg}.wav") as handle:
                with wave.open(handle, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16_000)
                    wav.writeframes(b"\x01\0" * samples)

        worker = WorkerProcess(self.root, self.manifest)
        try:
            finalized = worker.request(
                "capture.finalize",
                {
                    "meeting_id": meeting_id,
                    "started_at_epoch_seconds": 946684800,
                    "capture_elapsed_samples": samples,
                },
            )
            self.assertTrue(finalized["ok"])
            self.assertEqual(
                set(finalized["artifact_digests"]),
                {"capture-session", "capture-mic", "capture-system"},
            )
            verify_acquisition(capture)
            original = (capture / "session.json").read_bytes()

            repeated = worker.request(
                "capture.finalize",
                {
                    "meeting_id": meeting_id,
                    "started_at_epoch_seconds": 946684800,
                    "capture_elapsed_samples": samples,
                },
            )
            self.assertFalse(repeated["ok"])
            self.assertEqual((capture / "session.json").read_bytes(), original)
        finally:
            worker.close()

    def test_command_paths_and_research_flags_are_refused(self) -> None:
        worker = WorkerProcess(self.root, self.manifest)
        try:
            result = worker.request(
                "capture.inspect",
                {"meeting_id": "../escape", "capture_dir": "/tmp/private"},
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "protocol_failure")
            self.assertEqual(result["artifact_digests"], {})
        finally:
            worker.close()

    def test_unavailable_capture_start_cannot_report_success(self) -> None:
        worker = WorkerProcess(self.root, self.manifest)
        try:
            result = worker.request(
                "capture.start",
                {"meeting_id": str(uuid.uuid4())},
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "protocol_failure")
            self.assertFalse(result["recoverable"])
            self.assertEqual(result["artifact_digests"], {})
        finally:
            worker.close()

    def test_note_pair_matches_direct_validator(self) -> None:
        pack = json.loads(
            (REPO / "docs/prototype/fixtures/accepted-note2.fixture").read_text()
        )
        meeting_id = str(uuid.uuid4())
        transcript_bytes = (json.dumps(pack["transcript"], indent=2) + "\n").encode()
        transcript_id = hashlib.sha256(transcript_bytes).hexdigest()
        markdown_bytes = pack["markdown"].encode()
        markdown_id = hashlib.sha256(markdown_bytes).hexdigest()
        note = json.loads(json.dumps(pack["note"]))
        note["meeting"]["id"] = meeting_id
        note["transcript"] = f"../transcript/{transcript_id}.json"
        note["render"]["path"] = f"{markdown_id}.md"
        note_bytes = (json.dumps(note, ensure_ascii=False, indent=2) + "\n").encode()
        note_id = hashlib.sha256(note_bytes).hexdigest()
        transcript_dir = self.root / "meetings" / meeting_id / "transcript"
        notes_dir = self.root / "meetings" / meeting_id / "notes"
        transcript_dir.mkdir(mode=0o700, parents=True)
        notes_dir.mkdir(mode=0o700)
        transcript_path = transcript_dir / f"{transcript_id}.json"
        note_path = notes_dir / f"{note_id}.json"
        markdown_path = notes_dir / f"{markdown_id}.md"
        private_file(transcript_path, transcript_bytes)
        private_file(note_path, note_bytes)
        private_file(markdown_path, markdown_bytes)
        validate_artifact_pair(note, note_path, load(transcript_path))

        worker = WorkerProcess(self.root, self.manifest)
        try:
            result = worker.request(
                "note.inspect",
                {
                    "meeting_id": meeting_id,
                    "note_id": note_id,
                    "transcript_id": transcript_id,
                },
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["artifact_digests"]["note"], digest(note_path))
            self.assertEqual(
                result["artifact_digests"]["note-markdown"], digest(markdown_path)
            )
            self.assertEqual(result["artifact_digests"]["transcript"], transcript_id)

            refused = worker.request(
                "note.inspect",
                {
                    "meeting_id": meeting_id,
                    "note_id": str(uuid.uuid4()),
                    "transcript_id": transcript_id,
                },
            )
            self.assertFalse(refused["ok"])
            self.assertEqual(refused["code"], "protocol_failure")
            self.assertEqual(refused["artifact_digests"], {})

            wrong_meeting = json.loads(json.dumps(note))
            wrong_meeting["meeting"]["id"] = str(uuid.uuid4())
            wrong_meeting_bytes = (
                json.dumps(wrong_meeting, ensure_ascii=False, indent=2) + "\n"
            ).encode()
            wrong_meeting_id = hashlib.sha256(wrong_meeting_bytes).hexdigest()
            private_file(notes_dir / f"{wrong_meeting_id}.json", wrong_meeting_bytes)
            refused = worker.request(
                "note.inspect",
                {
                    "meeting_id": meeting_id,
                    "note_id": wrong_meeting_id,
                    "transcript_id": transcript_id,
                },
            )
            self.assertFalse(refused["ok"])
            self.assertEqual(refused["code"], "protocol_failure")
            self.assertEqual(refused["artifact_digests"], {})

            rejected = json.loads(json.dumps(note))
            rejected["checks"]["context"]["ok"] = False
            rejected["passed"] = False
            rejected_bytes = (
                json.dumps(rejected, ensure_ascii=False, indent=2) + "\n"
            ).encode()
            rejected_id = hashlib.sha256(rejected_bytes).hexdigest()
            private_file(notes_dir / f"{rejected_id}.json", rejected_bytes)
            refused = worker.request(
                "note.inspect",
                {
                    "meeting_id": meeting_id,
                    "note_id": rejected_id,
                    "transcript_id": transcript_id,
                },
            )
            self.assertFalse(refused["ok"])
            self.assertEqual(refused["code"], "protocol_failure")
            self.assertEqual(refused["artifact_digests"], {})

            changed_locator = json.loads(json.dumps(note))
            changed_locator["claims"][0]["turn"] += 1
            changed_bytes = (
                json.dumps(changed_locator, ensure_ascii=False, indent=2) + "\n"
            ).encode()
            changed_id = hashlib.sha256(changed_bytes).hexdigest()
            private_file(notes_dir / f"{changed_id}.json", changed_bytes)
            refused = worker.request(
                "note.inspect",
                {
                    "meeting_id": meeting_id,
                    "note_id": changed_id,
                    "transcript_id": transcript_id,
                },
            )
            self.assertFalse(refused["ok"])
            self.assertEqual(refused["code"], "protocol_failure")
            self.assertEqual(refused["artifact_digests"], {})
        finally:
            worker.close()

    def test_profile_adoption_matches_strict_loader(self) -> None:
        profile_id = str(uuid.uuid4())
        candidate_dir = self.root / "profile-candidates" / profile_id
        candidate_dir.mkdir(mode=0o700, parents=True)
        profile_path = candidate_dir / "voiceprint.json"
        centroid = np.zeros(192)
        centroid[0] = 1.0
        save_profile(
            profile_path,
            Profile(
                centroid=centroid,
                n_enrolled=100,
                n_excluded=0,
                seconds=400.0,
                cohesion=0.8,
                spread=0.1,
            ),
            selected_target=0.05,
            operator_scores=np.linspace(0.60, 0.90, 100).tolist(),
            negative_scores=np.linspace(0.20, 0.50, 20).tolist(),
            held_out="leave-one-sitting-out",
            sittings=[
                {
                    "audio": "a.wav",
                    "audio_sha256": "a" * 64,
                    "captured_at": "2026-07-20T09:00:00+0000",
                },
                {
                    "audio": "b.wav",
                    "audio_sha256": "b" * 64,
                    "captured_at": "2026-07-22T14:00:00+0000",
                },
            ],
            negative_sources=[
                {
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
                }
            ],
            encoder_fingerprint_value=self.encoder_digest,
        )
        load_profile(profile_path, expected_encoder_fingerprint=self.encoder_digest)
        expected_digest = digest(profile_path)

        worker = WorkerProcess(self.root, self.manifest)
        try:
            inspected = worker.request("profile.inspect", {"profile_id": profile_id})
            self.assertTrue(inspected["ok"])
            self.assertEqual(inspected["artifact_digests"]["profile"], expected_digest)
            adopted = worker.request("profile.adopt", {"profile_id": profile_id})
            self.assertTrue(adopted["ok"])
            self.assertEqual(adopted["artifact_digests"]["profile"], expected_digest)
            adopted_path = self.root / "profile" / "voiceprint.json"
            self.assertEqual(digest(adopted_path), expected_digest)
            load_profile(adopted_path, expected_encoder_fingerprint=self.encoder_digest)
        finally:
            worker.close()

    def test_parent_liveness_eof_stops_worker(self) -> None:
        worker = WorkerProcess(self.root, self.manifest)
        os.close(worker.write_fd)
        worker.closed = True
        worker.close()

    def test_parent_liveness_watchdog_interrupts_blocked_work(self) -> None:
        read_fd, write_fd = os.pipe()
        script = """
import sys
import time
from worker.main import start_parent_liveness_watchdog
start_parent_liveness_watchdog(int(sys.argv[1]))
while True:
    time.sleep(60)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(read_fd)],
            cwd=REPO,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            pass_fds=(read_fd,),
        )
        os.close(read_fd)
        os.close(write_fd)
        process.wait(timeout=3)
        error = process.stderr.read().decode()
        process.stderr.close()
        self.assertEqual(process.returncode, 0, error)

    def test_progress_helper_emits_the_closed_shape(self) -> None:
        from worker.main import emit_progress

        request_id = str(uuid.uuid4())
        meeting_id = str(uuid.uuid4())
        output = io.StringIO()
        with mock.patch("worker.main.sys.stdout", output):
            emit_progress(request_id, meeting_id, "recording")
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "schema": "worker-event/2",
                "request_id": request_id,
                "event": "capture.state",
                "state": "recording",
                "meeting_id": meeting_id,
            },
        )
        with self.assertRaises(ValueError):
            emit_progress(request_id, meeting_id, "arming")

    def test_operation_stdout_cannot_enter_protocol(self) -> None:
        from worker.main import dispatch_without_protocol_output

        def noisy_dispatch(*_args, **_kwargs):
            print("not a protocol frame")
            return {"transcript": "a" * 64}

        protocol = io.StringIO()
        with mock.patch("worker.main.dispatch", side_effect=noisy_dispatch):
            with mock.patch("worker.main.sys.stdout", protocol):
                result = dispatch_without_protocol_output(
                    self.root,
                    "transcript.create",
                    {"meeting_id": str(uuid.uuid4())},
                    encoder_digest=self.encoder_digest,
                    admission="internal-alpha",
                    model_dir=None,
                )

        self.assertEqual(result, {"transcript": "a" * 64})
        self.assertEqual(protocol.getvalue(), "")


class ProductOperationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(
            (REPO / "tests/fixtures/product-operations-v1.json").read_text(
                encoding="utf-8"
            )
        )

    def test_shared_fixture_matches_closed_worker_schemas(self) -> None:
        restoration = self.fixture["restoration"]
        restore_arguments, view, restore_digests = validate_transcript_restore_join(
            restoration["worker_arguments"],
            restoration["view"],
            restoration["worker_artifact_digests"],
        )
        self.assertEqual(
            transcript_view_digest(view), restore_digests["transcript"]
        )
        self.assertEqual(
            transcript_view_digest(dict(reversed(list(view.items())))),
            restore_digests["transcript"],
        )
        self.assertEqual(
            view["parent_transcript_sha256"],
            restore_arguments["source_transcript_sha256"],
        )
        self.assertEqual(
            view["restored_source_turn_indices"],
            [restore_arguments["source_turn_index"]],
        )

        accepted = self.fixture["accepted_note"]
        note = accepted["result"]["note"]
        validate_note_create_join(
            accepted["worker_arguments"],
            accepted["worker_artifact_digests"],
            note_sha256=note["json"]["sha256"],
            markdown_sha256=note["markdown"]["sha256"],
        )
        rejected = self.fixture["rejected_note"]
        validate_note_create_arguments(rejected["worker_arguments"])
        self.assertEqual(
            validate_note_create_error(rejected["worker_error"]), "note-rejected"
        )

    def test_worker_schemas_refuse_unknown_fields_and_drift(self) -> None:
        cases = [
            (
                validate_transcript_restore_arguments,
                self.fixture["restoration"]["worker_arguments"],
            ),
            (validate_transcript_view, self.fixture["restoration"]["view"]),
            (
                validate_note_create_arguments,
                self.fixture["accepted_note"]["worker_arguments"],
            ),
        ]
        for validator, source in cases:
            changed = dict(source)
            changed["unexpected"] = True
            with self.subTest(validator=validator.__name__):
                with self.assertRaises(ProductContractRefused):
                    validator(changed)

        changed_turn = dict(self.fixture["restoration"]["worker_arguments"])
        changed_turn["source_turn_index"] = True
        with self.assertRaises(ProductContractRefused):
            validate_transcript_restore_arguments(changed_turn)

        changed_view = dict(self.fixture["restoration"]["view"])
        changed_view["restored_source_turn_indices"] = [7, 7]
        with self.assertRaises(ProductContractRefused):
            validate_transcript_view(changed_view)

        extra_restore_digest = dict(
            self.fixture["restoration"]["worker_artifact_digests"]
        )
        extra_restore_digest["unexpected"] = "a" * 64
        with self.assertRaises(ProductContractRefused):
            validate_transcript_restore_digests(extra_restore_digest, "a" * 64)

        changed_note_digest = dict(
            self.fixture["accepted_note"]["worker_artifact_digests"]
        )
        changed_note_digest["transcript"] = "b" * 64
        with self.assertRaises(ProductContractRefused):
            validate_note_create_digests(
                changed_note_digest,
                self.fixture["accepted_note"]["worker_arguments"][
                    "source_transcript_sha256"
                ],
            )

        restoration = self.fixture["restoration"]
        for key in ("base-transcript", "parent-transcript", "transcript"):
            changed = dict(restoration["worker_artifact_digests"])
            changed[key] = "b" * 64
            with self.subTest(restore_digest=key):
                with self.assertRaises(ProductContractRefused):
                    validate_transcript_restore_join(
                        restoration["worker_arguments"],
                        restoration["view"],
                        changed,
                    )

        accepted = self.fixture["accepted_note"]
        note = accepted["result"]["note"]
        for key in ("note", "note-markdown", "transcript"):
            changed = dict(accepted["worker_artifact_digests"])
            changed[key] = "b" * 64
            with self.subTest(note_digest=key):
                with self.assertRaises(ProductContractRefused):
                    validate_note_create_join(
                        accepted["worker_arguments"],
                        changed,
                        note_sha256=note["json"]["sha256"],
                        markdown_sha256=note["markdown"]["sha256"],
                    )

        for field, value in (
            ("code", "protocol_failure"),
            ("recoverable", False),
            ("artifact_digests", {"note": "a" * 64}),
            ("unexpected", True),
        ):
            changed = dict(self.fixture["rejected_note"]["worker_error"])
            changed[field] = value
            with self.subTest(rejected_field=field):
                with self.assertRaises(ProductContractRefused):
                    validate_note_create_error(changed)


if __name__ == "__main__":
    unittest.main()
