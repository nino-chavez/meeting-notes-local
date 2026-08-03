"""Select and register the LibriSpeech public-audio parity fixtures.

This script IS the registration rule, kept executable so the selection can be
re-derived from the public archive instead of trusted from prose. It takes the
`dev-clean.tar.gz` archive itself (LibriSpeech, openslr.org/12, CC BY 4.0),
computes the archive digests it registers — never accepting them as caller
assertions — reads the speaker table and every fixture byte directly out of
that same archive, applies the deterministic rule below, and writes the chosen
flac files byte-unmodified plus `manifest.json`. The archive digest in the
manifest is therefore derived from the exact bytes the fixtures came out of;
there is no seam where a wrong or stale digest could decorate a clean-looking
manifest with fictional provenance.

Selection rule (deterministic, no hand-picking):
  1. Parse `SPEAKERS.TXT` from the archive; keep rows whose subset is exactly
     `dev-clean`.
  2. Split by the corpus's recorded sex field; sort each group by numeric
     speaker ID ascending; take the 6 lowest-ID F and 6 lowest-ID M speakers.
  3. For each speaker, walk that speaker's flac members in lexicographic path
     order and take the FIRST whose duration is >= 3.0 s at 16 kHz.
  4. Write the member bytes unmodified; the fixture digest equals the archive
     member's.

Twelve clips, twelve distinct speakers, both recorded sexes — mirroring the
twelve synthetic fixtures in `fixtures.py`. No private recording is involved
anywhere; every byte comes from the public CC BY 4.0 archive.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import soundfile

SAMPLE_RATE = 16_000
MIN_SECONDS = 3.0
PER_GROUP = 6
ARCHIVE_URL = "https://www.openslr.org/resources/12/dev-clean.tar.gz"


def archive_digests(archive: Path) -> tuple[str, str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return sha256.hexdigest(), md5.hexdigest()


def dev_clean_speakers(speakers_txt: str) -> list[tuple[int, str]]:
    rows = []
    for line in speakers_txt.splitlines():
        if line.startswith(";"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3 and parts[2] == "dev-clean":
            rows.append((int(parts[0]), parts[1]))
    return rows


def collect_from_archive(
    archive: Path,
) -> tuple[str, dict[int, dict[str, bytes]]]:
    """One sequential pass: the speaker table plus every dev-clean flac's bytes,
    grouped by speaker. Member order in the tar is not trusted for anything;
    selection happens afterwards over the collected names."""
    speakers_txt = None
    flacs: dict[int, dict[str, bytes]] = {}
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = member.name
            if name.endswith("SPEAKERS.TXT"):
                speakers_txt = tar.extractfile(member).read().decode()
            elif "/dev-clean/" in name and name.endswith(".flac"):
                speaker_id = int(name.split("/dev-clean/")[1].split("/")[0])
                flacs.setdefault(speaker_id, {})[Path(name).name] = tar.extractfile(
                    member
                ).read()
    if speakers_txt is None:
        raise SystemExit("SPEAKERS.TXT not found in the archive")
    return speakers_txt, flacs


def first_long_enough(candidates: dict[str, bytes]) -> tuple[str, bytes, float]:
    for name in sorted(candidates):
        data = candidates[name]
        info = soundfile.info(io.BytesIO(data))
        if info.samplerate != SAMPLE_RATE:
            raise SystemExit(f"unexpected sample rate {info.samplerate} in {name}")
        duration = info.frames / info.samplerate
        if duration >= MIN_SECONDS:
            return name, data, duration
    raise SystemExit(f"no clip >= {MIN_SECONDS}s among {len(candidates)} candidates")


def main() -> None:
    archive, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    archive_sha256, archive_md5 = archive_digests(archive)
    speakers_txt, flacs = collect_from_archive(archive)

    speakers = dev_clean_speakers(speakers_txt)
    chosen: list[tuple[int, str]] = []
    for sex in ("F", "M"):
        group = sorted(row for row in speakers if row[1] == sex)[:PER_GROUP]
        if len(group) != PER_GROUP:
            raise SystemExit(f"expected {PER_GROUP} dev-clean speakers of sex {sex}")
        chosen.extend(group)

    entries = []
    for speaker_id, sex in chosen:
        if speaker_id not in flacs:
            raise SystemExit(f"no dev-clean audio members for speaker {speaker_id}")
        name, data, duration = first_long_enough(flacs[speaker_id])
        (out_dir / name).write_bytes(data)
        entries.append(
            {
                "file": name,
                "speaker_id": speaker_id,
                "recorded_sex": sex,
                "seconds": round(duration, 3),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    manifest = {
        "schema": "librispeech-parity-fixtures/1",
        "source": "LibriSpeech dev-clean (openslr.org/12), CC BY 4.0",
        "attribution": (
            "Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, "
            '"LibriSpeech: an ASR corpus based on public domain audio books", ICASSP 2015'
        ),
        "archive": {
            "url": ARCHIVE_URL,
            "sha256": archive_sha256,
            "md5": archive_md5,
        },
        "selection_rule": (
            "6 lowest-ID F + 6 lowest-ID M dev-clean speakers from SPEAKERS.TXT; per "
            "speaker, the lexicographically first flac with duration >= 3.0 s at 16 kHz; "
            "member bytes written unmodified from the digested archive"
        ),
        "fixtures": entries,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"registered {len(entries)} fixtures from {archive.name} -> {manifest_path}")


if __name__ == "__main__":
    main()
