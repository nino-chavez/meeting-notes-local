#!/usr/bin/env python3
"""A BERT encoder forward pass on MLX, for the pinned MiniLM embedding weights.

Research code. It reads a local model directory and returns vectors; it opens no
meeting store, writes no product record, and reaches no network.

# Why this exists rather than a dependency

`mlx-embeddings` 0.1.0 does this and is **GPL-3.0**. This repository is MIT, so
that package is closed for anything that ships — on licence, not on preference.
`SEMANTIC_RETRIEVAL.md` recorded the constraint when the probe was registered and
named this file as the consequence: the probe measured the weights through the
Apache-2.0 reference implementation, and the shipping path is the same arithmetic
written here.

The tokenizer is still `transformers` (Apache-2.0). Tokenization is not the
licence problem and re-implementing WordPiece would add a second place for the
vocabulary to be wrong. **Whether `transformers` belongs in the product runtime
is a separate question** — it is a large dependency and the runtime currently
carries mlx, mlx-whisper and numpy — and it is not answered here.

# What makes this verifiable rather than hopeful

`SEMANTIC_RETRIEVAL.md` registered the falsifier before this file existed: it is
not enough for the rankings to agree, because three of the five deciding
comparisons in that run turned on 0.013 cosine. **The margins have to agree too,
within 0.01.** `verify_mlx_minilm.py` checks both against the committed receipts.

# The 256-token ceiling is the model's, and it is not raised here

`sentence_bert_config.json` sets `max_seq_length` to 256. The probe's fixtures
were 39 to 48 tokens, so nothing was ever truncated and the ceiling was invisible
in that result. A real meeting is not: an hour of speech is roughly twelve
thousand tokens, of which this model reads the first two per cent.

This file therefore refuses silently truncating input. `embed` takes text that
fits and raises otherwise, so the caller has to decide what to do about a long
meeting — which is a design decision about the unit being embedded, not something
a matrix multiply should make by dropping the rest of the transcript on the floor.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import mlx.core as mx

# From `config.json` on the pinned revision, and asserted against it at load so
# a different checkpoint cannot be run through constants that do not describe it.
EXPECTED_CONFIG = {
    "hidden_size": 384,
    "num_hidden_layers": 6,
    "num_attention_heads": 12,
    "intermediate_size": 1536,
    "vocab_size": 30522,
    "max_position_embeddings": 512,
    "type_vocab_size": 2,
    "layer_norm_eps": 1e-12,
    "hidden_act": "gelu",
}

# `sentence_bert_config.json`. Lower than the model's 512 positions, and it is
# the sentence-transformers configuration that decides what the reference
# implementation reads, so it is what this must match.
MAX_SEQUENCE_LENGTH = 256


class SequenceTooLong(ValueError):
    """The input exceeds the model's window and would be silently truncated."""


def _layer_norm(x: mx.array, weight: mx.array, bias: mx.array, eps: float) -> mx.array:
    mean = mx.mean(x, axis=-1, keepdims=True)
    variance = mx.var(x, axis=-1, keepdims=True)
    return (x - mean) * mx.rsqrt(variance + eps) * weight + bias


def _gelu(x: mx.array) -> mx.array:
    """The exact erf formulation, not the tanh approximation.

    `hidden_act` is `gelu`, and HuggingFace's `gelu` is the erf one; `gelu_new`
    is the tanh approximation. They differ by around 1e-3 at the extremes, which
    is a tenth of the 0.01 margin tolerance this file has to meet — close enough
    to pass a ranking check and fail the one that matters.
    """
    return x * 0.5 * (1.0 + mx.erf(x / math.sqrt(2.0)))


