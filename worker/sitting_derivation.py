"""Derive segment evidence and embeddings from one recorded enrollment sitting.

This is the producer for session-core's sitting evidence store
(`crates/session-core/src/sitting_evidence.rs`), whose `record_segments` and
`store_derived_material` rows previously had nothing to feed them. The division
of authority copies the transcript-restoration pattern: the worker computes and
writes its outputs into the sitting's WORK directory only, and returns digests;
the Rust `SittingEvidenceAuthority` re-reads, re-validates, and owns every
durable row and every deletion. Nothing here touches `sittings/<id>/`.

Content boundary: deriving segments requires transcribing the sitting, and the
transcript text exists only inside this process. The segments artifact carries
times, counts, and digests — never words. `audio.raw` is headerless mono
16 kHz little-endian 16-bit PCM, the same sample format every other capture
artifact in this repository uses; the store treats it as opaque bytes, so the
format contract lives here and in the recorder that writes it.

The embedding callable is an argument rather than an import, matching
`speaker_gate.py`: the adapter supplies the packaged ONNX chain, tests supply
deterministic fakes, and no encoder is admitted by this module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np

from .storage import durable_create_new

RATE = 16_000
# Mirrors enrollment_guidance::MIN_SCORABLE_SECONDS and speaker_gate.MIN_SCORABLE_S;
# cross-pinned by tests/test_distribution_tooling.py.
MIN_SCORABLE_SECONDS = 2.0
# Mirror the store's write-time bounds (sitting_evidence.rs); the worker refuses
# before producing an artifact the store would refuse to admit.
RAW_MAX_BYTES = 1_073_741_824
SEGMENTS_MAX_BYTES = 1_048_576
EMBEDDINGS_MAX_BYTES = 16_777_216

RAW_AUDIO_NAME = "audio.raw"
SEGMENTS_NAME = "segments.json"
EMBEDDINGS_NAME = "embeddings.bin"

DERIVATION_SCHEMA = "sitting-derivation/1"


class DerivationRefused(ValueError):
    """The sitting cannot yield admissible derived material."""


def read_raw_sitting_audio(work_dir: Path) -> tuple[np.ndarray, str]:
    """The sitting's raw capture as float32 in [-1, 1), with its digest."""
    path = work_dir / RAW_AUDIO_NAME
    if path.is_symlink() or not path.is_file():
        raise DerivationRefused("sitting audio is missing or unsafe")
    data = path.read_bytes()
    if not data:
        raise DerivationRefused("sitting audio is empty")
    if len(data) > RAW_MAX_BYTES:
        raise DerivationRefused("sitting audio exceeds its bound")
    if len(data) % 2:
        raise DerivationRefused("sitting audio is not 16-bit mono PCM")
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    return samples, hashlib.sha256(data).hexdigest()


def validate_spans(segments: list[dict], duration_seconds: float) -> list[dict]:
    """Times only, finite, in order, non-overlapping, inside the recording.

    Transcription may overshoot the final sample by a frame; the end is clamped
    to the recording rather than refused. Ordering and overlap are refused
    outright — the store enforces the same and a silent repair here would let
    the two authorities disagree about what was measured.
    """
    spans: list[dict] = []
    for segment in segments:
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            raise DerivationRefused("a segment lacks numeric bounds") from None
        if not (np.isfinite(start) and np.isfinite(end)):
            raise DerivationRefused("a segment has non-finite bounds")
        end = min(end, duration_seconds)
        if start < 0.0 or start >= end:
            raise DerivationRefused("a segment lies outside the recording")
        spans.append({"start_seconds": start, "end_seconds": end})
    for before, after in zip(spans, spans[1:]):
        if after["start_seconds"] < before["end_seconds"]:
            raise DerivationRefused("segments overlap or are out of order")
    return spans


def _write_or_match(path: Path, data: bytes) -> None:
    """Create durably, or accept an identical prior attempt.

    A crash between the two artifact writes leaves the first one behind; a
    deterministic re-derivation reproduces it byte-identically and may proceed.
    Any disagreement is refused — the sitting can be abandoned to a rehearsal
    label, never silently overwritten.
    """
    if path.is_symlink():
        raise DerivationRefused("an existing derived artifact is unsafe")
    if path.exists():
        if path.is_file() and path.read_bytes() == data:
            return
        raise DerivationRefused("an existing derived artifact disagrees with this derivation")
    durable_create_new(path, data)


def derive_sitting_material(
    work_dir: Path,
    sitting_id: str,
    *,
    encoder_sha256: str,
    onnx_artifact_sha256: str | None,
    embed_segment: Callable[[np.ndarray], np.ndarray],
    transcribe_audio: Callable[[np.ndarray], list[dict]],
) -> dict[str, str]:
    """Segment one sitting, embed its scorable speech, and return the digests.

    Writes `segments.json` (content-free spans plus the embedding join
    metadata) and `embeddings.bin` (unit-normalized float32-le rows, one per
    scorable segment, in order) into the work directory.
    """
    samples, raw_sha256 = read_raw_sitting_audio(work_dir)
    duration_seconds = len(samples) / RATE
    spans = validate_spans(transcribe_audio(samples), duration_seconds)
    scorable = [
        span for span in spans
        if span["end_seconds"] - span["start_seconds"] >= MIN_SCORABLE_SECONDS
    ]
    if not scorable:
        raise DerivationRefused("no scorable speech in this sitting")

    rows: list[np.ndarray] = []
    for span in scorable:
        clip = samples[
            int(span["start_seconds"] * RATE): int(span["end_seconds"] * RATE)
        ]
        embedding = np.asarray(embed_segment(clip), dtype=np.float64).reshape(-1)
        if embedding.size == 0 or not np.all(np.isfinite(embedding)):
            raise DerivationRefused("the encoder produced an unusable embedding")
        norm = float(np.linalg.norm(embedding))
        if norm == 0.0:
            raise DerivationRefused("the encoder produced an unusable embedding")
        rows.append((embedding / norm).astype("<f4"))
    dimensions = {row.size for row in rows}
    if len(dimensions) != 1:
        raise DerivationRefused("the encoder produced inconsistent embedding dimensions")
    embedding_dim = dimensions.pop()

    embeddings_bytes = np.stack(rows).tobytes()
    if len(embeddings_bytes) > EMBEDDINGS_MAX_BYTES:
        raise DerivationRefused("derived embeddings exceed their bound")
    embeddings_sha256 = hashlib.sha256(embeddings_bytes).hexdigest()

    document = {
        "schema": DERIVATION_SCHEMA,
        "sitting_id": sitting_id,
        "raw_sha256": raw_sha256,
        "sample_rate": RATE,
        "samples": len(samples),
        "segments": spans,
        "embedding": {
            "count": len(rows),
            "dim": int(embedding_dim),
            "sha256": embeddings_sha256,
            "encoder_sha256": encoder_sha256,
            "onnx_artifact_sha256": onnx_artifact_sha256,
        },
    }
    segments_bytes = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    if len(segments_bytes) > SEGMENTS_MAX_BYTES:
        raise DerivationRefused("derived segment evidence exceeds its bound")

    _write_or_match(work_dir / SEGMENTS_NAME, segments_bytes)
    _write_or_match(work_dir / EMBEDDINGS_NAME, embeddings_bytes)
    return {
        "segments": hashlib.sha256(segments_bytes).hexdigest(),
        "embeddings": embeddings_sha256,
    }
