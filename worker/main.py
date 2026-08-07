#!/usr/bin/env python3
"""Protocol-only application worker; no research CLI options are accepted."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import select
import sys
import threading
import uuid
from pathlib import Path

from worker.adapters import AdapterRefused, dispatch
from worker.storage import StorageRefused, require_private_root

MAX_FRAME_BYTES = 64 * 1024
# sitting.derive joined the packaged alpha set on 2026-08-04 by the operator's
# guided-enrollment registration decision, following the same-day encoder
# admission verdict (spike/encoder-packaging/RESULTS.md): the shipped recorder
# needs the derivation the sitting evidence store re-verifies. On the default
# lane the adapter still refuses ("runtime has no admitted speaker encoder"),
# so widening the set opens nothing a placeholder-encoder build can misuse.
# transcript.restore joined with the same day's correction-surface (J4)
# registration: the restoration coordinator re-verifies every artifact the
# worker names before anything is published.
# The profile family joined on 2026-08-05 with the operator's profile-build
# decision: choices/build produce from stored evidence through the canonical
# save_profile boundary, and inspect/discard serve the Rust lifecycle's
# strict-loader bridge. profile.adopt stays boundary-lane only — the
# packaged publication path is Rust's enroll_profile_candidate, which
# publishes the re-verified bytes itself.
ALPHA_OPERATIONS = frozenset(
    {"capture.finalize", "capture.inspect", "transcript.create",
     "sitting.derive", "transcript.restore",
     "profile.choices", "profile.build", "profile.inspect", "profile.discard"}
)
# note.inspect stays boundary-lane only: no note generator is admitted.
BOUNDARY_OPERATIONS = ALPHA_OPERATIONS | frozenset(
    {"profile.adopt", "note.inspect"}
)


def operations_for(admission: str) -> frozenset[str]:
    if admission == "internal-alpha":
        return ALPHA_OPERATIONS
    if admission in {"boundary-test", "product"}:
        return BOUNDARY_OPERATIONS
    raise ValueError("runtime admission is not current")


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


def emit_progress(request_id: str, meeting_id: str, state: str) -> None:
    uuid.UUID(request_id)
    uuid.UUID(meeting_id)
    if state != "recording":
        raise ValueError("progress state is outside the closed protocol")
    emit(
        {
            "schema": "worker-event/2",
            "request_id": request_id,
            "event": "capture.state",
            "state": state,
            "meeting_id": meeting_id,
        }
    )


def load_manifest(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "admission",
        "runtime",
        "worker",
        "tap",
        "encoder",
        "permission_probe",
        "models",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("runtime manifest has the wrong shape")
    if document["schema"] != "app-runtime/1":
        raise ValueError("runtime manifest schema is not current")
    if document["admission"] not in {"boundary-test", "internal-alpha", "product"}:
        raise ValueError("runtime manifest admission is not current")
    for name in ("runtime", "worker", "tap", "encoder", "permission_probe"):
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


def transcript_model_dir(manifest_path: Path, manifest: dict) -> Path | None:
    if manifest["admission"] == "boundary-test":
        return None
    resources = {model["id"]: model for model in manifest["models"]}
    expected = {
        "whisper-large-v3-turbo-config",
        "whisper-large-v3-turbo-weights",
    }
    if not expected.issubset(resources):
        raise ValueError("runtime manifest lacks the fixed transcript model")
    parents = {
        (manifest_path.parent / resources[model_id]["path"]).resolve(strict=True).parent
        for model_id in expected
    }
    if len(parents) != 1:
        raise ValueError("fixed transcript model resources do not share one directory")
    return parents.pop()


def parse_command(
    frame: bytes, operations: frozenset[str]
) -> tuple[str, str, object]:
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
    if command["schema"] != "worker-command/2" or command["operation"] not in operations:
        raise ValueError("command schema or operation is unsupported")
    uuid.UUID(command["request_id"])
    return command["request_id"], command["operation"], command["arguments"]


def parent_is_alive(parent_fd: int) -> bool:
    ready, _, _ = select.select([parent_fd], [], [], 0)
    if not ready:
        return True
    return os.read(parent_fd, 1) != b""


def start_parent_liveness_watchdog(parent_fd: int) -> threading.Thread:
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

    thread = threading.Thread(
        target=exit_at_eof,
        name="parent-liveness-watchdog",
        daemon=True,
    )
    thread.start()
    return thread


def dispatch_without_protocol_output(
    root: Path,
    operation: str,
    arguments: object,
    *,
    encoder_digest: str,
    admission: str,
    model_dir: Path | None,
    encoder_path: Path | None = None,
) -> dict:
    # The worker owns stdout as a newline-delimited JSON protocol. Research
    # adapters and model libraries may print progress on data-dependent paths;
    # letting one such line escape makes a valid operation look like a malformed
    # protocol frame. Discard operation stdout at the boundary. emit() runs
    # outside this context and remains the only writer to the protocol stream.
    with open(os.devnull, "w", encoding="utf-8") as discarded:
        with contextlib.redirect_stdout(discarded):
            return dispatch(
                root,
                operation,
                arguments,
                encoder_digest=encoder_digest,
                admission=admission,
                model_dir=model_dir,
                encoder_path=encoder_path,
            )


def run(root: Path, manifest_path: Path, parent_fd: int) -> int:
    root = require_private_root(root)
    manifest = load_manifest(manifest_path)
    model_dir = transcript_model_dir(manifest_path, manifest)
    operations = operations_for(manifest["admission"])
    emit(
        {
            "schema": "worker-event/2",
            "event": "worker.ready",
            "protocol": 2,
            "admission": manifest["admission"],
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
            "operations": sorted(operations),
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
            request_id, operation, arguments = parse_command(frame, operations)
            digests = dispatch_without_protocol_output(
                root,
                operation,
                arguments,
                encoder_digest=manifest["encoder"]["sha256"],
                admission=manifest["admission"],
                model_dir=model_dir,
                encoder_path=manifest_path.parent / manifest["encoder"]["path"],
            )
            emit(
                {
                    "schema": "worker-result/2",
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
                    "schema": "worker-result/2",
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
    start_parent_liveness_watchdog(parent_fd)
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
