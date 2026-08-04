"""Admission check 1, deciding half: do gate *classifications* agree across encoders?

`bench_fbank_parity.py` bounds feature/embedding/score drift between the torch
reference chain and the deployable chain (worker/fbank.py + ONNX Runtime). The
check's own definition says that is not what decides: "the score/classification
comparison decides, not raw feature equality" — classifications around
*registered operating points*, which do not exist until real calibration
material does. This harness closes the mechanism so the operator's two real
sittings are the only missing input.

Two subcommands, two processes, mirroring `prep_features.py` / `bench_fbank_parity.py`:

  prepare  (torch)      loads calibration material through the same functions the
                        registration CLI uses (`speaker_gate.load_segments`,
                        `load_wav`, the same slicing arithmetic), embeds every
                        scorable segment with the torch reference encoder, and
                        stores the exact waveform slices beside those embeddings
                        so the other arm judges identical audio.

  compare  (torch-free) re-embeds the stored slices through worker/fbank.py and
                        the registered ONNX artifact, derives the full gating
                        chain under BOTH embedding sets with speaker_gate's own
                        numpy math (leave-one-sitting-out held-out scores,
                        `enroll`, `score`, `operating_point_choices`), registers
                        operating points from the torch chain, and reports the
                        classification agreement, margins, and threshold deltas.

The output is measurements, not a verdict: flips per registered point, the
smallest |score - threshold| margin either chain observed, the largest
inter-chain score delta, and per-target threshold deltas. What those numbers
admit is the operator's call, recorded in RESULTS.md.

`--self-test` runs a two-sided control on fabricated embeddings: identical
chains must report zero flips, and a bounded perturbation must be *detected* as
flips — an instrument whose zero cannot be distinguished from blindness proves
nothing (the same bite-control shape as the deny-network offline check).

Calibration material identifies a person. The work directory is refused inside
the repository, and nothing here writes audio, transcripts, or any content-
bearing field into the JSON receipt — counts, seconds, digests, and cosine
statistics only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import aec_bound as ab
import speaker_gate as sg

# The registered export this measurement is about. Pinned identically in
# worker/build_runtime.sh and scripts/verify-release-bundle.py; the cross-pin
# test keeps the three in lockstep. `compare` refuses any other artifact unless
# the run is explicitly marked research-only.
EXPECTED_ONNX_SHA256 = "1d5e288b1037410fd0c98f618e94523a6b7ca8a99c7069f076efb40aa95759cd"

AGREEMENT_CONTRACT_VERSION = "speaker-gate-classification-agreement/1"
WORK_METADATA = "gate-agreement-material.json"
WORK_ARRAYS = "gate-agreement-arrays.npz"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def duplicate_audio_problem(
    calibrate_wavs: list[Path], against_wavs: list[Path]
) -> str | None:
    """One recording, one role, once. Duplicates corrupt silently, not loudly:
    a sitting reused as --against puts the operator's own voice in the negative
    pool and inflates every false-admit figure the registered points carry, and
    one negative recording passed twice double-counts toward the 60 s /
    20-segment floors. The refusal spans BOTH lists — review of 67e7fa8 found
    the sitting-only version left the cross-role path open."""
    seen: dict[str, str] = {}
    for role, wavs in (("--calibrate", calibrate_wavs), ("--against", against_wavs)):
        for wav in wavs:
            digest = ab.sha256(wav)
            prior = seen.get(digest)
            if prior == "--calibrate" and role == "--against":
                return (
                    f"{wav} repeats a --calibrate recording (digest {digest}); a "
                    "sitting cannot also price the negative pool — that scores "
                    "the operator's own voice as an impostor"
                )
            if prior is not None:
                return (
                    f"{role} repeats audio digest {digest}; one recording cannot "
                    "count twice"
                )
            seen[digest] = role
    return None


# ---------------------------------------------------------------------------
# prepare (torch reference arm)
# ---------------------------------------------------------------------------


def _sliced_group(seg_path: Path, wav_path: Path, source_class: str | None):
    """Load one (segments, audio) pair the way `speaker_gate._embed_pair` does,
    but keep the waveform slices so the torch-free arm embeds identical audio.
    The slicing arithmetic mirrors `embed_segments`; `prepare` asserts the two
    stay aligned by embedding through the same list."""
    segment_doc = json.loads(seg_path.read_text())
    segs = sg.load_segments(seg_path, wav_path, "mic")
    audio = sg.load_wav(wav_path)
    clips: list[np.ndarray] = []
    durations: list[float] = []
    for seg in segs:
        length = seg["end"] - seg["start"]
        if length < sg.MIN_SCORABLE_S:
            continue
        clips.append(audio[int(seg["start"] * sg.RATE): int(seg["end"] * sg.RATE)])
        durations.append(length)
    provenance = {
        "segments": str(seg_path), "audio": str(wav_path),
        "audio_sha256": ab.sha256(wav_path), "audio_samples": sg._wav_samples(wav_path),
        "segments_sha256": ab.sha256(seg_path),
        "segments_schema": segment_doc.get("schema"),
        "captured_at": segment_doc.get("captured_at"),
        "scorable_segments": len(clips), "scorable_seconds": float(sum(durations)),
    }
    if source_class is not None:
        provenance["source_class"] = source_class
    return clips, durations, provenance


def run_prepare(args) -> int:
    work_dir = Path(args.work_dir)
    if ab.inside_repo(work_dir):
        raise SystemExit(
            f"--work-dir {work_dir} is inside the repository. Calibration "
            "material identifies a person; use an owner-only directory outside it."
        )
    if len(args.calibrate or []) < 2:
        raise SystemExit(
            "the classification comparison needs at least two --calibrate "
            "sittings — the registered operating points must come from material "
            "that meets the registration bar, and one sitting is measurably "
            "over-tight (speaker_gate.py records why)"
        )
    if not args.against:
        raise SystemExit(
            "the classification comparison needs at least one attested "
            "--against source so false-admission decisions are compared too"
        )

    for source_class, _seg, _wav in args.against:
        if source_class not in sg.NEGATIVE_SOURCE_CLASSES:
            raise SystemExit(
                f"--against source class must be one of "
                f"{sorted(sg.NEGATIVE_SOURCE_CLASSES)}, got {source_class!r}"
            )
    paths = [Path(p) for pair in args.calibrate for p in pair]
    paths += [Path(p) for source in args.against for p in source[1:]]
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"{path} is not an existing file")
    problem = duplicate_audio_problem(
        [Path(wav) for _seg, wav in args.calibrate],
        [Path(wav) for _cls, _seg, wav in args.against],
    )
    if problem:
        raise SystemExit(problem)

    embed = sg.load_encoder(args.model_dir)

    groups: list[dict] = []
    arrays: dict[str, np.ndarray] = {}
    sitting_manifest: list[dict] = []
    for index, (seg_p, wav_p) in enumerate(args.calibrate):
        clips, durations, provenance = _sliced_group(Path(seg_p), Path(wav_p), None)
        if len(clips) <= sg.MIN_ENROLL_SEGMENTS:
            raise SystemExit(
                f"{wav_p}: only {len(clips)} segments reach {sg.MIN_SCORABLE_S}s — at "
                f"least {sg.MIN_ENROLL_SEGMENTS + 1} are needed to score any one of "
                "them against the rest"
            )
        _store_group(arrays, len(groups), clips, durations, embed)
        groups.append({"kind": "sitting", "index": index, "clips": len(clips),
                       "provenance": provenance})
        sitting_manifest.append(provenance)

    problems = sg._sitting_problems(sitting_manifest)
    if problems:
        raise SystemExit(
            "these recordings do not establish separate sittings, and the "
            "registered operating points may not be derived from weaker "
            "material:\n  " + "\n  ".join(problems)
        )

    for source_class, seg_p, wav_p in args.against:
        clips, durations, provenance = _sliced_group(Path(seg_p), Path(wav_p), source_class)
        if not clips:
            raise SystemExit(f"{wav_p}: no scorable negative segments")
        _store_group(arrays, len(groups), clips, durations, embed)
        groups.append({"kind": "negative", "source_class": source_class,
                       "clips": len(clips), "provenance": provenance})

    work_dir.mkdir(parents=True, exist_ok=True)
    np.savez(work_dir / WORK_ARRAYS, **arrays)
    metadata = {
        "contract": AGREEMENT_CONTRACT_VERSION,
        "targets_version": sg.OPERATING_POINT_TARGET_SET_VERSION,
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "torch_encoder_fingerprint": sg.encoder_fingerprint(args.model_dir),
        "groups": groups,
    }
    (work_dir / WORK_METADATA).write_text(json.dumps(metadata, indent=2))
    sittings = sum(1 for g in groups if g["kind"] == "sitting")
    print(f"prepared {sittings} sittings and {len(groups) - sittings} negative "
          f"source(s) into {work_dir}")
    print("material identifies a person: delete the work directory once the "
          "comparison has run")
    return 0


def _store_group(arrays: dict, group_index: int, clips, durations, embed) -> None:
    embeddings = np.stack([sg._unit(embed(clip)) for clip in clips])
    arrays[f"g{group_index}_torch"] = embeddings
    arrays[f"g{group_index}_dur"] = np.asarray(durations, dtype=np.float64)
    for clip_index, clip in enumerate(clips):
        arrays[f"g{group_index}_clip{clip_index}"] = np.asarray(clip, dtype=np.float32)


# ---------------------------------------------------------------------------
# derivation shared by compare and the self-test
# ---------------------------------------------------------------------------


def derive_chain(sittings: list[tuple[list, list]], negatives: list[list]) -> dict:
    """One encoder's full gating derivation, via speaker_gate's own math."""
    operator_embeddings = [e for emb, _dur in sittings for e in emb]
    operator_durations = [d for _emb, dur in sittings for d in dur]
    profile = sg.enroll(operator_embeddings, operator_durations)
    own = sg.leave_one_sitting_out_scores(sittings)
    other = [sg.score(profile, e) for group in negatives for e in group]
    return {"profile": profile, "own": own, "other": other}


def agreement_report(
    reference: dict,
    candidate: dict,
    negative_seconds: float,
) -> dict:
    """Registered points from the reference chain; decisions compared under both."""
    registered = sg.operating_point_choices(
        reference["own"], reference["other"], negative_scorable_seconds=negative_seconds
    )
    try:
        candidate_points = sg.operating_point_choices(
            candidate["own"], candidate["other"], negative_scorable_seconds=negative_seconds
        )
    except ValueError as exc:
        candidate_points = []
        candidate_refusal = str(exc)
    else:
        candidate_refusal = None

    ref_scores = np.asarray(reference["own"] + reference["other"], dtype=np.float64)
    cand_scores = np.asarray(candidate["own"] + candidate["other"], dtype=np.float64)
    assert ref_scores.shape == cand_scores.shape, "score lists must align one-to-one"
    score_delta_max = float(np.max(np.abs(ref_scores - cand_scores)))

    points = []
    total_flips = 0
    for point in registered:
        threshold = point["threshold"]
        ref_admit = ref_scores >= threshold
        cand_admit = cand_scores >= threshold
        flipped = ref_admit != cand_admit
        # `calibrate` takes the threshold as an observed order statistic, so at
        # least one reference score EQUALS it and has zero margin by
        # construction. Any nonzero drift can flip that one decision; that is
        # quantile-on-sample discreteness, not front-end damage. The report
        # separates it so a boundary flip cannot masquerade as a comfortable
        # decision changing — and so it is never silently ignored either.
        boundary = ref_scores == threshold
        off_boundary = ~boundary
        flips = int(np.sum(flipped))
        total_flips += flips
        points.append({
            "target_frr": point["target_frr"],
            "threshold": threshold,
            "measured_frr": point["measured_frr"],
            "false_admit_rate": point["false_admit_rate"],
            "decisions": int(ref_scores.size),
            "flips": flips,
            "boundary_decisions": int(np.sum(boundary)),
            "flips_at_boundary": int(np.sum(flipped & boundary)),
            "flips_off_boundary": int(np.sum(flipped & off_boundary)),
            "min_margin_reference": float(
                np.min(np.abs(ref_scores[off_boundary] - threshold))
            ),
            "min_margin_candidate": float(
                np.min(np.abs(cand_scores[off_boundary] - threshold))
            ),
        })

    threshold_deltas = []
    for point in registered:
        match = [
            c for c in candidate_points
            if np.isclose(c["target_frr"], point["target_frr"], rtol=0.0, atol=1e-12)
        ]
        if match:
            threshold_deltas.append({
                "target_frr": point["target_frr"],
                "threshold_delta": float(match[0]["threshold"] - point["threshold"]),
            })

    return {
        "contract": AGREEMENT_CONTRACT_VERSION,
        "targets_version": sg.OPERATING_POINT_TARGET_SET_VERSION,
        "held_out": "leave-one-sitting-out",
        "operator_scores": len(reference["own"]),
        "negative_scores": len(reference["other"]),
        "negative_scorable_seconds": round(float(negative_seconds), 3),
        "registered_points": points,
        "total_flips": total_flips,
        "score_delta_max": score_delta_max,
        "candidate_points_refusal": candidate_refusal,
        "candidate_threshold_deltas": threshold_deltas,
        "threshold_delta_max": (
            max((abs(d["threshold_delta"]) for d in threshold_deltas), default=None)
        ),
    }


# ---------------------------------------------------------------------------
# compare (torch-free deployable arm)
# ---------------------------------------------------------------------------


def run_compare(args) -> int:
    assert "torch" not in sys.modules, (
        "the compare arm must run torch-free; parity of the deployable chain "
        "is the thing under test"
    )
    work_dir = Path(args.work_dir)
    metadata = json.loads((work_dir / WORK_METADATA).read_text())
    if metadata.get("contract") != AGREEMENT_CONTRACT_VERSION:
        raise SystemExit(f"{work_dir} does not hold {AGREEMENT_CONTRACT_VERSION} material")
    arrays = np.load(work_dir / WORK_ARRAYS)

    model_path = Path(args.onnx)
    onnx_sha256 = sha256_file(model_path)
    if onnx_sha256 != EXPECTED_ONNX_SHA256 and not args.allow_unregistered_model:
        raise SystemExit(
            f"{model_path} has digest {onnx_sha256}, not the registered export "
            f"{EXPECTED_ONNX_SHA256}. The admission measurement is about the "
            "registered artifact; pass --allow-unregistered-model only for a "
            "research run, which the receipt will say."
        )

    from worker.fbank import fbank_features

    import onnxruntime as ort

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    lengths = np.ones(1, dtype=np.float32)

    def embed(clip: np.ndarray) -> np.ndarray:
        features = fbank_features(clip)
        return np.squeeze(
            session.run(None, {"features": features[None, ...], "lengths": lengths})[0]
        )

    reference_sittings: list[tuple[list, list]] = []
    candidate_sittings: list[tuple[list, list]] = []
    reference_negatives: list[list] = []
    candidate_negatives: list[list] = []
    negative_seconds = 0.0
    for group_index, group in enumerate(metadata["groups"]):
        torch_embeddings = list(arrays[f"g{group_index}_torch"])
        durations = list(arrays[f"g{group_index}_dur"])
        onnx_embeddings = [
            sg._unit(embed(arrays[f"g{group_index}_clip{clip_index}"]))
            for clip_index in range(group["clips"])
        ]
        if group["kind"] == "sitting":
            reference_sittings.append((torch_embeddings, durations))
            candidate_sittings.append((onnx_embeddings, durations))
        else:
            reference_negatives.append(torch_embeddings)
            candidate_negatives.append(onnx_embeddings)
            negative_seconds += group["provenance"]["scorable_seconds"]

    reference = derive_chain(reference_sittings, reference_negatives)
    candidate = derive_chain(candidate_sittings, candidate_negatives)
    report = agreement_report(reference, candidate, negative_seconds)
    report.update({
        "torch_encoder_fingerprint": metadata["torch_encoder_fingerprint"],
        "onnx_sha256": onnx_sha256,
        "onnx_is_registered_export": onnx_sha256 == EXPECTED_ONNX_SHA256,
        "sittings": len(reference_sittings),
        "prepared_at": metadata["prepared_at"],
    })

    print(json.dumps(report, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
    return 0


# ---------------------------------------------------------------------------
# self-test: the two-sided instrument control
# ---------------------------------------------------------------------------


def _fabricated_material(seed: int):
    """Speaker-clustered unit embeddings with sitting structure — no audio,
    because this controls the *instrument* (derivation, registration,
    classification comparison), whose inputs are embeddings. The audio-to-
    embedding halves have their own harnesses (bench_fbank_parity, prep_features)."""
    rng = np.random.default_rng(seed)

    def voice(base: np.ndarray, jitter: float, count: int) -> list[np.ndarray]:
        return [
            sg._unit(base + jitter * rng.standard_normal(base.shape))
            for _ in range(count)
        ]

    operator = rng.standard_normal(192)
    sittings = [
        (voice(operator, 0.35, 12), [3.0] * 12),
        (voice(operator, 0.40, 12), [3.0] * 12),
    ]
    negatives = [
        voice(rng.standard_normal(192), 0.35, 12),
        voice(rng.standard_normal(192), 0.35, 12),
    ]
    negative_seconds = 3.0 * 24
    return sittings, negatives, negative_seconds


def _perturbed(sittings, negatives, weight: float, seed: int):
    rng = np.random.default_rng(seed)
    direction = sg._unit(rng.standard_normal(192))

    def shift(embedding: np.ndarray) -> np.ndarray:
        return sg._unit(np.asarray(embedding) + weight * direction)

    return (
        [([shift(e) for e in emb], dur) for emb, dur in sittings],
        [[shift(e) for e in group] for group in negatives],
    )


def run_self_test() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool) -> None:
        print(f"  {'ok' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(name)

    from worker.fbank import fbank_features

    clip = np.sin(np.linspace(0, 2400 * np.pi, 3 * sg.RATE)).astype(np.float32)
    features = fbank_features(clip)
    check("fbank front end produces (frames, 80) float32 for a 3 s clip",
          features.ndim == 2 and features.shape[1] == 80 and features.dtype == np.float32)

    sittings, negatives, seconds = _fabricated_material(seed=20260803)
    chain = derive_chain(sittings, negatives)
    report = agreement_report(chain, chain, seconds)
    check("identical chains register at least two operating points",
          len(report["registered_points"]) >= 2)
    check("identical chains report zero flips", report["total_flips"] == 0)
    check("identical chains report zero score delta", report["score_delta_max"] == 0.0)
    margins = [p["min_margin_reference"] for p in report["registered_points"]]
    check("off-boundary margins are nonzero, so zero flips is a measurement "
          "rather than a degenerate tie", all(m > 0 for m in margins))
    check("each point names its threshold-defining boundary sample",
          all(p["boundary_decisions"] >= 1 for p in report["registered_points"]))

    detected_at = None
    for weight in (0.05, 0.1, 0.2, 0.4, 0.8):
        perturbed_sittings, perturbed_negatives = _perturbed(
            sittings, negatives, weight, seed=7
        )
        perturbed_chain = derive_chain(perturbed_sittings, perturbed_negatives)
        perturbed_report = agreement_report(chain, perturbed_chain, seconds)
        if perturbed_report["total_flips"] > 0:
            detected_at = weight
            break
    check("a bounded perturbation is detected as flips (the instrument can see "
          "disagreement)", detected_at is not None)
    if detected_at is not None:
        check("threshold deltas move under the detected perturbation",
              (perturbed_report["threshold_delta_max"] or 0) > 0
              or perturbed_report["candidate_points_refusal"] is not None)

    single = [sittings[0]]
    try:
        derive_chain(single, negatives)
        check("one sitting is refused by the held-out derivation", False)
    except ValueError:
        check("one sitting is refused by the held-out derivation", True)

    check("work directories inside the repository are refused",
          ab.inside_repo(Path(__file__)))
    outside = Path(tempfile.gettempdir())
    check("a temp directory outside the repository is accepted",
          not ab.inside_repo(outside))

    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        first = base / "first.wav"
        second = base / "second.wav"
        copy = base / "copy.wav"
        first.write_bytes(b"take-one")
        second.write_bytes(b"take-two")
        copy.write_bytes(b"take-one")
        check("distinct recordings in distinct roles are accepted",
              duplicate_audio_problem([first], [second]) is None)
        check("a sitting repeated as negative material is refused (operator "
              "voice must not price the impostor pool)",
              "cannot also price" in (duplicate_audio_problem([first], [copy]) or ""))
        check("a negative recording passed twice is refused (floors cannot be "
              "cleared by duplication)",
              "count twice" in (duplicate_audio_problem([second], [first, copy]) or ""))
        check("a sitting passed twice is refused",
              "count twice" in (duplicate_audio_problem([first, copy], []) or ""))

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--self-test", action="store_true",
                        help="run the two-sided instrument controls (torch-free)")
    sub = parser.add_subparsers(dest="command")

    prepare = sub.add_parser("prepare", help="embed calibration material with the "
                                             "torch reference encoder")
    prepare.add_argument("--calibrate", nargs=2, metavar=("SEGMENTS.json", "AUDIO.wav"),
                         action="append", required=True,
                         help="operator speech, one per sitting; at least two")
    prepare.add_argument("--against", nargs=3,
                         metavar=("SOURCE_CLASS", "SEGMENTS.json", "AUDIO.wav"),
                         action="append", required=True,
                         help="speech known not to be the operator; SOURCE_CLASS is "
                              "public-or-licensed or consenting-person")
    prepare.add_argument("--model-dir", type=Path,
                         default=Path.home() / ".cache" / "speaker-gate")
    prepare.add_argument("--work-dir", required=True,
                         help="owner-only directory OUTSIDE the repository; holds "
                              "biometric material, delete after the comparison")

    compare = sub.add_parser("compare", help="re-embed through worker/fbank.py + ONNX "
                                             "and compare classifications (torch-free)")
    compare.add_argument("--work-dir", required=True)
    compare.add_argument("--onnx", required=True,
                         help="the registered ecapa-tdnn.onnx export")
    compare.add_argument("--json-out", default=None)
    compare.add_argument("--allow-unregistered-model", action="store_true",
                         help="run against a non-registered model as research; the "
                              "receipt records the digest mismatch")

    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.command == "prepare":
        return run_prepare(args)
    if args.command == "compare":
        return run_compare(args)
    parser.error("nothing to do: pass --self-test, prepare, or compare")
    return 2


if __name__ == "__main__":
    sys.exit(main())
