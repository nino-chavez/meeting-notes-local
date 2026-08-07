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
    --model /path/to/pinned/whisper-large-v3-turbo \\
    --out /tmp/mlx-word-timestamps.json
  python3 spike/mlx_word_timestamp_benchmark.py --fixture public-longform-v1 \\
    --fixture-root /path/to/public-fixtures \\
    --model /path/to/pinned/whisper-large-v3-turbo \\
    --out /tmp/mlx-word-timestamps.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
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
SCHEMA = "mlx-word-timestamp-benchmark/2"
FIXTURE_SCHEMA = "mlx-word-timestamp-fixture/2"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BUILD_RUNTIME = REPOSITORY_ROOT / "worker" / "build_runtime.sh"
MLX_WHISPER_LOCK = REPOSITORY_ROOT / "worker" / "requirements-mlx-whisper.lock"
ALPHA_RUNTIME_LOCK = REPOSITORY_ROOT / "worker" / "requirements-alpha.lock"
TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.I)
FILLERS = {"um", "uh", "erm", "hmm", "mm"}
NEGATIONS = {"no", "not", "never", "none", "cannot", "can't", "won't", "isn't", "wasn't", "don't", "didn't"}
CORRECTION_CUES = {"sorry", "rather", "actually", "mean", "meant", "correction"}
KNOWN_COVERAGE = frozenset(
    {
        "silence",
        "timing",
        "repeatability",
        "latency",
        "memory",
        "fillers",
        "false_starts",
        "repeated_words",
        "corrections",
        "names",
        "numbers",
        "negation",
        "looping",
        "truncation",
    }
)
EXPECTED_KEYS = frozenset({"metric_counts", "token_hash_counts", "minimum_words"})
COVERAGE_METRICS = {
    "fillers": "fillers",
    "false_starts": "false_start_cues",
    "repeated_words": "repeated_words",
    "corrections": "correction_cues",
    "numbers": "number_tokens",
    "negation": "negation_tokens",
    "looping": "looping_pairs",
}
TOKEN_HASH_COVERAGE = frozenset(
    {"fillers", "false_starts", "repeated_words", "corrections", "names", "numbers", "negation"}
)
KNOWN_METRIC_EXPECTATIONS = frozenset({"words", *COVERAGE_METRICS.values()})
DECODE_CONFIG = {
    "language": "en",
    "verbose": None,
    "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    "compression_ratio_threshold": 2.4,
    "logprob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    "initial_prompt": None,
    "word_timestamps": True,
    "clip_timestamps": "0",
    "hallucination_silence_threshold": None,
    "timing_mode": "decoded",
    "alignment_method": "cross-attention dynamic-time-warping",
}
ARM_CONDITIONS = {
    "baseline_no_previous_text": False,
    "continuation_seam_comparator": True,
}


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


def is_within(path: Path, parent: Path) -> bool:
    try:
        return path.is_relative_to(parent)
    except ValueError:
        return False


def protected_roots(extra_roots: list[Path] | tuple[Path, ...] = ()) -> tuple[Path, ...]:
    return tuple(root.expanduser().resolve() for root in (REPOSITORY_ROOT, *extra_roots))


def inside_protected_root(path: Path, extra_roots: list[Path] | tuple[Path, ...] = ()) -> bool:
    return any(is_within(path, root) for root in protected_roots(extra_roots))


def validate_output_target(path: Path, extra_roots: list[Path] | tuple[Path, ...] = ()) -> Path:
    """Permit only a new, external content-free receipt."""
    target = path.expanduser().resolve()
    if inside_protected_root(target, extra_roots):
        raise ValueError("--out must be outside this repository and every explicit protected root")
    if not target.parent.is_dir():
        raise ValueError("--out parent directory does not exist")
    if target.exists():
        raise ValueError("--out must name a new receipt; refusing to overwrite")
    return target


def validate_public_fixture_root(
    path: Path, extra_roots: list[Path] | tuple[Path, ...] = ()
) -> Path:
    """Public speech fixtures live outside source, Preview, and product trees."""
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise ValueError("--fixture-root may not be a symlink")
    root = supplied.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("--fixture-root must be a directory")
    if inside_protected_root(root, extra_roots):
        raise ValueError("--fixture-root must be outside this repository and every explicit protected root")
    return root


