"""Exercise the contract mask against a synthetic vocabulary, before any download.

A mask that is subtly wrong produces a confident, meaningless model run — the
model would look like it satisfied a contract the mask was not actually
enforcing, or would be blocked from a response it could have produced. Neither
failure announces itself in the receipt, which is why this runs first and why it
tests reachability in both directions: nothing outside the contract survives,
and everything the contract permits is still reachable.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from structured_decoding import (
    ITEM_FIELDS,
    ContractMachine,
    MaskRefused,
    allowed_token_ids,
)

POPULATED = (
    '{"items":[{"candidate_id":"c1","source_fragment_ids":["f1","f2"],'
    '"citation":"we ship on Thursday","label":"DECISION",'
    '"claim":"the team decided to ship Thursday"}]}'
)
ABSTENTION = '{"items":[]}'


class ContractLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = ContractMachine()

    def test_the_two_shapes_the_parser_accepts_are_complete(self) -> None:
        for text in (POPULATED, ABSTENTION):
            with self.subTest(text=text[:40]):
                self.assertTrue(self.machine.complete(text))
                self.assertEqual(json.loads(text)["items"], json.loads(text)["items"])

    def test_every_prefix_of_a_valid_response_stays_viable(self) -> None:
        """The property the mask depends on. If any prefix were rejected the
        model would be blocked mid-response with no token left to sample."""
        for text in (POPULATED, ABSTENTION):
            for cut in range(len(text) + 1):
                with self.subTest(text=text[:20], cut=cut):
                    self.assertTrue(
                        self.machine.viable(text[:cut]),
                        f"prefix {text[:cut]!r} was rejected",
                    )

    def test_a_complete_response_admits_nothing_further(self) -> None:
        self.assertFalse(self.machine.viable(POPULATED + " "))
        self.assertFalse(self.machine.viable(ABSTENTION + "\n"))
        self.assertFalse(self.machine.viable(ABSTENTION + "{"))

    def test_two_items_and_a_single_fragment_id_are_reachable(self) -> None:
        item = (
            '{"candidate_id":"c1","source_fragment_ids":["f1"],'
            '"citation":"a","label":"ACTION","claim":"b"}'
        )
        self.assertTrue(self.machine.complete('{"items":[' + item + "," + item + "]}"))

    def test_the_failures_the_prior_probe_recorded_are_unreachable(self) -> None:
        # `response-contract`: the empty-candidate fixture returned two bytes.
        self.assertFalse(self.machine.viable("{}"))
        self.assertFalse(self.machine.viable("[]"))
        # `response-json-syntax`: prose, a fence, or a bare array.
        for text in ("Here", "```", '{"item', '{"items":{'):
            with self.subTest(text=text):
                self.assertFalse(self.machine.complete(text))
        self.assertFalse(self.machine.viable('{"items":{'))
        self.assertFalse(self.machine.viable("Here"))
        self.assertFalse(self.machine.viable("```json"))

    def test_field_order_is_enforced_not_merely_membership(self) -> None:
        swapped = (
            '{"items":[{"source_fragment_ids":["f1"],"candidate_id":"c1",'
            '"citation":"a","label":"ACTION","claim":"b"}]}'
        )
        self.assertFalse(self.machine.viable(swapped))

    def test_a_missing_or_extra_field_cannot_be_reached(self) -> None:
        missing = (
            '{"items":[{"candidate_id":"c1","source_fragment_ids":["f1"],'
            '"citation":"a","label":"ACTION"}]}'
        )
        self.assertFalse(self.machine.viable(missing))
        extra = POPULATED[:-3] + ',"extra":"x"}]}'
        self.assertFalse(self.machine.viable(extra))

    def test_an_empty_fragment_list_cannot_be_reached(self) -> None:
        # The contract requires one to three offered IDs, so `[]` here is not an
        # abstention — it is an item claiming no evidence.
        empty = (
            '{"items":[{"candidate_id":"c1","source_fragment_ids":[],'
            '"citation":"a","label":"ACTION","claim":"b"}]}'
        )
        self.assertFalse(self.machine.viable(empty))

    def test_the_fragment_id_ceiling_holds(self) -> None:
        ids = ",".join(f'"f{n}"' for n in range(1, 5))
        over = (
            '{"items":[{"candidate_id":"c1","source_fragment_ids":[' + ids + "],"
            '"citation":"a","label":"ACTION","claim":"b"}]}'
        )
        self.assertFalse(self.machine.viable(over))

    def test_free_text_cannot_break_out_of_its_string(self) -> None:
        for body in ('a"b', "a\\b", "a\nb"):
            with self.subTest(body=body):
                self.assertFalse(
                    self.machine.viable(
                        '{"items":[{"candidate_id":"' + body
                    )
                )

    def test_values_are_left_free_which_is_the_point(self) -> None:
        """The locator gate has to stay able to fail, so nothing checks values."""
        wrong = (
            '{"items":[{"candidate_id":"not-an-offered-id",'
            '"source_fragment_ids":["also-invented"],'
            '"citation":"words that appear in no fragment",'
            '"label":"NOT-A-LABEL","claim":"anything at all"}]}'
        )
        self.assertTrue(self.machine.complete(wrong))


class MaskTests(unittest.TestCase):
    """Reachability through a vocabulary, which is what the model actually sees."""

    def setUp(self) -> None:
        self.machine = ContractMachine()
        pieces = [
            "{", "}", "[", "]", '"', ":", ",", " ",
            "items", "candidate_id", "source_fragment_ids", "citation",
            "label", "claim", "c1", "f1", "f2", "DECISION", "ACTION",
            "we", "ship", "on", "Thursday", "the", "team", "decided", "to",
            '{"items":[', '"}]}', "Here", "```", "\n", "\\",
        ]
        self.vocabulary = dict(enumerate(pieces))
        self.eos = frozenset({len(pieces)})
        self.vocabulary[len(pieces)] = "<eos>"

    def allowed(self, emitted: str) -> set[str]:
        identifiers = allowed_token_ids(
            self.machine, emitted, self.vocabulary, self.eos
        )
        return {self.vocabulary[identifier] for identifier in identifiers}

    def test_only_the_opening_brace_starts_a_response(self) -> None:
        allowed = self.allowed("")
        self.assertIn("{", allowed)
        self.assertIn('{"items":[', allowed)
        for rejected in ("Here", "```", "[", '"', "\n"):
            self.assertNotIn(rejected, allowed)

    def test_after_the_root_only_abstain_or_open_an_item(self) -> None:
        self.assertEqual(self.allowed('{"items":['), {"{", "]"})

    def test_multi_character_tokens_that_span_the_skeleton_are_admitted(self) -> None:
        """A token carrying several skeleton characters must not be rejected for
        overshooting — byte-BPE vocabularies are full of them."""
        emitted = (
            '{"items":[{"candidate_id":"c1","source_fragment_ids":["f1"],'
            '"citation":"a","label":"ACTION","claim":"b'
        )
        self.assertIn('"}]}', self.allowed(emitted))

    def test_eos_is_withheld_until_the_response_is_complete(self) -> None:
        self.assertNotIn("<eos>", self.allowed('{"items":['))
        self.assertIn("<eos>", self.allowed(ABSTENTION))

    def test_free_text_admits_words_and_refuses_string_breakers(self) -> None:
        emitted = '{"items":[{"candidate_id":"c1","source_fragment_ids":["f1"],"citation":"'
        allowed = self.allowed(emitted)
        self.assertIn("we", allowed)
        self.assertIn("ship", allowed)
        self.assertIn('"', allowed)
        self.assertNotIn("\\", allowed)
        self.assertNotIn("\n", allowed)

    def test_a_vocabulary_that_cannot_express_the_contract_refuses_loudly(self) -> None:
        """Silence here would look like a model failure in the receipt."""
        with self.assertRaises(MaskRefused):
            allowed_token_ids(self.machine, "", {0: "Here", 1: "```"}, frozenset())

    def walk_to(self, target: str) -> str:
        """Emit `target` one token at a time, taking only tokens the mask allows.

        Reachability in the direction that matters. A mask can pass every
        rejection test above and still be useless if the response a good model
        would write cannot be assembled from this vocabulary without stepping
        outside the allowed set at some point.
        """
        emitted = ""
        while emitted != target:
            identifiers = allowed_token_ids(
                self.machine, emitted, self.vocabulary, self.eos
            )
            candidates = [
                self.vocabulary[identifier]
                for identifier in identifiers
                if identifier not in self.eos
                and target.startswith(emitted + self.vocabulary[identifier])
            ]
            self.assertTrue(
                candidates,
                f"the mask blocked every continuation of {emitted!r}",
            )
            emitted += max(candidates, key=len)
        return emitted

    def test_a_populated_response_is_reachable_token_by_token(self) -> None:
        emitted = self.walk_to(POPULATED)
        self.assertTrue(self.machine.complete(emitted))
        parsed = json.loads(emitted)
        self.assertEqual(list(parsed), ["items"])
        for row in parsed["items"]:
            self.assertEqual(tuple(row), ITEM_FIELDS)
        self.assertIn("<eos>", self.allowed(emitted))

    def test_the_abstention_is_reachable_token_by_token(self) -> None:
        self.assertTrue(self.machine.complete(self.walk_to(ABSTENTION)))


if __name__ == "__main__":
    unittest.main()
