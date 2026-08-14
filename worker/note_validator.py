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


class GenerationRefused(ValueError):
    """Untrusted generator output failed a check; the caller falls back.

    Separate from `ArtifactFailure` because the two answer different questions.
    An artifact failure says the retained bytes on this Mac are missing, unsafe,
    or changed. A generation refusal says the retained bytes were fine and the
    model's proposal did not survive the note/2 evidence rules. Only the second
    is allowed to produce `transcript-only`; collapsing them would let a storage
    fault be reported as a quiet quality outcome.
    """

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


def validate_locators(evidence_refs: list, transcript) -> list[dict]:
    """Re-derive one point's locators against the transcript it cites.

    The note/2 evidence rule, in one place: one to three references, in order,
    without duplicates, each bounds-checked against the loaded turns and each
    `text_sha256` recomputed from the transcript's own bytes. Nothing supplied
    is trusted, so a reference naming a turn or a span the transcript does not
    have cannot pass.

    The one-to-three bound is enforced twice, by two owners. This is the note/2
    artifact contract, and `note_projection.rs` re-parses it independently at
    `parse_claim`, failing closed with a content-free `Unavailable`. Relaxing it
    here would not relax it there: a wider view motivating more locators has to
    move both, and the Rust side is the one that will not follow a Python edit.
    """
    locators = []
    for reference in evidence_refs:
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
    return locators


def validate_claim_rows(cited: list, transcript) -> list[dict]:
    """Re-derive every stored claim and its locators against the transcript."""
    claims = []
    for ordinal, row in enumerate(cited):
        claim = row["claim"]
        claim_type = row["type"]
        if (
            not isinstance(claim, str)
            or not claim
            or len(claim) > 160
            or claim_type not in {"decision", "action", "proposal", "question"}
            or row.get("claim_sha256") != hashlib.sha256(claim.encode("utf-8")).hexdigest()
        ):
            raise ArtifactFailure("artifact-invalid", False)
        claims.append(
            {
                "claim_ordinal": ordinal,
                "claim_sha256": row["claim_sha256"],
                "claim_type": claim_type,
                "evidence_state": "located",
                "claim": claim,
                "locators": validate_locators(row["evidence_refs"], transcript),
            }
        )
    return claims


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
        claims = validate_claim_rows(citations["cited"], transcript)
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


def _response_refusal(raw: str) -> str:
    """Name which half of the response contract failed, without content."""
    try:
        json.loads(raw)
    except (UnicodeError, ValueError):
        return "response-json-syntax"
    return "response-contract"