def validate_fixture_definition(fixture: dict[str, Any]) -> dict[str, Any]:
    coverage = fixture.get("coverage")
    if (
        not isinstance(coverage, list)
        or any(not isinstance(item, str) for item in coverage)
        or len(coverage) != len(set(coverage))
    ):
        raise ValueError("fixture coverage must be a unique string list")
    unknown_coverage = set(coverage) - KNOWN_COVERAGE
    if unknown_coverage:
        raise ValueError(f"fixture coverage contains unknown metrics: {sorted(unknown_coverage)}")
    if fixture.get("seams_s"):
        raise ValueError("seam evaluation is mechanically unsupported by fixture schema v2")
    expected = fixture.get("expected")
    if not isinstance(expected, dict):
        raise ValueError("fixture expected values must be an object")
    unknown_expected = set(expected) - EXPECTED_KEYS
    if unknown_expected:
        raise ValueError(f"fixture expected contains unknown keys: {sorted(unknown_expected)}")
    metric_counts = expected.get("metric_counts", {})
    if not isinstance(metric_counts, dict):
        raise ValueError("expected metric_counts must be an object")
    unknown_metrics = set(metric_counts) - KNOWN_METRIC_EXPECTATIONS
    if unknown_metrics:
        raise ValueError(f"fixture expected contains unknown metric counts: {sorted(unknown_metrics)}")
    token_counts = expected.get("token_hash_counts", {})
    if not isinstance(token_counts, dict):
        raise ValueError("expected token_hash_counts must be an object")
    unknown_token_coverage = set(token_counts) - TOKEN_HASH_COVERAGE
    if unknown_token_coverage:
        raise ValueError(
            f"fixture expected contains unknown token coverage: {sorted(unknown_token_coverage)}"
        )
    for category, metric in COVERAGE_METRICS.items():
        if category in coverage and metric not in metric_counts:
            raise ValueError(f"coverage {category} requires expected metric count {metric}")
        if metric in metric_counts and category not in coverage:
            raise ValueError(f"expected metric count {metric} lacks registered coverage {category}")
    for category in TOKEN_HASH_COVERAGE:
        if category in coverage and category not in token_counts:
            raise ValueError(f"coverage {category} requires expected token hashes")
        if category in token_counts and category not in coverage:
            raise ValueError(f"expected token hashes {category} lack registered coverage")
    if "silence" in coverage and metric_counts.get("words") != 0:
        raise ValueError("silence coverage requires expected words == 0")
    if "words" in metric_counts and "silence" not in coverage:
        raise ValueError("expected word count lacks registered silence coverage")
    if "truncation" in coverage and "minimum_words" not in expected:
        raise ValueError("truncation coverage requires expected minimum_words")
    if "minimum_words" in expected and "truncation" not in coverage:
        raise ValueError("expected minimum_words lacks registered truncation coverage")
    return fixture


def load_fixture(
    fixture_id: str,
    fixture_root: Path | None,
    extra_protected_roots: list[Path] | tuple[Path, ...] = (),
) -> tuple[dict[str, Any], np.ndarray]:
    if fixture_id == "synthetic-silence-v1":
        fixture = validate_fixture_definition(
            {
                "schema": FIXTURE_SCHEMA,
                "id": fixture_id,
                "source": "synthetic",
                "license": "generated-synthetic",
                "source_ref": "in-memory float32 zero signal",
                "expect_speech": False,
                "coverage": ["silence", "timing", "repeatability", "latency", "memory"],
                "expected": {"metric_counts": {"words": 0}},
            }
        )
        return fixture, synthetic_silence()
    if fixture_root is None:
        raise ValueError("a public fixture requires --fixture-root; the repository contains no speech audio")
    fixture_root = validate_public_fixture_root(fixture_root, extra_protected_roots)
    manifest_file = fixture_path(fixture_root)
    if manifest_file.is_symlink():
        raise ValueError("fixture manifest may not be a symlink")
    manifest = json.loads(manifest_file.read_text())
    if manifest.get("schema") != FIXTURE_SCHEMA:
        raise ValueError("fixture manifest has an unknown schema")
    fixture = next((item for item in manifest.get("fixtures", []) if item.get("id") == fixture_id), None)
    if not fixture or fixture.get("source") != "public":
        raise ValueError("fixture id is not a registered public fixture")
    if not isinstance(fixture.get("license"), str) or not fixture["license"].strip():
        raise ValueError("public fixture lacks a license declaration")
    if not isinstance(fixture.get("source_ref"), str) or not fixture["source_ref"].strip():
        raise ValueError("public fixture lacks a provenance reference")
    audio_name = fixture.get("audio")
    if not isinstance(audio_name, str):
        raise ValueError("public fixture has no audio path")
    supplied_audio = fixture_root / audio_name
    if supplied_audio.is_symlink():
        raise ValueError("public fixture audio may not be a symlink")
    audio = supplied_audio.resolve()
    if not is_within(audio, fixture_root):
        raise ValueError("public fixture audio escapes its registered root")
    if not audio.is_file() or sha256_file(audio) != fixture.get("audio_sha256"):
        raise ValueError("public fixture audio is missing or its digest does not match the manifest")
    return validate_fixture_definition(fixture), load_wav(audio)


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
    non_finite_values = 0
    missing_or_non_numeric_values = 0
    non_monotonic = 0
    invalid_bounds = 0
    prior_end = -1.0
    for word in words:
        start, end = word["start"], word["end"]
        values = (start, end)
        invalid_value_count = sum(
            not isinstance(value, (int, float)) or isinstance(value, bool)
            for value in values
        )
        missing_or_non_numeric_values += invalid_value_count
        if invalid_value_count:
            continue
        non_finite = sum(not math.isfinite(float(value)) for value in values)
        non_finite_values += non_finite
        if non_finite:
            continue
        finite += 1
        if start < 0 or end < start or end > duration_s + 0.05:
            invalid_bounds += 1
        if start + 1e-6 < prior_end:
            non_monotonic += 1
        prior_end = max(prior_end, end)
    return {
        "timed_words": finite,
        "timing_non_finite_values": non_finite_values,
        "timing_missing_or_non_numeric_values": missing_or_non_numeric_values,
        "timing_non_monotonic": non_monotonic,
        "timing_out_of_bounds": invalid_bounds,
    }


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


