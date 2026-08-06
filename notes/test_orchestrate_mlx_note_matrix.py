"""Exercise the matrix orchestrator's gates before spending 36 model processes.

The failure this guards against is the expensive one: a run that costs minutes,
produces a receipt reading `passed`, and graded nothing. Every gate below is
tested in the direction that matters — it must go false when the condition it
names is violated — because a gate that cannot fail is not a gate that passed.

No model is loaded here. Worker output is a plain dict, so every branch is
reachable without inference.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import orchestrate_mlx_note_matrix as matrix
from mlx_note_admission import MLX_RUNTIME
from orchestrate_mlx_note_matrix import (
    COLD_REPEATS,
    EXPECTED_FIXTURES,
    PEAK_RSS_CEILING,
    WARM_REPEATS,
    _fixture_row,
    _matrix_receipt,
    _stable,
)

CONTROL = {"outcome": "accepted-research-candidate", "code": None, "expected": True}


def call(phase: str, index: int, *, response="r1", note="n1", receipt="c1", elapsed=3.0, checks=None):
    return {
        "phase": phase,
        "index": index,
        "outcome": "accepted-research-candidate",
        "code": None,
        "response_sha256": response,
        "note_sha256": note,
        "receipt_sha256": receipt,
        "generation": {"call_elapsed_s": elapsed, "finish_reason": "stop"},
        "checks": checks or {"expected_outcome": True, "required_citation_terms": True, "strict_empty_abstention": True},
        "load_average_before": [1.0, 1.0, 1.0],
        "load_average_after": [1.0, 1.0, 1.0],
    }


def worker(calls, *, peak_rss=1_000_000_000, tree="t1", postflight=None):
    return {
        "worker_failed": False,
        "calls": calls,
        "peak_rss": peak_rss,
        "preflight_tree_sha256": tree,
        "postflight_tree_sha256": postflight or tree,
        "load": {"model_load_elapsed_s": 0.5},
    }


def passing_workers():
    """The registered shape: three cold calls, two warm, all in agreement."""
    return [
        worker([call("cold-call", 0), call("warm-call", 1, elapsed=1.0), call("warm-call", 2, elapsed=1.0)]),
        worker([call("cold-call", 0)]),
        worker([call("cold-call", 0)]),
    ]


class StableProjectionTests(unittest.TestCase):
    def test_timings_and_footprint_are_stripped_at_every_depth(self) -> None:
        """The repeatability digest must not move just because a repeat is slower."""
        receipt = {
            "elapsed_s": 1.0,
            "keep": "x",
            "generation": {"call_elapsed_s": 2.0, "finish_reason": "stop"},
            "rows": [{"model_load_elapsed_s": 3.0, "peak_rss": 5, "id": "a"}],
        }
        self.assertEqual(
            _stable(receipt),
            {"keep": "x", "generation": {"finish_reason": "stop"}, "rows": [{"id": "a"}]},
        )

    def test_a_substantive_difference_still_survives_the_projection(self) -> None:
        """Otherwise the digest would be identical for genuinely different runs."""
        self.assertNotEqual(
            _stable({"response_sha256": "a", "elapsed_s": 1}),
            _stable({"response_sha256": "b", "elapsed_s": 9}),
        )


class FixtureRowTests(unittest.TestCase):
    def test_the_registered_shape_passes_every_per_fixture_gate(self) -> None:
        row = _fixture_row("ordinary-decision", CONTROL, passing_workers())
        self.assertEqual(row["cold_repeats"], COLD_REPEATS)
        self.assertEqual(row["warm_repeats"], WARM_REPEATS)
        self.assertTrue(all(row["gates"].values()), row["gates"])

    def test_a_moving_response_note_or_receipt_digest_fails_repeatability(self) -> None:
        """Stated over all three, so each must be able to fail it alone."""
        for field in ("response", "note", "receipt"):
            with self.subTest(field=field):
                workers = passing_workers()
                workers[2]["calls"][0] = call("cold-call", 0, **{field: "different"})
                row = _fixture_row("ordinary-decision", CONTROL, workers)
                self.assertFalse(row["gates"]["repeatable"])

    def test_a_warm_call_that_differs_does_not_fail_repeatability(self) -> None:
        """The gate is stated over the three cold runs, and only those."""
        workers = passing_workers()
        workers[0]["calls"][1] = call("warm-call", 1, response="other", elapsed=1.0)
        self.assertTrue(_fixture_row("ordinary-decision", CONTROL, workers)["gates"]["repeatable"])

    def test_a_failed_check_on_any_call_including_a_warm_one_fails_the_row(self) -> None:
        for index, phase in ((0, "cold-call"), (1, "warm-call")):
            with self.subTest(phase=phase):
                workers = passing_workers()
                workers[0]["calls"][index] = call(
                    phase, index, elapsed=1.0,
                    checks={"expected_outcome": False, "required_citation_terms": True, "strict_empty_abstention": True},
                )
                row = _fixture_row("ordinary-decision", CONTROL, workers)
                self.assertFalse(row["gates"]["checks_pass_on_every_call"])

    def test_the_wrong_number_of_repeats_fails_rather_than_grading_fewer(self) -> None:
        workers = passing_workers()[:2]
        row = _fixture_row("ordinary-decision", CONTROL, workers)
        self.assertFalse(row["gates"]["repeats_as_registered"])
        workers = passing_workers()
        workers[0]["calls"] = workers[0]["calls"][:2]
        self.assertFalse(_fixture_row("x", CONTROL, workers)["gates"]["repeats_as_registered"])

    def test_a_disagreeing_control_fails_the_row(self) -> None:
        row = _fixture_row("ordinary-decision", {**CONTROL, "expected": False}, passing_workers())
        self.assertFalse(row["gates"]["control_expected"])

    def test_a_model_tree_that_changed_under_a_worker_fails(self) -> None:
        workers = passing_workers()
        workers[1]["postflight_tree_sha256"] = "moved"
        self.assertFalse(_fixture_row("x", CONTROL, workers)["gates"]["tree_stable"])

    def test_a_crashed_worker_stops_the_row_instead_of_grading_the_survivors(self) -> None:
        workers = passing_workers()
        workers[1] = {"fixture": "x", "worker_failed": True, "returncode": -9, "terminated_by_signal": True}
        row = _fixture_row("x", CONTROL, workers)
        self.assertFalse(row["gates"]["workers_completed"])
        self.assertEqual(row["worker_failures"][0]["returncode"], -9)
        # A signal kill is how a memory-pressure termination arrives, and the
        # protocol rejects on it — so it must stay distinguishable here.
        self.assertTrue(row["worker_failures"][0]["terminated_by_signal"])

    def test_all_three_digests_the_gate_reads_are_recorded_not_two(self) -> None:
        """A `repeatable: false` must say which of the three moved.

        The gate is computed over the response, note and receipt digests; the
        row recorded only the first two, so a run that diverged on the receipt
        left a receipt showing one response digest, one note digest, and a
        failed gate with nothing to point at.
        """
        workers = passing_workers()
        workers[2]["calls"][0] = call("cold-call", 0, receipt="moved")
        row = _fixture_row("x", CONTROL, workers)
        self.assertFalse(row["gates"]["repeatable"])
        self.assertEqual(row["receipt_sha256"], ["c1", "moved"])
        self.assertEqual(row["response_sha256"], ["r1"])

    def test_load_is_recorded_for_warm_calls_which_carry_the_tighter_ceiling(self) -> None:
        row = _fixture_row("x", CONTROL, passing_workers())
        phases = [entry["phase"] for entry in row["load_average"]]
        self.assertEqual(phases.count("cold-call"), COLD_REPEATS)
        self.assertEqual(phases.count("warm-call"), WARM_REPEATS)
        self.assertIn("after", row["load_average"][0])

    def test_a_call_that_never_reached_generation_is_carried_not_crashed(self) -> None:
        """A MaskRefused or timeout produces a receipt with no generation block."""
        workers = passing_workers()
        broken = call("cold-call", 0)
        broken["generation"] = None
        workers[2]["calls"][0] = broken
        row = _fixture_row("x", CONTROL, workers)
        self.assertFalse(row["gates"]["timings_available"])
        self.assertIsNone(row["cold_median_s"])


class MatrixReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            _fixture_row(f"fixture-{index}", CONTROL, passing_workers())
            for index in range(EXPECTED_FIXTURES)
        ]

    def receipt(self, rows=None, preflight="t", postflight="t"):
        original = matrix.tree_sha256
        matrix.tree_sha256 = lambda _directory: postflight
        try:
            return _matrix_receipt(Path("/nonexistent"), preflight, [1.0, 1.0, 1.0], rows or self.rows)
        finally:
            matrix.tree_sha256 = original

    def test_a_complete_matrix_passes_and_still_admits_nothing(self) -> None:
        receipt = self.receipt()
        self.assertTrue(receipt["passed"], receipt["gates"])
        self.assertIs(receipt["admits"], False)
        self.assertEqual(receipt["matrix"], {"fixtures": 12, "cold_repeats": 3, "warm_repeats": 2})

    def test_fewer_than_twelve_fixtures_cannot_pass(self) -> None:
        receipt = self.receipt(rows=self.rows[:11])
        self.assertFalse(receipt["gates"]["every_fixture_ran"])
        self.assertFalse(receipt["passed"])

    def test_cold_and_warm_latency_are_separate_gates_at_their_own_ceilings(self) -> None:
        # 20 s cold is under the 30 s ceiling; the same figure warm is over 15 s.
        slow_cold = [
            _fixture_row("f", CONTROL, [
                worker([call("cold-call", 0, elapsed=20.0), call("warm-call", 1, elapsed=1.0), call("warm-call", 2, elapsed=1.0)]),
                worker([call("cold-call", 0, elapsed=20.0)]),
                worker([call("cold-call", 0, elapsed=20.0)]),
            ])
        ] * EXPECTED_FIXTURES
        receipt = self.receipt(rows=slow_cold)
        self.assertTrue(receipt["gates"]["cold_latency"])
        self.assertTrue(receipt["gates"]["warm_latency"])

        slow_warm = [
            _fixture_row("f", CONTROL, [
                worker([call("cold-call", 0, elapsed=20.0), call("warm-call", 1, elapsed=20.0), call("warm-call", 2, elapsed=20.0)]),
                worker([call("cold-call", 0, elapsed=20.0)]),
                worker([call("cold-call", 0, elapsed=20.0)]),
            ])
        ] * EXPECTED_FIXTURES
        receipt = self.receipt(rows=slow_warm)
        self.assertTrue(receipt["gates"]["cold_latency"])
        self.assertFalse(receipt["gates"]["warm_latency"])
        self.assertFalse(receipt["passed"])

    def test_a_cold_median_over_the_ceiling_fails(self) -> None:
        rows = [
            _fixture_row("f", CONTROL, [
                worker([call("cold-call", 0, elapsed=31.0), call("warm-call", 1, elapsed=1.0), call("warm-call", 2, elapsed=1.0)]),
                worker([call("cold-call", 0, elapsed=31.0)]),
                worker([call("cold-call", 0, elapsed=31.0)]),
            ])
        ] * EXPECTED_FIXTURES
        receipt = self.receipt(rows=rows)
        self.assertFalse(receipt["gates"]["cold_latency"])

    def test_load_average_is_recorded_so_a_latency_failure_is_attributable(self) -> None:
        """43 s and 3.5 s were both measured here for byte-identical work."""
        receipt = self.receipt()
        self.assertEqual(receipt["latency"]["load_average_at_start"], [1.0, 1.0, 1.0])
        self.assertIn("load_average_at_end", receipt["latency"])
        self.assertEqual(len(receipt["fixtures"][0]["load_average"]), COLD_REPEATS + WARM_REPEATS)

    def test_the_memory_ceiling_binds_and_a_zero_reading_is_not_a_pass(self) -> None:
        over = [_fixture_row("f", CONTROL, [worker(w["calls"], peak_rss=PEAK_RSS_CEILING + 1) for w in passing_workers()])]
        self.assertFalse(self.receipt(rows=over * EXPECTED_FIXTURES)["gates"]["memory"])
        # An unmeasured footprint reads 0, which must not satisfy "at most".
        zero = [_fixture_row("f", CONTROL, [worker(w["calls"], peak_rss=0) for w in passing_workers()])]
        self.assertFalse(self.receipt(rows=zero * EXPECTED_FIXTURES)["gates"]["memory"])

    def test_a_model_tree_that_moved_across_the_run_fails(self) -> None:
        self.assertFalse(self.receipt(preflight="a", postflight="b")["gates"]["tree_unchanged"])

    def test_one_failing_fixture_fails_the_matrix(self) -> None:
        rows = list(self.rows)
        rows[7] = _fixture_row("bad", {**CONTROL, "expected": False}, passing_workers())
        receipt = self.receipt(rows=rows)
        self.assertFalse(receipt["gates"]["per_fixture_gates"])
        self.assertFalse(receipt["passed"])


class SpawnFailureTests(unittest.TestCase):
    """A bad worker must become a row, never an exception out of the matrix.

    36 model loads are at stake. Anything that escapes `_spawn` discards the
    entire run and names no fixture.
    """

    def spawn(self, fake_run):
        original = matrix.subprocess.run
        matrix.subprocess.run = fake_run
        try:
            return matrix._spawn(Path("/model"), "ordinary-decision", 2)
        finally:
            matrix.subprocess.run = original

    def test_a_zero_exit_worker_with_unusable_stdout_becomes_a_row(self) -> None:
        class Completed:
            returncode = 0
            stdout = "Traceback (most recent call last):"
            stderr = "boom"

        row = self.spawn(lambda *a, **k: Completed())
        self.assertTrue(row["worker_failed"])
        self.assertEqual(row["failure"], "stdout-unparseable")
        self.assertEqual(row["fixture"], "ordinary-decision")

    def test_a_wedged_worker_times_out_instead_of_holding_the_matrix_open(self) -> None:
        def wedged(*args, **kwargs):
            self.assertIn("timeout", kwargs)
            raise matrix.subprocess.TimeoutExpired(cmd="worker", timeout=kwargs["timeout"])

        row = self.spawn(wedged)
        self.assertTrue(row["worker_failed"])
        self.assertEqual(row["failure"], "timeout")
        # The bound comes from the protocol's own cold ceiling, not a guess.
        self.assertEqual(row["timeout_s"], 3 * 30.0 + matrix.WORKER_STARTUP_ALLOWANCE_S)

    def test_a_signal_killed_worker_stays_distinguishable_from_an_exception(self) -> None:
        class Killed:
            returncode = -9
            stdout = ""
            stderr = "Killed"

        row = self.spawn(lambda *a, **k: Killed())
        self.assertEqual(row["failure"], "nonzero-exit")
        self.assertTrue(row["terminated_by_signal"])

    def test_a_child_that_never_starts_becomes_a_row(self) -> None:
        """posix_spawn raises EAGAIN/ENOMEM under memory pressure.

        In-domain, not exotic: this module already treats a memory-pressure kill
        as a first-class outcome, and the committed run recorded load averages
        above 10 against a 1.18 GB resident model.
        """
        def cannot_fork(*args, **kwargs):
            raise OSError(12, "Cannot allocate memory")

        row = self.spawn(cannot_fork)
        self.assertTrue(row["worker_failed"])
        self.assertEqual(row["failure"], "spawn-failed")
        self.assertEqual(row["errno"], 12)

    def test_parsed_but_unusable_worker_output_becomes_a_row(self) -> None:
        """Parsing is not the same as getting a worker record.

        The per-call cases are the ones an earlier guard let through: it checked
        six top-level keys while claiming to cover everything the projection
        reads, so `"calls": [{}]` cleared the boundary and raised KeyError on
        `phase` inside `_fixture_row` — after up to 36 model loads, with no
        receipt written and no fixture named.
        """
        complete = (
            '"preflight_tree_sha256":"a","postflight_tree_sha256":"a","peak_rss":1'
        )
        for label, payload in (
            ("non-dict", "[1, 2, 3]"),
            ("missing-top-level", '{"calls": [{}]}'),
            ("calls-empty", "{%s,\"calls\":[]}" % complete),
            ("calls-not-a-list", "{%s,\"calls\":{}}" % complete),
            ("call-is-empty-object", "{%s,\"calls\":[{}]}" % complete),
            ("peak-rss-not-a-number", '{"preflight_tree_sha256":"a","postflight_tree_sha256":"a","peak_rss":"1","calls":[{}]}'),
            ("checks-not-an-object", "{%s,\"calls\":[{\"phase\":\"cold-call\",\"outcome\":\"x\",\"code\":null,"
                                     "\"response_sha256\":\"r\",\"note_sha256\":null,\"receipt_sha256\":\"c\",\"checks\":[],"
                                     "\"load_average_before\":[],\"load_average_after\":[]}]}" % complete),
            ("call-missing-a-digest", "{%s,\"calls\":[{\"phase\":\"cold-call\",\"outcome\":\"x\",\"code\":null,"
                                      "\"response_sha256\":\"r\",\"note_sha256\":null,\"checks\":{},"
                                      "\"load_average_before\":[],\"load_average_after\":[]}]}" % complete),
        ):
            with self.subTest(payload=label):
                class Completed:
                    returncode = 0
                    stdout = payload
                    stderr = ""

                row = self.spawn(lambda *a, **k: Completed())
                self.assertTrue(row["worker_failed"])
                self.assertEqual(row["failure"], "worker-record-incomplete")

    def test_every_spawn_failure_shape_reaches_the_row_gate_as_incomplete(self) -> None:
        for reason in ("timeout", "stdout-unparseable", "nonzero-exit", "spawn-failed", "worker-record-incomplete"):
            with self.subTest(reason=reason):
                workers = passing_workers()
                workers[1] = matrix._failed_worker("x", reason, 1.0)
                self.assertFalse(_fixture_row("x", CONTROL, workers)["gates"]["workers_completed"])


class CommittedMatrixReceiptTests(unittest.TestCase):
    """Hold the committed run to what the write-up says about it."""

    def setUp(self) -> None:
        import json

        path = Path(__file__).resolve().parent / "mlx_note_matrix_receipt.json"
        self.receipt = json.loads(path.read_text())

    def test_the_run_is_the_registered_shape_and_admits_nothing(self) -> None:
        self.assertEqual(self.receipt["matrix"], {"fixtures": 12, "cold_repeats": 3, "warm_repeats": 2})
        self.assertEqual(len(self.receipt["fixtures"]), EXPECTED_FIXTURES)
        self.assertIs(self.receipt["admits"], False)
        self.assertEqual(self.receipt["decoding"], "structure-constrained")
        # The shape changed once under an unchanged version string. It must not
        # happen twice: /1 receipts with a different `load_average` shape are
        # still in git history.
        self.assertEqual(self.receipt["schema"], "mlx-note-matrix/2")
        self.assertIsInstance(self.receipt["fixtures"][0]["load_average"][0], dict)

    def test_the_receipt_names_the_instrument_that_produced_it(self) -> None:
        """The harness block hashes mlx_note_admission.py and nothing else.

        A receipt from the orchestrator that had the spawn defects and one from
        the repaired orchestrator were byte-identical in that block, so the
        artifact could not say which instrument ran.
        """
        from mlx_note_admission import _sha256

        source = Path(__file__).resolve().parent / "orchestrate_mlx_note_matrix.py"
        self.assertEqual(self.receipt["orchestrator_sha256"], _sha256(source.read_bytes()))

    def test_the_mechanical_envelope_passed_and_only_the_fixtures_failed(self) -> None:
        """The doc claims latency, memory, repeatability and coverage all held."""
        gates = self.receipt["gates"]
        for name in ("every_fixture_ran", "cold_latency", "warm_latency", "memory", "tree_unchanged"):
            with self.subTest(gate=name):
                self.assertTrue(gates[name])
        self.assertFalse(gates["per_fixture_gates"])
        self.assertFalse(self.receipt["passed"])

    def test_every_fixture_was_repeatable_across_the_three_cold_runs(self) -> None:
        """A failure that does not reproduce would be noise, not a finding."""
        for row in self.receipt["fixtures"]:
            with self.subTest(fixture=row["fixture"]):
                self.assertTrue(row["gates"]["repeatable"])

    def test_nine_supported_fixtures_failed_and_one_unseen_abstention_passed(self) -> None:
        """`abstain-plain` had never been run before this matrix, and passed.

        The name matters: an earlier write-up called all three passing fixtures
        "the ones run before", which is false, and a green test carrying that
        sentence would be the most credible artifact still asserting it.
        """
        passing = sorted(row["fixture"] for row in self.receipt["fixtures"] if all(row["gates"].values()))
        self.assertEqual(passing, ["abstain-chitchat", "abstain-plain", "ordinary-decision"])
        failing = [row for row in self.receipt["fixtures"] if not all(row["gates"].values())]
        self.assertEqual(len(failing), 9)
        # Every failure is the fixture checks, not the envelope.
        for row in failing:
            with self.subTest(fixture=row["fixture"]):
                self.assertFalse(row["gates"]["checks_pass_on_every_call"])


class IdAlignmentReceiptTests(unittest.TestCase):
    """The one empirical claim in the hypothesis table has to be sourced."""

    def test_the_token_alignment_refutation_rests_on_a_committed_measurement(self) -> None:
        import json

        path = Path(__file__).resolve().parent / "mlx_note_id_alignment_receipt.json"
        receipt = json.loads(path.read_text())
        self.assertEqual(receipt["schema"], "mlx-note-id-alignment/2")
        self.assertEqual(receipt["short_form_length"], 67)
        # Re-derived from `rows`, not read off the summary the probe wrote about
        # itself: a receipt carrying a false row would otherwise satisfy every
        # assertion here while the doc cites it as the refutation.
        self.assertTrue(receipt["rows"])
        self.assertTrue(all(row["boundary_is_token_aligned"] for row in receipt["rows"]))
        self.assertTrue(all(row["fragment_id_length"] > 67 for row in receipt["rows"]))
        self.assertEqual(receipt["counts"]["fragments"], len(receipt["rows"]))
        self.assertGreaterEqual(len(receipt["rows"]), EXPECTED_FIXTURES - 2)
        # Measured with the pinned tokenizer, since alignment is a property of
        # one tokenizer and of no other.
        self.assertEqual(receipt["model"]["tree_sha256"], MLX_RUNTIME["model"]["expected_tree_sha256"])
        covered = {row["fixture"] for row in receipt["rows"]}
        self.assertIn("ordinary-decision", covered, "the one success must be measured")
        self.assertIn("ordinary-action", covered, "the matched failure must be measured")


class RegisteredShapeTests(unittest.TestCase):
    def test_the_fixture_suite_is_the_twelve_the_protocol_registers(self) -> None:
        fixtures = matrix._fixtures()
        self.assertEqual(len(fixtures), EXPECTED_FIXTURES)
        # The protocol names the composition, not just the count: four ordinary,
        # two locator-order, two name/number, two negation, two abstention.
        prefixes = sorted(identifier.split("-")[0] for identifier in fixtures)
        self.assertEqual(
            prefixes,
            ["abstain"] * 2 + ["locator"] * 2 + ["name"] * 2 + ["negation"] * 2 + ["ordinary"] * 4,
        )

    def test_the_single_process_runner_still_refuses_the_full_scope(self) -> None:
        """The orchestrator exists precisely because that runner cannot do this."""
        from measure_mlx_note_candidate import fixtures_for_scope

        with self.assertRaises(ValueError):
            fixtures_for_scope("full")

    def test_both_runners_apply_the_same_model_side_checks(self) -> None:
        """Two copies of the gate would let the matrix grade itself leniently."""
        import measure_mlx_note_candidate as probe

        self.assertIs(matrix.model_call_checks, probe.model_call_checks)


if __name__ == "__main__":
    unittest.main()
