#!/usr/bin/env python3
"""Write one digest-bound application-runtime manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"runtime resource is missing or unsafe: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_note_project_runtime(root: Path) -> None:
    """Stage the read-only projection bridge beside the already fixed runtime."""
    repository = Path(__file__).resolve().parent.parent
    notes = root / "notes"
    notes.mkdir(exist_ok=True)
    bridge = notes / "note_bridge.py"
    bridge.write_bytes((repository / "worker/note_bridge.py").read_bytes())
    os.chmod(bridge, 0o644)

    validator = notes / "note-validator.zip"
    sources = {
        "note_validator.py": repository / "worker/note_validator.py",
        "summarize.py": repository / "notes/summarize.py",
        "transcript.py": repository / "notes/transcript.py",
        "capture_health.py": repository / "spike/capture_health.py",
    }
    with zipfile.ZipFile(validator, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, source in sources.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_STORED
            archive.writestr(entry, source.read_bytes())
    os.chmod(validator, 0o644)

    resources = {
        "runtime": Path("python-runtime/bin/python3.12"),
        "bridge": Path("notes/note_bridge.py"),
        "validator": Path("notes/note-validator.zip"),
    }
    manifest = {
        "schema": "note-runtime/1",
        "role": "project",
        **{
            name: {"relative_path": str(relative), "sha256": sha256(root / relative)}
            for name, relative in resources.items()
        },
        "generator": None,
        "models": [],
    }
    # The frozen note-runtime contract intentionally has no terminal newline.
    (root / "note-project-runtime.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.chmod(root / "note-project-runtime.json", 0o644)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--admission",
        choices=("boundary-test", "internal-alpha"),
        default="boundary-test",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve(strict=True)
    write_note_project_runtime(root)
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
    target = root / "app-runtime.json"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=root, prefix=".app-runtime.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
