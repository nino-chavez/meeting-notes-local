#!/usr/bin/env python3
"""Stage Yawn's pinned transcript-model files for immutable object hosting."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from worker.build_manifest import model_catalog


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q4-dir", required=True, type=Path)
    parser.add_argument("--full-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    output = arguments.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory is not empty: {output}")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    sources = {
        "whisper-large-v3-turbo-q4": arguments.q4_dir.resolve(strict=True),
        "whisper-large-v3-turbo": arguments.full_dir.resolve(strict=True),
    }
    catalog = model_catalog()
    uploads = []
    for model in catalog["models"]:
        source_dir = sources[model["id"]]
        if not source_dir.is_dir():
            raise SystemExit(f"model source is unsafe: {source_dir}")
        for expected in model["files"]:
            source_link = source_dir / expected["name"]
            try:
                source = source_link.resolve(strict=True)
            except OSError:
                raise SystemExit(f"model source file is missing: {source_link}") from None
            if not source.is_file():
                raise SystemExit(f"model source file is missing or unsafe: {source}")
            if source.stat().st_size != expected["bytes"] or sha256(source) != expected["sha256"]:
                raise SystemExit(f"model source does not match the pinned catalog: {source}")
            key = Path("models") / model["id"] / model["revision"] / expected["name"]
            destination = output / key
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o644)
            uploads.append(
                {
                    "key": key.as_posix(),
                    "bytes": expected["bytes"],
                    "sha256": expected["sha256"],
                    "url": expected["url"],
                }
            )

    manifest = {"schema": "yawn-model-upload/1", "objects": uploads}
    (output / "hosting-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(output / "hosting-manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
