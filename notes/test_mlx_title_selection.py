#!/usr/bin/env python3
"""Protocol tests for the title-selection probe. No model, no network.

The mask is exercised before anything is downloaded, per the rule
`MLX_NOTE_ADMISSION.md` set after two mask defects there "would have produced a
confident wrong answer rather than an error".
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mlx_note_admission import MLX_RUNTIME  # noqa: E402
from mlx_title_selection import (  # noqa: E402
    RUNTIME_IDENTITY_FIELDS,
    SYSTEM_PROMPT,
    TITLE_DECODING,
    TitleRefused,
    decode_response,
    load_fixtures,
    model_request,
    offered_turns,
    response_contract,
)
from title_decoding import (  # noqa: E402
    PREFIX,
    SUFFIX,
    TitleSelectionMachine,
    values_for,
)


def search_alphabet(machine: TitleSelectionMachine) -> set[str]:
    """Every character the machine can accept, **less whitespace**.

    Whitespace is excluded from the search and covered by its own test, because
    the machine tolerates unbounded runs of it before and after the object. With
    four whitespace characters in the alphabet the walk below stops enumerating
    a small language and starts enumerating 4^ceiling whitespace strings, which
    is how the first version of this file ran until it was killed. Padding a
    valid JSON string with whitespace cannot make it invalid, so nothing the
    soundness claim rests on is skipped.
    """
    alphabet = set(PREFIX + SUFFIX)
    for value in machine.values:
        alphabet |= set(value)
    # Characters that must be *refused* wherever they appear, so the walk is a
    # search over more than the language's own letters.
    alphabet |= set('0123456789 ",:{}[]-.tfn')
    return alphabet - set(" \t\r\n")


def complete_strings(machine: TitleSelectionMachine, ceiling: int = 14) -> set[str]:
    """Every string the machine completes, found by walking its transitions.

    Deliberately not `machine.language()`: that method is built from the same
    `values` tuple the machine walks, so comparing the two would only prove the
    tuple equals itself. This searches the alphabet the machine actually accepts
    and is what `language()` is checked against.
    """
    alphabet = search_alphabet(machine)
    found: set[str] = set()
    frontier = [""]
    seen = {""}
    while frontier:
        text = frontier.pop()
        if len(text) >= ceiling:
            continue
        for character in alphabet:
            extended = text + character
            state = machine.state_after(extended)
            if state is None:
                continue
            if state == ("done",):
                found.add(extended)
            if extended not in seen:
                seen.add(extended)
                frontier.append(extended)
    return found


class TitleMaskTests(unittest.TestCase):
    def test_the_whole_accepted_language_is_enumerated_and_every_string_is_valid_json(self):
        """Total, not sampled — which is the difference from the note mask.

        `structured_decoding.py` could only enumerate its language "at a reduced
        ceiling (one item, two fragment IDs)" because of its free-text holes, and
        288 of the 385 strings it accepted there were invalid JSON. This contract
        has no free-text hole, so every accepted string is checked.
        """
        for offered in [(0,), (0, 1, 2), (1, 12), (0, 3, 7, 11)]:
            machine = TitleSelectionMachine(offered)
            walked = complete_strings(machine)
            self.assertEqual(
                walked,
                set(machine.language()),
                f"{offered}: language() and the transitions disagree",
            )
            self.assertEqual(len(walked), len(offered) + 1)
            for string in walked:
                decoded = json.loads(string)
                self.assertEqual(tuple(decoded), ("turn",))
                self.assertIn(decoded["turn"], [None, *offered])

    def test_an_index_that_is_a_prefix_of_another_can_both_finish_and_continue(self):
        machine = TitleSelectionMachine((1, 12))
        self.assertTrue(machine.complete('{"turn":1}'))
        self.assertTrue(machine.complete('{"turn":12}'))
        self.assertTrue(machine.viable('{"turn":1'))
        self.assertFalse(machine.viable('{"turn":13'))

    def test_every_reachable_state_can_still_reach_a_complete_response(self):
        """The non-blocking property. It catches the opposite defect from
        soundness — a state the model can enter and then sample nothing from,
        which is a `MaskRefused` for a model that did nothing wrong. Introducing
        one is how the note mask's own fix broke it.
        """
        machine = TitleSelectionMachine((0, 1, 12))
        alphabet = search_alphabet(machine)
        frontier = [""]
        seen = {""}
        while frontier:
            text = frontier.pop()
            state = machine.state_after(text)
            self.assertIsNotNone(state)
            if state != ("done",):
                self.assertTrue(
                    any(
                        machine.state_after(text + character) is not None
                        for character in alphabet
                    ),
                    f"{text!r} is a dead end",
                )
            if len(text) >= 14:
                continue
            for character in alphabet:
                extended = text + character
                if extended in seen or machine.state_after(extended) is None:
                    continue
                seen.add(extended)
                frontier.append(extended)

    def test_leading_whitespace_is_tolerated_because_the_first_token_is_unmasked(self):
        machine = TitleSelectionMachine((0,))
        self.assertTrue(machine.complete('\n {"turn":0}'))
        self.assertTrue(machine.complete('{"turn":0}  '))
        self.assertFalse(machine.viable('{"turn" :0}'))

    def test_a_withheld_turn_has_no_index_in_the_language_at_all(self):
        fixture = next(f for f in load_fixtures() if f["name"] == "withheld-first")
        gated = [i for i, turn in enumerate(fixture["turns"]) if turn["gated"]]
        self.assertTrue(gated, "the fixture must contain a withheld turn")
        offered = offered_turns(fixture)
        for index in gated:
            self.assertNotIn(index, offered)
        machine = TitleSelectionMachine(offered)
        for index in gated:
            self.assertFalse(
                machine.viable(f'{PREFIX}{index}'),
                "a withheld turn is reachable in the response language",
            )

    def test_the_machine_refuses_an_empty_or_repeated_offer(self):
        with self.assertRaises(ValueError):
            values_for(())
        with self.assertRaises(ValueError):
            values_for((1, 1))
        with self.assertRaises(ValueError):
            values_for((-1,))


class TitleParserTests(unittest.TestCase):
    def test_the_registered_shapes_decode(self):
        self.assertEqual(decode_response('{"turn":2}', (0, 2)), 2)
        self.assertIsNone(decode_response('{"turn":null}', (0, 2)))

    def test_every_refusal_class_is_reachable(self):
        cases = {
            "": "response-json-syntax",
            "not json": "response-json-syntax",
            '{"turn":2,}': "response-json-syntax",
            '{"turn":2,"turn":3}': "response-contract",
            '{"turn":2,"extra":1}': "response-contract",
            '{"index":2}': "response-contract",
            "[2]": "response-contract",
            '{"turn":"2"}': "response-contract",
            '{"turn":2.0}': "response-contract",
            '{"turn":true}': "response-contract",
            '{"turn":9}': "turn-not-offered",
        }
        for raw, expected in cases.items():
            with self.assertRaises(TitleRefused, msg=raw) as caught:
                decode_response(raw, (0, 2))
            self.assertEqual(caught.exception.code, expected, raw)

    def test_true_does_not_decode_as_turn_one(self):
        """`isinstance(True, int)` is True in Python, so this is a real hole and
        not a hypothetical: an `isinstance` check would have selected turn 1."""
        with self.assertRaises(TitleRefused):
            decode_response('{"turn":true}', (0, 1))

    def test_the_mask_is_stricter_than_the_parser_and_only_about_formatting(self):
        """Where the two disagree, and why the difference is the right one.

        The mask accepts one spelling per answer, so a masked run's responses are
        byte-comparable across repeats. The parser accepts any JSON that means
        the same thing, because its job is the contract and not the formatting —
        `{"turn": 2}` with a space is the same answer.

        The first version of this test asserted the parser refused it too. It
        does not, and it should not; the assertion was wrong rather than the
        parser.
        """
        machine = TitleSelectionMachine((0, 2))
        self.assertFalse(machine.viable('{"turn": 2}'))
        self.assertEqual(decode_response('{"turn": 2}', (0, 2)), 2)

        # Both refuse these, independently. The note mask was believed to make
        # invalid JSON unreachable while admitting 288 invalid strings of 385,
        # and its parser is what caught that.
        for raw in ('{"turn":02}', '{"turn":-1}', '{"turn":2,}'):
            self.assertFalse(machine.viable(raw), raw)
            with self.assertRaises(TitleRefused, msg=raw):
                decode_response(raw, (0, 2))


class TitleRequestTests(unittest.TestCase):
    def test_the_offered_enum_ends_close_to_the_generation_point(self):
        """The exposure measurement in `MLX_NOTE_ADMISSION.md` found the *last
        complete instance* before the generation point predicting what this model
        reproduces, at 365 characters for the field it got right and 726–794 for
        the field it got wrong. This asserts the property rather than trusting
        the layout.

        An earlier version asserted `response_contract` sorted last. It does not
        — canonical JSON sorts `schema` after it, exactly as in the note request
        — and that assertion was measuring a proxy for the thing that matters.
        What matters is the tail, which is a short schema string and a closing
        brace.
        """
        for fixture in load_fixtures():
            request = model_request(fixture)
            user = {key: value for key, value in request.items() if key != "system"}
            payload = json.dumps(
                user, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            offered = offered_turns(fixture)
            last = str(offered[-1])
            tail = len(payload) - payload.rindex(f"{last}]") - len(last)
            self.assertLess(tail, 80, f"{fixture['name']}: enum is {tail} from the end")
            # And no turn text sits between the enum and the end.
            for turn in fixture["turns"]:
                self.assertNotIn(turn["text"], payload[-tail:])

    def test_the_contract_enumerates_exactly_the_offered_turns_and_null(self):
        for fixture in load_fixtures():
            offered = offered_turns(fixture)
            contract = response_contract(offered)
            self.assertEqual(contract["turn"]["enum"], [None, *offered])
            self.assertEqual(contract["ordered_fields"], ["turn"])

    def test_the_system_prompt_states_the_rule_the_parser_enforces(self):
        self.assertIn("null", SYSTEM_PROMPT)
        self.assertIn("turn number", SYSTEM_PROMPT)

    def test_a_request_offers_no_gated_turn_and_carries_no_gated_text(self):
        for fixture in load_fixtures():
            request = model_request(fixture)
            offered = {row["turn"] for row in request["offered_turns"]}
            for index, turn in enumerate(fixture["turns"]):
                if turn["gated"]:
                    self.assertNotIn(index, offered)
                    self.assertNotIn(
                        turn["text"],
                        json.dumps(request, ensure_ascii=False),
                        "withheld text reached the request",
                    )


class TitleFixtureTests(unittest.TestCase):
    def test_every_fixture_names_a_control_turn_and_an_intended_turn(self):
        for fixture in load_fixtures():
            name = fixture["name"]
            offered = offered_turns(fixture)
            self.assertIn(fixture["control_turn"], offered, name)
            intended = fixture["intended_turn"]
            if intended is not None:
                self.assertIn(intended, offered, name)
            self.assertTrue(fixture["why"].strip(), name)

    def test_the_suite_contains_a_case_where_control_and_intended_agree(self):
        """Without one, a rule that always avoids the deterministic pick would
        score perfectly while having learned nothing."""
        fixtures = load_fixtures()
        self.assertTrue(
            any(f["control_turn"] == f["intended_turn"] for f in fixtures),
            "no fixture where the deterministic rule is already right",
        )

    def test_the_suite_contains_an_abstention_case(self):
        self.assertTrue(any(f["intended_turn"] is None for f in load_fixtures()))

    def test_no_degenerate_position_rule_scores_well(self):
        """A rule that never reads a word must do badly, or the suite is not a
        measurement of selection.

        This is not hypothetical. The first draft of the fixture file put the
        identifying turn second-from-the-start in five of ten cases and last in
        five, so "always take the second offered turn" scored 6 of 10 and
        "always take the last" scored 5. Both are strategies a model can follow
        without reading anything, and either would have been reported as
        selection working. The suite was rebalanced against this test rather
        than the test relaxed against the suite.

        The ceiling is 3 of 10 — above the 1 of 10 the deterministic control
        scores, because a suite where position carried *no* information would be
        contrived in the other direction.
        """
        fixtures = load_fixtures()
        rules = {
            "always-first-offered": lambda offered: offered[0],
            "always-second-offered": lambda offered: offered[min(1, len(offered) - 1)],
            "always-last-offered": lambda offered: offered[-1],
            "always-abstain": lambda offered: None,
        }
        for name, rule in rules.items():
            score = sum(
                rule(offered_turns(fixture)) == fixture["intended_turn"]
                for fixture in fixtures
            )
            self.assertLessEqual(
                score,
                3,
                f"{name} scores {score}/{len(fixtures)} without reading a word",
            )

    def test_the_deterministic_control_scores_poorly_enough_to_be_worth_beating(self):
        """If the shipped rule already agreed with the intended turn everywhere,
        there would be nothing for a model to improve and the probe would be
        measuring nothing."""
        fixtures = load_fixtures()
        score = sum(f["control_turn"] == f["intended_turn"] for f in fixtures)
        self.assertLessEqual(score, 3, f"control already scores {score}")
        self.assertGreaterEqual(score, 1, "the control must be right somewhere")

    def test_most_fixtures_can_distinguish_the_model_from_the_control(self):
        """If control and intended agreed everywhere, the probe could not
        measure selection at all — every arm would score the same."""
        fixtures = load_fixtures()
        differing = [f for f in fixtures if f["control_turn"] != f["intended_turn"]]
        self.assertGreaterEqual(len(differing), len(fixtures) - 2)


def _receipt_paths() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        here / "mlx_title_selection_receipt.json",
        here / "mlx_title_selection_receipt_run2.json",
        here / "mlx_title_selection_receipt_run3.json",
    ]


class TitleReceiptTests(unittest.TestCase):
    """Against the committed 2026-08-08 receipts.

    Every number here is a **literal**, not a value read back from the live
    fixture file or a live constant. CLAUDE.md records this being got wrong three
    times in one day: a frozen receipt asserted through `EXPECTED_FIXTURES`
    silently re-certifies itself against whatever the suite later became. These
    receipts describe a run that happened once, with ten fixtures, and they will
    still describe it after an eleventh is added.
    """

    def test_the_committed_receipts_were_produced_by_the_current_harness(self):
        from mlx_note_admission import _sha256

        here = Path(__file__).resolve().parent
        current = {
            "source_sha256": _sha256((here / "mlx_title_selection.py").read_bytes()),
            "decoder_sha256": _sha256((here / "title_decoding.py").read_bytes()),
        }
        fixtures_sha256 = _sha256((here / "title_selection_fixtures.json").read_bytes())
        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt["harness"], current, path.name)
            self.assertEqual(receipt["fixtures_sha256"], fixtures_sha256, path.name)

    def test_the_registered_prediction_failed_at_five_of_ten(self):
        """The literal the run produced. The registered range was 6 to 9."""
        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            rows = receipt["rows"]
            self.assertEqual(len(rows), 10, path.name)
            self.assertEqual(
                sum(bool(row["agreed_with_intended"]) for row in rows), 5, path.name
            )

    def test_the_model_never_abstained_on_any_fixture(self):
        for path in _receipt_paths():
            rows = json.loads(path.read_text())["rows"]
            self.assertEqual([row["outcome"] for row in rows], ["selected"] * 10)
            self.assertEqual(
                [row["selected_turn"] for row in rows].count(None),
                0,
                "an abstention would change the finding recorded in the doc",
            )

    def test_the_three_cold_runs_are_identical_apart_from_timings(self):
        """The repeatability gate, resting on the artifacts rather than on a
        sentence in the doc."""

        def without_timings(receipt: dict) -> dict:
            receipt = json.loads(json.dumps(receipt))
            receipt["load"].pop("model_load_elapsed_s", None)
            for row in receipt["rows"]:
                generation = row.get("observed", {}).get("generation", {})
                generation.pop("call_elapsed_s", None)
                generation.pop("mask_build_elapsed_s", None)
            return receipt

        stripped = [
            without_timings(json.loads(path.read_text())) for path in _receipt_paths()
        ]
        self.assertEqual(stripped[0], stripped[1])
        self.assertEqual(stripped[1], stripped[2])

    def test_the_mask_never_refused_and_every_response_finished(self):
        for path in _receipt_paths():
            for row in json.loads(path.read_text())["rows"]:
                self.assertNotIn("code", row, path.name)
                self.assertEqual(row["observed"]["generation"]["finish_reason"], "stop")

    def test_the_model_tree_was_unchanged_across_the_run(self):
        for path in _receipt_paths():
            receipt = json.loads(path.read_text())
            self.assertEqual(
                receipt["load"]["preflight_model_tree_sha256"],
                receipt["postflight_model_tree_sha256"],
                path.name,
            )
            self.assertEqual(
                receipt["postflight_model_tree_sha256"],
                MLX_RUNTIME["model"]["expected_tree_sha256"],
            )


class TitleRuntimeTests(unittest.TestCase):
    def test_the_runtime_fields_are_driven_by_the_pin_rather_than_restated(self):
        self.assertEqual(
            RUNTIME_IDENTITY_FIELDS, tuple(MLX_RUNTIME["runtime_identity"])
        )

    def test_the_output_cap_is_far_below_the_note_contract_and_above_any_response(self):
        longest = max(
            len(string)
            for offered in [(0,), (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
            for string in TitleSelectionMachine(offered).language()
        )
        self.assertLess(TITLE_DECODING["max_tokens"], MLX_RUNTIME["decoding"]["max_tokens"])
        self.assertGreater(TITLE_DECODING["max_tokens"], longest // 4)
        self.assertEqual(TITLE_DECODING["temperature"], 0.0)
        self.assertEqual(TITLE_DECODING["seed"], 0)

    def test_this_probe_changes_no_registered_note_value(self):
        """A new contract in new files. The note harness's pin, prompt and
        decoding budget are read here and never written, so no committed matrix
        receipt is comparable-or-not because of this probe."""
        self.assertEqual(MLX_RUNTIME["decoding"]["max_tokens"], 512)
        self.assertEqual(MLX_RUNTIME["package"], "mlx-lm==0.30.4")
        self.assertEqual(
            MLX_RUNTIME["model"]["revision"],
            "8b403126fc14f14cfc99bb4cfa72ecbc129ea677",
        )


if __name__ == "__main__":
    unittest.main()
