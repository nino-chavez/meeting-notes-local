#!/usr/bin/env python3
"""Transcribe a recorded audio file into the pipeline's transcript format.

The live capture in `spike/` answers "can this record a meeting". This answers a
different and, for evaluation, more useful question: given a recording someone
already has, what does *our* half of the pipeline produce from it?

That matters because every measurement in `notes/EVAL.md` so far was made by
feeding our summarizer somebody else's transcript — QMSum's human-corrected text
or Google's ASR. The notes half has been graded; the listening half never has.
Any claim about being as good as a hosted notetaker is unfounded until the same
audio goes through both chains.

A recording mixed down to one channel carries no speaker information at all, so
the output is written at attribution level `none`. That is not a limitation being
worked around — it is the honest level for the input, and it is the same contract
a bleed-contaminated capture gets. See notes/transcript.py.

Usage:
    python notes/transcribe_file.py meeting.wav --out transcript.json
    python notes/transcribe_file.py meeting.m4a --out transcript.json   # needs ffmpeg
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

RATE = 16_000
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def load_audio(path: Path):
    """16 kHz mono float32, decoding through ffmpeg for anything but plain WAV."""
    import numpy as np

    if path.suffix.lower() == ".wav":
        with wave.open(str(path)) as w:
            if w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2:
                raw = w.readframes(w.getnframes())
                return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

    if not shutil_which("ffmpeg"):
        raise SystemExit(
            f"{path} is not already 16 kHz mono 16-bit WAV and ffmpeg is not installed.\n"
            "Install ffmpeg, or convert it yourself:\n"
            f"  ffmpeg -i {path} -vn -ac 1 -ar {RATE} -c:a pcm_s16le out.wav"
        )
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        capture_output=True, check=False,
    )
    if proc.returncode:
        raise SystemExit(f"ffmpeg could not decode {path}:\n{proc.stderr.decode()[:500]}")
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


def shutil_which(name: str):
    import shutil

    return shutil.which(name)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", type=Path)
    p.add_argument("--out", type=Path, required=True, help="transcript JSON to write")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--language", default="en")
    args = p.parse_args()

    if not args.audio.exists():
        raise SystemExit(f"{args.audio} not found")

    import mlx_whisper

    audio = load_audio(args.audio)
    minutes = len(audio) / RATE / 60
    print(f"  {args.audio.name}: {minutes:.1f} min at {RATE} Hz mono")
    print(f"  transcribing with {args.model} — expect roughly {minutes / 3:.0f} min")

    t0 = time.monotonic()
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=args.model, language=args.language,
        # The capture spike sets this too: carrying decoded text forward as
        # context lets one bad segment poison the rest of a long recording.
        condition_on_previous_text=False,
    )
    elapsed = time.monotonic() - t0

    turns = [
        {"start": round(s["start"], 2), "speaker": None, "text": s["text"].strip()}
        for s in result.get("segments", [])
        if s.get("text", "").strip()
    ]
    args.out.write_text(json.dumps({
        "source": f"recording:{args.audio.stem}",
        # One mixed channel. Who spoke is not in this signal.
        "attribution": "none",
        "turns": turns,
    }, indent=2))

    words = sum(len(t["text"].split()) for t in turns)
    print(f"\n  {len(turns)} segments, {words} words in {elapsed / 60:.1f} min "
          f"({minutes / (elapsed / 60):.1f}x realtime)")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
