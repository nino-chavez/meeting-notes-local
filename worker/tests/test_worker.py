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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def build_capture(capture_dir: Path) -> None:
    capture_dir.mkdir(mode=0o700, parents=True)
    samples = 3200
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
            "schema": "worker-command/1",
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
        packaged_root = os.environ.get("LMN_PACKAGED_RUNTIME_ROOT")
        if packaged_root:
            self.manifest = Path(packaged_root) / "app-runtime.json"
            packaged_manifest = json.loads(self.manifest.read_text())
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
            self.assertEqual(worker.ready["schema"], "worker-event/1")
            self.assertEqual(len(worker.ready["operations"]), 8)
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
            self.assertEqual(created["artifact_digests"]["transcript"], transcript_digest)
            retained = self.root / "meetings" / meeting_id / "transcript" / (
                transcript_digest + ".json"
            )
            self.assertEqual(digest(retained), transcript_digest)
            self.assertEqual(direct["status"], "complete")
            self.assertEqual(acquisition["status"], "complete")
        finally:
            worker.close()

    def test_capture_stop_finalizes_exact_wav_pair_without_overwrite(self) -> None:
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
                "capture.stop",
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
                "capture.stop",
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
        note_id = str(uuid.uuid4())
        transcript_bytes = (json.dumps(pack["transcript"], indent=2) + "\n").encode()
        transcript_id = hashlib.sha256(transcript_bytes).hexdigest()
        transcript_dir = self.root / "meetings" / meeting_id / "transcript"
        notes_dir = self.root / "meetings" / meeting_id / "notes"
        transcript_dir.mkdir(mode=0o700, parents=True)
        notes_dir.mkdir(mode=0o700)
        transcript_path = transcript_dir / f"{transcript_id}.json"
        note_path = notes_dir / f"{note_id}.json"
        markdown_path = notes_dir / pack["markdown_filename"]
        private_file(transcript_path, transcript_bytes)
        private_file(
            note_path, (json.dumps(pack["note"], ensure_ascii=False, indent=2) + "\n").encode()
        )
        private_file(markdown_path, pack["markdown"].encode())
        validate_artifact_pair(pack["note"], note_path, load(transcript_path))

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
                "schema": "worker-event/1",
                "request_id": request_id,
                "event": "capture.state",
                "state": "recording",
                "meeting_id": meeting_id,
            },
        )
        with self.assertRaises(ValueError):
            emit_progress(request_id, meeting_id, "arming")


if __name__ == "__main__":
    unittest.main()
