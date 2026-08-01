#!/usr/bin/env python3
"""Private, one-shot, inspect-only note bridge for the repository test harness."""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.util
import io
import json
import os
import re
import select
import stat
import sys
import threading
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

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
_VALIDATOR_MODULES = {
    "note_validator": "note_validator.py",
    "summarize": "summarize.py",
    "transcript": "transcript.py",
    "capture_health": "capture_health.py",
}


class BridgeRefused(ValueError):
    pass


class InvalidArguments(ValueError):
    pass


@dataclass
class _DirectoryLink:
    parent_fd: int
    name: str
    child_fd: int
    identity: os.stat_result


@dataclass
class _RetainedFile:
    parent_fd: int
    name: str
    file_fd: int
    identity: os.stat_result
    digest: str
    bytes: bytes
    directories: list[_DirectoryLink]

    def close(self) -> None:
        os.close(self.file_fd)
        os.close(self.parent_fd)
        for link in reversed(self.directories):
            os.close(link.child_fd)
            os.close(link.parent_fd)


@dataclass
class _VerifiedRuntime:
    root_fd: int
    manifest: _RetainedFile
    resources: dict[str, _RetainedFile]

    def require_unchanged(self) -> None:
        _require_link(self.manifest)
        for resource in self.resources.values():
            _require_link(resource)
            current = hashlib.sha256(
                _read_retained(resource.file_fd, resource.identity)
            ).hexdigest()
            if current != resource.digest:
                raise BridgeRefused("verified resource bytes changed")

    def close(self) -> None:
        for resource in self.resources.values():
            resource.close()
        self.manifest.close()
        os.close(self.root_fd)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
        and left.st_size == right.st_size
        and left.st_nlink == right.st_nlink
    )


def _read_retained(descriptor: int, identity: os.stat_result) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    remaining = identity.st_size
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        if not chunk:
            raise BridgeRefused("verified resource changed while being read")
        chunks.append(chunk)
        remaining -= len(chunk)
    if not _same_identity(identity, os.fstat(descriptor)):
        raise BridgeRefused("verified resource changed while being read")
    return b"".join(chunks)


def _open_absolute_directory(path: Path, *, private: bool) -> int:
    if not path.is_absolute():
        raise BridgeRefused("approved root must be absolute")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        identity = os.fstat(descriptor)
        if not stat.S_ISDIR(identity.st_mode) or identity.st_uid != os.geteuid():
            raise BridgeRefused("approved root is not an owned directory")
        if private and stat.S_IMODE(identity.st_mode) != 0o700:
            raise BridgeRefused("temporary root is not owner-private")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_beneath(root_fd: int, relative_path: str, expected_digest: str) -> _RetainedFile:
    parts = relative_path.split("/")
    parent = os.dup(root_fd)
    directories: list[_DirectoryLink] = []
    try:
        for component in parts[:-1]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            identity = os.fstat(child)
            if not stat.S_ISDIR(identity.st_mode) or identity.st_uid != os.geteuid():
                os.close(child)
                raise BridgeRefused("resource path has an unsafe directory")
            directories.append(_DirectoryLink(parent, component, child, identity))
            parent = os.dup(child)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode) or identity.st_uid != os.geteuid():
            os.close(descriptor)
            raise BridgeRefused("resource is not a bundle-owned regular file")
        data = _read_retained(descriptor, identity)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_digest:
            os.close(descriptor)
            raise BridgeRefused("resource digest differs from the manifest")
        return _RetainedFile(
            parent,
            parts[-1],
            descriptor,
            identity,
            digest,
            data,
            directories,
        )
    except Exception:
        os.close(parent)
        for link in reversed(directories):
            os.close(link.child_fd)
            os.close(link.parent_fd)
        raise


