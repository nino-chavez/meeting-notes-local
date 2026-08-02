#!/usr/bin/env python3
"""Isolated, content-free MLX Whisper word-timestamp benchmark.

This is deliberately not a worker, product schema, or Preview command.  It
transcribes only a registered synthetic or public fixture, requests
``word_timestamps=True``, and writes aggregate measurements without retaining
recognized text.  The shipped transcription path remains unchanged:
``condition_on_previous_text=False``.

The optional continuation arm is a comparator for long-form seams only.  A
passing run is research evidence, not permission to change the shipped default.

Examples:
  python3 spike/mlx_word_timestamp_benchmark.py --fixture synthetic-silence-v1 \\
    --out /tmp/mlx-word-timestamps.json
  python3 spike/mlx_word_timestamp_benchmark.py --fixture public-longform-v1 \\
    --fixture-root /path/to/public-fixtures --out /tmp/mlx-word-timestamps.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import resource
import sys
import time
import wave
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

RATE = 16_000
DEFAULT_MODEL_ID = "mlx-community/whisper-large-v3-turbo"
SCHEMA = "mlx-word-timestamp-benchmark/1"
FIXTURE_SCHEMA = "mlx-word-timestamp-fixture/1"
TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.I)
FILLERS = {"um", "uh", "erm", "hmm", "mm"}
NEGATIONS = {"no", "not", "never", "none", "cannot", "can't", "won't", "isn't", "wasn't", "don't", "didn't"}
CORRECTION_CUES = {"sorry", "rather", "actually", "mean", "meant", "correction"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.casefold().encode("utf-8")).hexdigest()


def synthetic_silence() -> np.ndarray:
    """A deterministic three-second no-speech fixture; never writes audio to disk."""
    return np.zeros(RATE * 3, dtype=np.float32)


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (RATE, 1, 2):
            raise ValueError("fixture must be 16 kHz, mono, 16-bit WAV")
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


def fixture_path(fixture_root: Path) -> Path:
    return fixture_root / "manifest.json"


def load_fixture(fixture_id: str, fixture_root: Path | None) -> tuple[dict[str, Any], np.ndarray]:
    if fixture_id == "synthetic-silence-v1":
        return (
            {
                "schema": FIXTURE_SCHEMA,
                "id": fixture_id,
                "source": "synthetic",
                "expect_speech": False,
                "seams_s": [],
                "expected": {"words": 0},
            },
            synthetic_silence(),
        )
    if fixture_root is None:
        raise ValueError("a public fixture requires --fixture-root; the repository contains no speech audio")
    manifest_file = fixture_path(fixture_root)
    manifest = json.loads(manifest_file.read_text())
    if manifest.get("schema") != FIXTURE_SCHEMA:
        raise ValueError("fixture manifest has an unknown schema")
    fixture = next((item for item in manifest.get("fixtures", []) if item.get("id") == fixture_id), None)
    if not fixture or fixture.get("source") != "public":
        raise ValueError("fixture id is not a registered public fixture")
    audio = fixture_root / fixture["audio"]
    if not audio.is_file() or sha256_file(audio) != fixture.get("audio_sha256"):
        raise ValueError("public fixture audio is missing or its digest does not match the manifest")
    return fixture, load_wav(audio)


def normalized_words(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract recognized words without ever returning their text to the caller."""
    words: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(result.get("segments", [])):
        for word in segment.get("words") or []:
            text = str(word.get("word", "")).strip()
            match = TOKEN.search(text)
            if not match:
                continue
            words.append(
                {
                    "token": match.group(0).casefold(),
                    "start": word.get("start"),
                    "end": word.get("end"),
                    "segment": segment_index,
                }
            )
    return words


