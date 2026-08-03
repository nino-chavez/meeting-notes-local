#!/usr/bin/env python3
"""Write one digest-bound application-runtime manifest."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
NOTE_MANIFEST = Path("note-runtime-project.json")
NOTE_BRIDGE = Path("note-bridge.py")
NOTE_VALIDATOR = Path("note-validator.zip")
VALIDATOR_SOURCES = {
    "note_validator.py": REPO / "worker/note_validator.py",
    "summarize.py": REPO / "notes/summarize.py",
    "transcript.py": REPO / "notes/transcript.py",
    "capture_health.py": REPO / "spike/capture_health.py",
}


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"runtime resource is missing or unsafe: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(target: Path, contents: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def validator_bundle() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, source in VALIDATOR_SOURCES.items():
            information = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            information.compress_type = zipfile.ZIP_STORED
            information.create_system = 3
            information.external_attr = 0o100644 << 16
            archive.writestr(information, source.read_bytes())
    return output.getvalue()


def note_manifest(root: Path) -> dict:
    resources = {
        "runtime": Path("python-runtime/bin/python3.12"),
        "bridge": NOTE_BRIDGE,
        "validator": NOTE_VALIDATOR,
    }
    return {
        "schema": "note-runtime/1",
        "role": "project",
        **{
            name: {
                "relative_path": str(relative),
                "sha256": sha256(root / relative),
            }
            for name, relative in resources.items()
        },
        "generator": None,
        "models": [],
    }


def canonical_note_manifest(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")


def verify_note_runtime(root: Path) -> None:
    raw = (root / NOTE_MANIFEST).read_bytes()
    if b"\\" in raw:
        raise SystemExit("note runtime manifest contains JSON escapes")
    document = json.loads(raw)
    if canonical_note_manifest(document) != raw or document != note_manifest(root):
        raise SystemExit("note runtime manifest is not canonical or digest-bound")
    with zipfile.ZipFile(root / NOTE_VALIDATOR) as archive:
        if archive.namelist() != list(VALIDATOR_SOURCES):
            raise SystemExit("note validator bundle inventory is not exact")
        for name, source in VALIDATOR_SOURCES.items():
            if archive.read(name) != source.read_bytes():
                raise SystemExit(f"note validator source differs: {name}")


def verify_note_runtime_absent(root: Path) -> None:
    for relative in (NOTE_BRIDGE, NOTE_MANIFEST, NOTE_VALIDATOR):
        path = root / relative
        if path.exists() or path.is_symlink():
            raise SystemExit(f"test-only note runtime resource is present in bundle root: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--admission",
        choices=("boundary-test", "internal-alpha", "product"),
        default="boundary-test",
    )
    parser.add_argument(
        "--exclude-note-runtime",
        action="store_true",
        help="write only the application runtime manifest for a bundle that excludes test-only note resources",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve(strict=True)
    if arguments.exclude_note_runtime:
        verify_note_runtime_absent(root)
    else:
        atomic_write(root / NOTE_VALIDATOR, validator_bundle())
        atomic_write(root / NOTE_MANIFEST, canonical_note_manifest(note_manifest(root)))
    resources = {
        "runtime": Path("python-runtime/bin/python3.12"),
        "worker": Path("worker/main.py"),
        "tap": Path(
            "bin/meeting-capture"
            if arguments.admission == "internal-alpha"
            else "bin/audiotee"
        ),
        "encoder": Path("encoder-unavailable.identity"),
    }
    models = []
    if arguments.admission == "internal-alpha":
        models = [
            {
                "id": "whisper-large-v3-turbo-config",
                "path": "models/whisper-large-v3-turbo/config.json",
            },
            {
                "id": "whisper-large-v3-turbo-weights",
                "path": "models/whisper-large-v3-turbo/weights.safetensors",
            },
        ]
    manifest = {
        "schema": "app-runtime/1",
        "admission": arguments.admission,
        **{
            name: {"path": str(relative), "sha256": sha256(root / relative)}
            for name, relative in resources.items()
        },
        "models": [
            {**model, "sha256": sha256(root / model["path"])}
            for model in models
        ],
    }
    atomic_write(root / "app-runtime.json", (json.dumps(manifest, indent=2) + "\n").encode())
    if not arguments.exclude_note_runtime:
        verify_note_runtime(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
