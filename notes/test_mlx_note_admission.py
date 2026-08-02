from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notes"))

from mlx_note_admission import (
    MLX_RUNTIME,
    _decode_response,
    _sha256,
    model_request,
    run_control_arm,
    run_model_arm,
    synthetic_corrective_probe_fixtures,
    synthetic_measurement_fixtures,
    synthetic_transcript,
    tree_sha256,
)
from measure_mlx_note_candidate import fixtures_for_scope
from candidate_first import STRATEGY_CUE, generate_manifest
from summarize import structured_artifact_citations


def advertised_response(request: dict, *, empty: bool = False) -> str:
    contract = request["response_contract"]
    root = contract["root"]
    root_field = root["ordered_fields"][0]
    if empty:
        return json.dumps(contract["empty_response"], separators=(",", ":"))
    candidate = request["candidates"][0]
    fragment = candidate["source_fragments"][0]
    fields = root["properties"][root_field]["item"]["ordered_fields"]
    values = {
        "candidate_id": candidate["candidate_id"],
        "source_fragment_ids": [fragment["source_fragment_id"]],
        "citation": fragment["text"],
        "label": contract["root"]["properties"][root_field]["item"]["properties"]["label"]["enum"][0],
        "claim": "Use the compact battery.",
    }
    return json.dumps({root_field: [{field: values[field] for field in fields}]}, separators=(",", ":"))


