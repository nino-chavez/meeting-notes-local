#!/usr/bin/env python3
"""Fetch the meeting transcripts the summarizer is evaluated against.

The corpus is downloaded rather than vendored: it is someone else's data under
someone else's licence, and this repository is public.

QMSum (Zhong et al., NAACL 2021, https://github.com/Yale-LILY/QMSum) repackages
three sources with human-written summaries attached:

  ES2004c   AMI — a product design team, four roles, mid-project. The closest
            public analogue to the meetings this tool is built for: a working
            session with real decisions and real drift.
  Bmr006    ICSI — an academic research group. Longer, looser, more speakers,
            far less structure. The case where "what was decided" may honestly
            be "nothing".
  covid_4   A parliamentary committee hearing. Formal register, long turns,
            many participants — the opposite failure mode from ICSI.

Three meetings is not a benchmark and this file does not pretend otherwise; see
notes/EVAL.md for what the numbers can and cannot support.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/Yale-LILY/QMSum/main/data/ALL/test"
MEETINGS = ["ES2004c", "Bmr006", "covid_4"]
DEST = Path(__file__).resolve().parent / "corpus"


def main() -> int:
    DEST.mkdir(exist_ok=True)
    failed = []
    for name in MEETINGS:
        target = DEST / f"{name}.json"
        if target.exists():
            print(f"  have  {target.relative_to(DEST.parent.parent)}")
            continue
        try:
            with urllib.request.urlopen(f"{BASE}/{name}.json", timeout=60) as r:
                target.write_bytes(r.read())
            print(f"  got   {target.relative_to(DEST.parent.parent)}  "
                  f"({target.stat().st_size // 1024} KB)")
        except (urllib.error.URLError, OSError) as e:
            failed.append((name, e))
            print(f"  FAIL  {name}: {e}")

    if failed:
        print("\nQMSum moved or is unreachable. The summarizer needs no specific\n"
              "corpus — any transcript in its JSON shape works. See notes/transcript.py.")
        return 1

    print(f"\n  corpus in {DEST}/ (gitignored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