class MiniLMEncoder:
    """The pinned checkpoint's weights, and the arithmetic that uses them."""

    def __init__(self, model_directory: Path):
        config = json.loads((model_directory / "config.json").read_text())
        for key, expected in EXPECTED_CONFIG.items():
            if config.get(key) != expected:
                raise ValueError(f"config.{key} is {config.get(key)!r}, expected {expected!r}")
        sentence_config = json.loads(
            (model_directory / "sentence_bert_config.json").read_text()
        )
        if sentence_config.get("max_seq_length") != MAX_SEQUENCE_LENGTH:
            raise ValueError("max_seq_length does not match the registered ceiling")

        self.config = config
        self.weights = mx.load(str(model_directory / "model.safetensors"))
        self.layers = config["num_hidden_layers"]
        self.heads = config["num_attention_heads"]
        self.head_dim = config["hidden_size"] // self.heads
        self.eps = config["layer_norm_eps"]

    def _w(self, name: str) -> mx.array:
        return self.weights[name]

    def _linear(self, x: mx.array, prefix: str) -> mx.array:
        # HuggingFace stores `nn.Linear` weight as (out, in), so the transpose is
        # part of the checkpoint's layout rather than a choice made here.
        return x @ self._w(f"{prefix}.weight").T + self._w(f"{prefix}.bias")

    def _attention(self, x: mx.array, mask: mx.array, layer: int) -> mx.array:
        prefix = f"encoder.layer.{layer}.attention"
        batch, length, _ = x.shape

        def heads(value: mx.array) -> mx.array:
            return value.reshape(batch, length, self.heads, self.head_dim).transpose(0, 2, 1, 3)

        query = heads(self._linear(x, f"{prefix}.self.query"))
        key = heads(self._linear(x, f"{prefix}.self.key"))
        value = heads(self._linear(x, f"{prefix}.self.value"))

        scores = (query @ key.transpose(0, 1, 3, 2)) / math.sqrt(self.head_dim)
        # Additive mask: 0 for real tokens, a large negative for padding. Applied
        # before the softmax so padding contributes nothing rather than a small
        # amount.
        scores = scores + mask
        weights = mx.softmax(scores, axis=-1)
        context = (weights @ value).transpose(0, 2, 1, 3).reshape(batch, length, -1)

        projected = self._linear(context, f"{prefix}.output.dense")
        return _layer_norm(
            projected + x,
            self._w(f"{prefix}.output.LayerNorm.weight"),
            self._w(f"{prefix}.output.LayerNorm.bias"),
            self.eps,
        )

    def _feed_forward(self, x: mx.array, layer: int) -> mx.array:
        prefix = f"encoder.layer.{layer}"
        hidden = _gelu(self._linear(x, f"{prefix}.intermediate.dense"))
        projected = self._linear(hidden, f"{prefix}.output.dense")
        return _layer_norm(
            projected + x,
            self._w(f"{prefix}.output.LayerNorm.weight"),
            self._w(f"{prefix}.output.LayerNorm.bias"),
            self.eps,
        )

    def forward(self, input_ids: mx.array, attention_mask: mx.array) -> mx.array:
        batch, length = input_ids.shape
        if length > MAX_SEQUENCE_LENGTH:
            raise SequenceTooLong(f"{length} tokens exceeds the {MAX_SEQUENCE_LENGTH} ceiling")

        positions = mx.arange(length).reshape(1, length)
        # `token_type_ids` is all zeros for a single sequence. Written out rather
        # than skipped, because the row is not zero and dropping it shifts every
        # vector.
        token_types = mx.zeros((batch, length), dtype=mx.int32)

        x = (
            self._w("embeddings.word_embeddings.weight")[input_ids]
            + self._w("embeddings.position_embeddings.weight")[positions]
            + self._w("embeddings.token_type_embeddings.weight")[token_types]
        )
        x = _layer_norm(
            x,
            self._w("embeddings.LayerNorm.weight"),
            self._w("embeddings.LayerNorm.bias"),
            self.eps,
        )

        additive = (1.0 - attention_mask.astype(mx.float32)) * -1e9
        additive = additive.reshape(batch, 1, 1, length)
        for layer in range(self.layers):
            x = self._attention(x, additive, layer)
            x = self._feed_forward(x, layer)
        return x

    def embed(self, input_ids: mx.array, attention_mask: mx.array) -> mx.array:
        """Mean pooling over the real tokens, which is what `1_Pooling` selects.

        Not the `[CLS]` vector and not the `pooler` head — the checkpoint carries
        `pooler.dense`, and sentence-transformers does not use it for this model.
        Using it would produce plausible vectors that rank differently.
        """
        hidden = self.forward(input_ids, attention_mask)
        mask = attention_mask.astype(mx.float32).reshape(*attention_mask.shape, 1)
        summed = mx.sum(hidden * mask, axis=1)
        counts = mx.maximum(mx.sum(mask, axis=1), 1e-9)
        return summed / counts


def load_tokenizer(model_directory: Path):
    """`transformers`, Apache-2.0. See the module docstring for why."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(str(model_directory))


def encode(encoder: MiniLMEncoder, tokenizer, texts: list[str]) -> mx.array:
    """One vector per text. Refuses rather than truncating.

    `padding=True` pads to the longest text in the batch, so a batch's vectors do
    not depend on how many other texts came with it — padding is masked out of
    both the attention and the mean.
    """
    encoded = tokenizer(texts, padding=True, truncation=False, return_tensors=None)
    lengths = [len(ids) for ids in encoded["input_ids"]]
    if max(lengths) > MAX_SEQUENCE_LENGTH:
        raise SequenceTooLong(
            f"longest input is {max(lengths)} tokens against a {MAX_SEQUENCE_LENGTH} ceiling"
        )
    return encoder.embed(
        mx.array(encoded["input_ids"]),
        mx.array(encoded["attention_mask"]),
    )