def observed_identity(request: dict) -> dict:
    user_request = {key: value for key, value in request.items() if key != "system"}
    return {
        "model_tree_sha256": MLX_RUNTIME["model"]["expected_tree_sha256"],
        "runtime_identity": deepcopy(MLX_RUNTIME["runtime_identity"]),
        "request_sha256": _sha256(json.dumps({"system": request["system"], "user": user_request}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
        "rendered_template_sha256": "a" * 64,
        "generation": {
            "call_elapsed_s": 0.1,
            "prompt_tokens": "unavailable",
            "generated_tokens": "unavailable",
            "finish_reason": "stop",
        },
    }


def accepted_provider(request: dict) -> tuple[str, dict]:
    return advertised_response(request), observed_identity(request)


class MlxNoteAdmissionTests(unittest.TestCase):
    def test_advertised_contract_nonempty_and_empty_shapes_pass_unchanged_parser(self) -> None:
        transcript = synthetic_transcript()
        manifest = generate_manifest(transcript, STRATEGY_CUE)
        request = model_request(transcript, manifest)
        self.assertEqual(request["response_contract"]["root"]["ordered_fields"], ["items"])
        self.assertEqual(
            request["response_contract"]["root"]["properties"]["items"]["item"]["ordered_fields"],
            ["candidate_id", "source_fragment_ids", "citation", "label", "claim"],
        )
        self.assertEqual(len(_decode_response(advertised_response(request), request, transcript)), 1)
        self.assertEqual(_decode_response(advertised_response(request, empty=True), request, transcript), [])

    def test_synthetic_measurement_plan_has_registered_coverage(self) -> None:
        fixtures = synthetic_measurement_fixtures()
        self.assertEqual(len(fixtures), 12)
        identifiers = [fixture[0] for fixture in fixtures]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(sum(fixture[2] == "accepted-research-candidate" for fixture in fixtures), 10)
        self.assertEqual(sum(fixture[2] == "transcript-only" for fixture in fixtures), 2)
        self.assertTrue(any("not" in fixture[3] for fixture in fixtures))
        self.assertTrue(any(any(character.isdigit() for character in term) for fixture in fixtures for term in fixture[3]))
        for _identifier, transcript, expected, _terms in fixtures:
            control = run_control_arm(transcript)
            if expected == "transcript-only":
                self.assertEqual(control.outcome, "transcript-only")
                self.assertEqual(control.code, "no-deterministic-candidates")
            else:
                self.assertEqual(control.outcome, expected)

    def test_corrective_probe_has_one_supported_and_one_empty_candidate_fixture(self) -> None:
        fixtures = synthetic_corrective_probe_fixtures()
        self.assertEqual([fixture[0] for fixture in fixtures], ["ordinary-decision", "abstain-chitchat"])
        self.assertEqual([fixture[2] for fixture in fixtures], ["accepted-research-candidate", "transcript-only"])

    def test_measurement_runner_refuses_unimplemented_full_scope(self) -> None:
        self.assertEqual(len(fixtures_for_scope("probe")), 2)
        with self.assertRaisesRegex(ValueError, "full-scope-not-implemented"):
            fixtures_for_scope("full")

    def test_research_model_manifest_is_immutable_and_has_a_download_budget(self) -> None:
        model = MLX_RUNTIME["model"]
        self.assertEqual(model["repository"], "mlx-community/Qwen2.5-1.5B-Instruct-4bit")
        self.assertEqual(len(model["revision"]), 40)
        self.assertTrue(all(character in "0123456789abcdef" for character in model["revision"]))
        self.assertEqual(model["license"], "Apache-2.0")
        self.assertGreater(model["expected_download_bytes"], 0)
        self.assertEqual(len(model["expected_model_safetensors_sha256"]), 64)
        self.assertEqual(
            model["expected_tree_sha256"],
            "3aaeeac4e5bffd4308187dac1b34d5145bc697f589255ff57d04cc53381ddb95",
        )
        self.assertEqual(model["status"], "corrective-probe-rejected-not-admitted")


    def test_control_arm_is_repeatable_and_replays_existing_note2_validation(self) -> None:
        transcript = synthetic_transcript()
        first = run_control_arm(transcript)
        second = run_control_arm(transcript)
        self.assertEqual(first.outcome, "accepted-research-candidate")
        self.assertEqual(first.note, second.note)
        assert first.note is not None
        self.assertEqual(structured_artifact_citations(first.note, transcript)["items"], 3)

    def test_model_arm_accepts_only_pinned_runtime_and_exact_canonical_citation(self) -> None:
        result = run_model_arm(
            synthetic_transcript(), accepted_provider
        )
        self.assertEqual(result.outcome, "accepted-research-candidate")
        assert result.note is not None
        self.assertEqual(result.note["schema"], "note/2")
        self.assertEqual(structured_artifact_citations(result.note, synthetic_transcript())["items"], 1)

    def test_malformed_unknown_citation_timeout_and_digest_mismatch_are_transcript_only(self) -> None:
        transcript = synthetic_transcript()
        request_manifest = generate_manifest(transcript, STRATEGY_CUE)
        candidate = request_manifest["candidates"][0]
        def malformed(_request: dict) -> tuple[str, dict]:
            return "{", observed_identity(_request)

        def unknown(_request: dict) -> tuple[str, dict]:
            raw = json.loads(advertised_response(_request))
            raw["items"][0]["candidate_id"] = "unknown"
            return json.dumps(raw), observed_identity(_request)

        def mismatch(_request: dict) -> tuple[str, dict]:
            raw = json.loads(advertised_response(_request))
            raw["items"][0]["citation"] = "not canonical words"
            return json.dumps(raw), observed_identity(_request)

        def unknown_source(_request: dict) -> tuple[str, dict]:
            raw = json.loads(advertised_response(_request))
            raw["items"][0]["source_fragment_ids"] = ["unknown"]
            return json.dumps(raw), observed_identity(_request)

        def wrong_root(_request: dict) -> tuple[str, dict]:
            return "[]", observed_identity(_request)

        def truncated(_request: dict) -> tuple[str, dict]:
            observed = observed_identity(_request)
            observed["generation"]["finish_reason"] = "length"
            return advertised_response(_request), observed

        def timeout(_request: dict) -> tuple[str, dict]:
            raise TimeoutError()

        def changed_digest(request: dict) -> tuple[str, dict]:
            raw, _ = accepted_provider(request)
            observed = observed_identity(request)
            observed["model_tree_sha256"] = "c" * 64
            return raw, observed

        def changed_package(request: dict) -> tuple[str, dict]:
            raw, _ = accepted_provider(request)
            observed = observed_identity(request)
            observed["runtime_identity"]["mlx"] = "0.0.0"
            return raw, observed

        expected = {
            malformed: "response-json-syntax",
            unknown: "citation-locator",
            mismatch: "citation-locator",
            unknown_source: "citation-locator",
            wrong_root: "response-contract",
            truncated: "response-length-truncation",
            timeout: "timeout",
            changed_digest: "model-digest-mismatch",
            changed_package: "runtime-package-mismatch",
        }
        for provider, code in expected.items():
            with self.subTest(code=code):
                result = run_model_arm(transcript, provider)
                self.assertEqual(result.outcome, "transcript-only")
                self.assertEqual(result.code, code)
                self.assertIsNone(result.note)

    def test_model_tree_digest_excludes_mutable_transfer_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.safetensors").write_bytes(b"synthetic model bytes")
            cache = root / ".cache" / "huggingface"
            cache.mkdir(parents=True)
            (cache / "transfer.lock").write_text("first", encoding="utf-8")
            first = tree_sha256(root)
            (cache / "transfer.lock").write_text("changed", encoding="utf-8")
            self.assertEqual(tree_sha256(root), first)


if __name__ == "__main__":
    unittest.main()
