#!/usr/bin/env python3
"""Verify one built Local Meeting Notes app without printing private content."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from xml.parsers.expat import ExpatError

EXPECTED_IDENTIFIER = "com.ninochavez.local-meeting-notes"
EXPECTED_MINIMUM_MACOS = "14.4"
EXPECTED_TEAM_ID = "34VZ63G58M"
EXPECTED_AUTHORITY = f"Developer ID Application: Abelino Chavez ({EXPECTED_TEAM_ID})"
REQUIRED_PURPOSES = (
    "NSMicrophoneUsageDescription",
    "NSAudioCaptureUsageDescription",
)
PYTHON_EXECUTABLE = Path("Contents/Resources/python-runtime/bin/python3.12")
PYTHON_ENTITLEMENTS = {
    "com.apple.security.cs.allow-unsigned-executable-memory": True,
}


class VerificationError(ValueError):
    pass


def run(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def load_plist(path: Path) -> dict:
    try:
        value = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise VerificationError(f"built Info.plist is unreadable ({exc})") from None
    require(isinstance(value, dict), "built Info.plist is not a dictionary")
    return value


def verify_metadata(app: Path) -> tuple[Path, dict]:
    plist_path = app / "Contents/Info.plist"
    require(plist_path.is_file(), "built app is missing Contents/Info.plist")
    plist = load_plist(plist_path)
    require(
        plist.get("CFBundleIdentifier") == EXPECTED_IDENTIFIER,
        "built app has the wrong bundle identifier",
    )
    require(
        plist.get("LSMinimumSystemVersion") == EXPECTED_MINIMUM_MACOS,
        "built app has the wrong minimum macOS version",
    )
    version = plist.get("CFBundleShortVersionString")
    require(
        isinstance(version, str)
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z.-]+)?", version)
        is not None,
        "built app version is missing or unsafe",
    )
    for key in REQUIRED_PURPOSES:
        purpose = plist.get(key)
        require(
            isinstance(purpose, str) and len(purpose.strip()) >= 24,
            f"built app is missing a useful {key}",
        )
    resources = app / "Contents/Resources"
    require(resources.is_dir(), "built app is missing Contents/Resources")
    return resources, plist


def verify_runtime(resources: Path, admission: str) -> None:
    manifest_path = resources / "app-runtime.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"runtime manifest is unreadable ({exc})") from None
    require(manifest.get("schema") == "app-runtime/1", "runtime schema is not current")
    require(
        manifest.get("admission") == admission,
        f"runtime admission is not {admission}; refusing this distribution candidate",
    )
    if admission == "internal-alpha":
        require(
            (manifest.get("tap") or {}).get("path") == "bin/meeting-capture",
            "internal-alpha runtime is not bound to the product capture helper",
        )
        expected_models = {
            "whisper-large-v3-turbo-config": (
                "models/whisper-large-v3-turbo/config.json"
            ),
            "whisper-large-v3-turbo-weights": (
                "models/whisper-large-v3-turbo/weights.safetensors"
            ),
        }
        actual_models = {
            model.get("id"): model.get("path")
            for model in manifest.get("models", [])
            if isinstance(model, dict)
        }
        require(
            actual_models == expected_models,
            "internal-alpha model inventory is incomplete or unexpected",
        )
    python = resources / "python-runtime/bin/python3.12"
    require(python.is_file() and os.access(python, os.X_OK), "bundled Python is missing")
    exercise = """
