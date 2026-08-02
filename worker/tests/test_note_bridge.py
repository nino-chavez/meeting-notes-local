from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

from worker.note_validator import ArtifactFailure
from worker.note_validator import inspect as inspect_snapshot
from worker.note_validator import project as project_snapshot
from worker.note_bridge import BridgeRefused, InvalidArguments, _parse_command

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "notes"))
sys.path.insert(0, str(REPO / "spike"))


def private_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NoteBridgeProcess:
    def __init__(
        self,
        root: Path,
        manifest: Path,
        *,
        executable: Path,
        bridge: Path,
        isolated: bool = True,
        parent_environment: dict[str, str] | None = None,
    ):
        read_fd, self._write_fd = os.pipe()
        command = [str(executable)]
        if isolated:
            command.extend(("-I", "-S", "-E", "-s", "-B"))
        command.extend(
            (
                str(bridge),
                "--temporary-private-root",
                str(root),
                "--note-runtime-manifest",
                str(manifest),
                "--parent-liveness-fd",
                str(read_fd),
            )
        )
        self._process = subprocess.Popen(
            command,
            cwd=manifest.parent,
            env=self._scrubbed_environment(parent_environment or dict(os.environ)),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(read_fd,),
        )
        os.close(read_fd)
        ready = self._process.stdout.readline()
        self.ready = json.loads(ready) if ready else None

    @staticmethod
    def _scrubbed_environment(_parent: dict[str, str]) -> dict[str, str]:
        return {}

    def send(self, frame: bytes) -> tuple[dict | None, int, bytes]:
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        self._process.stdin.write(frame)
        self._process.stdin.close()
        line = self._process.stdout.readline()
        self._process.wait(timeout=3)
        result = json.loads(line) if line else None
        error = self._process.stderr.read()
        return result, self._process.returncode, error

    def close(self) -> None:
        if self._write_fd >= 0:
            os.close(self._write_fd)
            self._write_fd = -1
        self._process.wait(timeout=3)
        if self._process.stdin and not self._process.stdin.closed:
            self._process.stdin.close()
        if self._process.stdout:
            self._process.stdout.close()
        if self._process.stderr:
            self._process.stderr.close()


class NoteBridgeHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.role = "inspect"
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "app"
        self.root.mkdir(mode=0o700)
        self.resources = self.base / "resources"
        self.resources.mkdir(mode=0o700)
        self.runtime = self.resources / "python-runtime"
        shutil.copyfile(sys.executable, self.runtime)
        self.runtime.chmod(0o700)
        self.bridge = self.resources / "note_bridge.py"
        shutil.copyfile(REPO / "worker/note_bridge.py", self.bridge)
        self.bridge.chmod(0o600)
        self.validator = self.resources / "note-validator.zip"
        self._write_validator_bundle(self.validator)
        self.manifest = self.resources / "note-runtime.json"
        self._write_manifest()
        self.meeting_id, self.note_id, self.transcript_id = self._write_note_pair()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_validator_bundle(path: Path, note_validator_suffix: bytes = b"") -> None:
        sources = {
            "note_validator.py": REPO / "worker/note_validator.py",
            "summarize.py": REPO / "notes/summarize.py",
            "transcript.py": REPO / "notes/transcript.py",
            "capture_health.py": REPO / "spike/capture_health.py",
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, source in sources.items():
                data = source.read_bytes()
                if name == "note_validator.py":
                    data += note_validator_suffix
                archive.writestr(name, data)
        path.chmod(0o600)

    def _replace_validator(self, note_validator_suffix: str) -> None:
        self.validator.unlink()
        self._write_validator_bundle(self.validator, note_validator_suffix.encode())
        self._write_manifest()

    def _manifest_document(self) -> dict:
        return {
            "schema": "note-runtime/1",
            "role": self.role,
            "runtime": {
                "relative_path": self.runtime.name,
                "sha256": digest(self.runtime),
            },
            "bridge": {
                "relative_path": self.bridge.name,
                "sha256": digest(self.bridge),
            },
            "validator": {
                "relative_path": self.validator.name,
                "sha256": digest(self.validator),
            },
            "generator": None,
            "models": [],
        }

    def _write_manifest(self, document: dict | None = None) -> None:
        self.manifest.unlink(missing_ok=True)
        manifest = document or self._manifest_document()
        private_file(
            self.manifest,
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        )

    def _write_note_pair(self) -> tuple[str, str, str]:
        meeting_id = str(uuid.uuid4())
        pack = json.loads((REPO / "docs/prototype/fixtures/accepted-note2.fixture").read_text())
        transcript_bytes = (json.dumps(pack["transcript"], indent=2) + "\n").encode()
        transcript_id = hashlib.sha256(transcript_bytes).hexdigest()
        transcript = self.root / "meetings" / meeting_id / "transcript" / f"{transcript_id}.json"
        private_file(transcript, transcript_bytes)
        markdown_bytes = pack["markdown"].encode()
        markdown_id = hashlib.sha256(markdown_bytes).hexdigest()
        note = pack["note"]
        note["meeting"]["id"] = meeting_id
        note["transcript"] = f"../transcript/{transcript_id}.json"
        note["render"]["path"] = f"{markdown_id}.md"
        note_bytes = (json.dumps(note, ensure_ascii=False, indent=2) + "\n").encode()
        note_id = hashlib.sha256(note_bytes).hexdigest()
        notes = self.root / "meetings" / meeting_id / "notes"
        private_file(notes / f"{markdown_id}.md", markdown_bytes)
        private_file(notes / f"{note_id}.json", note_bytes)
        for directory in (
            self.root / "meetings",
            self.root / "meetings" / meeting_id,
            self.root / "meetings" / meeting_id / "transcript",
            notes,
        ):
            directory.chmod(0o700)
        return meeting_id, note_id, transcript_id

    def _start(
        self,
        *,
        executable: Path | None = None,
        isolated: bool = True,
        parent_environment: dict[str, str] | None = None,
    ) -> NoteBridgeProcess:
        return NoteBridgeProcess(
            self.root,
            self.manifest,
            executable=executable or self.runtime,
            bridge=self.bridge,
            isolated=isolated,
            parent_environment=parent_environment,
        )

    def _arguments(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "note_id": self.note_id,
            "transcript_id": self.transcript_id,
        }

    def _command(self, arguments: dict | None = None) -> tuple[str, bytes]:
        request_id = str(uuid.uuid4())
        command = {
            "schema": "note-bridge-command/1",
            "request_id": request_id,
            "operation": f"note.{self.role}",
            "arguments": arguments or self._arguments(),
        }
        return request_id, json.dumps(command).encode() + b"\n"

    def _tree(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.root)): digest(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }

    def test_attested_runtime_bridge_and_validator_inspect_without_app_data_writes(self) -> None:
        before = self._tree()
        request_id, command = self._command()
        bridge = self._start()
        try:
            self.assertEqual(
                bridge.ready,
                {
                    "schema": "note-bridge-event/1",
                    "event": "ready",
                    "protocol": 1,
                    "role": "inspect",
                    "manifest_sha256": digest(self.manifest),
                    "operations": ["note.inspect"],
                },
            )
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual(returncode, 0)
        self.assertEqual(error, b"")
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(result["artifact_digests"]["note"], self.note_id)
        self.assertEqual(result["artifact_digests"]["transcript"], self.transcript_id)
        self.assertEqual(self._tree(), before)
        self.assertFalse(list(self.root.rglob("operations")))
        self.assertFalse(list(self.root.rglob("children")))

    def test_unattested_interpreter_never_reaches_ready(self) -> None:
        bridge = self._start(executable=Path(sys.executable))
        try:
            self.assertIsNone(bridge.ready)
        finally:
            bridge.close()
        self.assertEqual(bridge._process.returncode, 2)

    def test_unisolated_launcher_never_reaches_ready(self) -> None:
        bridge = self._start(isolated=False)
        try:
            self.assertIsNone(bridge.ready)
        finally:
            bridge.close()
        self.assertEqual(bridge._process.returncode, 2)

    def test_parent_pythonpath_sitecustomize_is_scrubbed_before_startup(self) -> None:
        hostile = self.base / "hostile-startup"
        hostile.mkdir(mode=0o700)
        marker = self.base / "sitecustomize-executed"
        private_file(
            hostile / "sitecustomize.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n".encode(),
        )
        request_id, command = self._command()
        bridge = self._start(parent_environment={"PYTHONPATH": str(hostile)})
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["outcome"], "succeeded")
        self.assertFalse(marker.exists())

    def test_resource_sibling_urllib_cannot_shadow_runtime_standard_library(self) -> None:
        marker = self.base / "urllib-shadow-executed"
        private_file(
            self.resources / "urllib" / "__init__.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n".encode(),
        )
        request_id, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["outcome"], "succeeded")
        self.assertFalse(marker.exists())

    def test_intermediate_resource_symlink_never_reaches_ready(self) -> None:
        document = self._manifest_document()
        real = self.resources / "real"
        real.mkdir(mode=0o700)
        moved = real / self.validator.name
        self.validator.rename(moved)
        (self.resources / "linked").symlink_to(real, target_is_directory=True)
        document["validator"] = {
            "relative_path": f"linked/{moved.name}",
            "sha256": digest(moved),
        }
        self._write_manifest(document)
        bridge = self._start()
        try:
            self.assertIsNone(bridge.ready)
        finally:
            bridge.close()
        self.assertEqual(bridge._process.returncode, 2)

    def test_json_array_artifact_returns_closed_invalid_refusal_without_traceback(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.write_bytes(b"[]")
        request_id, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual(returncode, 0)
        self.assertEqual(error, b"")
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["failure"], {"code": "artifact-invalid", "recoverable": False})

    def test_missing_artifact_keeps_its_frozen_refusal_code(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.unlink()
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["failure"], {"code": "artifact-missing", "recoverable": True})

    def test_changed_artifact_keeps_its_frozen_refusal_code(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.write_bytes(note.read_bytes() + b" ")
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["failure"], {"code": "artifact-changed", "recoverable": False})

    def test_intermediate_artifact_symlink_returns_closed_invalid_refusal(self) -> None:
        real_meetings = self.base / "real-meetings"
        (self.root / "meetings").rename(real_meetings)
        (self.root / "meetings").symlink_to(real_meetings, target_is_directory=True)
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["failure"], {"code": "artifact-invalid", "recoverable": False})

    def test_retained_snapshot_refuses_same_bytes_rename_race(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        original = note.read_bytes()

        def replace_after_open() -> None:
            note.rename(note.with_suffix(".old"))
            private_file(note, original)

        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaises(ArtifactFailure) as failure:
                inspect_snapshot(root_fd, self._arguments(), after_open=replace_after_open)
        finally:
            os.close(root_fd)
        self.assertEqual(
            (failure.exception.code, failure.exception.recoverable),
            (
                "artifact-changed",
                False,
            ),
        )

    def test_retained_snapshot_refuses_same_inode_same_size_mutation(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        original = note.read_bytes()
        replacement = bytearray(original)
        replacement[0] = ord("[") if replacement[0] != ord("[") else ord("{")
        original_identity = note.stat()

        def overwrite_after_open() -> None:
            with note.open("r+b") as handle:
                handle.write(replacement)
                handle.flush()
                os.fsync(handle.fileno())
            current_identity = note.stat()
            self.assertEqual(current_identity.st_ino, original_identity.st_ino)
            self.assertEqual(current_identity.st_size, original_identity.st_size)

        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaises(ArtifactFailure) as failure:
                inspect_snapshot(root_fd, self._arguments(), after_open=overwrite_after_open)
        finally:
            os.close(root_fd)
        self.assertEqual(
            (failure.exception.code, failure.exception.recoverable),
            ("artifact-changed", False),
        )

    def test_identity_drift_during_artifact_refusal_emits_no_result(self) -> None:
        self._replace_validator(
            "\n"
            "def inspect(*args, **kwargs):\n"
            "    from pathlib import Path\n"
            f"    target = Path({str(self.bridge)!r})\n"
            "    with target.open('r+b') as handle:\n"
            "        first = handle.read(1)\n"
            "        handle.seek(0)\n"
            "        handle.write(b'#' if first != b'#' else b'!')\n"
            "        handle.flush()\n"
            "    raise ArtifactFailure('artifact-invalid', False)\n"
        )
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertIsNone(result)
        self.assertEqual((returncode, error), (2, b""))

    def test_internal_validator_failure_emits_no_artifact_result(self) -> None:
        self._replace_validator(
            "\ndef inspect(*args, **kwargs):\n    raise RuntimeError('injected internal failure')\n"
        )
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertIsNone(result)
        self.assertEqual((returncode, error), (2, b""))

    def test_temporary_storage_failure_emits_no_artifact_result(self) -> None:
        self._replace_validator(
            "\n"
            "class _UnavailableTemporaryDirectory:\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        pass\n"
            "    def __enter__(self):\n"
            "        raise OSError('injected temporary storage failure')\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "tempfile.TemporaryDirectory = _UnavailableTemporaryDirectory\n"
        )
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertIsNone(result)
        self.assertEqual((returncode, error), (2, b""))

    def test_invalid_arguments_return_only_invalid_request(self) -> None:
        invalid = self._arguments()
        invalid["note_id"] = 7
        request_id, command = self._command(invalid)
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["failure"], {"code": "invalid-request", "recoverable": False})

    def test_inspect_uses_the_shared_opaque_meeting_id_predicate(self) -> None:
        accepted = self._arguments()
        accepted["meeting_id"] = "meeting-a"
        request_id, command = self._command(accepted)
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(
            result["failure"], {"code": "artifact-missing", "recoverable": True}
        )
        for meeting_id in ("meeting/a", ".", "a" * 129):
            arguments = self._arguments()
            arguments["meeting_id"] = meeting_id
            request_id, command = self._command(arguments)
            bridge = self._start()
            try:
                result, returncode, error = bridge.send(command)
            finally:
                bridge.close()
            self.assertEqual((returncode, error), (0, b""))
            self.assertEqual(result["request_id"], request_id)
            self.assertEqual(
                result["failure"], {"code": "invalid-request", "recoverable": False}
            )

    def test_duplicate_keys_and_second_frames_are_protocol_failures(self) -> None:
        request_id = str(uuid.uuid4())
        duplicate = (
            '{"schema":"note-bridge-command/1","request_id":"'
            + request_id
            + '","operation":"note.inspect","arguments":'
            + '{"meeting_id":"'
            + self.meeting_id
            + '","note_id":"'
            + self.note_id
            + '","note_id":"'
            + self.note_id
            + '","transcript_id":"'
            + self.transcript_id
            + '"}}\n'
        ).encode()
        for frame in (duplicate, self._command()[1] + self._command()[1]):
            bridge = self._start()
            try:
                result, returncode, error = bridge.send(frame)
            finally:
                bridge.close()
            self.assertIsNone(result)
            self.assertEqual(returncode, 2)
            self.assertEqual(error, b"")


class NoteProjectBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._harness = NoteBridgeHarnessTests()
        self._harness.setUp()
        self._harness.role = "project"
        self._harness._write_manifest()

    def tearDown(self) -> None:
        self._harness.tearDown()

    def __getattr__(self, name):
        harness = self.__dict__.get("_harness")
        if harness is None:
            raise AttributeError(name)
        return getattr(harness, name)

    def _fixture(self) -> dict:
        return json.loads(
            (REPO / "tests/fixtures/note-projection-v1.fixture").read_text(encoding="utf-8")
        )

    def test_project_ready_and_projection_are_read_only_and_use_no_temporary_copy(self) -> None:
        self._replace_validator(
            "\n"
            "class _UnavailableTemporaryDirectory:\n"
            "    def __init__(self, *args, **kwargs): pass\n"
            "    def __enter__(self): raise OSError('temporary storage is unavailable')\n"
            "    def __exit__(self, *args): return False\n"
            "tempfile.TemporaryDirectory = _UnavailableTemporaryDirectory\n"
        )
        before = self._tree()
        request_id, command = self._command()
        bridge = self._start()
        try:
            self.assertEqual(
                bridge.ready,
                {
                    "schema": "note-bridge-event/1",
                    "event": "ready",
                    "protocol": 1,
                    "role": "project",
                    "manifest_sha256": digest(self.manifest),
                    "operations": ["note.project"],
                },
            )
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(result["projection"]["note_json_sha256"], self.note_id)
        self.assertEqual(self._tree(), before)

    def test_shared_fixture_locks_project_command_strictness_and_result_shape(self) -> None:
        fixture = self._fixture()
        valid = fixture["valid_commands"][0]
        request_id, arguments = _parse_command(valid["raw_frame"].encode(), "project")
        self.assertEqual(request_id, "11111111-1111-4111-8111-111111111111")
        self.assertEqual(arguments["meeting_id"], "meeting-a")
        for invalid in fixture["invalid_command_frames"]:
            expected = invalid["expected"]
            failure = BridgeRefused if expected == "protocol-failure" else InvalidArguments
            with self.subTest(invalid["name"]), self.assertRaises(failure):
                _parse_command(invalid["raw_frame"].encode(), "project")
        for expected in fixture["valid_results"] + fixture["refusal_results"]:
            result = expected["result"]
            self.assertEqual(
                list(result),
                ["schema", "request_id", "operation", "outcome", "projection", "failure"],
            )
            if result["outcome"] == "succeeded":
                projection = result["projection"]
                self.assertEqual(
                    list(projection),
                    [
                        "schema",
                        "note_json_sha256",
                        "note_markdown_sha256",
                        "transcript_sha256",
                        "claims",
                    ],
                )
                for ordinal, claim in enumerate(projection["claims"]):
                    self.assertEqual(claim["claim_ordinal"], ordinal)
                    self.assertEqual(
                        list(claim),
                        ["claim_ordinal", "claim_sha256", "claim_type", "evidence_state", "claim", "locators"],
                    )
                    self.assertEqual(claim["evidence_state"], "located")
                    self.assertTrue(1 <= len(claim["locators"]) <= 3)
                    self.assertEqual(
                        claim["locators"],
                        sorted(
                            claim["locators"],
                            key=lambda locator: (
                                locator["turn"], locator["start"], locator["end"], locator["text_sha256"]
                            ),
                        ),
                    )
            else:
                self.assertIsNone(result["projection"])
                self.assertEqual(list(result["failure"]), ["code", "recoverable"])

    def test_shared_fixture_unicode_scalar_locator_is_not_a_utf8_byte_offset(self) -> None:
        fixture = self._fixture()
        claim = fixture["valid_results"][1]["result"]["projection"]["claims"][4]
        locator = claim["locators"][1]
        turn = fixture["transcript_turns"][locator["turn"]]
        self.assertEqual(turn[locator["start"] : locator["end"]], "é🙂")
        self.assertEqual(locator["end"], 3)
        self.assertNotEqual(len("aé🙂".encode("utf-8")), locator["end"])

    def _assert_project_failure(self, code: str, recoverable: bool) -> None:
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["failure"], {"code": code, "recoverable": recoverable})

    def test_project_maps_missing_artifacts_to_the_closed_refusal(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.unlink()
        self._assert_project_failure("artifact-missing", True)

    def test_project_maps_changed_artifacts_to_the_closed_refusal(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.write_bytes(note.read_bytes() + b" ")
        self._assert_project_failure("artifact-changed", False)

    def test_project_maps_invalid_artifacts_to_the_closed_refusal(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.write_bytes(b"[]")
        self._assert_project_failure("artifact-invalid", False)

    def test_project_rechecks_descriptor_identity_after_derivation(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        original = note.read_bytes()

        def replace_after_open() -> None:
            note.rename(note.with_suffix(".old"))
            private_file(note, original)

        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaises(ArtifactFailure) as failure:
                project_snapshot(root_fd, self._arguments(), after_open=replace_after_open)
        finally:
            os.close(root_fd)
        self.assertEqual((failure.exception.code, failure.exception.recoverable), ("artifact-changed", False))

    def _replace_project_with_capacity_projection(self, count: int) -> None:
        self._replace_validator(
            "\n"
            "def project(root_fd, arguments):\n"
            "    claim_texts = [f'claim-{ordinal:06d}' for ordinal in range(" + str(count) + ")]\n"
            "    claims = [{\n"
            "        'claim_ordinal': ordinal,\n"
            "        'claim_sha256': hashlib.sha256(claim.encode('utf-8')).hexdigest(),\n"
            "        'claim_type': 'action',\n"
            "        'evidence_state': 'located',\n"
            "        'claim': claim,\n"
            "        'locators': [{'turn': 0, 'start': 0, 'end': 5, 'text_sha256': '8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8'}],\n"
            "    } for ordinal, claim in enumerate(claim_texts)]\n"
            "    return {'schema': 'note-claim-projection/1', 'note_json_sha256': arguments['note_id'], 'note_markdown_sha256': 'b' * 64, 'transcript_sha256': arguments['transcript_id'], 'claims': claims}\n"
        )

    def test_shared_fixture_capacity_is_217_or_refusal_at_218_without_truncation(self) -> None:
        fixture = self._fixture()["capacity_case"]
        self._replace_project_with_capacity_projection(fixture["last_fitting_claim_count"])
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(len(result["projection"]["claims"]), fixture["last_fitting_claim_count"])
        self.assertEqual(
            len(json.dumps(result, separators=(",", ":")).encode() + b"\n"),
            fixture["last_fitting_frame_bytes"],
        )
        self._replace_project_with_capacity_projection(fixture["claim_count"])
        _, command = self._command()
        bridge = self._start()
        try:
            result, returncode, error = bridge.send(command)
        finally:
            bridge.close()
        self.assertEqual((returncode, error), (0, b""))
        self.assertEqual(result["failure"], {
            "code": fixture["expected_result"],
            "recoverable": False,
        })
        self.assertIsNone(result["projection"])


if __name__ == "__main__":
    unittest.main()
