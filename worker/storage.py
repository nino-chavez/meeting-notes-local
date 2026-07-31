"""Owner-private, durable writes for canonical application artifacts."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


class StorageRefused(ValueError):
    pass


def require_private_root(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise StorageRefused("app data root must be an absolute non-symlink directory")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or stat.S_IMODE(resolved.stat().st_mode) != 0o700:
        raise StorageRefused("app data root must be an owner-private directory")
    return resolved


def opaque_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StorageRefused(f"{label} must be an opaque identifier")
    if len(value) > 128 or value in {".", ".."} or "/" in value or "\\" in value:
        raise StorageRefused(f"{label} must be an opaque identifier")
    if not all(character.isalnum() or character in "-_" for character in value):
        raise StorageRefused(f"{label} must be an opaque identifier")
    return value


def resolve_below(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts)
    current = root
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise StorageRefused("storage path contains a symlink")
    resolved_parent = candidate.parent.resolve(strict=True)
    if resolved_parent != root and root not in resolved_parent.parents:
        raise StorageRefused("storage path escapes the app data root")
    if candidate.is_symlink():
        raise StorageRefused("storage target may not be a symlink")
    return candidate


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise StorageRefused("private directory target is invalid")
    path.chmod(0o700)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_create_new(path: Path, data: bytes) -> None:
    private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            raise StorageRefused("canonical artifact already exists") from None
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
