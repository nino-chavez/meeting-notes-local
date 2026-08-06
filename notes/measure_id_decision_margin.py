#!/usr/bin/env python3
"""Measure the model's margin at the token that ends the fragment identifier.

`MLX_NOTE_ADMISSION.md` records that 9 of 10 supported fixtures end
`source_fragment_id` after 67 characters and one does not, and that nothing
measured so far distinguishes them. Two mechanisms have been asserted and
retracted. This script does not propose a third; it asks whether there is
anything to explain.

At the step where the model has emitted `sf-` plus the fragment's 64 hex
characters, the next token either continues the identifier (`-`, leading to the
`-t000000-c000000-NNNNNN` tail) or closes the string (`"`). The mask permits
both. This records the logit margin between them at exactly that step, on every
fixture, by wrapping the same `make_contract_logits_processor` the admission
harness installs — so it observes the real decoding path rather than a
reconstruction.

    <venv>/bin/python notes/measure_id_decision_margin.py [--json] [--fixture NAME]

**This changes no request and no contract.** It loads the pinned model, sends the
requests the harness already builds, and reads the distribution at one step. No
mask is edited, so the committed receipts stay valid. Run it before spending
either registered intervention.

Reading the result:

* **Near-zero margin on all ten** — there is no mechanism behind the one success,
  only an unstable argmax, and the honest statement is that the model copies a
  non-enumerated 90-character identifier unreliably.
* **Decisive margin that inverts on the success** — the trace names a cause, and
  the fixture pair becomes worth pursuing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mlx_note_admission as admission  # noqa: E402
from candidate_first import STRATEGY_CUE, generate_manifest  # noqa: E402
from structured_decoding import make_contract_logits_processor  # noqa: E402

FRAGMENT_ID = re.compile(r"sf-[0-9a-f]{64}")
TOP_K = 6


def _fixture_rows() -> dict:
    return {name: row for name, *row in
            ((r[0], r[1]) for r in admission.synthetic_measurement_fixtures())}


def measure_fixture(name, transcript, model, tokenizer) -> dict:
    import mlx.core as mx
    from mlx_lm.generate import stream_generate
    from mlx_lm.sample_utils import make_sampler

    manifest = generate_manifest(transcript, STRATEGY_CUE)
    request = admission.model_request(transcript, manifest)
    payload = admission._canonical_json({k: v for k, v in request.items() if k != "system"})
    anchors = sorted(set(FRAGMENT_ID.findall(payload)))
    if not anchors:
        return {"fixture": name, "skipped": "abstain fixture — no fragment offered"}

    messages = [
        {"role": "system", "content": request["system"]},
        {"role": "user", "content": payload},
    ]
    prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)

    inner = make_contract_logits_processor(tokenizer)
    observations: list[dict] = []
    emitted: dict = {"text": ""}

    def recording_processor(tokens, logits):
        out = inner(tokens, logits)
        # The identifier ends at the step where the text so far closes with
        # `sf-` + 64 hex and nothing more. Decode lazily; this is one call per token.
        ids = tokens.tolist() if hasattr(tokens, "tolist") else list(tokens)
        text = tokenizer.decode(ids) if ids else ""
        emitted["text"] = text
        for anchor in anchors:
            if text.endswith(anchor):
                row = mx.array(out[0]) if out.ndim > 1 else mx.array(out)
                order = mx.argsort(-row)[:TOP_K].tolist()
                values = [float(row[i]) for i in order]
                decoded = [tokenizer.decode([i]) for i in order]
                cont = next((v for d, v in zip(decoded, values) if d.startswith("-")), None)
                close = next((v for d, v in zip(decoded, values) if d.startswith('"')), None)
                observations.append({
                    "step": int(len(tokens)),
                    "top_k": [{"token": d, "logit": round(v, 4)} for d, v in zip(decoded, values)],
                    "continue_logit": None if cont is None else round(cont, 4),
                    "close_logit": None if close is None else round(close, 4),
                    "margin_continue_minus_close": (
                        None if cont is None or close is None else round(cont - close, 4)
                    ),
                    "chose": "continue" if cont is not None and (close is None or cont > close) else "close",
                })
                break
        return out

    chunks: list[str] = []
    for response in stream_generate(
        model, tokenizer, prompt=prompt,
        max_tokens=admission.MLX_RUNTIME["decoding"]["max_tokens"],
        max_kv_size=admission.MLX_RUNTIME["decoding"]["max_kv_size"],
        sampler=make_sampler(temp=admission.MLX_RUNTIME["decoding"]["temperature"]),
        logits_processors=[recording_processor],
    ):
        chunks.append(response.text)
    raw = "".join(chunks)

    produced = sorted(set(re.findall(r'sf-[0-9a-f]{64}[-a-z0-9]*', raw)))
    return {
        "fixture": name,
        "offered_id_length": sorted({len(a) + len("-t000000-c000000-000000") for a in anchors}),
        "produced_id_lengths": sorted({len(p) for p in produced}) or None,
        "full_length_reproduced": bool(produced) and all(len(p) == 90 for p in produced),
        "decision_points": observations,
        "response_length": len(raw),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixture", action="append", help="limit to named fixtures")
    args = parser.parse_args(argv[1:])

    import mlx.core as mx
    from mlx_lm import load

    mx.random.seed(admission.MLX_RUNTIME["decoding"]["seed"])
    repo = admission.MLX_RUNTIME.get("model", {}).get("repository") if isinstance(
        admission.MLX_RUNTIME.get("model"), dict) else None
    if repo is None:
        repo = json.loads(
            (Path(__file__).with_name("mlx_note_matrix_receipt.json")).read_text()
        )["registered_model"]["repository"]
    model, tokenizer = load(repo)

    wanted = set(args.fixture or [])
    rows = []
    for name, transcript, *_ in admission.synthetic_measurement_fixtures():
        if wanted and name not in wanted:
            continue
        mx.random.seed(admission.MLX_RUNTIME["decoding"]["seed"])
        rows.append(measure_fixture(name, transcript, model, tokenizer))

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0

    print(f"{'fixture':24} {'produced':>9} {'full90':>7} {'margin(cont-close)':>19}  top-2 at the decision step")
    for row in rows:
        if row.get("skipped"):
            print(f"{row['fixture']:24} {row['skipped']}")
            continue
        pts = row["decision_points"]
        if not pts:
            print(f"{row['fixture']:24} {str(row['produced_id_lengths']):>9} "
                  f"{str(row['full_length_reproduced']):>7} {'<no decision step seen>':>19}")
            continue
        p = pts[0]
        top2 = ", ".join(f"{t['token']!r}={t['logit']}" for t in p["top_k"][:2])
        print(f"{row['fixture']:24} {str(row['produced_id_lengths']):>9} "
              f"{str(row['full_length_reproduced']):>7} {str(p['margin_continue_minus_close']):>19}  {top2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
