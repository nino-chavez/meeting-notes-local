#!/usr/bin/env python3
"""Protocol tests for the semantic-retrieval probe. No model, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from semantic_retrieval_probe import (  # noqa: E402
    PIN,
    content_words,
    control_rank,
    load_fixtures,
    meeting_text,
    run,
)


class FixtureShapeTests(unittest.TestCase):
    def test_the_suite_is_half_answerable_by_exact_search_and_half_not(self):
        questions = load_fixtures()["questions"]
        easy = [q for q in questions if q["exact_helps"]]
        hard = [q for q in questions if not q["exact_helps"]]
        self.assertEqual((len(easy), len(hard)), (5, 5))

    def test_every_question_names_a_meeting_that_exists(self):
        document = load_fixtures()
        identifiers = {m["id"] for m in document["meetings"]}
        for question in document["questions"]:
            self.assertIn(question["intended_meeting"], identifiers)
            self.assertTrue(question["why"].strip())

    def test_the_corpus_is_large_enough_that_top_one_means_something(self):
        self.assertGreaterEqual(len(load_fixtures()["meetings"]), 8)

    def test_no_meeting_is_a_duplicate_of_another(self):
        texts = [meeting_text(m) for m in load_fixtures()["meetings"]]
        self.assertEqual(len(set(texts)), len(texts))


class ControlTests(unittest.TestCase):
    """The control is the suite's own difficulty check.

    The fixtures were once passable by word overlap alone — 8 of 10 overall and 3
    of 5 on the hard half — and two of those three were transcripts containing a
    word the fixture claimed was absent. These tests fail if that returns.
    """

    def test_a_ranker_that_reads_no_meaning_answers_none_of_the_hard_questions(self):
        document = load_fixtures()
        meetings = document["meetings"]
        for question in document["questions"]:
            if question["exact_helps"]:
                continue
            self.assertNotEqual(
                control_rank(question["question"], meetings),
                question["intended_meeting"],
                f"word overlap alone found {question['intended_meeting']} for "
                f"{question['question']!r}; the fixture is not as hard as it claims",
            )

    def test_zero_shared_words_is_no_answer_rather_than_a_tie_break_win(self):
        meetings = [
            {"id": "meeting-a", "turns": ["alpha beta gamma"]},
            {"id": "meeting-b", "turns": ["delta epsilon zeta"]},
        ]
        self.assertIsNone(control_rank("nothing whatsoever overlaps", meetings))

    def test_the_control_still_answers_where_a_word_is_genuinely_shared(self):
        meetings = [
            {"id": "meeting-a", "turns": ["the warehouse move is in April"]},
            {"id": "meeting-b", "turns": ["the pricing page conversion dropped"]},
        ]
        self.assertEqual(control_rank("when is the warehouse move?", meetings), "meeting-a")

    def test_stop_words_do_not_carry_a_match(self):
        self.assertEqual(content_words("What did we do about it?"), set())


class HarnessTests(unittest.TestCase):
    def test_the_probe_runs_without_a_model_and_reports_only_the_control(self):
        receipt = run(load_fixtures(), None)
        self.assertEqual(receipt["schema"], "semantic-retrieval/1")
        self.assertNotIn("model", receipt)
        self.assertIsNone(receipt["model_weights_sha256"])
        self.assertEqual(receipt["control"]["on_hard"], 0)
        self.assertEqual(len(receipt["rows"]), receipt["questions"])

    def test_no_receipt_row_carries_a_question_or_a_transcript(self):
        """Fixtures are synthetic and in Git, so this is not a privacy gate — it
        is the habit that makes the receipt shape the same one a real corpus
        could use."""
        receipt = run(load_fixtures(), None)
        document = load_fixtures()
        encoded = str(receipt)
        for question in document["questions"]:
            self.assertNotIn(question["question"], encoded)
        for meeting in document["meetings"]:
            for turn in meeting["turns"]:
                self.assertNotIn(turn, encoded)

    def test_the_pin_names_a_permissive_licence_for_both_model_and_package(self):
        self.assertEqual(PIN["model"]["license"], "Apache-2.0")
        self.assertEqual(PIN["package_license"], "Apache-2.0")
        # Recorded as rejected rather than omitted: the reason the probe uses a
        # reference implementation is a licence, and a later reader needs it.
        self.assertEqual(PIN["rejected_dependency"]["license"], "GPL-3.0")


def _receipt_paths() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        here / "semantic_retrieval_receipt.json",
        here / "semantic_retrieval_receipt_run2.json",
        here / "semantic_retrieval_receipt_run3.json",
    ]


class ReceiptTests(unittest.TestCase):
    """Against the committed 2026-08-08 receipts.

    Every number is a **literal**. CLAUDE.md records a frozen receipt asserted
    through a live constant silently re-certifying itself against whatever the
    suite later became, three times in one day. These describe a run that
    happened once, over ten meetings and ten questions.
    """

    def test_the_committed_receipts_were_produced_by_this_harness_and_these_fixtures(self):
        import json
        from semantic_retrieval_probe import _sha256

        here = Path(__file__).resolve().parent
        harness = _sha256((here / "semantic_retrieval_probe.py").read_bytes())
        fixtures = _sha256((here / "semantic_retrieval_fixtures.json").read_bytes())
        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt["harness_sha256"], harness, path.name)
            self.assertEqual(receipt["fixtures_sha256"], fixtures, path.name)

    def test_the_run_scored_ten_of_ten_and_five_of_five_on_the_hard_half(self):
        import json

        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt["questions"], 10, path.name)
            self.assertEqual(
                receipt["model"], {"overall": 10, "on_hard": 5, "on_easy": 5}, path.name
            )
            self.assertEqual(receipt["control"], {"overall": 5, "on_hard": 0}, path.name)

    def test_three_of_the_hard_five_were_decided_by_under_a_twentieth(self):
        """The finding the score hides. Recorded as a literal so a later run that
        widens these margins is visibly a different result rather than the same
        one."""
        import json

        receipt = json.loads(_receipt_paths()[0].read_text())
        hard = sorted(
            row["model_margin"] for row in receipt["rows"] if not row["exact_helps"]
        )
        self.assertEqual([round(m, 4) for m in hard], [0.0127, 0.0214, 0.0381, 0.1172, 0.2143])
        self.assertEqual(sum(1 for m in hard if m < 0.05), 3)

    def test_the_three_runs_agree_to_the_last_recorded_decimal(self):
        import json

        stripped = []
        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            receipt.pop("corpus_embed_elapsed_s", None)
            stripped.append(receipt)
        self.assertEqual(stripped[0], stripped[1])
        self.assertEqual(stripped[1], stripped[2])

    def test_the_receipts_bind_the_weights_that_were_pinned_before_download(self):
        import json

        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            self.assertEqual(
                receipt["model_weights_sha256"],
                PIN["model"]["expected_model_safetensors_sha256"],
                path.name,
            )


class ScaleReceiptTests(unittest.TestCase):
    """Against the committed 2026-08-08 scale run. Literals, not constants."""

    def setUp(self):
        import json

        self.receipt = json.loads(
            (Path(__file__).resolve().parent / "semantic_scale_receipt.json").read_text()
        )

    def at(self, unit: str, size: int) -> dict:
        return next(
            row
            for row in self.receipt["results"]
            if row["unit"] == unit and row["size"] == size
        )

    def test_every_meeting_in_the_corpus_crossed_the_truncation_ceiling(self):
        """The first corpus produced 212-token meetings and 8 of 200 crossed it.
        It would have measured dilution and reported it as truncation."""
        tokens = self.receipt["meeting_tokens"]
        self.assertEqual(tokens["over_ceiling"], 200)
        self.assertGreater(tokens["min"], 256)

    def test_both_registered_clauses_held(self):
        truncated = self.at("meeting-truncated", 200)["correct"]
        turn = self.at("turn", 200)["correct"]
        window = self.at("window", 200)["correct"]
        self.assertEqual((truncated, turn, window), (1, 7, 7))
        self.assertGreaterEqual(turn - truncated, 3)
        self.assertGreaterEqual(window - truncated, 3)
        self.assertLessEqual(abs(turn - window), 1)

    def test_the_tiebreak_that_chose_the_window_unit_is_twenty_to_one(self):
        self.assertEqual(self.at("turn", 200)["pieces"], 16020)
        self.assertEqual(self.at("window", 200)["pieces"], 800)

    def test_truncated_meetings_crowd_together_as_the_corpus_grows(self):
        medians = [self.at("meeting-truncated", n)["median_within_band"] for n in (30, 60, 120, 200)]
        self.assertEqual(medians, [3, 6, 13, 22])
        for unit in ("turn", "window"):
            self.assertEqual(
                [self.at(unit, n)["median_within_band"] for n in (30, 60, 120, 200)],
                [0, 0, 0, 0],
                unit,
            )

    def test_the_two_failures_arrive_as_exact_ties_rather_than_confident_answers(self):
        """A wrong answer with a 0.0000 margin and a crowded band is something a
        surface could act on. A wrong answer with a clean margin is not."""
        rows = [row for row in self.at("window", 200)["rows"] if not row["correct"]]
        self.assertEqual(len(rows), 3)
        tied = [row for row in rows if row["margin"] == 0.0]
        self.assertEqual(len(tied), 2)
        self.assertTrue(all(row["within_band"] >= 10 for row in tied))


if __name__ == "__main__":
    unittest.main()
