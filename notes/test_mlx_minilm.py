#!/usr/bin/env python3
"""Tests for the MLX MiniLM forward pass and its verification receipt.

Split deliberately. Everything in `ContractTests` and `ReceiptTests` runs with no
model and no MLX, because this repository's default Python suite has neither —
so those are the checks that keep running. `--with-model` adds the arithmetic
ones for a machine that has both.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from semantic_retrieval_probe import PIN, _sha256  # noqa: E402

HERE = Path(__file__).resolve().parent
RECEIPT = HERE / "mlx_minilm_verification_receipt.json"


class ContractTests(unittest.TestCase):
    """Read as source. The module imports `mlx`, which the default suite lacks,
    so its constants are checked textually rather than by importing it."""

    def setUp(self):
        self.source = (HERE / "mlx_minilm.py").read_text()

    def test_the_sequence_ceiling_is_the_sentence_transformers_one_not_the_models(self):
        # 512 positions in the checkpoint, 256 in the sentence-transformers
        # config. The reference implementation reads 256, so this must too.
        self.assertIn("MAX_SEQUENCE_LENGTH = 256", self.source)
        self.assertIn('"max_position_embeddings": 512', self.source)

    def test_long_input_is_refused_rather_than_truncated(self):
        """The ceiling went unnoticed in the probe precisely because the
        reference implementation truncates without saying so."""
        self.assertIn("class SequenceTooLong", self.source)
        self.assertIn("truncation=False", self.source)
        self.assertIn("raise SequenceTooLong", self.source)

    def test_the_activation_is_the_erf_gelu_and_says_why(self):
        self.assertIn("mx.erf", self.source)
        # The called function, not the word: the docstring names the tanh
        # approximation in order to say it is not used, and a bare substring
        # check cannot tell an explanation from a call.
        self.assertNotIn("mx.tanh", self.source)
        self.assertNotIn("math.tanh", self.source)

    def test_the_unused_pooler_head_is_named_as_unused(self):
        """The checkpoint carries `pooler.dense` and sentence-transformers does
        not use it for this model. Using it produces plausible vectors that rank
        differently."""
        self.assertIn("pooler", self.source)
        self.assertNotIn('_w("pooler.dense.weight")', self.source)


class ReceiptTests(unittest.TestCase):
    """Against the committed 2026-08-08 verification. Literals, not constants."""

    def setUp(self):
        self.receipt = json.loads(RECEIPT.read_text())

    def test_the_implementation_agreed_on_every_ranking(self):
        self.assertEqual(self.receipt["verdict"], "agrees")
        self.assertEqual(self.receipt["ranking_disagreements"], 0)
        self.assertEqual(len(self.receipt["rows"]), 10)
        self.assertTrue(all(row["ranking_agrees"] for row in self.receipt["rows"]))

    def test_the_margins_agreed_far_inside_the_registered_tolerance(self):
        """The registered falsifier was 0.01, because three of the deciding
        comparisons turn on 0.013. The measured worst case was 1e-6."""
        self.assertEqual(self.receipt["margin_tolerance"], 0.01)
        self.assertEqual(self.receipt["worst_margin_delta"], 1e-06)

    def test_the_receipt_names_the_implementation_and_reference_it_compared(self):
        self.assertEqual(
            self.receipt["implementation_sha256"],
            _sha256((HERE / "mlx_minilm.py").read_bytes()),
            "the implementation changed since the verification ran; re-run it",
        )
        self.assertEqual(
            self.receipt["reference_receipt_sha256"],
            _sha256((HERE / "semantic_retrieval_receipt.json").read_bytes()),
        )
        self.assertEqual(
            self.receipt["model_weights_sha256"],
            PIN["model"]["expected_model_safetensors_sha256"],
        )

    def test_the_hard_five_are_still_the_narrow_ones_in_this_implementation_too(self):
        hard = sorted(
            row["mlx_margin"] for row in self.receipt["rows"] if not row["exact_helps"]
        )
        self.assertEqual(sum(1 for margin in hard if margin < 0.05), 3)


class ModelTests(unittest.TestCase):
    """Only on a machine with MLX and the pinned checkpoint."""

    @classmethod
    def setUpClass(cls):
        if "--with-model" not in sys.argv:
            raise unittest.SkipTest("pass --with-model and LMN_MINILM_DIR to run")

    def test_a_sequence_over_the_ceiling_raises_rather_than_truncating(self):
        import os

        from mlx_minilm import MiniLMEncoder, SequenceTooLong, encode, load_tokenizer

        directory = Path(os.environ["LMN_MINILM_DIR"])
        encoder = MiniLMEncoder(directory)
        tokenizer = load_tokenizer(directory)
        with self.assertRaises(SequenceTooLong):
            encode(encoder, tokenizer, ["word " * 400])

    def test_padding_does_not_change_a_vector(self):
        """A batch's vectors must not depend on what else was in the batch.
        Padding is masked out of both the attention and the mean, and this is
        the check that it is."""
        import os

        import numpy

        from mlx_minilm import MiniLMEncoder, encode, load_tokenizer

        directory = Path(os.environ["LMN_MINILM_DIR"])
        encoder = MiniLMEncoder(directory)
        tokenizer = load_tokenizer(directory)
        alone = numpy.asarray(encode(encoder, tokenizer, ["a short sentence"])[0])
        with_padding = numpy.asarray(
            encode(encoder, tokenizer, ["a short sentence", "a considerably " * 20])[0]
        )
        self.assertLess(float(numpy.abs(alone - with_padding).max()), 1e-4)


if __name__ == "__main__":
    unittest.main(argv=[argument for argument in sys.argv if argument != "--with-model"])
