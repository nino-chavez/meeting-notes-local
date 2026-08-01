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
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def private_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NoteBridgeProcess:
    def __init__(self, root: Path, manifest: Path):
        read_fd, self._write_fd = os.pipe()
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "worker.note_bridge",
                "--temporary-private-root",
                str(root),
                "--note-runtime-manifest",
                str(manifest),
                "--parent-liveness-fd",
                str(read_fd),
            ],
            cwd=REPO,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(read_fd,),
        )
        os.close(read_fd)
        ready = self._process.stdout.readline()
        self.ready = json.loads(ready) if ready else None

    def inspect(self, arguments: dict) -> dict:
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        command = {
            "schema": "note-bridge-command/1",
            "request_id": str(uuid.uuid4()),
            "operation": "note.inspect",
            "arguments": arguments,
        }
        self._process.stdin.write(json.dumps(command).encode("utf-8") + b"\n")
        self._process.stdin.close()
        result = self._process.stdout.readline()
        self._process.wait(timeout=3)
        os.close(self._write_fd)
        self._write_fd = -1
        if self._process.returncode != 0:
            error = self._process.stderr.read().decode("utf-8", "replace")
            raise AssertionError(error)
        parsed = json.loads(result)
        if parsed["request_id"] != command["request_id"]:
            raise AssertionError("bridge result request ID mismatch")
        return parsed

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
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "app"
        self.root.mkdir(mode=0o700)
        self.resources = self.base / "resources"
        self.resources.mkdir(mode=0o700)
        for source, target in (
            (REPO / "worker/note_bridge.py", self.resources / "bridge.py"),
            (REPO / "worker/adapters.py", self.resources / "validator.py"),
        ):
            shutil.copyfile(source, target)
            target.chmod(0o600)
        private_file(self.resources / "runtime.py", b"harness runtime only\n")
        self.manifest = self.resources / "note-runtime.json"
        manifest = {
            "schema": "note-runtime/1",
            "role": "inspect",
            "runtime": {
                "relative_path": "runtime.py",
                "sha256": digest(self.resources / "runtime.py"),
            },
            "bridge": {
                "relative_path": "bridge.py",
                "sha256": digest(self.resources / "bridge.py"),
            },
            "validator": {
                "relative_path": "validator.py",
                "sha256": digest(self.resources / "validator.py"),
            },
            "generator": None,
            "models": [],
        }
        private_file(
            self.manifest,
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        self.meeting_id, self.note_id, self.transcript_id = self._write_note_pair()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_note_pair(self) -> tuple[str, str, str]:
        meeting_id = str(uuid.uuid4())
        pack = json.loads(
            (REPO / "docs/prototype/fixtures/accepted-note2.fixture").read_text()
        )
        transcript_bytes = (json.dumps(pack["transcript"], indent=2) + "\n").encode()
        transcript_id = hashlib.sha256(transcript_bytes).hexdigest()
        transcript = (
            self.root / "meetings" / meeting_id / "transcript" / f"{transcript_id}.json"
        )
        private_file(transcript, transcript_bytes)
        markdown_bytes = pack["markdown"].encode("utf-8")
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
        return meeting_id, note_id, transcript_id

    def _tree(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.root)): digest(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }

    def _arguments(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "note_id": self.note_id,
            "transcript_id": self.transcript_id,
        }

    def _markdown_id(self) -> str:
        note_path = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        return json.loads(note_path.read_text())["render"]["path"].removesuffix(".md")

    def test_inspection_succeeds_without_writing_app_data_or_receipts(self) -> None:
        before = self._tree()
        bridge = NoteBridgeProcess(self.root, self.manifest)
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
            result = bridge.inspect(self._arguments())
        finally:
            bridge.close()
        self.assertEqual(result["outcome"], "succeeded")
        self.assertIsNone(result["failure"])
        self.assertEqual(
            result["artifact_digests"],
            {
                "note": self.note_id,
                "note-markdown": self._markdown_id(),
                "transcript": self.transcript_id,
            },
        )
        self.assertEqual(self._tree(), before)
        self.assertFalse(list(self.root.rglob("operations")))
        self.assertFalse(list(self.root.rglob("children")))

    def test_changed_artifact_is_refused_without_harness_mutation(self) -> None:
        note = self.root / "meetings" / self.meeting_id / "notes" / f"{self.note_id}.json"
        note.chmod(0o600)
        note.write_bytes(note.read_bytes() + b" ")
        before = self._tree()
        bridge = NoteBridgeProcess(self.root, self.manifest)
        try:
            result = bridge.inspect(self._arguments())
        finally:
            bridge.close()
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(
            result["failure"], {"code": "artifact-changed", "recoverable": False}
        )
        self.assertEqual(result["artifact_digests"], {})
        self.assertEqual(self._tree(), before)


if __name__ == "__main__":
    unittest.main()
