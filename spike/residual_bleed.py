#!/usr/bin/env python3
"""Measure a conservative residual-bleed transcript repair offline.

This harness never changes a capture or a canonical transcript. It rebuilds the
current voicing + acoustic-bleed baseline from retained per-leg ASR, applies one
text-and-time duplicate candidate, and writes aggregate evidence only.

The candidate is intentionally not admitted to production. Two speakers saying
the same longer phrase at once are indistinguishable from an echoed copy at this
layer, and the project does not retain a real double-talk control yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import wave
from pathlib import Path

import numpy as np

from dual_capture import bleed, contaminated, drop_bled, drop_unvoiced

SCHEMA = "residual-bleed-measurement/1"
TIME_PAD_S = 1.0
MIN_MATCHED_WORDS = 4
MIN_ORDERED_COVERAGE = 0.75
WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def ordered_overlap(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for left_word in left:
        current = [0] * (len(right) + 1)
        for index, right_word in enumerate(right):
            current[index + 1] = (
                previous[index] + 1
                if left_word == right_word
                else max(previous[index + 1], current[index])
            )
        previous = current
    return previous[-1]


def collapse_candidate(
    mic_segments: list[dict], system_segments: list[dict], acoustic: dict | None
) -> tuple[list[dict], list[dict]]:
    """Return kept and removed mic turns without mutating either input."""
    if not mic_segments or not system_segments or not contaminated(acoustic):
        return list(mic_segments), []

    kept, removed = [], []
    for mic in mic_segments:
        mic_words = words(mic["text"])
        nearby_text = " ".join(
            segment["text"]
            for segment in system_segments
            if segment["end"] >= mic["start"] - TIME_PAD_S
            and segment["start"] <= mic["end"] + TIME_PAD_S
        )
        matched = ordered_overlap(mic_words, words(nearby_text))
        coverage = matched / len(mic_words) if mic_words else 0.0
        if matched >= MIN_MATCHED_WORDS and coverage >= MIN_ORDERED_COVERAGE:
            removed.append(mic)
        else:
            kept.append(mic)
    return kept, removed


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, reference_word in enumerate(reference, start=1):
        current = [row] + [0] * len(hypothesis)
        for column, hypothesis_word in enumerate(hypothesis, start=1):
            current[column] = (
                previous[column - 1]
                if reference_word == hypothesis_word
                else min(
                    previous[column - 1], previous[column], current[column - 1]
                )
                + 1
            )
        previous = current
    return previous[-1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getnchannels() != 1
            or audio.getsampwidth() != 2
            or audio.getframerate() != 16_000
        ):
            raise ValueError(f"{path} is not mono 16 kHz 16-bit PCM")
        return np.frombuffer(
            audio.readframes(audio.getnframes()), dtype="<i2"
        ).astype(np.float32) / 32768.0


def transcript_segments(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    segments = document.get("turns")
    if not isinstance(segments, list):
        raise ValueError(f"{path} has no transcript turns")
    for segment in segments:
        if not all(field in segment for field in ("start", "end", "text")):
            raise ValueError(
                f"{path} needs per-leg ASR with start and end timestamps; "
                "regenerate it with notes/transcribe_file.py"
            )
    return segments


def merged_words(mic_segments: list[dict], system_segments: list[dict]) -> list[str]:
    merged = [
        (segment["start"], segment["end"], label, segment["text"])
        for segments, label in ((mic_segments, "mic"), (system_segments, "system"))
        for segment in segments
    ]
    merged.sort(key=lambda turn: (turn[0], turn[1], turn[2]))
    return words(" ".join(turn[3] for turn in merged))


def self_test() -> dict:
    dirty = {"positive_r": 0.9}
    system = [{"start": 5.0, "end": 7.0, "text": "we should ship this on Tuesday"}]
    cases = {
        "long_same_phrase": {
            "segment": {"start": 5.1, "end": 6.9, "text": "we should ship this on Tuesday"},
            "removed": True,
        },
        "unrelated_double_talk": {
            "segment": {"start": 5.1, "end": 6.9, "text": "the budget needs another review"},
            "removed": False,
        },
        "short_confirmation": {
            "segment": {"start": 5.1, "end": 5.8, "text": "yes we agree"},
            "removed": False,
        },
        "same_phrase_outside_window": {
            "segment": {"start": 20.0, "end": 22.0, "text": "we should ship this on Tuesday"},
            "removed": False,
        },
    }
    outcomes = {}
    for name, case in cases.items():
        kept, removed = collapse_candidate([case["segment"]], system, dirty)
        observed = bool(removed) and not kept
        outcomes[name] = observed == case["removed"]
    clean_kept, clean_removed = collapse_candidate(
        [cases["long_same_phrase"]["segment"]], system, {"positive_r": 0.1}
    )
    outcomes["clean_capture_unchanged"] = bool(clean_kept) and not clean_removed
    if not all(outcomes.values()):
        raise AssertionError(outcomes)
    return outcomes


def measure(args: argparse.Namespace) -> dict:
    mic_audio = read_wav(args.mic_wav)
    system_audio = read_wav(args.system_wav)
    acoustic = bleed(mic_audio, system_audio)

    raw_mic = transcript_segments(args.mic_transcript)
    raw_system = transcript_segments(args.system_transcript)
    voiced_mic = drop_unvoiced(raw_mic, mic_audio, "mic")
    voiced_system = drop_unvoiced(raw_system, system_audio, "system")
    baseline_mic = drop_bled(voiced_mic, mic_audio, system_audio, acoustic, "mic")
    candidate_mic, removed = collapse_candidate(
        baseline_mic, voiced_system, acoustic
    )

    reference = words(args.reference.read_text(encoding="utf-8"))
    baseline = merged_words(baseline_mic, voiced_system)
    candidate = merged_words(candidate_mic, voiced_system)
    baseline_edits = edit_distance(reference, baseline)
    candidate_edits = edit_distance(reference, candidate)
    controls = self_test()

    canonical = None
    if args.canonical_transcript is not None:
        canonical_document = json.loads(
            args.canonical_transcript.read_text(encoding="utf-8")
        )
        canonical_words = words(
            " ".join(turn["text"] for turn in canonical_document["turns"])
        )
        canonical_edits = edit_distance(reference, canonical_words)
        canonical = {
            "turns": len(canonical_document["turns"]),
            "words": len(canonical_words),
            "edits": canonical_edits,
            "wer": canonical_edits / len(reference),
        }

    result = {
        "schema": SCHEMA,
        "sources": {
            "mic_wav_sha256": sha256(args.mic_wav),
            "system_wav_sha256": sha256(args.system_wav),
            "mic_transcript_sha256": sha256(args.mic_transcript),
            "system_transcript_sha256": sha256(args.system_transcript),
            "reference_sha256": sha256(args.reference),
            **(
                {"canonical_transcript_sha256": sha256(args.canonical_transcript)}
                if args.canonical_transcript is not None
                else {}
            ),
        },
        "bleed": {
            key: acoustic[key]
            for key in ("peak_r", "positive_r", "positive_lag_ms", "analysed_s")
        },
        "candidate": {
            "strategy": "time-aligned-ordered-words/1",
            "time_pad_s": TIME_PAD_S,
            "min_matched_words": MIN_MATCHED_WORDS,
            "min_ordered_coverage": MIN_ORDERED_COVERAGE,
            "removed_segments": len(removed),
            "removed_seconds": round(
                sum(segment["end"] - segment["start"] for segment in removed), 2
            ),
            "removed_words": sum(len(words(segment["text"])) for segment in removed),
        },
        "comparison": {
            "reference_words": len(reference),
            **({"canonical": canonical} if canonical is not None else {}),
            "baseline": {
                "turns": len(baseline_mic) + len(voiced_system),
                "words": len(baseline),
                "edits": baseline_edits,
                "wer": baseline_edits / len(reference),
            },
            "candidate": {
                "turns": len(candidate_mic) + len(voiced_system),
                "words": len(candidate),
                "edits": candidate_edits,
                "wer": candidate_edits / len(reference),
            },
        },
        "safety_controls": controls,
        "production_admitted": False,
        "blockers": [
            "no retained real double-talk control",
            "a longer same-phrase overlap is indistinguishable from bleed and is removed",
            "candidate transcript error remains above the note-generation input bar",
        ],
    }
    if canonical is not None and canonical["turns"] != result["comparison"]["baseline"]["turns"]:
        result["blockers"].append(
            "the same local ASR model did not reproduce the canonical segment count"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mic-wav", type=Path)
    parser.add_argument("--system-wav", type=Path)
    parser.add_argument("--mic-transcript", type=Path)
    parser.add_argument("--system-transcript", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--canonical-transcript", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return 0
    required = (
        "mic_wav",
        "system_wav",
        "mic_transcript",
        "system_transcript",
        "reference",
        "out",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing " + ", ".join(f"--{name.replace('_', '-')}" for name in missing))

    result = measure(args)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["comparison"], indent=2))
    print(f"wrote aggregate receipt {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
