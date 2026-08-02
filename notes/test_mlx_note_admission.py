from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notes"))

from mlx_note_admission import (
    MLX_RUNTIME,
    run_control_arm,
    run_model_arm,
    synthetic_measurement_fixtures,
    synthetic_transcript,
    tree_sha256,
)
from candidate_first import STRATEGY_CUE, generate_manifest
from summarize import structured_artifact_citations


MODEL_TREE_DIGEST = "b" * 64


def accepted_provider(request: dict) -> tuple[str, dict]:
    candidate = request["candidates"][0]
    fragment = candidate["source_fragments"][0]
    raw = json.dumps({"items": [{
        "candidate_id": candidate["candidate_id"],
        "source_fragment_ids": [fragment["source_fragment_id"]],
        "citation": fragment["text"],
        "label": "DECISION",
        "claim": "Use the compact battery.",
    }]}, separators=(",", ":"))
    return raw, {"package": MLX_RUNTIME["package"], "model_tree_sha256": MODEL_TREE_DIGEST}


class MlxNoteAdmissionTests(unittest.TestCase):
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
        self.assertEqual(model["status"], "measured-rejected-not-admitted")


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
            synthetic_transcript(), accepted_provider, expected_model_tree_sha256=MODEL_TREE_DIGEST
        )
        self.assertEqual(result.outcome, "accepted-research-candidate")
        assert result.note is not None
        self.assertEqual(result.note["schema"], "note/2")
        self.assertEqual(structured_artifact_citations(result.note, synthetic_transcript())["items"], 1)

    def test_malformed_unknown_citation_timeout_and_digest_mismatch_are_transcript_only(self) -> None:
        transcript = synthetic_transcript()
        request_manifest = generate_manifest(transcript, STRATEGY_CUE)
        candidate = request_manifest["candidates"][0]
        fragment = candidate["anchor_fragment_id"]

        def malformed(_request: dict) -> tuple[str, dict]:
            return "{", {"package": MLX_RUNTIME["package"], "model_tree_sha256": MODEL_TREE_DIGEST}

        def unknown(_request: dict) -> tuple[str, dict]:
            return json.dumps({"items": [{
                "candidate_id": "unknown", "source_fragment_ids": [fragment],
                "citation": "x", "label": "DECISION", "claim": "x",
            }]}), {"package": MLX_RUNTIME["package"], "model_tree_sha256": MODEL_TREE_DIGEST}

        def mismatch(_request: dict) -> tuple[str, dict]:
            return json.dumps({"items": [{
                "candidate_id": candidate["candidate_id"], "source_fragment_ids": [fragment],
                "citation": "not canonical words", "label": "DECISION", "claim": "x",
            }]}), {"package": MLX_RUNTIME["package"], "model_tree_sha256": MODEL_TREE_DIGEST}

        def unknown_source(_request: dict) -> tuple[str, dict]:
            return json.dumps({"items": [{
                "candidate_id": candidate["candidate_id"], "source_fragment_ids": ["unknown"],
                "citation": "x", "label": "DECISION", "claim": "x",
            }]}), {"package": MLX_RUNTIME["package"], "model_tree_sha256": MODEL_TREE_DIGEST}

        def timeout(_request: dict) -> tuple[str, dict]:
            raise TimeoutError()

        def changed_digest(request: dict) -> tuple[str, dict]:
            raw, _ = accepted_provider(request)
            return raw, {"package": MLX_RUNTIME["package"], "model_tree_sha256": "c" * 64}

        def changed_package(request: dict) -> tuple[str, dict]:
            raw, _ = accepted_provider(request)
            return raw, {"package": "mlx-lm==0.0.0", "model_tree_sha256": MODEL_TREE_DIGEST}

        expected = {
            malformed: "malformed-response",
            unknown: "unknown-candidate",
            mismatch: "citation-mismatch",
            unknown_source: "unknown-source-fragment",
            timeout: "timeout",
            changed_digest: "model-digest-mismatch",
            changed_package: "runtime-package-mismatch",
        }
        for provider, code in expected.items():
            with self.subTest(code=code):
                result = run_model_arm(transcript, provider, expected_model_tree_sha256=MODEL_TREE_DIGEST)
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
