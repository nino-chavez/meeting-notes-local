import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np


MODULE = Path(__file__).resolve().parents[1] / "spike" / "mlx_word_timestamp_benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark", MODULE)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)


def word(token, start, end):
    return {"token": token, "start": start, "end": end, "segment": 0}


class BenchmarkTests(unittest.TestCase):
    def test_synthetic_silence_is_deterministic_and_has_no_speech(self):
        audio = benchmark.synthetic_silence()
        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(len(audio), benchmark.RATE * 3)
        self.assertFalse(audio.any())

    def test_metrics_detect_repeat_loop_negation_number_and_bad_timing_without_text_output(self):
        words = [word("um", 0.0, 0.1), word("no", 0.12, 0.2), word("42", 0.22, 0.3), word("go", 0.4, 0.5), word("go", 0.45, 0.6), word("go", 0.7, 0.8)]
        lexical = benchmark.lexical_metrics(words)
        timing = benchmark.timing_metrics(words, 1.0)
        self.assertEqual(lexical["fillers"], 1)
        self.assertEqual(lexical["negation_tokens"], 1)
        self.assertEqual(lexical["number_tokens"], 1)
        self.assertEqual(lexical["repeated_words"], 2)
        self.assertGreaterEqual(lexical["looping_pairs"], 1)
        self.assertEqual(timing["timing_non_monotonic"], 1)

    def test_public_fixture_requires_registered_digest_checked_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text('{"schema":"mlx-word-timestamp-fixture/1","fixtures":[]}')
            with self.assertRaisesRegex(ValueError, "registered public fixture"):
                benchmark.load_fixture("unknown", root)

    def test_fingerprint_ignores_peak_memory(self):
        first = {"metrics": {"words": 1, "peak_rss_bytes": 100}, "result_shape": {"segments": 1}}
        second = {"metrics": {"words": 1, "peak_rss_bytes": 200}, "result_shape": {"segments": 1}}
        self.assertEqual(benchmark.stable_fingerprint(first), benchmark.stable_fingerprint(second))

    def test_word_timestamp_and_continuation_switches_are_explicit(self):
        calls = []
        fake = type("FakeMLXWhisper", (), {"transcribe": staticmethod(lambda audio, **kwargs: calls.append(kwargs) or {"segments": []})})
        with mock.patch.dict("sys.modules", {"mlx_whisper": fake}):
            benchmark.transcribe(np.zeros(10, dtype=np.float32), "model", False)
            benchmark.transcribe(np.zeros(10, dtype=np.float32), "model", True)
        self.assertTrue(all(call["word_timestamps"] for call in calls))
        self.assertEqual([call["condition_on_previous_text"] for call in calls], [False, True])

    def test_measured_run_never_returns_recognized_text(self):
        result = {"segments": [{"words": [{"word": "privateword", "start": 0.0, "end": 0.1}]}]}
        fixture = {"expect_speech": True, "seams_s": [], "expected": {"minimum_words": 1}}
        with mock.patch.object(benchmark, "transcribe", return_value=result):
            run = benchmark.one_run(np.zeros(benchmark.RATE, dtype=np.float32), fixture, "model", False)
        self.assertNotIn("privateword", str(run))
        self.assertEqual(run["metrics"]["words"], 1)

    def test_public_token_hash_checks_report_names_without_storing_words(self):
        words = [word("Ada", 0.0, 0.1)]
        expected = {"token_hash_counts": {"names": {benchmark.token_hash("ada"): 1}}}
        metrics = benchmark.expected_metric_deltas(words, expected)
        self.assertEqual(metrics, {"names_matched": 1, "names_missing": 0})

    def test_one_arm_can_run_as_first_model_load_in_a_fresh_process(self):
        fake_run = {"elapsed_ms": 10.0, "metrics": {"words": 0, "peak_rss_bytes": 1}, "result_shape": {"segments": 0}}
        with mock.patch.object(benchmark, "one_run", return_value=fake_run):
            arms = benchmark.benchmark(
                np.zeros(benchmark.RATE, dtype=np.float32),
                {"expect_speech": False},
                "model",
                1,
                "continuation_seam_comparator",
            )
        self.assertEqual(list(arms), ["continuation_seam_comparator"])
        self.assertEqual(arms["continuation_seam_comparator"]["first_run_process_state"], "model_not_loaded_in_process")


if __name__ == "__main__":
    unittest.main()
