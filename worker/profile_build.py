"""Measured operating-point choices and candidate profiles from stored evidence.

This is the producing boundary between the sitting evidence store
(`crates/session-core/src/sitting_evidence.rs`) and the canonical profile
contract in `spike/speaker_gate.py`. The math is deliberately not ported:
`enroll`, `leave_one_sitting_out_scores`, `operating_point_choices`, and
`save_profile` remain the single implementations, and this module only reads
the store's durable rows into their inputs. § I's prose is a restatement of
that contract, not the contract.

Two operations are served, mirroring the CLI's report-then-explicit-rerun
shape:

* `profile.choices` computes the measured options and writes them to
  `enrollment-choices/<operation_id>.json`. The document body is
  deterministic over the evidence — no operation id or timestamp inside — so
  identical evidence yields an identical digest, which is how the build
  refuses a selection made against measurements that have since changed.
* `profile.build` recomputes everything, verifies the selected target is one
  of the recomputed choices, and writes the candidate through `save_profile`
  into `profile-candidates/<profile_id>`, where `profile.inspect` and the
  Rust lifecycle's strict-loader bridge take over.

Everything read here is content-free evidence: digests, spans, embeddings.
Raw audio is gone by the time a sitting is readable here, and no transcript
text exists anywhere in these rows.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from .sitting_derivation import MIN_SCORABLE_SECONDS
from .storage import durable_create_new

CHOICES_SCHEMA = "profile-choices/1"
CHOICES_DIR = "enrollment-choices"
CANDIDATES_DIR = "profile-candidates"
SITTINGS_DIR = Path("enrollment") / "sittings"


class ProfileBuildRefused(ValueError):
    """The stored evidence cannot yield the requested artifact."""


def _load_row(directory: Path, name: str, schema: str, sitting_id: str) -> dict:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ProfileBuildRefused(f"sitting {name} row is missing")
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProfileBuildRefused(f"sitting {name} row is unreadable") from error
    if not isinstance(row, dict) or row.get("schema") != schema:
        raise ProfileBuildRefused(f"sitting {name} row has the wrong schema")
    if row.get("sitting_id") != sitting_id:
        raise ProfileBuildRefused(f"sitting {name} row names another sitting")
    return row


def _iso_utc(epoch_seconds: int) -> str:
    return dt.datetime.fromtimestamp(int(epoch_seconds), dt.timezone.utc).isoformat()


def read_saved_evidence(root: Path, encoder_digest: str) -> tuple[list[dict], list[dict]]:
    """Every sitting whose derived voice material is durably stored.

    Raw-retained and rehearsal sittings carry no embeddings and are skipped —
    the evaluator already reports them as pending or spent. Derived material
    under any other encoder identity is refused outright: cosines between
    embedding spaces are not comparable, the same fact behind the `stale`
    profile state.
    """
    sittings_root = root / SITTINGS_DIR
    operators: list[dict] = []
    negatives: list[dict] = []
    if not sittings_root.is_dir() or sittings_root.is_symlink():
        return operators, negatives
    for directory in sorted(sittings_root.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            continue
        sitting_id = directory.name
        if not (directory / "derived.json").is_file():
            continue
        identity = _load_row(directory, "sitting.json", "sitting-evidence/1", sitting_id)
        capture = _load_row(directory, "capture.json", "sitting-capture/1", sitting_id)
        segments = _load_row(directory, "segments.json", "sitting-segments/1", sitting_id)
        derived = _load_row(directory, "derived.json", "sitting-derived/1", sitting_id)

        raw = capture.get("raw")
        if not isinstance(raw, dict):
            raise ProfileBuildRefused("sitting capture row lacks its raw artifact")
        raw_sha256 = raw.get("sha256")
        if segments.get("raw_sha256") != raw_sha256 or derived.get("raw_sha256") != raw_sha256:
            raise ProfileBuildRefused("sitting rows disagree about the recording identity")
        if derived.get("encoder_sha256") != encoder_digest:
            raise ProfileBuildRefused(
                "stored voice material was derived under another encoder"
            )

        embeddings_path = directory / "embeddings.bin"
        if embeddings_path.is_symlink() or not embeddings_path.is_file():
            raise ProfileBuildRefused("sitting embeddings are missing")
        embeddings_bytes = embeddings_path.read_bytes()
        if hashlib.sha256(embeddings_bytes).hexdigest() != derived.get("embeddings_sha256"):
            raise ProfileBuildRefused("sitting embeddings disagree with their derived row")
        count = int(derived.get("embedding_count") or 0)
        dim = int(derived.get("embedding_dim") or 0)
        if count < 1 or dim < 1 or len(embeddings_bytes) != count * dim * 4:
            raise ProfileBuildRefused("sitting embeddings have an impossible shape")
        rows = np.frombuffer(embeddings_bytes, dtype="<f4").reshape(count, dim)

        spans = segments.get("segments")
        if not isinstance(spans, list):
            raise ProfileBuildRefused("sitting segments row lacks its spans")
        durations = []
        for span in spans:
            try:
                length = float(span["end_seconds"]) - float(span["start_seconds"])
            except (KeyError, TypeError, ValueError):
                raise ProfileBuildRefused("a sitting span lacks numeric bounds") from None
            if length >= MIN_SCORABLE_SECONDS:
                durations.append(length)
        if len(durations) != count:
            raise ProfileBuildRefused(
                "sitting embeddings do not align with its scorable spans"
            )

        entry = {
            "sitting_id": sitting_id,
            "kind": identity.get("kind"),
            "source_class": identity.get("source_class"),
            "captured_at_epoch_seconds": capture.get("captured_at_epoch_seconds"),
            "raw_relative_name": raw.get("relative_name"),
            "raw_sha256": raw_sha256,
            "raw_byte_size": int(raw.get("byte_size") or 0),
            "segments_sha256": hashlib.sha256(
                (directory / "segments.json").read_bytes()
            ).hexdigest(),
            "embeddings": [np.asarray(row, dtype=np.float64) for row in rows],
            "durations": durations,
        }
        if identity.get("kind") == "operator-sitting":
            operators.append(entry)
        elif identity.get("kind") == "negative-source":
            negatives.append(entry)
        else:
            raise ProfileBuildRefused("sitting identity row has an unknown kind")
    return operators, negatives


def _measured_inputs(root: Path, encoder_digest: str):
    from speaker_gate import enroll, leave_one_sitting_out_scores, score

    operators, negatives = read_saved_evidence(root, encoder_digest)
    if len(operators) < 2:
        raise ProfileBuildRefused(
            "measured choices need at least two saved voice sessions"
        )
    if not negatives:
        raise ProfileBuildRefused("measured choices need saved comparison speech")
    per_sitting = [(entry["embeddings"], entry["durations"]) for entry in operators]
    profile = enroll(
        [row for entry in operators for row in entry["embeddings"]],
        [duration for entry in operators for duration in entry["durations"]],
    )
    operator_scores = leave_one_sitting_out_scores(per_sitting)
    negative_scores = [
        score(profile, row) for entry in negatives for row in entry["embeddings"]
    ]
    negative_seconds = sum(
        duration for entry in negatives for duration in entry["durations"]
    )
    return operators, negatives, profile, operator_scores, negative_scores, negative_seconds


def choices_document(root: Path, encoder_digest: str) -> bytes:
    """The deterministic measured-choices document for the current evidence."""
    from speaker_gate import operating_point_choices

    operators, negatives, _profile, operator_scores, negative_scores, negative_seconds = (
        _measured_inputs(root, encoder_digest)
    )
    try:
        choices = operating_point_choices(
            operator_scores,
            negative_scores,
            negative_scorable_seconds=negative_seconds,
        )
    except ValueError as error:
        raise ProfileBuildRefused(str(error)) from None
    document = {
        "schema": CHOICES_SCHEMA,
        "encoder_sha256": encoder_digest,
        "evidence": {
            "sittings": [
                {"sitting_id": e["sitting_id"], "audio_sha256": e["raw_sha256"]}
                for e in operators
            ],
            "negative_sources": [
                {"sitting_id": e["sitting_id"], "audio_sha256": e["raw_sha256"]}
                for e in negatives
            ],
        },
        "n_operator_scores": len(operator_scores),
        "n_negative_scores": len(negative_scores),
        "negative_scorable_seconds": negative_seconds,
        "choices": choices,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_choices(root: Path, operation_id: str, encoder_digest: str) -> str:
    """Write the measured choices for Rust to re-read, returning their digest."""
    body = choices_document(root, encoder_digest)
    directory = root / CHOICES_DIR
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / f"{operation_id}.json"
    if path.is_symlink():
        raise ProfileBuildRefused("the choices destination is unsafe")
    if path.exists():
        path.unlink()
    durable_create_new(path, body)
    return hashlib.sha256(body).hexdigest()


def build_candidate(
    root: Path,
    profile_id: str,
    selected_target: float,
    encoder_digest: str,
) -> str:
    """Recompute the choices, verify the selection, and write the candidate.

    The caller cannot supply a threshold or a rate — only a target that must
    equal one of the recomputed choices, which is `save_profile`'s own
    contract restated at this boundary.
    """
    from speaker_gate import operating_point_choices, save_profile

    operators, negatives, profile, operator_scores, negative_scores, negative_seconds = (
        _measured_inputs(root, encoder_digest)
    )
    try:
        choices = operating_point_choices(
            operator_scores,
            negative_scores,
            negative_scorable_seconds=negative_seconds,
        )
    except ValueError as error:
        raise ProfileBuildRefused(str(error)) from None
    if not any(choice["target_frr"] == selected_target for choice in choices):
        raise ProfileBuildRefused(
            "the selected option is not one of the measured choices"
        )

    def _sitting_manifest(entry: dict) -> dict:
        return {
            "audio": f"enrollment/sittings/{entry['sitting_id']}/audio.raw",
            "audio_sha256": entry["raw_sha256"],
            "captured_at": _iso_utc(entry["captured_at_epoch_seconds"]),
        }

    negative_manifest = [
        {
            "source_class": entry["source_class"],
            "audio": f"enrollment/sittings/{entry['sitting_id']}/audio.raw",
            "segments": f"enrollment/sittings/{entry['sitting_id']}/segments.json",
            "audio_sha256": entry["raw_sha256"],
            "audio_samples": max(1, entry["raw_byte_size"] // 2),
            "segments_sha256": entry["segments_sha256"],
            "segments_schema": "sitting-segments/1",
            "captured_at": _iso_utc(entry["captured_at_epoch_seconds"]),
            "scorable_segments": len(entry["embeddings"]),
            "scorable_seconds": sum(entry["durations"]),
        }
        for entry in negatives
    ]

    # The quarantine shape both `profile.inspect` and the Rust bridge pin:
    # one private directory per candidate holding exactly `voiceprint.json`.
    candidates = root / CANDIDATES_DIR
    candidates.mkdir(mode=0o700, exist_ok=True)
    directory = candidates / profile_id
    if directory.is_symlink():
        raise ProfileBuildRefused("the candidate destination is unsafe")
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / "voiceprint.json"
    if path.is_symlink():
        raise ProfileBuildRefused("the candidate destination is unsafe")
    if path.exists():
        path.unlink()
    try:
        save_profile(
            path,
            profile,
            selected_target=selected_target,
            operator_scores=operator_scores,
            negative_scores=negative_scores,
            held_out="leave-one-sitting-out",
            sittings=[_sitting_manifest(entry) for entry in operators],
            negative_sources=negative_manifest,
            encoder_fingerprint_value=encoder_digest,
        )
    except (SystemExit, ValueError) as error:
        if path.exists() and not path.is_symlink():
            os.unlink(path)
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
        raise ProfileBuildRefused(f"the profile could not be saved: {error}") from None
    return hashlib.sha256(path.read_bytes()).hexdigest()