def timing_metrics(words: list[dict[str, Any]], duration_s: float) -> dict[str, int]:
    finite = 0
    non_monotonic = 0
    invalid_bounds = 0
    prior_end = -1.0
    for word in words:
        start, end = word["start"], word["end"]
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            invalid_bounds += 1
            continue
        finite += 1
        if start < 0 or end < start or end > duration_s + 0.05:
            invalid_bounds += 1
        if start + 1e-6 < prior_end:
            non_monotonic += 1
        prior_end = max(prior_end, end)
    return {"timed_words": finite, "timing_non_monotonic": non_monotonic, "timing_out_of_bounds": invalid_bounds}


def lexical_metrics(words: list[dict[str, Any]]) -> dict[str, int]:
    tokens = [word["token"] for word in words]
    repeated_words = sum(left == right for left, right in zip(tokens, tokens[1:]))
    pairs = [" ".join(tokens[index:index + 2]) for index in range(max(0, len(tokens) - 1))]
    pair_counts = Counter(pairs)
    looping_pairs = sum(count - 1 for count in pair_counts.values() if count >= 2)
    return {
        "words": len(tokens),
        "fillers": sum(token in FILLERS for token in tokens),
        "false_start_cues": sum(token in CORRECTION_CUES for token in tokens),
        "repeated_words": repeated_words,
        "looping_pairs": looping_pairs,
        "correction_cues": sum(token in CORRECTION_CUES for token in tokens),
        "number_tokens": sum(any(char.isdigit() for char in token) for token in tokens),
        "negation_tokens": sum(token in NEGATIONS for token in tokens),
    }


def expected_metric_deltas(words: list[dict[str, Any]], expected: dict[str, Any]) -> dict[str, int]:
    """Compare only token digests/counts supplied by a public fixture, never text."""
    observed_hashes = Counter(token_hash(word["token"]) for word in words)
    deltas: dict[str, int] = {}
    for label, required in (expected.get("token_hash_counts") or {}).items():
        wanted = sum(int(value) for value in required.values())
        got = sum(min(observed_hashes[digest], int(count)) for digest, count in required.items())
        deltas[f"{label}_matched"] = got
        deltas[f"{label}_missing"] = wanted - got
    return deltas


def seam_metrics(words: list[dict[str, Any]], seams_s: list[float]) -> dict[str, int]:
    # A duplicate is observable without a transcript reference.  A missing word
    # needs fixture-provided public token digests and remains a separate delta.
    duplicates = 0
    for seam in seams_s:
        around = [word["token"] for word in words if isinstance(word["start"], (int, float)) and abs(word["start"] - seam) <= 1.5]
        duplicates += sum(left == right for left, right in zip(around, around[1:]))
    return {"seams": len(seams_s), "seam_local_duplicates": duplicates}


def transcribe(audio: np.ndarray, model: str, continuation: bool) -> dict[str, Any]:
    import mlx_whisper

    return mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        language="en",
        word_timestamps=True,
        condition_on_previous_text=continuation,
    )


def validated_local_model(model: Path) -> tuple[Path, str]:
    supplied = model.expanduser().resolve()
    weights = supplied / "weights.safetensors"
    if not supplied.is_dir() or not weights.is_file():
        raise ValueError("--model must be an explicit local model directory containing weights.safetensors")
    return supplied, sha256_file(weights)


def one_run(audio: np.ndarray, fixture: dict[str, Any], model: str, continuation: bool) -> dict[str, Any]:
    started = time.perf_counter()
    result = transcribe(audio, model, continuation)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    words = normalized_words(result)
    duration_s = len(audio) / RATE
    metrics = lexical_metrics(words) | timing_metrics(words, duration_s) | seam_metrics(words, fixture.get("seams_s", []))
    expected = fixture.get("expected") or {}
    for metric, expected_count in (expected.get("metric_counts") or {}).items():
        if metric in metrics:
            metrics[f"{metric}_expected_delta"] = metrics[metric] - int(expected_count)
    metrics.update(expected_metric_deltas(words, expected))
    metrics["silence_hallucination"] = int(not fixture.get("expect_speech") and metrics["words"] > 0)
    metrics["early_eot"] = int(bool(fixture.get("expect_speech")) and metrics["words"] == 0)
    minimum_words = int(expected.get("minimum_words", 1 if fixture.get("expect_speech") else 0))
    metrics["truncation"] = int(metrics["words"] < minimum_words)
    raw_peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    metrics["peak_rss_bytes"] = raw_peak_rss if sys.platform == "darwin" else raw_peak_rss * 1024
    return {"elapsed_ms": elapsed_ms, "metrics": metrics, "result_shape": {"segments": len(result.get("segments", []))}}


