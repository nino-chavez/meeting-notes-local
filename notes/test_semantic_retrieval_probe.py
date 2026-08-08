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


if __name__ == "__main__":
    unittest.main()