def _classify_candidates(transcript, ask: Callable[[dict], str]) -> tuple[dict, list[dict]]:
    """Enumerate candidates locally, then take one verdict per offered candidate.

    This is the measured task, not a paraphrase of it. Deterministic local code
    builds the candidate manifest and every request packet; the model's entire
    output surface is one KEEP or ABSTAIN per candidate it was offered. It
    cannot name a row it was not shown, invent a locator, or decide how many
    points exist — `decode_classification` refuses an unknown, duplicated,
    reordered, or miscounted verdict before anything reaches the transcript.
    """
    import candidate_first
    from summarize import StructuredOutputError

    registered = candidate_first.REGISTERED_RUN["classifier"]
    budget = candidate_first.REGISTERED_RUN["gates"]["maximum_keep"]
    batch_size = registered["batch_size"]
    try:
        manifest = candidate_first.generate_manifest(transcript, candidate_first.STRATEGY_BROAD)
        candidate_first.validate_manifest(manifest, transcript)
        batches = candidate_first.candidate_batches(manifest["candidates"], batch_size)
    except (StructuredOutputError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise GenerationRefused("no-generatable-transcript", True) from exc
    if not batches:
        raise GenerationRefused("no-generatable-transcript", True)
    kept: list[dict] = []
    for batch in batches:
        candidate_ids = [row["candidate_id"] for row in batch]
        try:
            schema, system, user = candidate_first.classification_request(
                transcript, manifest, batch, batch_size
            )
        except (StructuredOutputError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise GenerationRefused("request-contract", False) from exc
        raw = ask(
            {
                "schema": "note-classification-request/1",
                "system": system,
                "user": user,
                "response_format": schema,
                "num_predict": candidate_first.classification_num_predict(len(batch)),
                "num_ctx": registered["num_ctx"],
                "temperature": registered["temperature"],
            }
        )
        try:
            decoded = candidate_first.decode_classification(raw, candidate_ids)
        except (StructuredOutputError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            # `decode_classification` reports one error type for both "this is
            # not JSON" and "this is JSON that breaks the contract". The
            # research taxonomy separates them, so the discriminator is a
            # parse attempt — not a second copy of the decoder.
            raise GenerationRefused(_response_refusal(raw), False) from exc
        verdicts = {row["candidate_id"]: row["verdict"] for row in decoded["items"]}
        kept.extend(row for row in batch if verdicts[row["candidate_id"]] == "KEEP")
        # Checked as it accumulates, so a run that has already blown the
        # registered budget stops instead of classifying the remaining batches.
        if len(kept) > budget:
            raise GenerationRefused("keep-budget-exceeded", False)
    if not kept:
        raise GenerationRefused("no-model-candidates", True)
    return manifest, kept


def locate_kept_candidates(manifest: dict, kept: list[dict], transcript) -> list[dict]:
    """Resolve every kept candidate to its anchor locator, and verify it here.

    The excerpts are exact by construction — they are transcript slices the
    enumerator produced — and they are re-derived anyway. `validate_locators`
    recomputes each span's digest from the loaded turns, so a fragment id that
    no longer resolves to the bytes it names refuses rather than rendering.

    A point cites its **anchor**, not the whole window it was classified in.
    `visible_fragment_ids` is what the model was shown for context; the anchor
    is what the candidate is about, which is why the deterministic control arm
    cites the anchor alone. Two consequences follow. The point never cites text
    the model merely saw nearby, and the locator count stays 1 whatever the view
    is — a ±2 window would offer five fragments and blow note/2's three-locator
    rule if the window were the citation.
    """
    from summarize import build_fragment_map

    fragment_map = build_fragment_map(transcript)
    lookup = {row["source_fragment_id"]: row for row in fragment_map["fragments"]}
    if fragment_map["transcript_view_sha256"] != manifest["transcript_view_sha256"]:
        raise GenerationRefused("citation-locator", False)
    points = []
    for ordinal, candidate in enumerate(kept):
        try:
            anchor = lookup[candidate["anchor_fragment_id"]]
            locators = validate_locators(
                [
                    {
                        "turn": anchor["turn"],
                        "char_start": anchor["char_start"],
                        "char_end": anchor["char_end"],
                        "text_sha256": anchor["text_sha256"],
                    }
                ],
                transcript,
            )
        except ArtifactFailure as exc:
            # The retained transcript is intact; the candidate no longer
            # resolves against it. Not a storage code.
            raise GenerationRefused("citation-locator", False) from exc
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise GenerationRefused("citation-locator", False) from exc
        points.append(
            {
                "point_ordinal": ordinal,
                "candidate_id": candidate["candidate_id"],
                "evidence_state": "located",
                "locators": locators,
            }
        )
    return points


def generate(
    root_fd: int,
    arguments: dict,
    *,
    ask: Callable[[dict], str],
    after_open: Callable[[], None] | None = None,
) -> dict:
    """Select note points from one pinned transcript and locate them here.

    The transcript is opened, digest-checked, and held open exactly as the
    read-only paths do. `ask` is the injected model seam: it takes one built
    classification request and returns the raw response. The caller owns the
    transport and may add transport-only fields to it — the bridge attaches the
    verified model directory to every request — but nothing it adds is read
    back here. No note, markdown, or product record is read or written, and the
    transcript's identity is re-checked after classification, so a swap mid-run
    is caught.

    What comes back is locators, not prose. Every point is an excerpt the
    transcript already holds; no claim text is synthesized here, because a
    prose stage is a separate measurement.
    """
    from transcript import load_bytes

    meeting_id = arguments["meeting_id"]
    transcript_id = arguments["transcript_id"]
    directories: list[_DirectoryLink] = []
    files: list[_FileLink] = []
    open_directories: list[int] = []
    try:
        transcript_fd, transcript_links = _open_directories(
            root_fd, ["meetings", meeting_id, "transcript"]
        )
        open_directories.append(transcript_fd)
        directories.extend(transcript_links)
        transcript_file = _open_file(transcript_fd, f"{transcript_id}.json")
        files.append(transcript_file)
        if after_open is not None:
            after_open()
        transcript_bytes = _read_file(transcript_file)
        _require_links(directories, files)
        if hashlib.sha256(transcript_bytes).hexdigest() != transcript_id:
            raise ArtifactFailure("artifact-changed", False)
        try:
            transcript = load_bytes(transcript_bytes, source=f"transcript:{transcript_id}")
        except (UnicodeError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise ArtifactFailure("artifact-invalid", False) from exc
        if not transcript.turns:
            raise GenerationRefused("no-generatable-transcript", True)
        manifest, kept = _classify_candidates(transcript, ask)
        points = locate_kept_candidates(manifest, kept, transcript)
        _require_links(directories, files)
        _require_snapshot(transcript_file, transcript_bytes, transcript_id)
        _require_links(directories, files)
        return {
            "schema": "note-generation/1",
            "transcript_sha256": transcript_id,
            "manifest_sha256": manifest["manifest_sha256"],
            "candidates": len(manifest["candidates"]),
            "points": points,
        }
    finally:
        for link in files:
            os.close(link.file_fd)
        for descriptor in open_directories:
            os.close(descriptor)
        for link in reversed(directories):
            os.close(link.child_fd)
            os.close(link.parent_fd)


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
