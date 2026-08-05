#!/usr/bin/env python3
"""Fresh-process orchestrator for the registered 12-fixture cold/warm matrix.

`MLX_NOTE_ADMISSION.md` § "Measurement protocol and pass gates" registers this
shape and `measure_mlx_note_candidate.py` deliberately refuses `--scope full`
because a single process cannot produce it:

> Each is run three times from a fresh process for cold timing and twice more in
> the same loaded process for warm timing.

So each fixture gets three worker processes. All three make one cold call. The
first makes two further calls in its already-loaded process, which are the warm
repeats — three cold timings and two warm timings per fixture, 36 processes and
60 calls in total.

**Why a process and not a loop.** A cold timing is the first call after a model
load, and nothing inside one process is cold twice. Building the mask costs
~1.9 s of vocabulary decoding on top of the load, and paying it 36 times is the
measurement rather than waste: caching it across workers would make every cold
number after the first one warm, quietly.

**The deterministic control runs first**, for all twelve fixtures, in this
process. It needs no model, and the protocol asks for it before the suite so a
fixture whose control already disagrees is visible before any inference.

**Content-free.** Identifiers, hashes, sizes, timings, refusal classes, and
gate booleans. No transcript text, no note body, no model reply. Synthetic
fixtures only.

**Load is recorded because latency is a rejection gate.** The registered
ceilings are a 30 s cold median and a 15 s warm median, and this machine has
produced 3.5 s and 43.0 s for byte-identical work hours apart. A receipt that
reports only the number cannot distinguish a slow candidate from a busy Mac,
and the protocol says exceeding the ceiling rejects the candidate. Load average
is captured around every call so that a latency failure can be attributed
rather than assumed.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

from measure_mlx_note_candidate import control_expected, model_call_checks
from mlx_note_admission import (
    MLX_RUNTIME,
    _canonical_json,
    _harness_identity,
    _sha256,
    local_mlx_provider,
    run_control_arm,
    run_model_arm,
    synthetic_measurement_fixtures,
    tree_sha256,
)

# Registered in the protocol, restated here so a drifting run is a failed
# assertion rather than a quieter matrix.
COLD_REPEATS = 3
WARM_REPEATS = 2
EXPECTED_FIXTURES = 12
COLD_MEDIAN_CEILING_S = 30.0
WARM_MEDIAN_CEILING_S = 15.0
PEAK_RSS_CEILING = 4_282_063_304
# Interpreter start, model load, and the ~1.9 s vocabulary decode, generously.
WORKER_STARTUP_ALLOWANCE_S = 120.0

# Timings and footprint are the only values a repeat may move, so they are
# excluded from the digest that the repeatability gate compares.
_VOLATILE_KEYS = frozenset({"elapsed_s", "call_elapsed_s", "model_load_elapsed_s", "peak_rss"})


def _stable(value):
    """Strip timing and footprint fields wherever they appear."""
    if isinstance(value, dict):
        return {key: _stable(item) for key, item in value.items() if key not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _fixtures() -> dict:
    fixtures = {row[0]: row for row in synthetic_measurement_fixtures()}
    if len(fixtures) != EXPECTED_FIXTURES:
        raise SystemExit(
            f"the registered matrix is {EXPECTED_FIXTURES} fixtures; found {len(fixtures)}"
        )
    return fixtures


def _load_average() -> list:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except OSError:
        return []


def run_worker(model_directory: Path, fixture_id: str, warm_repeats: int) -> int:
    """One fresh process: load once, one cold call, then `warm_repeats` warm."""
    fixtures = _fixtures()
    if fixture_id not in fixtures:
        raise SystemExit(f"unknown fixture: {fixture_id}")
    _, transcript, expected_outcome, required_terms = fixtures[fixture_id]

    preflight = tree_sha256(model_directory)
    if preflight != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise SystemExit("model tree does not match registered identity")
    provider = local_mlx_provider(model_directory, constrained=True)

    calls = []
    for index in range(1 + warm_repeats):
        load_before = _load_average()
        result = run_model_arm(transcript, provider)
        note_sha256 = _sha256(_canonical_json(result.note)) if result.note is not None else None
        calls.append({
            "phase": "cold-call" if index == 0 else "warm-call",
            "index": index,
            "outcome": result.outcome,
            "code": result.code,
            "refusal_category": result.receipt.get("refusal_category"),
            "error_type": result.receipt.get("error_type"),
            "elapsed_s": result.receipt.get("elapsed_s"),
            "response_sha256": result.receipt.get("response_sha256"),
            "response_bytes": result.receipt.get("response_bytes"),
            "generation": result.receipt.get("generation"),
            "identity": result.receipt.get("identity"),
            # The repeatability gate is stated over the response *and* the
            # accepted note and receipt, so both digests travel with the call.
            "note_sha256": note_sha256,
            "receipt_sha256": _sha256(_canonical_json(_stable(result.receipt))),
            "checks": model_call_checks(result, transcript, expected_outcome, required_terms),
            "load_average_before": load_before,
            "load_average_after": _load_average(),
        })

    print(_canonical_json({
        "schema": "mlx-note-matrix-worker/1",
        "fixture": fixture_id,
        "preflight_tree_sha256": preflight,
        "postflight_tree_sha256": tree_sha256(model_directory),
        "load": provider.load_receipt,
        "peak_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "calls": calls,
    }))
    return 0


def _worker_timeout_s(warm_repeats: int) -> float:
    """A bound taken from the protocol's own ceiling, not invented.

    One cold call plus the warm repeats, each allowed the registered 30 s cold
    ceiling, plus a fixed allowance for interpreter start, model load, and the
    ~1.9 s vocabulary decode. A wedged worker must not hold the matrix open
    indefinitely — there are 36 of them.
    """
    return (1 + warm_repeats) * COLD_MEDIAN_CEILING_S + WORKER_STARTUP_ALLOWANCE_S


def _failed_worker(fixture_id: str, reason: str, wall_s: float, **extra) -> dict:
    return {
        "fixture": fixture_id,
        "worker_failed": True,
        "failure": reason,
        "process_wall_s": wall_s,
        **extra,
    }


# Everything `_fixture_row` reads off a worker. A record missing any of these
# would fail deep inside the projection instead of at the boundary.
_WORKER_FIELDS = frozenset({
    "fixture", "preflight_tree_sha256", "postflight_tree_sha256", "load", "peak_rss", "calls",
})


def _spawn(model_directory: Path, fixture_id: str, warm_repeats: int) -> dict:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [
                sys.executable, str(Path(__file__).resolve()),
                "--model-directory", str(model_directory),
                "--worker", fixture_id,
                "--warm-repeats", str(warm_repeats),
            ],
            capture_output=True,
            text=True,
            timeout=_worker_timeout_s(warm_repeats),
        )
    except subprocess.TimeoutExpired:
        return _failed_worker(
            fixture_id, "timeout", round(time.monotonic() - started, 6),
            timeout_s=_worker_timeout_s(warm_repeats),
        )
    except OSError as error:
        # The child may never exist: `posix_spawn` raises EAGAIN or ENOMEM under
        # memory pressure. That is in-domain here — this code already models a
        # memory-pressure kill as a first-class outcome, and the committed run
        # recorded load averages above 10 against a 1.18 GB resident model.
        return _failed_worker(
            fixture_id, "spawn-failed", round(time.monotonic() - started, 6),
            error_type=type(error).__name__,
            errno=getattr(error, "errno", None),
        )
    wall_s = round(time.monotonic() - started, 6)
    if completed.returncode != 0:
        return _failed_worker(
            fixture_id, "nonzero-exit", wall_s,
            # A negative return code is a signal, which is how a memory-pressure
            # termination arrives. The protocol rejects on that, not just on the
            # footprint number, so it must be distinguishable from an exception.
            returncode=completed.returncode,
            terminated_by_signal=completed.returncode < 0,
            stderr_tail=completed.stderr.strip().splitlines()[-3:],
        )
    try:
        worker = json.loads(completed.stdout)
    except ValueError as error:
        # A worker can exit zero and still hand back something unusable. Left
        # unguarded this raised out of the matrix after up to 36 model loads,
        # writing no receipt and naming no fixture — the parent could not tell
        # "worker succeeded" from "worker output unreadable", and only the
        # second is fatal.
        return _failed_worker(
            fixture_id, "stdout-unparseable", wall_s,
            error_type=type(error).__name__,
            stdout_bytes=len(completed.stdout),
            stderr_tail=completed.stderr.strip().splitlines()[-3:],
        )
    # Parsing is not the same as getting a worker record. A parsed non-dict, or
    # a dict missing what the projection reads, would raise later — here, or
    # deeper in `_fixture_row` — producing exactly the failure this boundary
    # exists to prevent: a traceback out of the matrix after up to 36 model
    # loads, with no receipt written and no fixture named.
    missing = _WORKER_FIELDS - set(worker) if isinstance(worker, dict) else _WORKER_FIELDS
    if missing:
        return _failed_worker(
            fixture_id, "worker-record-incomplete", wall_s,
            missing=sorted(missing),
            record_type=type(worker).__name__,
        )
    worker["process_wall_s"] = wall_s
    worker["worker_failed"] = False
    return worker


def run_matrix(model_directory: Path) -> dict:
    fixtures = _fixtures()
    preflight = tree_sha256(model_directory)
    if preflight != MLX_RUNTIME["model"]["expected_tree_sha256"]:
        raise SystemExit("model tree does not match registered identity")

    # The deterministic control, for every fixture, before any inference.
    controls = {}
    for fixture_id, (_, transcript, expected_outcome, _terms) in fixtures.items():
        control = run_control_arm(transcript)
        controls[fixture_id] = {
            "outcome": control.outcome,
            "code": control.code,
            "expected": control_expected(control, expected_outcome),
        }

    started_at_load = _load_average()
    rows = []
    for fixture_id in fixtures:
        workers = [
            _spawn(model_directory, fixture_id, WARM_REPEATS if index == 0 else 0)
            for index in range(COLD_REPEATS)
        ]
        rows.append(_fixture_row(fixture_id, controls[fixture_id], workers))

    return _matrix_receipt(model_directory, preflight, started_at_load, rows)


def _call_elapsed_s(call: dict):
    """The call's generation time, or None if it never reached generation.

    A timeout or a provider throw — `MaskRefused` is one — produces a receipt
    with no `generation` block at all. Reading through it would crash the
    orchestrator on the worker that has the most to say, so the absence is
    carried as a value and surfaces as the `timings_available` gate rather than
    as a traceback.
    """
    generation = call.get("generation")
    if isinstance(generation, dict) and isinstance(generation.get("call_elapsed_s"), (int, float)):
        return generation["call_elapsed_s"]
    return None


def _fixture_row(fixture_id: str, control: dict, workers: list) -> dict:
    failed = [worker for worker in workers if worker["worker_failed"]]
    if failed:
        return {
            "fixture": fixture_id,
            "control": control,
            "worker_failures": failed,
            "gates": {"workers_completed": False},
        }

    cold = [call for worker in workers for call in worker["calls"] if call["phase"] == "cold-call"]
    warm = [call for worker in workers for call in worker["calls"] if call["phase"] == "warm-call"]

    # Stated over the response, the accepted note, and the receipt — all three,
    # across the three cold runs, with no averaging.
    repeatable = (
        len({call["response_sha256"] for call in cold}) == 1
        and len({call["note_sha256"] for call in cold}) == 1
        and len({call["receipt_sha256"] for call in cold}) == 1
    )
    every_call = cold + warm
    cold_elapsed = [_call_elapsed_s(call) for call in cold]
    warm_elapsed = [_call_elapsed_s(call) for call in warm]
    timings_available = all(value is not None for value in cold_elapsed + warm_elapsed)
    return {
        "fixture": fixture_id,
        "control": control,
        "cold_repeats": len(cold),
        "warm_repeats": len(warm),
        "outcomes": sorted({call["outcome"] for call in every_call}),
        "codes": sorted({call["code"] or "" for call in every_call}),
        "response_sha256": sorted({call["response_sha256"] or "" for call in cold}),
        "note_sha256": sorted({call["note_sha256"] or "" for call in cold}),
        # All three digests the gate is computed over are recorded, not two. If
        # the receipt digest is the one that moved, a reader must be able to see
        # which field diverged rather than only that `repeatable` went false.
        "receipt_sha256": sorted({call["receipt_sha256"] or "" for call in cold}),
        "cold_elapsed_s": cold_elapsed,
        "warm_elapsed_s": warm_elapsed,
        "cold_median_s": round(statistics.median(cold_elapsed), 6) if timings_available and cold else None,
        "warm_median_s": round(statistics.median(warm_elapsed), 6) if timings_available and warm else None,
        "peak_rss": max(worker["peak_rss"] for worker in workers),
        # Every call, not only the cold ones. Warm carries the tighter ceiling —
        # 15 s against 30 s — so a `warm_latency: false` is the failure most
        # likely to arrive with nothing to attribute it to.
        "load_average": [
            {"phase": call["phase"], "before": call["load_average_before"], "after": call["load_average_after"]}
            for call in every_call
        ],
        "gates": {
            "workers_completed": True,
            "control_expected": control["expected"],
            "repeats_as_registered": len(cold) == COLD_REPEATS and len(warm) == WARM_REPEATS,
            "checks_pass_on_every_call": all(all(call["checks"].values()) for call in every_call),
            "repeatable": repeatable,
            "timings_available": timings_available,
            "tree_stable": all(
                worker["preflight_tree_sha256"] == worker["postflight_tree_sha256"] for worker in workers
            ),
        },
    }


def _matrix_receipt(model_directory: Path, preflight: str, started_at_load: list, rows: list) -> dict:
    postflight = tree_sha256(model_directory)
    complete = [row for row in rows if row["gates"].get("workers_completed")]
    cold_medians = [row["cold_median_s"] for row in complete if row["cold_median_s"] is not None]
    warm_medians = [row["warm_median_s"] for row in complete if row["warm_median_s"] is not None]
    peak_rss = max([row["peak_rss"] for row in complete], default=0)

    # Reported separately, exactly as registered, and never averaged together.
    latency = {
        "cold_median_s": round(statistics.median(cold_medians), 6) if cold_medians else None,
        "warm_median_s": round(statistics.median(warm_medians), 6) if warm_medians else None,
        "cold_ceiling_s": COLD_MEDIAN_CEILING_S,
        "warm_ceiling_s": WARM_MEDIAN_CEILING_S,
        "load_average_at_start": started_at_load,
        "load_average_at_end": _load_average(),
    }
    gates = {
        "every_fixture_ran": len(complete) == len(rows) == EXPECTED_FIXTURES,
        "per_fixture_gates": all(all(row["gates"].values()) for row in complete),
        "cold_latency": latency["cold_median_s"] is not None and latency["cold_median_s"] <= COLD_MEDIAN_CEILING_S,
        "warm_latency": latency["warm_median_s"] is not None and latency["warm_median_s"] <= WARM_MEDIAN_CEILING_S,
        "memory": 0 < peak_rss <= PEAK_RSS_CEILING,
        "tree_unchanged": preflight == postflight,
    }
    return {
        # /2: `fixtures[].load_average` carries every call as
        # {phase, before, after} rather than the cold calls' bare triples, and
        # every row records `receipt_sha256`. A /1 receipt is still in git
        # history, and a reader pinned to /1 would mis-parse one of the two.
        "schema": "mlx-note-matrix/2",
        "decoding": "structure-constrained",
        "harness": _harness_identity(),
        # `_harness_identity` hashes `mlx_note_admission.py` and nothing else,
        # so a receipt produced by a defective orchestrator and one produced by
        # the repaired orchestrator were byte-identical in that block. The
        # protocol's own rule is that a receipt unable to say what produced it
        # cannot be compared with another, and the instrument is half of that.
        "orchestrator_sha256": _sha256(Path(__file__).resolve().read_bytes()),
        "registered_model": {
            "repository": MLX_RUNTIME["model"]["repository"],
            "revision": MLX_RUNTIME["model"]["revision"],
            "tree_sha256": MLX_RUNTIME["model"]["expected_tree_sha256"],
        },
        "matrix": {"fixtures": EXPECTED_FIXTURES, "cold_repeats": COLD_REPEATS, "warm_repeats": WARM_REPEATS},
        "preflight_tree_sha256": preflight,
        "postflight_tree_sha256": postflight,
        "latency": latency,
        "peak_rss": peak_rss,
        "peak_rss_ceiling": PEAK_RSS_CEILING,
        "fixtures": rows,
        "gates": gates,
        # Mechanical only. The registered human semantic/usefulness review is
        # untouched by anything here, and no value below is an admission.
        "passed": all(gates.values()),
        "admits": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--worker", help="internal: run one fixture in this process")
    parser.add_argument("--warm-repeats", type=int, default=WARM_REPEATS)
    args = parser.parse_args()

    if args.worker:
        return run_worker(args.model_directory, args.worker, args.warm_repeats)
    receipt = run_matrix(args.model_directory)
    print(_canonical_json(receipt))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
