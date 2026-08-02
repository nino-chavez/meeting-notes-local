#!/usr/bin/env python3
"""Verify one built Local Meeting Notes app without printing private content."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.parsers.expat import ExpatError

EXPECTED_IDENTIFIER = "com.ninochavez.local-meeting-notes"
EXPECTED_PYTHON_IDENTIFIER = f"{EXPECTED_IDENTIFIER}.python-runtime"
EXPECTED_MINIMUM_MACOS = "14.4"
EXPECTED_TEAM_ID = "34VZ63G58M"
EXPECTED_AUTHORITY = f"Developer ID Application: Abelino Chavez ({EXPECTED_TEAM_ID})"
REQUIRED_PURPOSES = (
    "NSMicrophoneUsageDescription",
    "NSAudioCaptureUsageDescription",
)
PYTHON_EXECUTABLE = Path("Contents/Resources/python-runtime/bin/python3.12")
MAIN_EXECUTABLE = Path("Contents/MacOS/local-meeting-notes-desktop")
CAPTURE_EXECUTABLE = Path("Contents/Resources/bin/meeting-capture")
PYTHON_ENTITLEMENTS = {
    "com.apple.security.cs.allow-unsigned-executable-memory": True,
}
CAPTURE_ENTITLEMENTS = {
    "com.apple.security.device.audio-input": True,
}
CODE_SIGNATURE_RUNTIME = 0x00010000
NOTE_RUNTIME_RESOURCES = {
    "runtime": Path("python-runtime/bin/python3.12"),
    "bridge": Path("note-bridge.py"),
    "validator": Path("note-validator.zip"),
}
NOTE_VALIDATOR_INVENTORY = (
    "note_validator.py",
    "summarize.py",
    "transcript.py",
    "capture_health.py",
)


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    require(path.is_file() and not path.is_symlink(), "runtime resource is missing or unsafe")
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise VerificationError(f"runtime resource is unreadable ({exc})") from None
    return digest.hexdigest()


def verify_note_runtime(resources: Path) -> None:
    manifest_path = resources / "note-runtime-project.json"
    try:
        raw = manifest_path.read_bytes()
        require(b"\\" not in raw, "note runtime manifest contains JSON escapes")
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"note runtime manifest is unreadable ({exc})") from None
    require(
        isinstance(document, dict)
        and list(document) == [
            "schema",
            "role",
            "runtime",
            "bridge",
            "validator",
            "generator",
            "models",
        ],
        "note runtime manifest fields are not exact",
    )
    require(
        json.dumps(document, ensure_ascii=False, indent=2).encode() == raw,
        "note runtime manifest is not canonical",
    )
    require(
        document["schema"] == "note-runtime/1"
        and document["role"] == "project"
        and document["generator"] is None
        and document["models"] == [],
        "note runtime role is not the closed project role",
    )
    for name, relative in NOTE_RUNTIME_RESOURCES.items():
        value = document.get(name)
        require(
            isinstance(value, dict)
            and list(value) == ["relative_path", "sha256"]
            and value["relative_path"] == str(relative)
            and value["sha256"] == sha256(resources / relative),
            f"note runtime {name} is not path- and digest-bound",
        )
    try:
        with zipfile.ZipFile(resources / NOTE_RUNTIME_RESOURCES["validator"]) as archive:
            require(
                tuple(archive.namelist()) == NOTE_VALIDATOR_INVENTORY,
                "note validator ZIP inventory is not exact",
            )
            for entry in archive.infolist():
                require(not entry.is_dir(), "note validator ZIP contains a directory")
                archive.read(entry)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise VerificationError(f"note validator ZIP is unreadable ({exc})") from None


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
    verify_note_runtime(resources)
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


def expected_designated_requirement(identifier: str) -> str:
    return (
        f'identifier "{identifier}" and anchor apple generic and '
        "certificate 1[field.1.2.840.113635.100.6.2.6] exists and "
        "certificate leaf[field.1.2.840.113635.100.6.1.13] exists and "
        f'certificate leaf[subject.OU] = "{EXPECTED_TEAM_ID}"'
    )


def normalized_requirement(value: str) -> str:
    value = re.sub(r"/\*\s*exists\s*\*/", "exists", value)
    return " ".join(value.split())


def signing_identity(path: Path) -> tuple[str, int, str, str]:
    detail = run(
        "/usr/bin/codesign",
        "-d",
        "--verbose=5",
        "--requirements",
        "-",
        str(path),
    )
    require(detail.returncode == 0, f"codesign could not inspect {path}")
    output = detail.stdout + detail.stderr
    identifier = re.search(r"(?m)^Identifier=(\S+)$", output)
    team = re.search(r"(?m)^TeamIdentifier=(\S+)$", output)
    flags = re.search(r"(?m)^CodeDirectory .* flags=0x([0-9a-fA-F]+)", output)
    requirement = re.search(r"(?m)^designated => (.+)$", output)
    require(identifier is not None, f"missing signing identifier: {path}")
    require(team is not None, f"missing signing team: {path}")
    require(flags is not None, f"missing signature flags: {path}")
    require(requirement is not None, f"missing designated requirement: {path}")
    return (
        identifier.group(1),
        int(flags.group(1), 16),
        normalized_requirement(requirement.group(1)),
        team.group(1),
    )


def verify_exact_code_identity(path: Path, identifier: str) -> None:
    actual_identifier, flags, requirement, team = signing_identity(path)
    require(actual_identifier == identifier, f"wrong signing identifier: {path}")
    require(team == EXPECTED_TEAM_ID, f"wrong signing team: {path}")
    require(
        flags & CODE_SIGNATURE_RUNTIME == CODE_SIGNATURE_RUNTIME,
        f"executable lacks the hardened-runtime bit: {path}",
    )
    require(
        requirement == expected_designated_requirement(identifier),
        f"unexpected designated requirement: {path}",
    )


def verify_signatures(app: Path, inventory: list[tuple[Path, str]]) -> None:
    outer = run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
    require(outer.returncode == 0, "outer app signature is not strict and complete")
    verify_exact_code_identity(app, EXPECTED_IDENTIFIER)
    require(entitlements(app) == CAPTURE_ENTITLEMENTS, "unexpected outer entitlement")
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
        relative = path.relative_to(app)
        if relative == PYTHON_EXECUTABLE:
            expected_entitlements = PYTHON_ENTITLEMENTS
            verify_exact_code_identity(path, EXPECTED_PYTHON_IDENTIFIER)
        elif relative in {MAIN_EXECUTABLE, CAPTURE_EXECUTABLE}:
            expected_entitlements = CAPTURE_ENTITLEMENTS
            if relative == MAIN_EXECUTABLE:
                verify_exact_code_identity(path, EXPECTED_IDENTIFIER)
        else:
            expected_entitlements = {}
            if "executable" in kind:
                _, flags, _, _ = signing_identity(path)
                require(
                    flags & CODE_SIGNATURE_RUNTIME == CODE_SIGNATURE_RUNTIME,
                    f"executable lacks the hardened-runtime bit: {relative}",
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
