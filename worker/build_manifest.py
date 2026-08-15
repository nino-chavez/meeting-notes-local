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
# Insertion order is the zip write order, and `verify_note_runtime` compares
# `archive.namelist()` to this list positionally. Append; do not reorder.
VALIDATOR_SOURCES = {
    "note_validator.py": REPO / "worker/note_validator.py",
    "summarize.py": REPO / "notes/summarize.py",
    "transcript.py": REPO / "notes/transcript.py",
    "capture_health.py": REPO / "spike/capture_health.py",
    "candidate_first.py": REPO / "notes/candidate_first.py",
}

MODEL_BASE_URL = os.environ.get(
    "YAWN_MODEL_BASE_URL",
    "https://pub-91cec3695eaf486bbfaaa114df6f2268.r2.dev/models",
).rstrip("/")
TRANSCRIPT_MODELS = [
    {
        "id": "whisper-large-v3-turbo-q4",
        "revision": "660c343bbf4e52ac257f0b7d952e5388e6f93bef",
        "title": "Smaller download",
        "detail": "A 4-bit local transcription model that uses about 464 MB.",
        "files": [
            {
                "role": "config",
                "name": "config.json",
                "bytes": 341,
                "sha256": "538e24557b8f9bc504700add5e7bbe32087c2353001ff563e64772ad4398671a",
            },
            {
                "role": "weights",
                "name": "weights.npz",
                "bytes": 463_664_664,
                "sha256": "862bbc832b05f3f4ec19dd632b701d61a6d3f5c7906360a10d72a79870642a80",
            },
        ],
    },
    {
        "id": "whisper-large-v3-turbo",
        "revision": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
        "title": "Full model",
        "detail": "The full local Turbo transcription model, using about 1.61 GB.",
        "files": [
            {
                "role": "config",
                "name": "config.json",
                "bytes": 268,
                "sha256": "b34fc29e4e11e0a25e812775dd67f4dd16fc2c8eb43d28ae25ff7d660ecb6379",
            },
            {
                "role": "weights",
                "name": "weights.safetensors",
                "bytes": 1_613_977_612,
                "sha256": "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6",
            },
        ],
    },
]


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


def model_catalog() -> dict:
    models = []
    for source in TRANSCRIPT_MODELS:
        revision = source["revision"]
        files = [
            {
                **file,
                "url": f"{MODEL_BASE_URL}/{source['id']}/{revision}/{file['name']}",
            }
            for file in source["files"]
        ]
        installed_bytes = sum(file["bytes"] for file in files)
        models.append(
            {
                "id": source["id"],
                "revision": revision,
                "title": source["title"],
                "detail": source["detail"],
                "downloadBytes": installed_bytes,
                "installedBytes": installed_bytes,
                "files": files,
            }
        )
    return {"schema": "yawn-model-catalog/1", "models": models}


def write_model_catalog(root: Path) -> Path:
    path = root / "model-catalog.json"
    atomic_write(path, (json.dumps(model_catalog(), indent=2) + "\n").encode())
    return path


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
    parser.add_argument(
        "--encoder",
        type=Path,
        default=Path("encoder-unavailable.identity"),
        help=(
            "relative path of the packaged speaker-encoder artifact; the default records the"
            " placeholder identity, which every consumer reads as encoder-unavailable"
        ),
    )
    parser.add_argument(
        "--external-transcript-models",
        action="store_true",
        help="bind the signed hosted-model catalog instead of bundled Whisper weights",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve(strict=True)
    if arguments.encoder.is_absolute() or not (root / arguments.encoder).resolve().is_relative_to(
        root
    ):
        raise SystemExit(f"encoder path escapes the runtime root: {arguments.encoder}")
    if arguments.exclude_note_runtime:
        verify_note_runtime_absent(root)
    else:
        atomic_write(root / NOTE_VALIDATOR, validator_bundle())
        atomic_write(root / NOTE_MANIFEST, canonical_note_manifest(note_manifest(root)))
    # Tauri's resource map is intentionally identical in every lane. The
    # catalog is signed into all bundles; only app-runtime/2 authorizes models
    # installed outside the bundle.
    catalog_path = write_model_catalog(root)
    resources = {
        "runtime": Path("python-runtime/bin/python3.12"),
        "worker": Path("worker/main.py"),
        "tap": Path(
            "bin/meeting-capture"
            if arguments.admission == "internal-alpha"
            else "bin/audiotee"
        ),
        "encoder": arguments.encoder,
        # Fallback requester for admissions without meeting-capture. Carried here
        # because the app can run it, and every child this app runs is
        # digest-verified from this manifest before it is spawned.
        "permission_probe": Path("bin/permission-probe"),
    }
    models = []
    if arguments.admission == "internal-alpha":
        if not arguments.external_transcript_models:
            models.extend(
                [
                    {
                        "id": "whisper-large-v3-turbo-config",
                        "path": "models/whisper-large-v3-turbo/config.json",
                    },
                    {
                        "id": "whisper-large-v3-turbo-weights",
                        "path": "models/whisper-large-v3-turbo/weights.safetensors",
                    },
                ]
            )
        # All four or none. `worker.main.embedding_model_dir` requires the
        # whole set before it will name a directory, because a model missing
        # its `tokenizer.json` would load and then embed with whatever
        # tokenizer happened to be importable.
        models.extend([
            {
                "id": "all-minilm-l6-v2-config",
                "path": "models/all-MiniLM-L6-v2/config.json",
            },
            {
                "id": "all-minilm-l6-v2-sentence-config",
                "path": "models/all-MiniLM-L6-v2/sentence_bert_config.json",
            },
            {
                "id": "all-minilm-l6-v2-tokenizer",
                "path": "models/all-MiniLM-L6-v2/tokenizer.json",
            },
            {
                "id": "all-minilm-l6-v2-weights",
                "path": "models/all-MiniLM-L6-v2/model.safetensors",
            },
        ])
    catalog_resource = None
    if arguments.external_transcript_models:
        if arguments.admission != "internal-alpha":
            raise SystemExit("external transcript models require internal-alpha admission")
        catalog_resource = {"path": catalog_path.name, "sha256": sha256(catalog_path)}
    manifest = {
        "schema": "app-runtime/2" if catalog_resource else "app-runtime/1",
        "admission": arguments.admission,
        **{
            name: {"path": str(relative), "sha256": sha256(root / relative)}
            for name, relative in resources.items()
        },
        **({"model_catalog": catalog_resource} if catalog_resource else {}),
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
