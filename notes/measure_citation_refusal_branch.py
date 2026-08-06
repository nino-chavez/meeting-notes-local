"""Localize which `citation-locator` branch refuses, and why.

`_decode_response` raises `AdmissionRefused("citation-locator")` from five
distinct places. A receipt carrying that code cannot say which one fired, so
the 2026-08-06 matrix reported the same string on four fixtures and the
"one remaining failure class" reading of that result is unproven: five branches
share one label.

This probe re-runs the registered constrained arm per fixture, catches the
refusal, and walks the traceback to the line number inside
`mlx_note_admission.py`. That localizes the branch without editing the harness
— which matters, because `_harness_identity()` hashes the harness source, and
an edit would invalidate comparison against the receipts committed at c07e1a6.

It also character-diffs the emitted `citation` against the canonical slice, so
a mismatch can be told apart from a truncation. Truncation would mean the
remaining failure is the same identifier-transcription mechanism this work has
been chasing since 2026-08-02, not a new one about citation.

Synthetic fixtures only; no product data, no network, no model download.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

import mlx_note_admission as M  # noqa: E402

BRANCHES = {
    "candidate_id-unknown": "candidate_id absent from the offered candidates",
    "source-id-not-offered": "source_fragment_id not offered for this candidate",
    "source-id-order": "source ids not in canonical fragment order",
    "primary-reused": "primary fragment already consumed by an earlier row",
    "citation-text-mismatch": "citation is not the exact canonical slice",
}


def branch_name(lineno: int) -> str:
    """Map a harness line number onto a named branch.

    Resolved by reading the source rather than hard-coding line numbers, so
    this stays correct if `_decode_response` moves.
    """
    return _BRANCH_LINES.get(lineno, f"unmapped-line-{lineno}")


def _resolve_branch_lines() -> dict[int, str]:
    source = Path(M.__file__).read_text(encoding="utf-8").splitlines()
    hits = [
        index + 1
        for index, line in enumerate(source)
        if 'AdmissionRefused("citation-locator")' in line
    ]
    if len(hits) != len(BRANCHES):
        raise SystemExit(
            f"expected {len(BRANCHES)} citation-locator raises, found {len(hits)}"
        )
    return dict(zip(hits, BRANCHES))


_BRANCH_LINES = _resolve_branch_lines()


def refusal_line(exc: BaseException) -> int | None:
    """Last traceback frame inside the harness — the raising line."""
    lineno = None
    tb = exc.__traceback__
    harness = Path(M.__file__).resolve()
    while tb is not None:
        if Path(tb.tb_frame.f_code.co_filename).resolve() == harness:
            lineno = tb.tb_lineno
        tb = tb.tb_next
    return lineno


def common_prefix(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def probe(fixture_id: str, transcript, provider) -> dict:
    manifest = M.generate_manifest(transcript, M.STRATEGY_CUE)
    request = M.model_request(transcript, manifest)
    raw, observed = provider(request)
    fragments = {
        row["source_fragment_id"]: row
        for row in M.build_fragment_map(transcript)["fragments"]
    }
    record: dict[str, object] = {
        "fixture": fixture_id,
        "finish_reason": observed["generation"].get("finish_reason"),
        "response_bytes": len(raw.encode("utf-8")),
        "candidates_offered": len(request["candidates"]),
        # Fixtures are synthetic and public, so the raw response is safe to
        # retain and is the only thing that makes this diagnosis re-readable.
        "raw": raw,
        "offered_source_fragment_ids": [
            fragment["source_fragment_id"]
            for candidate in request["candidates"]
            for fragment in candidate["source_fragments"]
        ],
        "offered_candidate_ids": [
            candidate["candidate_id"] for candidate in request["candidates"]
        ],
    }
    try:
        rows = M._decode_response(raw, request, transcript)
    except M.AdmissionRefused as exc:
        line = refusal_line(exc)
        record["refused"] = exc.code
        record["branch_line"] = line
        record["branch"] = branch_name(line) if line else "unlocated"
    except Exception as exc:  # noqa: BLE001
        record["refused"] = type(exc).__name__
        record["branch"] = "non-admission-exception"
    else:
        record["refused"] = None
        record["records"] = len(rows)

    # Independent of the refusal, report what the model actually emitted, so a
    # text mismatch can be told apart from a truncation.
    try:
        root = json.loads(raw)
        emitted = root.get("items", [])
    except Exception:  # noqa: BLE001
        record["parse"] = "response is not JSON"
        return record
    record["rows_emitted"] = len(emitted)
    # A row per offered candidate is what the contract's ordering rule exists to
    # constrain; nothing in `_decode_response` requires it, so record the ratio.
    record["covers_every_candidate"] = len(emitted) == len(request["candidates"])
    offered_ids = {
        fragment["source_fragment_id"]
        for candidate in request["candidates"]
        for fragment in candidate["source_fragments"]
    }
    by_candidate_id = {
        candidate["candidate_id"]: candidate for candidate in request["candidates"]
    }

    def slice_of(fragment: dict) -> str:
        return transcript.turns[fragment["turn"]].text[
            fragment["char_start"]:fragment["char_end"]
        ]

    detail = []
    for index, row in enumerate(emitted):
        if not isinstance(row, dict):
            detail.append({"index": index, "shape": "not an object"})
            continue
        citation = row.get("citation")
        source_ids = row.get("source_fragment_ids")
        primary = source_ids[0] if isinstance(source_ids, list) and source_ids else None
        canonical = None
        resolved_via = None
        if isinstance(primary, str) and primary in fragments:
            canonical = slice_of(fragments[primary])
            resolved_via = "source_fragment_ids[0]"
        else:
            # A truncated identifier resolves to no fragment, which would leave
            # citation correctness unscored on exactly the fixtures that
            # truncate — the receipt would call the citation wrong when the text
            # is right. Fall back to the candidate the row names, so identifier
            # transcription and citation fidelity stay independently measurable.
            named = by_candidate_id.get(row.get("candidate_id"))
            if named is not None:
                canonical = slice_of(
                    fragments[named["source_fragments"][0]["source_fragment_id"]]
                )
                resolved_via = "candidate_id"
        entry = {
            "index": index,
            "candidate_id": row.get("candidate_id"),
            "candidate_id_known": row.get("candidate_id")
            in {candidate["candidate_id"] for candidate in request["candidates"]},
            "source_fragment_ids": source_ids,
            "source_ids_offered": bool(source_ids)
            and all(value in offered_ids for value in source_ids),
            "label": row.get("label"),
            "claim": row.get("claim"),
            "citation_repr": repr(citation),
        }
        entry["canonical_resolved_via"] = resolved_via
        if canonical is not None and isinstance(citation, str):
            entry["canonical_repr"] = repr(canonical)
            entry["citation_matches"] = citation == canonical
            entry["len_citation"] = len(citation)
            entry["len_canonical"] = len(canonical)
            entry["common_prefix"] = common_prefix(citation, canonical)
            entry["is_prefix_of_canonical"] = canonical.startswith(citation)
        else:
            entry["canonical_repr"] = None
            entry["citation_matches"] = False
        detail.append(entry)
    record["rows"] = detail
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument(
        "--fixture",
        action="append",
        default=None,
        help="fixture id; repeatable. Default: every supported fixture.",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    fixtures = {
        row[0]: row for row in M.synthetic_measurement_fixtures()
    }
    wanted = args.fixture or [
        name for name, row in fixtures.items() if row[2] != "transcript-only"
    ]
    provider = M.local_mlx_provider(args.model_directory, constrained=True)

    records = []
    for name in wanted:
        record = probe(name, fixtures[name][1], provider)
        records.append(record)
        line = record.get("branch_line")
        print(
            f"{name:24s} refused={record['refused'] or '-':22s} "
            f"branch={record.get('branch', '-')}"
            + (f" @{line}" if line else "")
        )
        for row in record.get("rows", []):
            if row.get("citation_matches") is False:
                print(f"    emitted   {row['citation_repr']}")
                print(f"    canonical {row['canonical_repr']}")
                print(
                    f"    len {row.get('len_citation')} vs {row.get('len_canonical')}"
                    f"  common_prefix={row.get('common_prefix')}"
                    f"  prefix_of_canonical={row.get('is_prefix_of_canonical')}"
                )
    if args.out:
        args.out.write_text(
            json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