def _require_link(resource: _RetainedFile) -> None:
    for link in resource.directories:
        try:
            current = os.stat(link.name, dir_fd=link.parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise BridgeRefused("verified resource directory changed") from exc
        if not _same_identity(link.identity, current):
            raise BridgeRefused("verified resource directory changed")
    try:
        current = os.stat(resource.name, dir_fd=resource.parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise BridgeRefused("verified resource pathname changed") from exc
    if not _same_identity(resource.identity, current):
        raise BridgeRefused("verified resource pathname changed")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise BridgeRefused("JSON object contains a duplicate field")
        result[key] = value
    return result


def _safe_component(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or not _SAFE_IDENTIFIER.fullmatch(value):
        raise BridgeRefused(f"{label} is not ASCII-safe")
    if any(part in {"", ".", ".."} for part in value.split("/")):
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


def verify_runtime(manifest_path: Path) -> _VerifiedRuntime:
    resource_root = manifest_path.parent
    root_fd = _open_absolute_directory(resource_root, private=False)
    manifest: _RetainedFile | None = None
    manifest_parent: int | None = None
    manifest_fd: int | None = None
    resources: dict[str, _RetainedFile] = {}
    try:
        name = manifest_path.name
        if not name or "/" in name or name in {".", ".."}:
            raise BridgeRefused("manifest name is unsafe")
        manifest_parent = os.dup(root_fd)
        manifest_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=manifest_parent)
        identity = os.fstat(manifest_fd)
        if not stat.S_ISREG(identity.st_mode) or identity.st_uid != os.geteuid():
            raise BridgeRefused("manifest is not a bundle-owned regular file")
        raw = _read_retained(manifest_fd, identity)
        manifest = _RetainedFile(
            manifest_parent,
            name,
            manifest_fd,
            identity,
            hashlib.sha256(raw).hexdigest(),
            raw,
            [],
        )
        manifest_parent = None
        manifest_fd = None
        if b"\\" in raw:
            raise BridgeRefused("manifest may not use JSON escapes")
        document = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(document, dict) or list(document) != list(_MANIFEST_FIELDS):
            raise BridgeRefused("manifest fields or field order are not current")
        if json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8") != raw:
            raise BridgeRefused("manifest bytes are not canonical")
        if document["schema"] != "note-runtime/1" or document["role"] != "inspect":
            raise BridgeRefused("inspect bridge manifest has the wrong role")
        for field in ("runtime", "bridge", "validator"):
            document[field] = _resource(document[field], field)
        if document["generator"] is not None or document["models"] != []:
            raise BridgeRefused("inspect bridge may not carry a generator or models")
        for field in ("runtime", "bridge", "validator"):
            resource = document[field]
            resources[field] = _open_beneath(root_fd, resource["relative_path"], resource["sha256"])
        verified = _VerifiedRuntime(root_fd, manifest, resources)
        _require_runtime_identity(verified)
        verified.require_unchanged()
        return verified
    except Exception:
        for resource in resources.values():
            resource.close()
        if manifest is not None:
            manifest.close()
        else:
            if manifest_fd is not None:
                os.close(manifest_fd)
            if manifest_parent is not None:
                os.close(manifest_parent)
        os.close(root_fd)
        raise


def _require_runtime_identity(runtime: _VerifiedRuntime) -> None:
    executable = os.stat(sys.executable, follow_symlinks=False)
    if not _same_identity(runtime.resources["runtime"].identity, executable):
        raise BridgeRefused("running interpreter differs from the verified runtime")
    bridge = os.stat(__file__, follow_symlinks=False)
    if not _same_identity(runtime.resources["bridge"].identity, bridge):
        raise BridgeRefused("running bridge differs from the verified bridge")


class _BundleLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, sources: dict[str, bytes]):
        self.sources = sources

    def find_spec(self, fullname: str, path=None, target=None):
        if fullname in self.sources:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        source = self.sources[module.__name__]
        module.__file__ = f"/verified/{module.__name__}.py"
        code = compile(source, f"<verified-validator:{module.__name__}>", "exec")
        exec(code, module.__dict__)


def load_validator(runtime: _VerifiedRuntime):
    bundle = runtime.resources["validator"].bytes
    try:
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(_VALIDATOR_MODULES.values()):
                raise BridgeRefused("validator bundle has the wrong module inventory")
            sources = {
                module: archive.read(filename) for module, filename in _VALIDATOR_MODULES.items()
            }
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise BridgeRefused("validator bundle is malformed") from exc
    finder = _BundleLoader(sources)
    sys.meta_path.insert(0, finder)
    try:
        for name in _VALIDATOR_MODULES:
            sys.modules.pop(name, None)
        for name in ("capture_health", "transcript", "summarize"):
            importlib.import_module(name)
        module = importlib.import_module("note_validator")
    finally:
        sys.meta_path.remove(finder)
    if getattr(module, "__loader__", None) is not finder:
        raise BridgeRefused("validator did not load from the verified bundle")
    if any(
        getattr(sys.modules[name], "__loader__", None) is not finder for name in _VALIDATOR_MODULES
    ):
        raise BridgeRefused("validator helper did not load from the verified bundle")
    return module


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidArguments("identifier is not a UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise InvalidArguments("identifier is not a UUID") from exc
    if str(parsed) != value:
        raise InvalidArguments("identifier is not a canonical lowercase UUID")
    return value


def _parse_command(frame: bytes) -> tuple[str, dict]:
    value = json.loads(frame, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "request_id",
        "operation",
        "arguments",
    }:
        raise BridgeRefused("command has the wrong outer shape")
    try:
        request_id = _canonical_uuid(value["request_id"])
    except InvalidArguments as exc:
        raise BridgeRefused("command request ID is invalid") from exc
    if value["schema"] != "note-bridge-command/1" or value["operation"] != "note.inspect":
        raise BridgeRefused("command is outside the inspect role")
    arguments = value["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != {
        "meeting_id",
        "note_id",
        "transcript_id",
    }:
        raise InvalidArguments("inspect arguments have the wrong shape")
    _canonical_uuid(arguments["meeting_id"])
    try:
        _safe_digest(arguments["note_id"], "note ID")
        _safe_digest(arguments["transcript_id"], "transcript ID")
    except BridgeRefused as exc:
        raise InvalidArguments(str(exc)) from exc
    return request_id, arguments


def _read_frame(parent_fd: int) -> bytes:
    buffer = bytearray()
    while b"\n" not in buffer:
        ready, _, _ = select.select([sys.stdin.fileno(), parent_fd], [], [], 10)
        if parent_fd in ready and os.read(parent_fd, 1) == b"":
            raise BridgeRefused("parent liveness ended")
        if sys.stdin.fileno() not in ready:
            raise BridgeRefused("note command timed out")
        chunk = os.read(sys.stdin.fileno(), MAX_FRAME_BYTES + 2 - len(buffer))
        if not chunk:
            raise BridgeRefused("note command ended before a frame")
        buffer.extend(chunk)
        if len(buffer) > MAX_FRAME_BYTES:
            raise BridgeRefused("note command exceeds the frame limit")
    frame, extra = bytes(buffer).split(b"\n", 1)
    if extra:
        raise BridgeRefused("note bridge received a second input frame")
    return frame


def _emit(value: dict) -> None:
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) + 1 > MAX_FRAME_BYTES:
        raise BridgeRefused("bridge frame exceeds its limit")
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


def _refused(request_id: str, code: str, recoverable: bool) -> None:
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


def run(root_path: Path, manifest_path: Path, parent_fd: int) -> int:
    runtime = verify_runtime(manifest_path)
    root_fd = _open_absolute_directory(root_path, private=True)
    try:
        validator = load_validator(runtime)
        runtime.require_unchanged()
        _emit(
            {
                "schema": "note-bridge-event/1",
                "event": "ready",
                "protocol": 1,
                "role": "inspect",
                "manifest_sha256": runtime.manifest.digest,
                "operations": ["note.inspect"],
            }
        )
        frame = _read_frame(parent_fd)
        request_id: str | None = None
        try:
            parsed = json.loads(frame, object_pairs_hook=_reject_duplicate_keys)
            if isinstance(parsed, dict) and isinstance(parsed.get("request_id"), str):
                request_id = parsed["request_id"]
            request_id, arguments = _parse_command(frame)
        except InvalidArguments:
            if request_id is None:
                return 2
            try:
                request_id = _canonical_uuid(request_id)
            except InvalidArguments:
                return 2
            _refused(request_id, "invalid-request", False)
            return 0
        except (BridgeRefused, UnicodeDecodeError, json.JSONDecodeError):
            return 2
        runtime.require_unchanged()
        try:
            digests = validator.inspect(root_fd, arguments)
        except validator.ArtifactFailure as exc:
            if (exc.code, exc.recoverable) not in {
                ("artifact-invalid", False),
                ("artifact-missing", True),
                ("artifact-changed", False),
            }:
                return 2
            _refused(request_id, exc.code, exc.recoverable)
            return 0
        except Exception:
            _refused(request_id, "artifact-invalid", False)
            return 0
        runtime.require_unchanged()
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
    finally:
        os.close(root_fd)
        runtime.close()


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
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