def stable_fingerprint(run: dict[str, Any]) -> str:
    # Repeatability compares non-content output only.  It cannot certify word-level
    # equality; public fixtures may supply token-digest checks for that purpose.
    stable_metrics = {key: value for key, value in run["metrics"].items() if key != "peak_rss_bytes"}
    encoded = json.dumps(stable_metrics | run["result_shape"], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def benchmark(audio: np.ndarray, fixture: dict[str, Any], model: str, repetitions: int, selected_arm: str = "both") -> dict[str, Any]:
    arms = {}
    registered_arms = (("baseline_no_previous_text", False), ("continuation_seam_comparator", True))
    if selected_arm != "both":
        registered_arms = tuple(item for item in registered_arms if item[0] == selected_arm)
    for arm_index, (name, continuation) in enumerate(registered_arms):
        runs = [one_run(audio, fixture, model, continuation) for _ in range(repetitions)]
        fingerprints = [stable_fingerprint(run) for run in runs]
        arms[name] = {
            "condition_on_previous_text": continuation,
            "first_run_process_state": "model_not_loaded_in_process" if arm_index == 0 else "warm_after_previous_arm",
            "cold_elapsed_ms": runs[0]["elapsed_ms"] if arm_index == 0 else None,
            "first_run_elapsed_ms": runs[0]["elapsed_ms"],
            "warm_elapsed_ms": runs[-1]["elapsed_ms"] if len(runs) > 1 else None,
            "repeatability_distinct_content_free_fingerprints": len(set(fingerprints)),
            "runs": runs,
        }
    return arms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixture", default="synthetic-silence-v1")
    parser.add_argument("--fixture-root", type=Path, help="directory containing a registered public fixture manifest and WAV")
    parser.add_argument("--model", type=Path, required=True, help="explicit local model directory containing weights.safetensors")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="content-free model identity recorded in the report")
    parser.add_argument(
        "--arm",
        choices=("both", "baseline_no_previous_text", "continuation_seam_comparator"),
        default="both",
        help="run one arm in a fresh process for fair latency/memory measurement, or both for a quick quality comparison",
    )
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    try:
        model_path, model_weights_sha256 = validated_local_model(args.model)
        fixture, audio = load_fixture(args.fixture, args.fixture_root)
        import mlx_whisper  # noqa: F401
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema": SCHEMA, "status": "unavailable", "fixture": args.fixture, "model": args.model, "reason": str(exc)}
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        return 2
    report = {
        "schema": SCHEMA,
        "status": "measured",
        "fixture": {"id": fixture["id"], "source": fixture["source"], "duration_s": round(len(audio) / RATE, 3)},
        "runtime": {
            "framework": "mlx-whisper",
            "framework_version": importlib.metadata.version("mlx-whisper"),
            "platform": f"{platform.system()}-{platform.machine()}",
            "model_id": args.model_id,
            "model_weights_sha256": model_weights_sha256,
            "language": "en",
            "sample_rate_hz": RATE,
            "word_timestamps": True,
            "timing_mode": "decoded",
            "alignment_method": "mlx-whisper word_timestamps",
        },
        "arms": benchmark(audio, fixture, str(model_path), args.repetitions, args.arm),
        "limits": [
            "aggregate metrics only; recognized text is never written",
            "first-call means the model was not loaded in this process; OS/file-cache state is uncontrolled and the model digest is read first",
            "when --arm=both, the second arm runs after the first and its timing is warm-biased; run each arm in a fresh process for latency comparison",
            "continuation arm is a comparator, not a shipped-default change",
            "no product records, Preview data, or private audio were read",
        ],
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
