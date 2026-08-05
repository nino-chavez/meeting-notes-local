"""Exercise the contract mask against a synthetic vocabulary, before any download.

A mask that is subtly wrong produces a confident, meaningless model run — the
model would look like it satisfied a contract the mask was not actually
enforcing, or would be blocked from a response it could have produced. Neither
failure announces itself in the receipt, which is why this runs first and why it
tests reachability in both directions: nothing outside the contract survives,
and everything the contract permits is still reachable.
"""

from __future__ import annotations

import contextlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structured_decoding
from structured_decoding import (
    ITEM_FIELDS,
    START,
    ContractMachine,
    MaskRefused,
    allowed_token_ids,
    step,
)

# Every character that can advance the skeleton. Literal and free-text states
# are handled separately by `_outgoing`, so this list only has to cover the
# junctions where the machine actually branches.
STRUCTURAL_CHARS = ("{", "}", "[", "]", ",", '"', ":")


def _outgoing(state: tuple) -> tuple:
    """The characters worth trying from `state`.

    A literal state admits exactly one character, and a free-text state admits
    one representative body character plus the closing quote. Enumerating the
    full alphabet at those positions would only multiply identical structure —
    the branches that matter are all structural.
    """
    if state[0] == "lit":
        return (state[1][state[2]],)
    if state[0] == "free":
        return ("x", '"')
    return STRUCTURAL_CHARS


@contextlib.contextmanager
def bounded(items: int, ids: int):
    """Shrink the ceilings so the language can be enumerated exhaustively."""
    before = (structured_decoding.MAX_ITEMS, structured_decoding.MAX_FRAGMENT_IDS)
    structured_decoding.MAX_ITEMS = items
    structured_decoding.MAX_FRAGMENT_IDS = ids
    try:
        yield
    finally:
        structured_decoding.MAX_ITEMS, structured_decoding.MAX_FRAGMENT_IDS = before

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
                parsed = json.loads(text)
                self.assertEqual(list(parsed), ["items"])
                for row in parsed["items"]:
                    self.assertEqual(tuple(row), ITEM_FIELDS)

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

    def test_a_complete_response_admits_only_trailing_whitespace(self) -> None:
        # `_strict_json` calls json.loads on the raw string, which tolerates
        # surrounding whitespace and nothing else. The mask matches that exactly.
        self.assertTrue(self.machine.complete(POPULATED + " "))
        self.assertTrue(self.machine.complete(ABSTENTION + "\n"))
        self.assertFalse(self.machine.viable(ABSTENTION + "{"))
        self.assertFalse(self.machine.viable(ABSTENTION + "and here is why"))

    def test_leading_whitespace_is_tolerated_because_the_parser_tolerates_it(self) -> None:
        # Load-bearing rather than cosmetic: mlx-lm 0.30.4 samples the first
        # token before any logits processor runs, and this model opens its turn
        # with a newline. Rejecting it would refuse every generation.
        self.assertTrue(self.machine.viable("\n"))
        self.assertTrue(self.machine.complete("\n" + ABSTENTION))
        self.assertTrue(self.machine.complete("  \n" + POPULATED + "\n"))
        # Whitespace inside the skeleton is still not reachable, so the mask
        # cannot drift into accepting a differently-formatted object.
        self.assertFalse(self.machine.viable('{ "items"'))
        self.assertFalse(self.machine.viable('{"items": ['))

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

    def test_a_trailing_comma_cannot_be_reached_in_either_list(self) -> None:
        """The hole a review found after the probe had already been reported.

        Both strings walked to a complete response and both are invalid JSON, so
        `_strict_json` would raise `response-json-syntax` — the very refusal
        class the mask exists to make unreachable, and the class the earlier
        unconstrained probe attributed to the model. Had the model taken the
        comma after an item and then hit `]` on the argmax, the run would have
        recorded a syntax refusal that could no longer be attributed between
        model and mask, which is the one distinction the experiment rests on.
        """
        after_item = POPULATED[:-2] + ",]}"
        in_id_list = POPULATED.replace('["f1","f2"]', '["f1","f2",]')
        for text in (after_item, in_id_list):
            with self.subTest(text=text[-24:]):
                self.assertRaises(json.JSONDecodeError, json.loads, text)
                self.assertFalse(self.machine.viable(text))

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


