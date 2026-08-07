#!/usr/bin/env python3
"""Isolated probe: can a pinned local model pick the turn that names a meeting?

Research code. It reads `title_selection_fixtures.json` and nothing else — no
meeting store, no Preview datum, no product record, no artifact written except a
content-free receipt the caller asks for.

# The model returns an index, never text

`meeting_title::derived_title` already names a meeting, deterministically, with
the first turn whose opening sentence is long enough. The question here is
whether a model picks a *better* turn — and the contract is built so that is the
only question it can answer. A response is one integer or `null`. Every word of
every title still comes from `meeting_title.rs`, applied to the turn the model
named.

Three things follow, and they are the reason for the shape:

- **A selected title is a span of the transcript by construction.** Not checked
  afterwards, not promised in a prompt. The model has no channel through which
  text could reach a title.
- **The measured weakness is designed out.** `MLX_NOTE_ADMISSION.md` records this
  model reproducing enumerated values 10 of 10 and non-enumerated 90-character
  identifiers 1 of 10 — and that one a coin flip at +0.16 logits. A small
  integer from an enumerated set is the easiest thing it was measured doing.
- **A wrong pick is a real sentence from the meeting**, just not the most
  identifying one. The failure mode is a worse label, never an invented one.

# What this is not

It admits nothing. `MLX_NOTE_ADMISSION.md`'s gate table ends at "no admission
without a recorded human decision", and whether a title is worth reading is that
decision. A pass here licenses building the selection seam in Rust; it cannot
license the feature.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import time
from pathlib import Path

from mlx_note_admission import MLX_RUNTIME, _canonical_json, _sha256, tree_sha256
from title_decoding import TitleSelectionMachine, values_for

PROBE_SCHEMA = "mlx-title-selection/1"
RESPONSE_SCHEMA = "mlx-title-response/1"
FIXTURES_SCHEMA = "title-selection-fixtures/1"

# The model, wheels and interpreter come from `MLX_RUNTIME`, which this module
# reads and does not restate. Decoding does not: 512 output tokens is the note
# contract's budget for five free-text fields, and this response is at most
# eleven characters. A cap that cannot be reached measures nothing, and one this
# tight turns a runaway into an immediate, visible refusal.
TITLE_DECODING = {
    "temperature": 0.0,
    "max_tokens": 24,
    "max_kv_size": 4096,
    "seed": 0,
}

# Driven off the pin rather than restated, so a field added to `MLX_RUNTIME`
# cannot be silently unchecked here. `test_mlx_title_selection.py` asserts the
# two agree.
RUNTIME_IDENTITY_FIELDS = tuple(MLX_RUNTIME["runtime_identity"])

SYSTEM_PROMPT = """\
Return only one JSON object matching the supplied response contract.

Choose the one offered turn that best says what this meeting is about, and
return its turn number. Prefer the turn that states the meeting's subject,
decision or question over greetings, apologies, audio checks and scheduling
talk. Return null if no offered turn says what the meeting is about.

