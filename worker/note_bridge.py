#!/usr/bin/env python3
"""Private, one-shot, inspect-only note bridge for the repository test harness.

This is deliberately not part of the application worker or bundle.  It proves the
closed framing and artifact reinspection transport with a temporary private root;
it cannot create a note, generate a rejection, write an operation receipt, or
participate in the Rust note coordinator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import select
import stat
import sys
import threading
import uuid
from pathlib import Path

from worker.adapters import AdapterRefused, note_inspect
from worker.storage import StorageRefused, require_private_root


MAX_FRAME_BYTES = 64 * 1024
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._/-]+$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FIELDS = (
    "schema",
    "role",
    "runtime",
    "bridge",
    "validator",
    "generator",
    "models",
)


class BridgeRefused(ValueError):
    pass


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _exact_object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise BridgeRefused("manifest has duplicate fields")
        result[key] = value
    return result


def _safe_component(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or not _SAFE_IDENTIFIER.fullmatch(value):
        raise BridgeRefused(f"{label} is not ASCII-safe")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BridgeRefused(f"{label} has an unsafe path component")
    return value


def _safe_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_DIGEST.fullmatch(value):
        raise BridgeRefused(f"{label} is not a lowercase SHA-256 digest")
    return value


def _resource(value: object, label: str) -> dict:
    if not isinstance(value, dict) or list(value) != ["relative_path", "sha256"]:
        raise BridgeRefused(f"{label} has the wrong shape")
    return {
        "relative_path": _safe_component(value["relative_path"], f"{label} path"),
        "sha256": _safe_digest(value["sha256"], f"{label} digest"),
    }


def _generator(value: object) -> None:
    if value is not None:
        raise BridgeRefused("inspect bridge may not carry a generator")


def _verify_resource(resource_root: Path, resource: dict, label: str) -> None:
    path = resource_root.joinpath(*resource["relative_path"].split("/"))
    try:
        relative = path.relative_to(resource_root)
    except ValueError as exc:
        raise BridgeRefused(f"{label} escapes the resource root") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise BridgeRefused(f"{label} has an unsafe resource path")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BridgeRefused(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid():
            raise BridgeRefused(f"{label} is not a bundle-owned regular file")
        hasher = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mode != after.st_mode
            or before.st_uid != after.st_uid
            or hasher.hexdigest() != resource["sha256"]
        ):
            raise BridgeRefused(f"{label} changed during verification")
    finally:
        os.close(descriptor)


def load_manifest(path: Path) -> tuple[dict, str]:
    if path.is_symlink():
        raise BridgeRefused("manifest may not be a symlink")
    raw = path.read_bytes()
    if b"\\" in raw:
        raise BridgeRefused("manifest may not use JSON escapes")
    try:
        document = json.loads(raw, object_pairs_hook=_exact_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeRefused("manifest is not valid JSON") from exc
    if not isinstance(document, dict) or list(document) != list(_MANIFEST_FIELDS):
        raise BridgeRefused("manifest fields or field order are not current")
    canonical = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    if raw != canonical:
        raise BridgeRefused("manifest bytes are not canonical")
    if document["schema"] != "note-runtime/1" or document["role"] != "inspect":
        raise BridgeRefused("inspect bridge manifest has the wrong role")
    for name in ("runtime", "bridge", "validator"):
        document[name] = _resource(document[name], name)
    _generator(document["generator"])
    if document["models"] != []:
        raise BridgeRefused("inspect bridge may not carry models")
    resource_root = path.parent.resolve(strict=True)
    if path.is_symlink() or not resource_root.is_dir():
        raise BridgeRefused("manifest resource root is unsafe")
    for name in ("runtime", "bridge", "validator"):
        _verify_resource(resource_root, document[name], name)
    return document, hashlib.sha256(raw).hexdigest()


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise BridgeRefused("request ID is invalid")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise BridgeRefused("request ID is invalid") from exc
    if str(parsed) != value:
        raise BridgeRefused("request ID must be canonical lowercase UUID")
    return value


def _command(value: object) -> tuple[str, dict]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "request_id",
        "operation",
        "arguments",
    }:
        raise BridgeRefused("command has the wrong shape")
    request_id = _canonical_uuid(value["request_id"])
    if value["schema"] != "note-bridge-command/1" or value["operation"] != "note.inspect":
        raise BridgeRefused("command is outside the inspect role")
    arguments = value["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != {
        "meeting_id",
        "note_id",
        "transcript_id",
    }:
        raise BridgeRefused("inspect arguments have the wrong shape")
    _canonical_uuid(arguments["meeting_id"])
    _safe_digest(arguments["note_id"], "note ID")
    _safe_digest(arguments["transcript_id"], "transcript ID")
    return request_id, arguments


def _emit(value: dict) -> None:
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) + 1 > MAX_FRAME_BYTES:
        raise BridgeRefused("bridge frame exceeds its limit")
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


def _failure(message: str) -> tuple[str, bool]:
    if "missing" in message:
        return "artifact-missing", True
    if "changed" in message:
        return "artifact-changed", False
    return "artifact-invalid", False


def _watch_parent(parent_fd: int) -> None:
    def exit_at_eof() -> None:
        while True:
            try:
                value = os.read(parent_fd, 1)
            except InterruptedError:
                continue
            except OSError:
                os._exit(2)
            if value == b"":
                os._exit(0)

    threading.Thread(target=exit_at_eof, daemon=True).start()


def run(root: Path, manifest_path: Path, parent_fd: int) -> int:
    root = require_private_root(root)
    manifest, manifest_sha256 = load_manifest(manifest_path)
    # The harness invokes this module directly, so bind the running bridge and
    # the imported canonical validator to the resource identities just checked.
    # This is still inspect-only: no generator or model is loaded here.
    if _digest(Path(__file__).resolve()) != manifest["bridge"]["sha256"]:
        raise BridgeRefused("running bridge differs from its verified resource")
    validator_source = Path(note_inspect.__code__.co_filename).resolve()
    if _digest(validator_source) != manifest["validator"]["sha256"]:
        raise BridgeRefused("running validator differs from its verified resource")
    _emit(
        {
            "schema": "note-bridge-event/1",
            "event": "ready",
            "protocol": 1,
            "role": "inspect",
            "manifest_sha256": manifest_sha256,
            "operations": ["note.inspect"],
        }
    )
    ready, _, _ = select.select([sys.stdin.buffer, parent_fd], [], [], 10)
    if parent_fd in ready and os.read(parent_fd, 1) == b"":
        return 0
    if sys.stdin.buffer not in ready:
        return 2
    frame = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 2)
    if not frame or len(frame) > MAX_FRAME_BYTES or not frame.endswith(b"\n"):
        return 2
    try:
        command = json.loads(frame)
        request_id, arguments = _command(command)
    except (BridgeRefused, UnicodeDecodeError, json.JSONDecodeError):
        return 2
    try:
        digests = note_inspect(root, arguments)
        _emit(
            {
                "schema": "note-bridge-result/1",
                "request_id": request_id,
                "operation": "note.inspect",
                "outcome": "succeeded",
                "artifact_digests": digests,
                "failure": None,
            }
        )
        return 0
    except (AdapterRefused, StorageRefused, OSError, ValueError) as exc:
        code, recoverable = _failure(str(exc))
        _emit(
            {
                "schema": "note-bridge-result/1",
                "request_id": request_id,
                "operation": "note.inspect",
                "outcome": "refused",
                "artifact_digests": {},
                "failure": {"code": code, "recoverable": recoverable},
            }
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--temporary-private-root", type=Path, required=True)
    parser.add_argument("--note-runtime-manifest", type=Path, required=True)
    parser.add_argument("--parent-liveness-fd", type=int, required=True)
    arguments = parser.parse_args()
    _watch_parent(arguments.parent_liveness_fd)
    try:
        return run(
            arguments.temporary_private_root,
            arguments.note_runtime_manifest,
            arguments.parent_liveness_fd,
        )
    except (BridgeRefused, StorageRefused, OSError, ValueError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
