#!/usr/bin/env python3
"""Does the tokenizer the app can actually ship reproduce the measured result?

`notes/SEMANTIC_RETRIEVAL.md` registers the prediction and records that the first
version of it compared the wrong two things. Read that before reading a number
here.

# The question

The 2026-08-08 scale run used `transformers.AutoTokenizer`. `transformers` is not
in the packaged runtime and is not a small thing to add. The `tokenizers` wheel is
— Apache-2.0, one wheel — and the pinned revision publishes `tokenizer.json`,
which is what that wheel reads. **There is no `vocab.txt` at this revision**, so a
hand-written WordPiece pass would parse the same file to arrive where the wheel
already is.

# Two comparisons, and only one of them is attributable

**Same environment, only the tokenizer swapped.** Both tokenizers drive the same
weights through the same forward pass in one process. Any difference here is the
tokenizer, because nothing else moved. This is the comparison that decides.

**Against the committed receipt.** Reported too, and it is *not* a tokenizer
test: `semantic_scale_receipt.json` records the corpus, harness and
implementation digests but not the environment that produced it, so a difference
can be a different MLX build as easily as a different tokenizer. Registering
equality with it — which the first version of this harness did — asserted
cross-environment float reproducibility that nothing had ever established.

The token-identity check is the third leg and the cheapest: identical input IDs
over every piece and every question means the tokenizers cannot differ.

# Why this monkeypatches rather than reimplements

The scoring, the corpus composition and the windowing live in
`semantic_scale_probe.main`. Copying any of it here would compare two
implementations rather than two tokenizers. So this replaces exactly one name on
the `mlx_minilm` module — `load_tokenizer` — and calls the probe's own `main()`.

**Neither file is edited.** `semantic_scale_receipt.json` records the SHA-256 of
both, and a byte changed in either invalidates a committed result. This asserts
both digests before it runs.

    /private/tmp/lmn-tok/venv/bin/python notes/packaged_tokenizer_parity.py \
      --model-directory /private/tmp/lmn-tok/model \
      --receipt notes/packaged_tokenizer_receipt.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mlx_minilm  # noqa: E402
import semantic_scale_probe as probe  # noqa: E402

PARITY_SCHEMA = "packaged-tokenizer-parity/2"

# The window arm is the one the store is built on. The other two run because the
# probe runs all three; their numbers are reported, not gated.
COMPARED_UNIT = "window"

SUMMARY_FIELDS = (
    "pieces",
    "correct",
    "median_margin",
    "median_within_band",
    "max_within_band",
    "near_miss_beat_target",
)
ROW_FIELDS = ("target", "top1", "correct", "margin", "within_band", "near_miss_rank")


class TokenizersAdapter:
    """The three `transformers` methods the probe and the forward pass call.

    Deliberately thin. Anything cleverer would be a third implementation to
    attribute a difference to.
    """

    def __init__(self, path: Path):
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        # `tokenizer.json` at this revision bakes in truncation at 128 tokens and
        # **fixed** padding to 128. Both are wrong for this use and both are
        # silent: truncation would cut a window in half, and fixed padding would
        # pad a question out to 128 positions. The first version of the token
        # comparison here left the padding in place and reported 206 mismatches
        # in 810 that were entirely its own artifact.
        self._tokenizer.no_truncation()
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

    def __call__(self, texts, padding=True, truncation=False, return_tensors=None):
        if not padding or truncation or return_tensors is not None:
            raise ValueError("the probe calls this one way; anything else is unverified")
        encodings = self._tokenizer.encode_batch(texts)
        return {
            "input_ids": [encoding.ids for encoding in encodings],
            "attention_mask": [encoding.attention_mask for encoding in encodings],
        }

    def encode(self, text, add_special_tokens=True):
        return self._tokenizer.encode(text, add_special_tokens=add_special_tokens).ids

    def decode(self, ids, skip_special_tokens=True):
        return self._tokenizer.decode(list(ids), skip_special_tokens=skip_special_tokens)

    def ids_without_padding(self, text: str) -> list[int]:
        """For the token comparison, where batch padding would be noise."""
        encoding = self._tokenizer.encode(text)
        length = sum(encoding.attention_mask)
        return encoding.ids[:length]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_unedited(reference: dict) -> None:
    for name, key in (
        ("semantic_scale_probe.py", "harness_sha256"),
        ("mlx_minilm.py", "implementation_sha256"),
        ("semantic_scale_corpus.json", "corpus_parts_sha256"),
    ):
        actual = _sha256(HERE / name)
        if actual != reference[key]:
            raise SystemExit(
                f"{name} is not the file the reference receipt was produced with "
                f"({actual} != {reference[key]}); a comparison against it would be "
                "unattributable"
            )


def run_probe(model_directory: Path, tokenizer) -> dict:
    """One full probe run against an injected tokenizer. Never edits the probe."""
    mlx_minilm.load_tokenizer = lambda _directory: tokenizer
    with tempfile.TemporaryDirectory() as scratch:
        output = Path(scratch) / "receipt.json"
        sys.argv = [
            "semantic_scale_probe",
            "--model-directory",
            str(model_directory),
            "--receipt",
            str(output),
        ]
        status = probe.main()
        if status != 0:
            raise SystemExit(f"the probe exited {status}; nothing is compared")
        return json.loads(output.read_text(encoding="utf-8"))


def window_rows(receipt: dict) -> dict:
    return {r["size"]: r for r in receipt["results"] if r["unit"] == COMPARED_UNIT}


def compare(left_receipt: dict, right_receipt: dict) -> dict:
    """Every field of the window arm, per size. Not a summary."""
    left, right = window_rows(left_receipt), window_rows(right_receipt)
    differences = []
    compared = 0
    for size in sorted(left):
        for field in SUMMARY_FIELDS:
            compared += 1
            if left[size][field] != right[size][field]:
                differences.append(
                    {
                        "size": size,
                        "field": field,
                        "left": left[size][field],
                        "right": right[size][field],
                    }
                )
        for index, (a, b) in enumerate(zip(left[size]["rows"], right[size]["rows"])):
            for field in ROW_FIELDS:
                compared += 1
                if a[field] != b[field]:
                    differences.append(
                        {
                            "size": size,
                            "question": index,
                            "field": field,
                            "left": a[field],
                            "right": b[field],
                        }
                    )
    return {"fields_compared": compared, "differences": differences}


def environment() -> dict:
    """Recorded because the receipt this compares against did not record it, and
    that omission is what made the first comparison unattributable."""
    import mlx.core
    import numpy

    record = {
        "python": sys.version.split()[0],
        "mlx": getattr(mlx.core, "__version__", "unknown"),
        "numpy": numpy.__version__,
    }
    import tokenizers

    record["tokenizers"] = tokenizers.__version__
    try:
        import transformers

        record["transformers"] = transformers.__version__
    except ImportError:
        record["transformers"] = None
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    arguments = parser.parse_args()

    reference_path = HERE / "semantic_scale_receipt.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    require_unedited(reference)

    model_directory = arguments.model_directory
    wheel = TokenizersAdapter(model_directory)

    parts = probe.load_corpus_parts()
    corpus = probe.build_corpus(parts, max(30, 200))
    pieces = [p for m in corpus for p in probe.chunk_units(m, COMPARED_UNIT, None)]
    pieces += [q["question"] for q in parts["questions"]]

    try:
        from transformers import AutoTokenizer

        wrapper = AutoTokenizer.from_pretrained(str(model_directory))
    except ImportError:
        wrapper = None

    if wrapper is None:
        token_check = {"ran": False, "why": "transformers is absent from this environment"}
        same_environment = {"ran": False, "why": "transformers is absent from this environment"}
    else:
        mismatches = sum(
            1
            for text in pieces
            if wheel.ids_without_padding(text) != wrapper(text)["input_ids"]
        )
        token_check = {"ran": True, "texts": len(pieces), "mismatches": mismatches}

    produced = run_probe(model_directory, wheel)
    if wrapper is not None:
        baseline = run_probe(model_directory, wrapper)
        same_environment = compare(baseline, produced)
        same_environment["ran"] = True

    against_receipt = compare(reference, produced)
    against_receipt["ran"] = True

    receipt = {
        "schema": PARITY_SCHEMA,
        "compared_unit": COMPARED_UNIT,
        "environment": environment(),
        "reference_receipt_sha256": _sha256(reference_path),
        "harness_sha256": _sha256(Path(__file__).resolve()),
        "tokenizer": {
            "package": "tokenizers",
            "source": "tokenizer.json",
            "sha256": _sha256(model_directory / "tokenizer.json"),
        },
        "weights_sha256": _sha256(model_directory / "model.safetensors"),
        "token_identity": token_check,
        "same_environment_swap": same_environment,
        "against_committed_receipt": against_receipt,
        "verdict": {
            "tokenizer_is_the_cause": bool(
                same_environment.get("ran") and same_environment["differences"]
            ),
            "identical_in_the_environment_that_isolates_it": bool(
                same_environment.get("ran") and not same_environment["differences"]
            ),
        },
    }
    arguments.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"token mismatches: {token_check}")
    print(f"same-environment swap differences: {len(same_environment.get('differences', []))}")
    print(f"against committed receipt: {len(against_receipt['differences'])}")
    return 0 if receipt["verdict"]["identical_in_the_environment_that_isolates_it"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
