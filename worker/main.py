#!/usr/bin/env python3
"""Protocol-only application worker; no research CLI options are accepted."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import sys
import uuid
from pathlib import Path

from worker.adapters import AdapterRefused, dispatch
from worker.storage import StorageRefused, require_private_root

MAX_FRAME_BYTES = 64 * 1024
OPERATIONS = frozenset(
    {
        "profile.inspect",
        "profile.adopt",
        "capture.start",
        "capture.stop",
        "capture.inspect",
        "transcript.create",
        "note.create",
        "note.inspect",
    }
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit(value: dict) -> None:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_FRAME_BYTES:
        raise RuntimeError("outbound protocol frame exceeds limit")
    sys.stdout.write(encoded + "\n")
    sys.stdout.flush()


def load_manifest(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "admission",
        "runtime",
        "worker",
        "tap",
        "encoder",
        "models",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("runtime manifest has the wrong shape")
    if document["schema"] != "app-runtime/1":
        raise ValueError("runtime manifest schema is not current")
    if document["admission"] not in {"boundary-test", "product"}:
        raise ValueError("runtime manifest admission is not current")
    for name in ("runtime", "worker", "tap", "encoder"):
        entry = document[name]
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError(f"runtime manifest {name} entry is malformed")
        unresolved = path.parent / entry["path"]
        if unresolved.is_symlink():
            raise ValueError(f"runtime manifest {name} resource may not be a symlink")
        resource = unresolved.resolve(strict=True)
        if path.parent.resolve() not in resource.parents and resource != path.parent.resolve():
            raise ValueError("runtime manifest resource escapes its directory")
        if not resource.is_file() or file_sha256(resource) != entry["sha256"]:
            raise ValueError(f"runtime manifest {name} digest mismatch")
    if not isinstance(document["models"], list):
        raise ValueError("runtime manifest models must be a list")
    seen_models = set()
    for model in document["models"]:
        if not isinstance(model, dict) or set(model) != {"id", "path", "sha256"}:
            raise ValueError("runtime manifest model entry is malformed")
        if (
            not isinstance(model["id"], str)
            or not model["id"]
            or model["id"] in seen_models
        ):
            raise ValueError("runtime manifest model ID is invalid or duplicated")
        seen_models.add(model["id"])
        unresolved = path.parent / model["path"]
        if unresolved.is_symlink():
            raise ValueError("runtime manifest model may not be a symlink")
        resource = unresolved.resolve(strict=True)
        if path.parent.resolve() not in resource.parents and resource != path.parent.resolve():
            raise ValueError("runtime manifest model escapes its directory")
        if not resource.is_file() or file_sha256(resource) != model["sha256"]:
            raise ValueError("runtime manifest model digest mismatch")
    return document


def parse_command(frame: bytes) -> tuple[str, str, object]:
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError("protocol frame exceeds limit")
    command = json.loads(frame)
    if not isinstance(command, dict) or set(command) != {
        "schema",
        "request_id",
        "operation",
        "arguments",
    }:
        raise ValueError("command has the wrong shape")
    if command["schema"] != "worker-command/1" or command["operation"] not in OPERATIONS:
        raise ValueError("command schema or operation is unsupported")
    uuid.UUID(command["request_id"])
    return command["request_id"], command["operation"], command["arguments"]


def parent_is_alive(parent_fd: int) -> bool:
    ready, _, _ = select.select([parent_fd], [], [], 0)
    if not ready:
        return True
    return os.read(parent_fd, 1) != b""


def run(root: Path, manifest_path: Path, parent_fd: int) -> int:
    root = require_private_root(root)
    manifest = load_manifest(manifest_path)
    emit(
        {
            "schema": "worker-event/1",
            "event": "worker.ready",
            "protocol": 1,
            "build": manifest["worker"]["sha256"],
            "runtime": {"kind": "bundled", "digest": manifest["runtime"]["sha256"]},
            "tap": {"build": manifest["tap"]["sha256"], "available": True},
            "models": [
                {
                    "id": model["id"],
                    "digest": model["sha256"],
                    "available": True,
                }
                for model in manifest["models"]
            ],
            "operations": sorted(OPERATIONS),
        }
    )
    while parent_is_alive(parent_fd):
        ready, _, _ = select.select([sys.stdin.buffer, parent_fd], [], [])
        if parent_fd in ready and not parent_is_alive(parent_fd):
            return 0
        if sys.stdin.buffer not in ready:
            continue
        frame = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 2)
        if not frame:
            return 0
        try:
            request_id, operation, arguments = parse_command(frame)
            digests = dispatch(
                root,
                operation,
                arguments,
                encoder_digest=manifest["encoder"]["sha256"],
            )
            emit(
                {
                    "schema": "worker-result/1",
                    "request_id": request_id,
                    "ok": True,
                    "code": None,
                    "recoverable": None,
                    "artifact_digests": digests,
                }
            )
        except (AdapterRefused, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            known_request = None
            try:
                candidate = json.loads(frame)
                uuid.UUID(candidate.get("request_id", ""))
                known_request = candidate["request_id"]
            except Exception:
                return 2
            emit(
                {
                    "schema": "worker-result/1",
                    "request_id": known_request,
                    "ok": False,
                    "code": "protocol_failure",
                    "recoverable": False,
                    "artifact_digests": {},
                }
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--app-data-root", required=True, type=Path)
    parser.add_argument("--runtime-manifest", required=True, type=Path)
    parser.add_argument("--parent-liveness-fd", type=int)
    arguments = parser.parse_args()
    parent_fd = arguments.parent_liveness_fd
    if parent_fd is None:
        try:
            parent_fd = int(os.environ["LMN_PARENT_LIVENESS_FD"])
        except (KeyError, ValueError):
            return 2
    try:
        return run(
            arguments.app_data_root,
            arguments.runtime_manifest,
            parent_fd,
        )
    except (OSError, ValueError, StorageRefused, json.JSONDecodeError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
