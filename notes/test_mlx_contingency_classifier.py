from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notes"))

from mlx_contingency_classifier import (
    FIXTURES,
    MODALITIES,
    REPEATS,
    decode_response,
    expected_modalities,
    model_request,
    run_probe,
)
from mlx_note_admission import (
    AdmissionRefused,
    MLX_RUNTIME,
    _canonical_json,
    _provider_user_request,
    _sha256,
)


def response_for(request: dict, modalities: list[str] | None = None) -> str:
    values = modalities or expected_modalities()
    return json.dumps({
        "items": [
            {"candidate_id": row["candidate_id"], "modality": modality}
            for row, modality in zip(request["candidates"], values, strict=True)
        ]
    }, separators=(",", ":"))


def observed_for(request: dict) -> dict:
    user = _provider_user_request(request)
    return {
        "model_tree_sha256": MLX_RUNTIME["model"]["expected_tree_sha256"],
        "runtime_identity": deepcopy(MLX_RUNTIME["runtime_identity"]),
        "request_sha256": _sha256(_canonical_json({
            "system": request["system"], "user": user,
        })),
        "rendered_template_sha256": "a" * 64,
        "decoder": "unconstrained",
        "generation": {
            "call_elapsed_s": 0.1,
            "prompt_tokens": "unavailable",
            "generated_tokens": "unavailable",
            "finish_reason": "stop",
        },
    }


class MlxContingencyClassifierTests(unittest.TestCase):
    def test_expected_labels_never_enter_the_model_request(self) -> None:
        request = model_request()
        candidates = _canonical_json(request["candidates"])
        self.assertEqual(len(request["candidates"]), len(FIXTURES))
        for modality in MODALITIES:
            self.assertNotIn(modality, candidates)
        self.assertNotIn("expected", candidates)

    def test_fixture_set_contains_both_marker_free_controls(self) -> None:
        fixtures = {name: (text.lower(), expected) for name, text, expected in FIXTURES}
        pending, pending_expected = fixtures["conditional-pending"]
        scenario, scenario_expected = fixtures["hypothetical-scenario"]
        self.assertEqual(pending_expected, "CONDITIONAL")
        self.assertFalse(any(term in pending.split() for term in ("if", "unless", "barring")))
        self.assertEqual(scenario_expected, "HYPOTHETICAL")
        self.assertNotIn("if", scenario.split())
        self.assertNotIn("would", scenario.split())

    def test_decoder_accepts_only_exact_ordered_complete_rows(self) -> None:
        request = model_request()
        self.assertEqual(
            [row["modality"] for row in decode_response(response_for(request), request)],
            expected_modalities(),
        )

        invalid = json.loads(response_for(request))
        invalid["items"][0] = {
            "modality": invalid["items"][0]["modality"],
            "candidate_id": invalid["items"][0]["candidate_id"],
        }
        with self.assertRaises(AdmissionRefused):
            decode_response(json.dumps(invalid, separators=(",", ":")), request)

        invalid = json.loads(response_for(request))
        invalid["items"][0]["candidate_id"] = "unknown"
        with self.assertRaises(AdmissionRefused):
            decode_response(json.dumps(invalid, separators=(",", ":")), request)

    def test_perfect_repeatable_provider_passes_without_admitting_notes(self) -> None:
        def provider(request: dict) -> tuple[str, dict]:
            return response_for(request), observed_for(request)

        receipt = run_probe(provider)
        self.assertEqual(len(receipt["calls"]), REPEATS)
        self.assertTrue(receipt["passed"])
        self.assertFalse(receipt["admits"])
        self.assertTrue(all(receipt["gates"].values()))

    def test_semantic_miss_or_changed_repeat_fails(self) -> None:
        calls = 0

        def provider(request: dict) -> tuple[str, dict]:
            nonlocal calls
            calls += 1
            modalities = expected_modalities()
            if calls == REPEATS:
                modalities[0] = "HYPOTHETICAL"
            return response_for(request, modalities), observed_for(request)

        receipt = run_probe(provider)
        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["gates"]["all_fixtures_match"])
        self.assertFalse(receipt["gates"]["repeatable"])

    def test_parse_refusal_keeps_runtime_and_content_free_shape(self) -> None:
        def provider(request: dict) -> tuple[str, dict]:
            raw = json.dumps([{"modality": value} for value in expected_modalities()])
            return raw, observed_for(request)

        receipt = run_probe(provider)
        self.assertFalse(receipt["passed"])
        for call in receipt["calls"]:
            self.assertEqual(call["code"], "response-contract")
            self.assertIsNotNone(call["runtime"])
            self.assertEqual(call["untrusted_actual"], expected_modalities())
            self.assertEqual(call["untrusted_agreement"], len(FIXTURES))
            self.assertEqual(call["response_shape"], {
                "root_type": "array",
                "items": len(FIXTURES),
                "item_keys": [("modality",)],
            })

    def test_committed_receipt_records_the_failed_candidate_and_current_harness(self) -> None:
        receipt = json.loads(
            (Path(__file__).with_name("mlx_note_modality_probe_receipt.json")).read_text()
        )
        harness = Path(__file__).with_name("mlx_contingency_classifier.py")
        self.assertEqual(receipt["harness_sha256"], _sha256(harness.read_bytes()))
        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["admits"])
        self.assertTrue(receipt["gates"]["expected_labels_hidden"])
        self.assertTrue(receipt["gates"]["repeatable"])
        self.assertFalse(receipt["gates"]["all_fixtures_match"])
        self.assertEqual({call["code"] for call in receipt["calls"]}, {"response-contract"})
        self.assertEqual({call["untrusted_agreement"] for call in receipt["calls"]}, {6})
        self.assertEqual(len({call["response_sha256"] for call in receipt["calls"]}), 1)


if __name__ == "__main__":
    unittest.main()