from pathlib import Path
import numpy as np
from worker.main import load_manifest
load_manifest(Path('app-runtime.json'))
np.linalg.svd(np.eye(2))
np.fft.fft(np.ones(4))
"""
    completed = run(str(python), "-E", "-s", "-B", "-c", exercise, cwd=resources)
    require(
        completed.returncode == 0,
        "bundled Python, worker, manifest, or NumPy runtime exercise failed",
    )
    if admission == "internal-alpha":
        alpha_exercise = "import mlx.core, mlx_whisper, worker.transcription"
        completed = run(
            str(python), "-E", "-s", "-B", "-c", alpha_exercise, cwd=resources
        )
        require(
            completed.returncode == 0,
            "internal-alpha offline transcription runtime failed to import",
        )


def macho_inventory(app: Path) -> list[tuple[Path, str]]:
    inventory: list[tuple[Path, str]] = []
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        kind = run("/usr/bin/file", "-b", str(path))
        require(kind.returncode == 0, "file could not inspect a bundled artifact")
        if not kind.stdout.startswith("Mach-O"):
            continue
        arches = run("/usr/bin/lipo", "-archs", str(path))
        require(arches.returncode == 0, "lipo could not inspect a Mach-O")
        architecture_list = arches.stdout.strip().split()
        architecture_set = set(architecture_list)
        require(
            "arm64" in architecture_set,
            f"Mach-O lacks an arm64 slice: {path.relative_to(app)}",
        )
        require(
            architecture_set <= {"arm64", "x86_64"},
            f"Mach-O contains an unexpected architecture: {path.relative_to(app)}",
        )
        if "executable" in kind.stdout:
            require(
                architecture_list == ["arm64"],
                f"bundle executable is not arm64-only: {path.relative_to(app)}",
            )
        inventory.append((path, kind.stdout.strip()))
    require(inventory, "built app contains no Mach-O files")
    return inventory


def entitlements(path: Path) -> dict:
    result = run("/usr/bin/codesign", "-d", "--entitlements", ":-", str(path))
    xml_start = result.stdout.find("<?xml")
    if xml_start < 0:
        return {}
    try:
        value = plistlib.loads(result.stdout[xml_start:].encode())
    except (plistlib.InvalidFileException, ExpatError):
        raise VerificationError("signed entitlement output is malformed") from None
    require(isinstance(value, dict), "signed entitlements are not a dictionary")
    return value


def verify_signatures(app: Path, inventory: list[tuple[Path, str]]) -> None:
    outer = run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
    require(outer.returncode == 0, "outer app signature is not strict and complete")
    for path, kind in inventory:
        checked = run("/usr/bin/codesign", "--verify", "--strict", str(path))
        require(
            checked.returncode == 0,
            f"invalid nested signature: {path.relative_to(app)}",
        )
        detail = run("/usr/bin/codesign", "-dv", "--verbose=4", str(path))
        signature = detail.stdout + detail.stderr
        require(
            f"Authority={EXPECTED_AUTHORITY}" in signature,
            f"wrong signing authority: {path.relative_to(app)}",
        )
        require(
            f"TeamIdentifier={EXPECTED_TEAM_ID}" in signature,
            f"wrong signing team: {path.relative_to(app)}",
        )
        if "executable" in kind:
            require(
                "runtime" in signature,
                f"executable lacks hardened runtime: {path.relative_to(app)}",
            )
        relative = path.relative_to(app)
        expected_entitlements = (
            PYTHON_ENTITLEMENTS if relative == PYTHON_EXECUTABLE else {}
        )
        require(
            entitlements(path) == expected_entitlements,
            f"unexpected entitlement: {path.relative_to(app)}",
        )


def verify(app: Path, *, signed: bool, admission: str) -> tuple[str, int]:
    supplied = app.expanduser()
    require(not supplied.is_symlink(), "app path may not be a symlink")
    app = supplied.resolve()
    require(app.is_dir(), f"app bundle does not exist: {app}")
    resources, plist = verify_metadata(app)
    verify_runtime(resources, admission)
    inventory = macho_inventory(app)
    if signed:
        verify_signatures(app, inventory)
    return str(plist["CFBundleShortVersionString"]), len(inventory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--signed", action="store_true")
    parser.add_argument(
        "--admission",
        choices=("product", "internal-alpha"),
        default="product",
    )
    args = parser.parse_args()
    try:
        version, macho_count = verify(
            args.app, signed=args.signed, admission=args.admission
        )
    except VerificationError as exc:
        print(f"release bundle verification: BLOCKED — {exc}", file=sys.stderr)
        return 1
    mode = "signed" if args.signed else "unsigned"
    print(
        f"release bundle verification: PASS ({mode}, version {version}, "
        f"{macho_count} arm64-compatible Mach-O files, {args.admission})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
