#!/usr/bin/env python3
"""Write one digest-bound application-runtime manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"runtime resource is missing or unsafe: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