Return the turn number only. Do not return any of the meeting's words.
"""


class TitleRefused(ValueError):
    """The model arm falls back to the deterministic rule."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def load_fixtures(path: Path | None = None) -> tuple[dict, ...]:
    """The shared fixture file, which a Rust test also reads.

    `control_turn` is asserted there against the real `derived_title`, so this
    module treats it as given rather than recomputing it. Reimplementing the
    deterministic rule in Python is the one thing this probe must not do: two
    implementations of a baseline is how a measurement comes to be against a
    baseline nothing ships.
    """
    path = path or Path(__file__).with_name("title_selection_fixtures.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != FIXTURES_SCHEMA:
        raise ValueError("fixture schema is not the registered one")
    fixtures = tuple(document["fixtures"])
    if not fixtures:
        raise ValueError("no fixtures")
    return fixtures


def offered_turns(fixture: dict) -> tuple[int, ...]:
    """Canonical indices of the turns the model may choose between.

    Gated turns are **absent**, not marked. A withheld turn therefore has no
    index in the response language at all, so the mask cannot emit one — the
    safety property is structural here rather than a validation, which is
    strictly stronger than `derived_title`'s filter.
    """
    return tuple(
        index for index, turn in enumerate(fixture["turns"]) if not turn["gated"]
    )


def response_contract(offered: tuple[int, ...]) -> dict:
    """The exact shape advertised to the model.

    The offered indices are *enumerated* here, in the object that sorts last and
    therefore sits nearest the generation point. That placement is not
    incidental: `MLX_NOTE_ADMISSION.md`'s exposure measurement found the last
    complete instance before the generation point predicting what the model
    reproduces, and enumerating the offered identifiers moved the decision margin
    +2.74 and fixed 7 of 10 fixtures. This contract is built the way that
    measurement says to build it.
    """
    return {
        "root": "object",
        "ordered_fields": ["turn"],
        "turn": {
            "enum": [None, *offered],
            "description": "one offered turn number, or null for no answer",
        },
    }


def model_request(fixture: dict) -> dict:
    """One canonical request. Contains the meeting's words; retains none of them.

    The turn text has to be here — a model cannot choose between turns it cannot
    read. Nothing downstream keeps it: receipts carry digests, counts and
    indices, never a fixture's text.
    """
    offered = offered_turns(fixture)
    return {
        "schema": PROBE_SCHEMA,
        "system": SYSTEM_PROMPT,
        "offered_turns": [
            {"turn": index, "text": fixture["turns"][index]["text"]} for index in offered
        ],
        "response_contract": response_contract(offered),
    }


def decode_response(raw: str, offered: tuple[int, ...]) -> int | None:
    """The enforcement boundary. It does not unwrap fences, prose, or whitespace.

    The mask makes every refusal below unreachable in a masked run, and they are
    enforced anyway: the mask is a decoder and this is the contract. The note
    probe's own history is the argument — its mask was believed to make invalid
    JSON "unreachable by construction" while admitting 288 invalid strings of
    385, and the parser is what caught it.
    """

    def pairs(items: list[tuple[str, object]]) -> tuple[tuple[str, object], ...]:
        names = [name for name, _ in items]
        if len(names) != len(set(names)):
            raise TitleRefused("response-contract")
        return tuple(items)

    if not isinstance(raw, str) or not raw.strip():
        raise TitleRefused("response-json-syntax")
    try:
        parsed = json.loads(raw, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise TitleRefused("response-json-syntax") from exc
    if not isinstance(parsed, tuple) or tuple(name for name, _ in parsed) != ("turn",):
        raise TitleRefused("response-contract")
    value = dict(parsed)["turn"]
    if value is None:
        return None
    # `isinstance(True, int)` is True in Python, so a bare `true` would otherwise
    # decode as turn one. Type identity, not isinstance.
    if type(value) is not int:
        raise TitleRefused("response-contract")
    if value not in offered:
        raise TitleRefused("turn-not-offered")
    return value


def verified_runtime_identity() -> dict:
    """The running environment, or `runtime-package-mismatch`.

    A second copy of the check `mlx_note_admission.local_mlx_provider` runs, and
    the duplication is deliberate. Extracting a shared function was tried on
    2026-08-08 and reverted: it changed `mlx_note_admission.py`'s bytes, and
    `test_the_committed_matrix_receipts_name_this_harness` binds the committed
    matrix receipts to that file's digest. A refactor for this probe's
    convenience would have invalidated another experiment's evidence, which is a
    worse trade than fifteen duplicated lines.

    What is *not* duplicated is the pin. `MLX_RUNTIME` is imported, and
    `RUNTIME_IDENTITY_FIELDS` is derived from it, so the two checks cannot come
    to disagree about which fields matter — only about code that produces the
    same values.
    """
    try:
        package = importlib.metadata.version("mlx-lm")
        import mlx
    except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
        raise TitleRefused("runtime-package-mismatch") from exc

    def metadata_sha256(name: str) -> str:
        distribution = importlib.metadata.distribution(name)
        target = next(
            (item for item in distribution.files or () if item.name == "METADATA"),
            None,
        )
        if target is None:
            raise TitleRefused("runtime-package-mismatch")
        return _sha256(distribution.locate_file(target).read_bytes())

    identity = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "mlx": mlx.__version__
        if hasattr(mlx, "__version__")
        else importlib.metadata.version("mlx"),
        "transformers": importlib.metadata.version("transformers"),
        "package_metadata_sha256": {
            name: {"metadata": metadata_sha256(name)}
            for name in ("mlx-lm", "mlx", "transformers")
        },
    }
    if (
        f"mlx-lm=={package}" != MLX_RUNTIME["package"]
        or identity != MLX_RUNTIME["runtime_identity"]
    ):
        raise TitleRefused("runtime-package-mismatch")
    return identity


def local_title_provider(model_directory: Path):
    """A private MLX-LM provider over the pinned tree. No download, no service.

    The mask is rebuilt per request because its language depends on which turns
    that request offers — unlike the note contract, whose shape is fixed. That
    costs one vocabulary scan per distinct machine state per request, which is
    setup rather than generation and is measured separately for exactly that
    reason.
    """
    if not model_directory.is_dir():
        raise ValueError("model directory does not exist")
    preflight_tree_sha256 = tree_sha256(model_directory)
    if preflight_tree_sha256 != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise TitleRefused("model-digest-mismatch")
    try:
        import mlx.core as mx
        from mlx_lm import load, stream_generate
        from mlx_lm.sample_utils import make_sampler
    except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
        raise TitleRefused("runtime-package-mismatch") from exc
    runtime_identity = verified_runtime_identity()

    from structured_decoding import make_contract_logits_processor

    decoder_identity = _sha256(
        Path(__file__).with_name("title_decoding.py").read_bytes()
    )

    load_started = time.monotonic()
    model, tokenizer = load(str(model_directory))
    load_elapsed_s = round(time.monotonic() - load_started, 6)

    def provider(request: dict, offered: tuple[int, ...]) -> tuple[str, dict]:
        mx.random.seed(TITLE_DECODING["seed"])
        user_request = {key: value for key, value in request.items() if key != "system"}
        messages = [
            {"role": "system", "content": request["system"]},
            {"role": "user", "content": _canonical_json(user_request)},
        ]
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        mask_started = time.monotonic()
        processor = make_contract_logits_processor(
            tokenizer, TitleSelectionMachine(offered)
        )
        mask_elapsed_s = round(time.monotonic() - mask_started, 6)

        started = time.monotonic()
        chunks: list[str] = []
        prompt_tokens: object = "unavailable"
        generated_tokens: object = "unavailable"
        finish_reason: object = "unavailable"
        for response in stream_generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=TITLE_DECODING["max_tokens"],
            max_kv_size=TITLE_DECODING["max_kv_size"],
            sampler=make_sampler(temp=TITLE_DECODING["temperature"]),
            logits_processors=[processor],
        ):
            chunks.append(response.text)
            if isinstance(getattr(response, "prompt_tokens", None), int):
                prompt_tokens = response.prompt_tokens
            if isinstance(getattr(response, "generation_tokens", None), int):
                generated_tokens = response.generation_tokens
            if getattr(response, "finish_reason", None) is not None:
                finish_reason = response.finish_reason
        raw = "".join(chunks)
        return raw, {
            "model_tree_sha256": preflight_tree_sha256,
            "runtime_identity": runtime_identity,
            "decoder": decoder_identity,
            "request_sha256": _sha256(
                _canonical_json({"system": request["system"], "user": user_request})
            ),
            "rendered_template_sha256": _sha256(_canonical_json(prompt)),
            "generation": {
                "call_elapsed_s": round(time.monotonic() - started, 6),
                "mask_build_elapsed_s": mask_elapsed_s,
                "prompt_tokens": prompt_tokens,
                "generated_tokens": generated_tokens,
                "finish_reason": finish_reason,
            },
        }

    setattr(provider, "load_receipt", {
        "model_load_elapsed_s": load_elapsed_s,
        "preflight_model_tree_sha256": preflight_tree_sha256,
        "runtime_identity": runtime_identity,
    })
    setattr(provider, "decoder_identity", decoder_identity)
    return provider


