"""Select and register the LibriSpeech public-audio parity fixtures.

This script IS the registration rule, kept executable so the selection can be
re-derived from the public archive instead of trusted from prose. It reads an
extracted `dev-clean.tar.gz` (LibriSpeech, openslr.org/12, CC BY 4.0), applies
the deterministic rule below, copies the chosen flac files byte-unmodified
into the fixtures directory, and writes `manifest.json` with one sha256 per
file plus the archive digests the run was derived from.

Selection rule (deterministic, no hand-picking):
  1. Parse `SPEAKERS.TXT`; keep rows whose subset is exactly `dev-clean`.
  2. Split by the corpus's recorded sex field; sort each group by numeric
     speaker ID ascending; take the 6 lowest-ID F and 6 lowest-ID M speakers.
  3. For each speaker, walk that speaker's flac files in lexicographic path
     order and take the FIRST whose duration is >= 3.0 s at 16 kHz.
  4. Copy the file unmodified; the fixture digest equals the archive member's.

Twelve clips, twelve distinct speakers, both recorded sexes — mirroring the
twelve synthetic fixtures in `fixtures.py`. No private recording is involved
anywhere; every byte comes from the public CC BY 4.0 archive.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import soundfile

SAMPLE_RATE = 16_000
MIN_SECONDS = 3.0
PER_GROUP = 6


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dev_clean_speakers(speakers_txt: Path) -> list[tuple[int, str]]:
    rows = []
    for line in speakers_txt.read_text().splitlines():
        if line.startswith(";"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3 and parts[2] == "dev-clean":
            rows.append((int(parts[0]), parts[1]))
    return rows


def first_long_enough(speaker_dir: Path) -> tuple[Path, float]:
    for flac in sorted(speaker_dir.rglob("*.flac")):
        info = soundfile.info(str(flac))
        if info.samplerate != SAMPLE_RATE:
            raise SystemExit(f"unexpected sample rate {info.samplerate} in {flac}")
        duration = info.frames / info.samplerate
        if duration >= MIN_SECONDS:
            return flac, duration
    raise SystemExit(f"no clip >= {MIN_SECONDS}s for {speaker_dir}")


def main() -> None:
    librispeech_root = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    archive_sha256 = sys.argv[3]
    archive_md5 = sys.argv[4]
    out_dir.mkdir(parents=True, exist_ok=True)

    speakers = dev_clean_speakers(librispeech_root / "SPEAKERS.TXT")
    chosen: list[tuple[int, str]] = []
    for sex in ("F", "M"):
        group = sorted(row for row in speakers if row[1] == sex)[:PER_GROUP]
        if len(group) != PER_GROUP:
            raise SystemExit(f"expected {PER_GROUP} dev-clean speakers of sex {sex}")
        chosen.extend(group)

    entries = []
    for speaker_id, sex in chosen:
        speaker_dir = librispeech_root / "dev-clean" / str(speaker_id)
        flac, duration = first_long_enough(speaker_dir)
        target = out_dir / flac.name
        shutil.copyfile(flac, target)
        entries.append(
            {
                "file": flac.name,
                "speaker_id": speaker_id,
                "recorded_sex": sex,
                "seconds": round(duration, 3),
                "sha256": sha256_file(target),
            }
        )

    manifest = {
        "schema": "librispeech-parity-fixtures/1",
        "source": "LibriSpeech dev-clean (openslr.org/12), CC BY 4.0",
        "attribution": (
            'Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, '
            '"LibriSpeech: an ASR corpus based on public domain audio books", ICASSP 2015'
        ),
        "archive": {
            "url": "https://www.openslr.org/resources/12/dev-clean.tar.gz",
            "sha256": archive_sha256,
            "md5": archive_md5,
        },
        "selection_rule": (
            "6 lowest-ID F + 6 lowest-ID M dev-clean speakers from SPEAKERS.TXT; per "
            "speaker, the lexicographically first flac with duration >= 3.0 s at 16 kHz; "
            "files copied byte-unmodified"
        ),
        "fixtures": entries,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"registered {len(entries)} fixtures -> {manifest_path}")


if __name__ == "__main__":
    main()