def transcribe(audio: np.ndarray, model: str, continuation: bool) -> dict[str, Any]:
    import mlx_whisper

    return mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        language=DECODE_CONFIG["language"],
        verbose=DECODE_CONFIG["verbose"],
        temperature=tuple(DECODE_CONFIG["temperature"]),
        compression_ratio_threshold=DECODE_CONFIG["compression_ratio_threshold"],
        logprob_threshold=DECODE_CONFIG["logprob_threshold"],
        no_speech_threshold=DECODE_CONFIG["no_speech_threshold"],
        initial_prompt=DECODE_CONFIG["initial_prompt"],
        word_timestamps=DECODE_CONFIG["word_timestamps"],
        clip_timestamps=DECODE_CONFIG["clip_timestamps"],
        hallucination_silence_threshold=DECODE_CONFIG[
            "hallucination_silence_threshold"
        ],
        condition_on_previous_text=continuation,
    )


def pinned_value(document: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}='([^']+)'$", document, re.MULTILINE)
    if not match:
        raise RuntimeError(f"canonical runtime pin {name} is unavailable")
    return match.group(1)


def double_quoted_pinned_value(document: str, name: str) -> str:
    match = re.search(rf'^{re.escape(name)}="([^"]+)"$', document, re.MULTILINE)
    if not match:
        raise RuntimeError(f"canonical runtime pin {name} is unavailable")
    return match.group(1)


def locked_version(path: Path, distribution: str) -> str:
    match = re.search(
        rf"^{re.escape(distribution)}==([^ \\\n]+)", path.read_text(), re.MULTILINE
    )
    if not match:
        raise RuntimeError(f"canonical runtime pin for {distribution} is unavailable")
    return match.group(1)


def canonical_identity_expectations() -> dict[str, str]:
    build = BUILD_RUNTIME.read_text()
    python_url = pinned_value(build, "PYTHON_URL")
    python_version = re.search(r"cpython-(\d+\.\d+\.\d+)", python_url)
    model_cache = double_quoted_pinned_value(build, "WHISPER_DEFAULT")
    model_slug = re.search(r"models--([^/]+)/snapshots/", model_cache)
    if not python_version:
        raise RuntimeError("canonical Python version pin is unavailable")
    if not model_slug or "--" not in model_slug.group(1):
        raise RuntimeError("canonical model ID pin is unavailable")
    return {
        "python_version": python_version.group(1),
        "mlx_whisper_version": locked_version(MLX_WHISPER_LOCK, "mlx-whisper"),
        "mlx_version": locked_version(ALPHA_RUNTIME_LOCK, "mlx"),
        "model_id": model_slug.group(1).replace("--", "/", 1),
        "model_revision": pinned_value(build, "WHISPER_REVISION"),
        "config_sha256": pinned_value(build, "WHISPER_CONFIG_SHA256"),
        "weights_sha256": pinned_value(build, "WHISPER_WEIGHTS_SHA256"),
    }


def installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def existing_digest(path: Path) -> str | None:
    try:
        return sha256_file(path) if path.is_file() else None
    except OSError:
        return None


def execution_identity(model: Path, expected: dict[str, str] | None = None) -> dict[str, Any]:
    expected = expected or canonical_identity_expectations()
    supplied = model.expanduser().resolve()
    config_digest = existing_digest(supplied / "config.json")
    weights_digest = existing_digest(supplied / "weights.safetensors")
    observed = {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "mlx_whisper_version": installed_version("mlx-whisper"),
        "mlx_version": installed_version("mlx"),
        "model_directory": str(supplied),
        "model_id": expected["model_id"] if config_digest == expected["config_sha256"] and weights_digest == expected["weights_sha256"] else None,
        "model_revision": expected["model_revision"] if config_digest == expected["config_sha256"] and weights_digest == expected["weights_sha256"] else None,
        "config_sha256": config_digest,
        "weights_sha256": weights_digest,
    }
    matches = {
        key: observed[key] == expected[key]
        for key in (
            "python_version",
            "mlx_whisper_version",
            "mlx_version",
            "model_id",
            "model_revision",
            "config_sha256",
            "weights_sha256",
        )
    }
    return {
        "observed": observed,
        "expected": expected,
        "matches_expected": matches,
        "canonical_identity_match": all(matches.values()),
    }


def require_pinned_execution_identity(identity: dict[str, Any]) -> Path:
    mismatches = [
        key for key, matches in identity["matches_expected"].items() if not matches
    ]
    if mismatches:
        raise ValueError(f"pinned execution identity mismatch: {', '.join(mismatches)}")
    return Path(identity["observed"]["model_directory"])


def write_receipt(path: Path, report: dict[str, Any]) -> None:
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def one_run(audio: np.ndarray, fixture: dict[str, Any], model: str, continuation: bool) -> dict[str, Any]:
    started = time.perf_counter()
    result = transcribe(audio, model, continuation)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    words = normalized_words(result)
    duration_s = len(audio) / RATE
    metrics = lexical_metrics(words) | timing_metrics(words, duration_s)
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
    registered_arms = tuple(ARM_CONDITIONS.items())
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
    parser.add_argument("--model", type=Path, required=True, help="explicit pinned local model directory containing config.json and weights.safetensors")
    parser.add_argument(
        "--protected-root",
        action="append",
        default=[],
        type=Path,
        help="additional Preview/product/private root that fixture and output paths must not enter",
    )
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
        output_path = validate_output_target(args.out, args.protected_root)
    except ValueError as exc:
        parser.error(str(exc))
    identity = execution_identity(args.model)
    try:
        model_path = require_pinned_execution_identity(identity)
        fixture, audio = load_fixture(
            args.fixture, args.fixture_root, args.protected_root
        )
        import mlx_whisper  # noqa: F401
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schema": SCHEMA,
            "status": "unavailable",
            "fixture": {"id": args.fixture},
            "execution_identity": identity,
            "decoding_config": {
                **DECODE_CONFIG,
                "selected_arm": args.arm,
                "condition_on_previous_text_by_arm": {
                    name: condition
                    for name, condition in ARM_CONDITIONS.items()
                    if args.arm in ("both", name)
                },
            },
            "reason": str(exc),
        }
        write_receipt(output_path, report)
        return 2
    report = {
        "schema": SCHEMA,
        "status": "measured",
        "fixture": {
            "id": fixture["id"],
            "source": fixture["source"],
            "license": fixture["license"],
            "source_ref": fixture["source_ref"],
            "duration_s": round(len(audio) / RATE, 3),
            "registered_coverage": fixture["coverage"],
        },
        "execution_identity": identity,
        "runtime": {
            "platform": f"{platform.system()}-{platform.machine()}",
            "sample_rate_hz": RATE,
        },
        "decoding_config": {
            **DECODE_CONFIG,
            "condition_on_previous_text_by_arm": {
                name: condition
                for name, condition in ARM_CONDITIONS.items()
                if args.arm in ("both", name)
            },
        },
        "evaluation_eligibility": {
            "registered_coverage_only": fixture["coverage"],
            "seams": {
                "status": "ineligible",
                "reason": "fixture schema v2 has no declared time/token-window contract",
            },
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
    write_receipt(output_path, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