def run_fixture(fixture: dict, provider) -> dict:
    """One fixture, one call. Content-free result.

    `agreed` compares against the fixture's preregistered `intended_turn`. It is
    a selection measurement and says nothing about whether the resulting title is
    worth reading, which no mechanical result here can reach.
    """
    offered = offered_turns(fixture)
    request = model_request(fixture)
    row: dict = {
        "fixture": fixture["name"],
        "offered": list(offered),
        "control_turn": fixture["control_turn"],
        "intended_turn": fixture["intended_turn"],
    }
    try:
        raw, observed = provider(request, offered)
    except TitleRefused as refused:
        row["outcome"] = "refused"
        row["code"] = refused.code
        row["decoder"] = getattr(provider, "decoder_identity", "unavailable")
        return row
    row["observed"] = observed
    row["response_sha256"] = _sha256(raw)
    row["response_bytes"] = len(raw.encode("utf-8"))
    try:
        selected = decode_response(raw, offered)
    except TitleRefused as refused:
        row["outcome"] = "refused"
        row["code"] = refused.code
        return row
    row["outcome"] = "selected"
    row["selected_turn"] = selected
    row["agreed_with_intended"] = selected == fixture["intended_turn"]
    row["differs_from_control"] = selected != fixture["control_turn"]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--receipt", type=Path)
    arguments = parser.parse_args()

    fixtures = load_fixtures()
    if arguments.self_test or arguments.model_directory is None:
        # No model. Exercises request construction, the mask's language and the
        # parser against every fixture, which is the part that must be right
        # before a single token is generated.
        for fixture in fixtures:
            offered = offered_turns(fixture)
            model_request(fixture)
            machine = TitleSelectionMachine(offered)
            for string in machine.language():
                assert machine.complete(string), string
                decode_response(string, offered)
        print(
            _canonical_json(
                {
                    "schema": PROBE_SCHEMA,
                    "self_test": "passed",
                    "fixtures": len(fixtures),
                    "values": sum(len(values_for(offered_turns(f))) for f in fixtures),
                }
            )
        )
        return 0

    provider = local_title_provider(arguments.model_directory)
    rows = [run_fixture(fixture, provider) for fixture in fixtures]
    receipt = {
        "schema": PROBE_SCHEMA,
        "decoding": TITLE_DECODING,
        "fixtures_sha256": _sha256(
            Path(__file__).with_name("title_selection_fixtures.json").read_bytes()
        ),
        "harness": {
            "source_sha256": _sha256(Path(__file__).read_bytes()),
            "decoder_sha256": _sha256(
                Path(__file__).with_name("title_decoding.py").read_bytes()
            ),
        },
        "load": provider.load_receipt,
        "postflight_model_tree_sha256": tree_sha256(arguments.model_directory),
        "rows": rows,
    }
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
    if arguments.receipt:
        arguments.receipt.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
