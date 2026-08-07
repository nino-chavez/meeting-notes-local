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
    POLARITY_TERMS,
    _admission_candidates,
    _decode_response,
    _refusal_category,
    _sha256,
    dropped_polarity_terms,
    model_request,
    response_contract,
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
        # The arm that produced the response. "unconstrained" is what the
        # 2026-08-02 corrective probe ran; the masked arm records the mask's own
        # source digest instead.
        "decoder": "unconstrained",
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

    def test_the_mask_agrees_with_the_contract_it_claims_to_enforce(self) -> None:
        """The mask declares the shape independently; nothing tied the two.

        `ITEM_FIELDS` and the two ceilings live in `structured_decoding.py`, and
        the contract the model is actually handed lives in `response_contract`.
        If either moves the mask silently blocks valid responses or admits ones
        `_decode_response` rejects, and the receipt still reads `passed`. Same
        failure shape as `ALPHA_OPERATIONS` versus `internal_alpha_operations`,
        so it gets the same cross-pin.
        """
        from structured_decoding import ITEM_FIELDS, MAX_FRAGMENT_IDS, MAX_ITEMS

        transcript = synthetic_transcript()
        contract = response_contract(generate_manifest(transcript, STRATEGY_CUE))
        item = contract["root"]["properties"]["items"]["item"]
        self.assertEqual(contract["root"]["ordered_fields"], ["items"])
        self.assertEqual(list(ITEM_FIELDS), item["ordered_fields"])
        self.assertEqual(contract["empty_response"], {"items": []})
        ids = item["properties"]["source_fragment_ids"]
        self.assertEqual(MAX_FRAGMENT_IDS, ids["max_items"])
        self.assertEqual(ids["min_items"], 1)

        # The contract states no item ceiling, so the mask's is an extra
        # restriction. It is only safe while it stays above the most items any
        # fixture could legitimately produce — one per offered candidate, since
        # `_decode_response` requires unique candidate IDs in ascending order.
        worst = max(
            len(_admission_candidates(generate_manifest(fixture[1], STRATEGY_CUE)))
            for fixture in (*synthetic_measurement_fixtures(), *fixtures_for_scope("probe"))
        )
        self.assertLessEqual(
            worst,
            MAX_ITEMS,
            "the mask would block a response the contract permits",
        )

    def test_the_committed_constrained_receipts_evidence_the_repeatability_gate(self) -> None:
        """The registered gate is three cold runs, and prose is not the artifact.

        `MLX_NOTE_ADMISSION.md` claimed repeatability while one receipt was
        committed, so a reader had to take the sentence on trust. All three are
        committed now, and this checks them against each other rather than
        restating the claim: everything but wall-clock timings and process RSS
        must be identical, because those are the only values a repeat is allowed
        to move.
        """
        directory = Path(__file__).resolve().parent
        receipts = [
            json.loads((directory / name).read_text())
            for name in (
                "mlx_note_constrained_probe_receipt.json",
                "mlx_note_constrained_probe_receipt_run2.json",
                "mlx_note_constrained_probe_receipt_run3.json",
            )
        ]

        def invariant(receipt: dict) -> dict:
            return {
                "passed": receipt["passed"],
                "decoding": receipt["decoding"],
                "preflight_tree_sha256": receipt["preflight_tree_sha256"],
                "postflight_tree_sha256": receipt["postflight_tree_sha256"],
                # Dropping the whole `load` block would discard two fields that
                # must not move between repeats — the tree the model was loaded
                # from, and the runtime it was loaded into — to exclude the one
                # that must, its load time. Only the timing is excluded.
                "load": {
                    key: value
                    for key, value in receipt["load"].items()
                    if key != "model_load_elapsed_s"
                },
                "calls": [
                    {
                        key: call[key]
                        for key in ("phase", "outcome", "code", "response_sha256", "response_bytes", "checks", "identity")
                    }
                    | {"generation": {k: v for k, v in call["generation"].items() if k != "call_elapsed_s"}}
                    for call in receipt["calls"]
                ],
            }

        first = invariant(receipts[0])
        for index, receipt in enumerate(receipts[1:], start=2):
            with self.subTest(run=index):
                self.assertEqual(invariant(receipt), first)
        self.assertTrue(first["passed"])
        self.assertEqual(first["decoding"], "structure-constrained")
        self.assertEqual(first["preflight_tree_sha256"], first["postflight_tree_sha256"])
        # The mask that produced them is the one in the tree, so a later edit to
        # the mask invalidates these receipts loudly instead of silently.
        expected_decoder = _sha256((directory / "structured_decoding.py").read_bytes())
        for call in first["calls"]:
            self.assertEqual(call["identity"]["decoder"], expected_decoder)

    def test_every_receipt_past_the_runtime_gate_names_the_decoder_that_produced_it(self) -> None:
        """`_runtime_receipt` demands `decoder` and the receipt then dropped it.

        Nothing failed, because the field was validated on the observed dict and
        simply never copied out — so every committed receipt was silent about
        which sampler ran, and for the masked arm that digest is the only thing
        pinning *which* mask ran. Both the accepted and the refused path are
        checked here: attribution matters most on a syntax refusal, where the
        question is whether the model or the mask produced the bad string.
        """
        transcript = synthetic_transcript()
        accepted = run_model_arm(transcript, accepted_provider)
        self.assertEqual(accepted.outcome, "accepted-research-candidate")
        self.assertEqual(accepted.receipt["identity"]["decoder"], "unconstrained")

        def masked(request: dict) -> tuple[str, dict]:
            observed = observed_identity(request)
            observed["decoder"] = "d" * 64
            return "{", observed

        refused = run_model_arm(transcript, masked)
        self.assertEqual(refused.outcome, "transcript-only")
        self.assertEqual(refused.receipt["identity"]["decoder"], "d" * 64)

        # The path that matters most, and the one the fix above does not reach:
        # `MaskRefused` is raised inside the logits processor, so the provider
        # throws and there is no `observed` dict to read an identity from. A
        # mask refusal is by construction the mask's failure and not the
        # model's, which made this the least useful receipt in the set.
        def throws(_request: dict) -> tuple[str, dict]:
            raise ValueError("no token continues the contract")

        setattr(throws, "decoder_identity", "e" * 64)
        thrown = run_model_arm(transcript, throws)
        self.assertEqual(thrown.outcome, "transcript-only")
        self.assertEqual(thrown.code, "provider-generation-failure")
        self.assertEqual(thrown.receipt["decoder"], "e" * 64)

        # A provider that names no decoder says so, rather than going silent.
        def anonymous(_request: dict) -> tuple[str, dict]:
            raise ValueError("boom")

        self.assertEqual(
            run_model_arm(transcript, anonymous).receipt["decoder"], "unavailable"
        )

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

    def test_a_claim_that_drops_its_evidence_polarity_is_refused(self) -> None:
        """The 2026-08-07 finding, pinned.

        `negation-proposal` claimed "merge the red branch" from evidence reading
        "I propose that we do not merge the red branch". Nothing registered
        refused it; the only thing failing that fixture was the unrelated
        identifier truncation, so closing that bug alone would have admitted a
        claim asserting the opposite of its own cited evidence.
        """
        self.assertEqual(
            dropped_polarity_terms(
                "I propose that we do not merge the red branch.",
                "merge the red branch",
            ),
            ["not"],
        )

    def test_a_claim_that_keeps_the_polarity_is_untouched(self) -> None:
        """The control. A gate that fails this is over-broad and is withdrawn."""
        self.assertEqual(
            dropped_polarity_terms(
                "We decided not to cancel Project Atlas.",
                "We decided not to cancel Project Atlas.",
            ),
            [],
        )
        # Shortened, but the polarity survives.
        self.assertEqual(
            dropped_polarity_terms(
                "We decided not to cancel Project Atlas.",
                "not cancelling Project Atlas",
            ),
            [],
        )

    def test_evidence_without_polarity_never_triggers_the_gate(self) -> None:
        self.assertEqual(
            dropped_polarity_terms(
                "Dana decided that Battery 7 ships on Tuesday.",
                "Dana decided to ship Battery 7 on Tuesday.",
            ),
            [],
        )

    def test_the_polarity_rule_is_advertised_as_well_as_enforced(self) -> None:
        """A rule enforced and unstated is the defect response_contract exists to fix."""
        transcript = synthetic_transcript()
        manifest = generate_manifest(transcript, STRATEGY_CUE)
        contract = response_contract(manifest)
        claim = contract["root"]["properties"]["items"]["item"]["properties"]["claim"]
        self.assertEqual(
            claim["must_not_drop_polarity_terms"], list(POLARITY_TERMS)
        )

    def test_the_polarity_term_list_has_exactly_one_owner(self) -> None:
        """read_semantic_support imports it; a second copy is the drift to prevent."""
        source = (Path(__file__).parent / "read_semantic_support.py").read_text()
        self.assertIn("POLARITY_TERMS = admission.POLARITY_TERMS", source)
        self.assertNotIn('POLARITY_TERMS = ("not"', source)

    def test_the_refusal_code_has_its_own_category(self) -> None:
        self.assertEqual(
            _refusal_category("claim-polarity"),
            "claim-contradicts-cited-evidence",
        )

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
