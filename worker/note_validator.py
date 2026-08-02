"""FD-pinned, read-only product note reinspection for the one-shot bridge."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024


class ArtifactFailure(ValueError):
    def __init__(self, code: str, recoverable: bool):
        super().__init__(code)
        self.code = code
        self.recoverable = recoverable


@dataclass
class _DirectoryLink:
    parent_fd: int
    name: str
    child_fd: int
    identity: os.stat_result


@dataclass
class _FileLink:
    parent_fd: int
    name: str
    file_fd: int
    identity: os.stat_result


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
        and left.st_size == right.st_size
        and left.st_nlink == right.st_nlink
    )


def _open_directories(root_fd: int, names: list[str]) -> tuple[int, list[_DirectoryLink]]:
    current = os.dup(root_fd)
    links: list[_DirectoryLink] = []
    try:
        for name in names:
            child = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            identity = os.fstat(child)
            if (
                not stat.S_ISDIR(identity.st_mode)
                or stat.S_IMODE(identity.st_mode) != 0o700
                or identity.st_uid != os.geteuid()
            ):
                os.close(child)
                raise ArtifactFailure("artifact-invalid", False)
            links.append(_DirectoryLink(current, name, child, identity))
            current = os.dup(child)
        return os.dup(current), links
    except FileNotFoundError as exc:
        raise ArtifactFailure("artifact-missing", True) from exc
    except OSError as exc:
        raise ArtifactFailure("artifact-invalid", False) from exc
    finally:
        os.close(current)


def _open_file(parent_fd: int, name: str) -> _FileLink:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except FileNotFoundError as exc:
        raise ArtifactFailure("artifact-missing", True) from exc
    except OSError as exc:
        raise ArtifactFailure("artifact-invalid", False) from exc
    identity = os.fstat(descriptor)
    if (
        not stat.S_ISREG(identity.st_mode)
        or stat.S_IMODE(identity.st_mode) != 0o600
        or identity.st_uid != os.geteuid()
        or identity.st_nlink != 1
        or identity.st_size > MAX_ARTIFACT_BYTES
    ):
        os.close(descriptor)
        raise ArtifactFailure("artifact-invalid", False)
    return _FileLink(parent_fd, name, descriptor, identity)


def _read_file(link: _FileLink) -> bytes:
    os.lseek(link.file_fd, 0, os.SEEK_SET)
    remaining = link.identity.st_size
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(link.file_fd, min(remaining, 1024 * 1024))
        if not chunk:
            raise ArtifactFailure("artifact-changed", False)
        chunks.append(chunk)
        remaining -= len(chunk)
    if not _same_identity(link.identity, os.fstat(link.file_fd)):
        raise ArtifactFailure("artifact-changed", False)
    return b"".join(chunks)


def _require_links(directories: list[_DirectoryLink], files: list[_FileLink]) -> None:
    for link in directories:
        try:
            current = os.stat(link.name, dir_fd=link.parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ArtifactFailure("artifact-changed", False) from exc
        if not _same_identity(link.identity, current):
            raise ArtifactFailure("artifact-changed", False)
    for link in files:
        try:
            current = os.stat(link.name, dir_fd=link.parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ArtifactFailure("artifact-changed", False) from exc
        if not _same_identity(link.identity, current):
            raise ArtifactFailure("artifact-changed", False)


def _require_snapshot(link: _FileLink, expected: bytes, expected_digest: str) -> None:
    current = _read_file(link)
    if current != expected or hashlib.sha256(current).hexdigest() != expected_digest:
        raise ArtifactFailure("artifact-changed", False)


def _write_snapshot(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _validate_snapshot(
    meeting_id: str,
    note_id: str,
    transcript_id: str,
    markdown_id: str,
    note_bytes: bytes,
    transcript_bytes: bytes,
    markdown_bytes: bytes,
) -> None:
    from summarize import structured_artifact_citations, validate_artifact_pair
    from transcript import load

    with tempfile.TemporaryDirectory(prefix="lmn-note-inspect-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        note_path = root / f"{note_id}.json"
        transcript_path = root / f"{transcript_id}.json"
        markdown_path = root / f"{markdown_id}.md"
        _write_snapshot(note_path, note_bytes)
        _write_snapshot(transcript_path, transcript_bytes)
        _write_snapshot(markdown_path, markdown_bytes)
        try:
            document = json.loads(note_bytes)
            if not isinstance(document, dict):
                raise ArtifactFailure("artifact-invalid", False)
            if document.get("schema") != "note/2" or document.get("passed") is not True:
                raise ArtifactFailure("artifact-invalid", False)
            meeting = document.get("meeting")
            if not isinstance(meeting, dict) or meeting.get("id") != meeting_id:
                raise ArtifactFailure("artifact-invalid", False)
            if document.get("transcript") != f"../transcript/{transcript_id}.json":
                raise ArtifactFailure("artifact-invalid", False)
            render = document.get("render")
            if not isinstance(render, dict) or render.get("path") != f"{markdown_id}.md":
                raise ArtifactFailure("artifact-invalid", False)
            transcript = load(transcript_path)
            validated_markdown = validate_artifact_pair(document, note_path, transcript)
            if validated_markdown != markdown_path:
                raise ArtifactFailure("artifact-invalid", False)
            citations = structured_artifact_citations(document, transcript)
            checks = document.get("checks")
            if not isinstance(checks, dict) or checks.get("citations") != citations:
                raise ArtifactFailure("artifact-invalid", False)
        except ArtifactFailure:
            raise
        except (
            UnicodeError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            SystemExit,
        ) as exc:
            raise ArtifactFailure("artifact-invalid", False) from exc


def _project_snapshot(
    meeting_id: str,
    note_id: str,
    transcript_id: str,
    markdown_id: str,
    note_bytes: bytes,
    transcript_bytes: bytes,
    markdown_bytes: bytes,
) -> dict:
    """Re-derive a note/2 claim projection without writing private bytes to disk."""
    from summarize import (
        reconcile_capture_provenance,
        structured_artifact_citations,
        validate_note_render,
        validate_stored_verdict,
    )
    from transcript import load_bytes

    try:
        document = json.loads(note_bytes)
        if not isinstance(document, dict):
            raise ArtifactFailure("artifact-invalid", False)
        if document.get("schema") != "note/2" or document.get("passed") is not True:
            raise ArtifactFailure("artifact-invalid", False)
        meeting = document.get("meeting")
        if not isinstance(meeting, dict) or meeting.get("id") != meeting_id:
            raise ArtifactFailure("artifact-invalid", False)
        if document.get("transcript") != f"../transcript/{transcript_id}.json":
            raise ArtifactFailure("artifact-invalid", False)
        render = document.get("render")
        if not isinstance(render, dict) or render.get("path") != f"{markdown_id}.md":
            raise ArtifactFailure("artifact-invalid", False)
        transcript = load_bytes(transcript_bytes, source=f"transcript:{transcript_id}")
        checks = document.get("checks")
        validate_stored_verdict(checks, document.get("passed"), "note candidate")
        reconcile_capture_provenance(document, transcript, where="note candidate")
        validate_note_render(document, markdown_bytes.decode("utf-8"))
        citations = structured_artifact_citations(document, transcript)
        if not isinstance(checks, dict) or checks.get("citations") != citations:
            raise ArtifactFailure("artifact-invalid", False)
        claims = []
        for ordinal, cited in enumerate(citations["cited"]):
            claim = cited["claim"]
            claim_type = cited["type"]
            if (
                not isinstance(claim, str)
                or not claim
                or len(claim) > 160
                or claim_type not in {"decision", "action", "proposal", "question"}
                or cited.get("claim_sha256") != hashlib.sha256(claim.encode("utf-8")).hexdigest()
            ):
                raise ArtifactFailure("artifact-invalid", False)
            locators = []
            for reference in cited["evidence_refs"]:
                turn = reference["turn"]
                start = reference["char_start"]
                end = reference["char_end"]
                if (
                    type(turn) is not int
                    or type(start) is not int
                    or type(end) is not int
                    or turn < 0
                    or start < 0
                    or end <= start
                    or turn >= len(transcript.turns)
                    or end > len(transcript.turns[turn].text)
                ):
                    raise ArtifactFailure("artifact-invalid", False)
                text_sha256 = hashlib.sha256(
                    transcript.turns[turn].text[start:end].encode("utf-8")
                ).hexdigest()
                if reference.get("text_sha256") != text_sha256:
                    raise ArtifactFailure("artifact-invalid", False)
                locators.append(
                    {
                        "turn": turn,
                        "start": start,
                        "end": end,
                        "text_sha256": text_sha256,
                    }
                )
            if not 1 <= len(locators) <= 3 or locators != sorted(
                locators, key=lambda locator: (
                    locator["turn"], locator["start"], locator["end"], locator["text_sha256"]
                )
            ) or len({tuple(locator.items()) for locator in locators}) != len(locators):
                raise ArtifactFailure("artifact-invalid", False)
            claims.append(
                {
                    "claim_ordinal": ordinal,
                    "claim_sha256": cited["claim_sha256"],
                    "claim_type": claim_type,
                    "evidence_state": "located",
                    "claim": claim,
                    "locators": locators,
                }
            )
        return {
            "schema": "note-claim-projection/1",
            "note_json_sha256": note_id,
            "note_markdown_sha256": markdown_id,
            "transcript_sha256": transcript_id,
            "claims": claims,
        }
    except ArtifactFailure:
        raise
    except (
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        SystemExit,
    ) as exc:
        raise ArtifactFailure("artifact-invalid", False) from exc


def inspect(
    root_fd: int,
    arguments: dict,
    *,
    after_open: Callable[[], None] | None = None,
) -> dict[str, str]:
    """Inspect one coherent snapshot of the three content-addressed artifacts."""
    meeting_id = arguments["meeting_id"]
    note_id = arguments["note_id"]
    transcript_id = arguments["transcript_id"]
    directories: list[_DirectoryLink] = []
    files: list[_FileLink] = []
    open_directories: list[int] = []
    try:
        notes_fd, notes_links = _open_directories(root_fd, ["meetings", meeting_id, "notes"])
        open_directories.append(notes_fd)
        directories.extend(notes_links)
        transcript_fd, transcript_links = _open_directories(
            root_fd, ["meetings", meeting_id, "transcript"]
        )
        open_directories.append(transcript_fd)
        directories.extend(transcript_links)
        note = _open_file(notes_fd, f"{note_id}.json")
        transcript = _open_file(transcript_fd, f"{transcript_id}.json")
        files.extend((note, transcript))
        note_bytes = _read_file(note)
        try:
            document = json.loads(note_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactFailure("artifact-invalid", False) from exc
        if not isinstance(document, dict):
            raise ArtifactFailure("artifact-invalid", False)
        render = document.get("render")
        render_path = render.get("path") if isinstance(render, dict) else None
        if (
            not isinstance(render_path, str)
            or len(render_path) != 67
            or not render_path.endswith(".md")
            or any(character not in "0123456789abcdef" for character in render_path[:-3])
        ):
            raise ArtifactFailure("artifact-invalid", False)
        markdown_id = render_path[:-3]
        markdown = _open_file(notes_fd, render_path)
        files.append(markdown)
        if after_open is not None:
            after_open()
        transcript_bytes = _read_file(transcript)
        markdown_bytes = _read_file(markdown)
        _require_links(directories, files)
        if hashlib.sha256(note_bytes).hexdigest() != note_id:
            raise ArtifactFailure("artifact-changed", False)
        if hashlib.sha256(transcript_bytes).hexdigest() != transcript_id:
            raise ArtifactFailure("artifact-changed", False)
        if hashlib.sha256(markdown_bytes).hexdigest() != markdown_id:
            raise ArtifactFailure("artifact-changed", False)
        _validate_snapshot(
            meeting_id,
            note_id,
            transcript_id,
            markdown_id,
            note_bytes,
            transcript_bytes,
            markdown_bytes,
        )
        _require_links(directories, files)
        _require_snapshot(note, note_bytes, note_id)
        _require_snapshot(transcript, transcript_bytes, transcript_id)
        _require_snapshot(markdown, markdown_bytes, markdown_id)
        _require_links(directories, files)
        return {
            "note": note_id,
            "note-markdown": markdown_id,
            "transcript": transcript_id,
        }
    finally:
        for link in files:
            os.close(link.file_fd)
        for descriptor in open_directories:
            os.close(descriptor)
        for link in reversed(directories):
            os.close(link.child_fd)
            os.close(link.parent_fd)


def project(
    root_fd: int,
    arguments: dict,
    *,
    after_open: Callable[[], None] | None = None,
) -> dict:
    """Return a coherent, fully re-derived projection from retained descriptors."""
    meeting_id = arguments["meeting_id"]
    note_id = arguments["note_id"]
    transcript_id = arguments["transcript_id"]
    directories: list[_DirectoryLink] = []
    files: list[_FileLink] = []
    open_directories: list[int] = []
    try:
        notes_fd, notes_links = _open_directories(root_fd, ["meetings", meeting_id, "notes"])
        open_directories.append(notes_fd)
        directories.extend(notes_links)
        transcript_fd, transcript_links = _open_directories(
            root_fd, ["meetings", meeting_id, "transcript"]
        )
        open_directories.append(transcript_fd)
        directories.extend(transcript_links)
        note = _open_file(notes_fd, f"{note_id}.json")
        transcript = _open_file(transcript_fd, f"{transcript_id}.json")
        files.extend((note, transcript))
        note_bytes = _read_file(note)
        try:
            document = json.loads(note_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactFailure("artifact-invalid", False) from exc
        if not isinstance(document, dict):
            raise ArtifactFailure("artifact-invalid", False)
        render = document.get("render")
        render_path = render.get("path") if isinstance(render, dict) else None
        if (
            not isinstance(render_path, str)
            or len(render_path) != 67
            or not render_path.endswith(".md")
            or any(character not in "0123456789abcdef" for character in render_path[:-3])
        ):
            raise ArtifactFailure("artifact-invalid", False)
        markdown_id = render_path[:-3]
        markdown = _open_file(notes_fd, render_path)
        files.append(markdown)
        if after_open is not None:
            after_open()
        transcript_bytes = _read_file(transcript)
        markdown_bytes = _read_file(markdown)
        _require_links(directories, files)
        if hashlib.sha256(note_bytes).hexdigest() != note_id:
            raise ArtifactFailure("artifact-changed", False)
        if hashlib.sha256(transcript_bytes).hexdigest() != transcript_id:
            raise ArtifactFailure("artifact-changed", False)
        if hashlib.sha256(markdown_bytes).hexdigest() != markdown_id:
            raise ArtifactFailure("artifact-changed", False)
        projection = _project_snapshot(
            meeting_id,
            note_id,
            transcript_id,
            markdown_id,
            note_bytes,
            transcript_bytes,
            markdown_bytes,
        )
        _require_links(directories, files)
        _require_snapshot(note, note_bytes, note_id)
        _require_snapshot(transcript, transcript_bytes, transcript_id)
        _require_snapshot(markdown, markdown_bytes, markdown_id)
        _require_links(directories, files)
        return projection
    finally:
        for link in files:
            os.close(link.file_fd)
        for descriptor in open_directories:
            os.close(descriptor)
        for link in reversed(directories):
            os.close(link.child_fd)
            os.close(link.parent_fd)
