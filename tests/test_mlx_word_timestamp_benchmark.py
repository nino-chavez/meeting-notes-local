import importlib.util
import json
import platform
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import wave

import numpy as np


MODULE = Path(__file__).resolve().parents[1] / "spike" / "mlx_word_timestamp_benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark", MODULE)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)


def word(token, start, end):
    return {"token": token, "start": start, "end": end, "segment": 0}


def write_silence_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(benchmark.RATE)
        output.writeframes(b"\0\0" * benchmark.RATE)


def registered_fixture(root: Path) -> dict:
    audio = root / "fixture.wav"
    write_silence_wav(audio)
    return {
        "id": "public-v1",
        "source": "public",
        "license": "CC0-1.0",
        "source_ref": "https://example.invalid/public-v1",
        "audio": audio.name,
        "audio_sha256": benchmark.sha256_file(audio),
        "expect_speech": False,
        "coverage": ["silence", "timing"],
        "expected": {"metric_counts": {"words": 0}},
    }


def write_manifest(path: Path, fixture: dict) -> None:
    path.write_text(
        json.dumps({"schema": benchmark.FIXTURE_SCHEMA, "fixtures": [fixture]})
    )


class BenchmarkTests(unittest.TestCase):
    def test_synthetic_silence_is_deterministic_and_has_no_speech(self):
        fixture, audio = benchmark.load_fixture("synthetic-silence-v1", None)
        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(len(audio), benchmark.RATE * 3)
        self.assertFalse(audio.any())
        self.assertEqual(
            fixture["coverage"],
            ["silence", "timing", "repeatability", "latency", "memory"],
        )

    def test_metrics_detect_repeat_loop_negation_number_and_bad_timing_without_text_output(self):
        words = [
            word("um", 0.0, 0.1),
            word("no", 0.12, 0.2),
            word("42", 0.22, 0.3),
            word("go", 0.4, 0.5),
            word("go", 0.45, 0.6),
            word("go", 0.7, 0.8),
        ]
        lexical = benchmark.lexical_metrics(words)
        timing = benchmark.timing_metrics(words, 1.0)
        self.assertEqual(lexical["fillers"], 1)
        self.assertEqual(lexical["negation_tokens"], 1)
        self.assertEqual(lexical["number_tokens"], 1)
        self.assertEqual(lexical["repeated_words"], 2)
        self.assertGreaterEqual(lexical["looping_pairs"], 1)
        self.assertEqual(timing["timing_non_monotonic"], 1)

    def test_timing_rejects_and_counts_every_non_finite_start_or_end(self):
        cases = [
            ("nan-start", float("nan"), 0.2, 1),
            ("nan-end", 0.1, float("nan"), 1),
            ("positive-infinity", float("inf"), float("inf"), 2),
            ("negative-infinity", float("-inf"), 0.2, 1),
        ]
        for label, start, end, expected_count in cases:
            with self.subTest(label=label):
                metrics = benchmark.timing_metrics([word("x", start, end)], 1.0)
                self.assertEqual(metrics["timed_words"], 0)
                self.assertEqual(
                    metrics["timing_non_finite_values"], expected_count
                )
                self.assertEqual(metrics["timing_out_of_bounds"], 0)

    def test_timing_counts_missing_or_non_numeric_values_separately(self):
        metrics = benchmark.timing_metrics(
            [word("x", None, "0.2"), word("y", 0.2, 0.3)], 1.0
        )
        self.assertEqual(metrics["timed_words"], 1)
        self.assertEqual(metrics["timing_missing_or_non_numeric_values"], 2)
        self.assertEqual(metrics["timing_non_finite_values"], 0)

    def test_public_fixture_validation_table(self):
        cases = {
            "valid": None,
            "missing-source-ref": "provenance reference",
            "bad-digest": "digest does not match",
            "traversal": "escapes its registered root",
            "manifest-symlink": "manifest may not be a symlink",
            "audio-symlink": "audio may not be a symlink",
        }
        for case, expected_error in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                root = base / "public-fixture"
                root.mkdir()
                fixture = registered_fixture(root)
                manifest = root / "manifest.json"
                if case == "missing-source-ref":
                    fixture.pop("source_ref")
                elif case == "bad-digest":
                    fixture["audio_sha256"] = "0" * 64
                elif case == "traversal":
                    outside = base / "outside.wav"
                    write_silence_wav(outside)
                    fixture["audio"] = "../outside.wav"
                    fixture["audio_sha256"] = benchmark.sha256_file(outside)
                elif case == "audio-symlink":
                    audio = root / "fixture.wav"
                    actual = root / "actual.wav"
                    audio.rename(actual)
                    audio.symlink_to(actual)
                if case == "manifest-symlink":
                    actual_manifest = root / "actual-manifest.json"
                    write_manifest(actual_manifest, fixture)
                    manifest.symlink_to(actual_manifest)
                else:
                    write_manifest(manifest, fixture)
                if expected_error is None:
                    loaded, audio = benchmark.load_fixture("public-v1", root)
                    self.assertEqual(loaded["source_ref"], fixture["source_ref"])
                    self.assertEqual(len(audio), benchmark.RATE)
                else:
                    with self.assertRaisesRegex(ValueError, expected_error):
                        benchmark.load_fixture("public-v1", root)

    def test_fixture_expectations_require_known_keys_and_explicit_coverage(self):
        base = {
            "coverage": ["timing"],
            "expected": {},
        }
        cases = [
            ({**base, "expected": {"mystery": 1}}, "unknown keys"),
            (
                {**base, "expected": {"metric_counts": {"mystery": 1}}},
                "unknown metric counts",
            ),
            (
                {"coverage": ["fillers"], "expected": {"metric_counts": {"fillers": 1}}},
                "expected token hashes",
            ),
            (
                {
                    "coverage": ["timing"],
                    "expected": {"metric_counts": {"fillers": 1}},
                },
                "lacks registered coverage fillers",
            ),
            (
                {**base, "seams_s": [30.0]},
                "seam evaluation is mechanically unsupported",
            ),
        ]
        for fixture, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    benchmark.validate_fixture_definition(fixture)

    def test_path_protection_is_scoped_to_repo_and_explicit_roots(self):
        with self.assertRaisesRegex(ValueError, "outside this repository"):
            benchmark.validate_output_target(
                Path(__file__).resolve().parents[1] / "receipt.json"
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other_checkout = root / "public-corpus-checkout"
            other_checkout.mkdir()
            (other_checkout / ".git").mkdir()
            allowed = other_checkout / "receipt.json"
            self.assertEqual(benchmark.validate_output_target(allowed), allowed.resolve())
            protected = root / "private-product-root"
            protected.mkdir()
            with self.assertRaisesRegex(ValueError, "explicit protected root"):
                benchmark.validate_output_target(
                    protected / "receipt.json", [protected]
                )
            with self.assertRaisesRegex(ValueError, "explicit protected root"):
                benchmark.validate_public_fixture_root(protected, [protected])

    def test_receipt_write_is_exclusive_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            first = {"schema": benchmark.SCHEMA, "status": "unavailable"}
            benchmark.write_receipt(target, first)
            original = target.read_bytes()
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                benchmark.write_receipt(target, {"status": "measured"})
            self.assertEqual(target.read_bytes(), original)

    def test_canonical_identity_is_derived_from_runtime_pins(self):
        expected = benchmark.canonical_identity_expectations()
        self.assertEqual(expected["python_version"], "3.12.13")
        self.assertEqual(expected["mlx_whisper_version"], "0.4.3")
        self.assertEqual(expected["mlx_version"], "0.29.3")
        self.assertEqual(expected["model_id"], benchmark.DEFAULT_MODEL_ID)
        self.assertEqual(
            expected["model_revision"], "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb"
        )

    def test_execution_identity_requires_config_weights_runtime_and_exact_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)
            config = model / "config.json"
            weights = model / "weights.safetensors"
            config.write_bytes(b"config")
            weights.write_bytes(b"weights")
            expected = {
                "python_version": platform.python_version(),
                "mlx_whisper_version": "test-whisper",
                "mlx_version": "test-mlx",
                "model_id": benchmark.DEFAULT_MODEL_ID,
                "model_revision": "immutable-revision",
                "config_sha256": benchmark.sha256_file(config),
                "weights_sha256": benchmark.sha256_file(weights),
            }
            versions = {"mlx-whisper": "test-whisper", "mlx": "test-mlx"}
            with mock.patch.object(
                benchmark, "installed_version", side_effect=versions.get
            ):
                identity = benchmark.execution_identity(model, expected)
                self.assertEqual(
                    benchmark.require_pinned_execution_identity(identity),
                    model.resolve(),
                )
                config.unlink()
                mismatch = benchmark.execution_identity(model, expected)
            self.assertFalse(mismatch["canonical_identity_match"])
            self.assertIsNone(mismatch["observed"]["model_revision"])
            with self.assertRaisesRegex(ValueError, "config_sha256"):
                benchmark.require_pinned_execution_identity(mismatch)

    def test_fingerprint_ignores_peak_memory(self):
        first = {
            "metrics": {"words": 1, "peak_rss_bytes": 100},
            "result_shape": {"segments": 1},
        }
        second = {
            "metrics": {"words": 1, "peak_rss_bytes": 200},
            "result_shape": {"segments": 1},
        }
        self.assertEqual(
            benchmark.stable_fingerprint(first), benchmark.stable_fingerprint(second)
        )

    def test_word_timestamp_and_continuation_switches_are_explicit(self):
        calls = []
        fake = type(
            "FakeMLXWhisper",
            (),
            {
                "transcribe": staticmethod(
                    lambda audio, **kwargs: calls.append(kwargs) or {"segments": []}
                )
            },
        )
        with mock.patch.dict("sys.modules", {"mlx_whisper": fake}):
            benchmark.transcribe(np.zeros(10, dtype=np.float32), "model", False)
            benchmark.transcribe(np.zeros(10, dtype=np.float32), "model", True)
        self.assertTrue(all(call["word_timestamps"] for call in calls))
        self.assertEqual(
            [call["condition_on_previous_text"] for call in calls], [False, True]
        )
        self.assertEqual(
            [list(call["temperature"]) for call in calls],
            [benchmark.DECODE_CONFIG["temperature"]] * 2,
        )

    def test_measured_run_never_returns_recognized_text(self):
        result = {
            "segments": [
                {"words": [{"word": "privateword", "start": 0.0, "end": 0.1}]}
            ]
        }
        fixture = {
            "expect_speech": True,
            "expected": {"minimum_words": 1},
        }
        with mock.patch.object(benchmark, "transcribe", return_value=result):
            run = benchmark.one_run(
                np.zeros(benchmark.RATE, dtype=np.float32), fixture, "model", False
            )
        self.assertNotIn("privateword", str(run))
        self.assertEqual(run["metrics"]["words"], 1)

    def test_public_token_hash_checks_report_names_without_storing_words(self):
        words = [word("Ada", 0.0, 0.1)]
        expected = {
            "token_hash_counts": {"names": {benchmark.token_hash("ada"): 1}}
        }
        metrics = benchmark.expected_metric_deltas(words, expected)
        self.assertEqual(metrics, {"names_matched": 1, "names_missing": 0})

    def test_one_arm_can_run_as_first_model_load_in_a_fresh_process(self):
        fake_run = {
            "elapsed_ms": 10.0,
            "metrics": {"words": 0, "peak_rss_bytes": 1},
            "result_shape": {"segments": 0},
        }
        with mock.patch.object(benchmark, "one_run", return_value=fake_run):
            arms = benchmark.benchmark(
                np.zeros(benchmark.RATE, dtype=np.float32),
                {"expect_speech": False},
                "model",
                1,
                "continuation_seam_comparator",
            )
        self.assertEqual(list(arms), ["continuation_seam_comparator"])
        self.assertEqual(
            arms["continuation_seam_comparator"]["first_run_process_state"],
            "model_not_loaded_in_process",
        )


if __name__ == "__main__":
    unittest.main()
