from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notes"))

from mlx_note_admission import (
    MLX_RUNTIME,
    run_control_arm,
    run_model_arm,
    synthetic_transcript,
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


if __name__ == "__main__":
    unittest.main()