class StructuralPropertyTests(unittest.TestCase):
    """Two properties of the state graph, walked rather than case-listed.

    These exist because of what the hand-written cases above missed. Every one
    of them passed while `{"items":[{…},]}` walked cleanly to a complete
    response that `json.loads` rejects. A case list only tests the strings
    somebody thought of; a mask has to hold for the ones nobody did.

    The properties are independent and both are needed:

    * **Soundness** — everything the machine completes is valid JSON in the
      contract's shape. This is what catches a trailing comma, and the walk
      below is the check that would have failed on the shipped code.
    * **Non-blocking** — every reachable state can still reach a complete
      response. Co-reachability is *blind* to the trailing-comma hole, because
      the offending state does reach `("done",)` — that is the bug. What it
      catches is the opposite failure: a state the model can enter and never
      leave, which surfaces as `MaskRefused` on a run doing nothing wrong.
    """

    def setUp(self) -> None:
        self.machine = ContractMachine()

    def completed_strings(self, max_length: int = 400) -> list[str]:
        """Every string reachable from START that lands on ("done",)."""
        completed: list[str] = []
        stack = [("", START, False)]
        while stack:
            text, state, looped = stack.pop()
            if state == ("done",):
                completed.append(text)
                continue
            self.assertLessEqual(len(text), max_length, "the walk did not terminate")
            for character in _outgoing(state):
                following = step(state, character)
                if following is None:
                    continue
                # A free-text state loops on its body character; one is enough
                # to cover the hole, and more would only multiply the language.
                repeat = following == state
                if repeat and looped:
                    continue
                stack.append((text + character, following, repeat))
        return completed

    def test_everything_the_machine_completes_is_valid_json_in_contract_shape(self) -> None:
        with bounded(items=2, ids=2):
            completed = self.completed_strings()
        # Guards the walk itself: a machine that completed nothing would pass a
        # bare for-loop over an empty list without asserting anything at all.
        self.assertGreater(len(completed), 100)
        self.assertIn(ABSTENTION, completed)
        for text in completed:
            with self.subTest(text=text[:60]):
                parsed = json.loads(text)
                self.assertEqual(list(parsed), ["items"])
                self.assertLessEqual(len(parsed["items"]), 2)
                for row in parsed["items"]:
                    self.assertEqual(tuple(row), ITEM_FIELDS)
                    self.assertTrue(1 <= len(row["source_fragment_ids"]) <= 2)

    def transitions(self) -> dict[tuple, set[tuple]]:
        edges: dict[tuple, set[tuple]] = {}
        stack = [START]
        seen = {START}
        while stack:
            state = stack.pop()
            following = set()
            for character in _outgoing(state):
                nxt = step(state, character)
                if nxt is None:
                    continue
                following.add(nxt)
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
            edges[state] = following
        return edges

    def test_no_reachable_state_can_strand_the_model(self) -> None:
        """Run at the real ceilings, which is where the dead ends live."""
        edges = self.transitions()
        live = {("done",)}
        changed = True
        while changed:
            changed = False
            for state, following in edges.items():
                if state not in live and following & live:
                    live.add(state)
                    changed = True
        stranded = sorted(set(edges) - live, key=repr)
        self.assertEqual(
            stranded,
            [],
            "these states can be entered and never completed, so the mask would "
            f"raise MaskRefused mid-response: {stranded[:4]}",
        )

    def test_the_ceilings_are_reachable_and_are_where_the_language_stops(self) -> None:
        """The ceiling guards must bind at the ceiling, not before it."""
        item = (
            '{"candidate_id":"c","source_fragment_ids":["a","b","c"],'
            '"citation":"x","label":"y","claim":"z"}'
        )
        full = '{"items":[' + ",".join([item] * structured_decoding.MAX_ITEMS) + "]}"
        self.assertTrue(self.machine.complete(full))
        self.assertEqual(len(json.loads(full)["items"]), structured_decoding.MAX_ITEMS)
        # One past each ceiling is refused rather than stranded.
        self.assertFalse(
            self.machine.viable('{"items":[' + ",".join([item] * (structured_decoding.MAX_ITEMS + 1)))
        )
        self.assertFalse(
            self.machine.viable('{"items":[{"candidate_id":"c","source_fragment_ids":["a","b","c",')
        )


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
        state = self.machine.state_after(emitted)
        self.assertIsNotNone(state, f"{emitted!r} already left the contract")
        identifiers = allowed_token_ids(
            self.machine, state, self.vocabulary, self.eos
        )
        return {self.vocabulary[identifier] for identifier in identifiers}

    def test_only_the_opening_brace_starts_a_response(self) -> None:
        allowed = self.allowed("")
        self.assertIn("{", allowed)
        self.assertIn('{"items":[', allowed)
        # Whitespace survives, because the parser accepts it around the object.
        self.assertIn("\n", allowed)
        # Prose, fences, and any other opening do not.
        for rejected in ("Here", "```", "[", '"', "\\"):
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

    def test_a_stop_token_outside_the_scanned_vocabulary_is_still_admitted(self) -> None:
        """The bug that truncated every real generation.

        A tokenizer's `vocab_size` counts the base vocabulary and excludes the
        added special tokens, so the model's actual end-of-turn id sat above the
        scanned range and never entered the allowed set. The model produced a
        correct response and then could not stop, padding whitespace to the
        token cap. Stop ids are therefore handled outside the scan.
        """
        outside = max(self.vocabulary) + 500
        eos = frozenset({outside})
        state = self.machine.state_after(ABSTENTION)
        self.assertIn(outside, allowed_token_ids(self.machine, state, self.vocabulary, eos))
        open_state = self.machine.state_after('{"items":[')
        self.assertNotIn(
            outside, allowed_token_ids(self.machine, open_state, self.vocabulary, eos)
        )

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
            allowed_token_ids(self.machine, START, {0: "Here", 1: "```"}, frozenset())

    def walk_to(self, target: str) -> str:
        """Emit `target` one token at a time, taking only tokens the mask allows.

        Reachability in the direction that matters. A mask can pass every
        rejection test above and still be useless if the response a good model
        would write cannot be assembled from this vocabulary without stepping
        outside the allowed set at some point.
        """
        emitted = ""
        while emitted != target:
            state = self.machine.state_after(emitted)
            self.assertIsNotNone(state)
            identifiers = allowed_token_ids(
                self.machine, state, self.vocabulary, self.eos
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
