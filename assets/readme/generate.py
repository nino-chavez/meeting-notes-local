#!/usr/bin/env python3
"""Emit README SVGs for local-meeting-notes from real captured envelopes.

    .venv/bin/python assets/readme/generate.py                    # deterministic
    .venv/bin/python assets/readme/generate.py --from-capture DIR # re-measure

The level tracks in the hero and the bleed board are real measured envelopes, not
drawn decoration.

**The envelopes are pinned to a file, not re-measured on every run**, and that is
a correctness rule rather than a convenience. This script used to read
`spike/out/{mic,system}.wav` — a mutable scratch directory holding whatever
capture ran last. Editing the pipeline diagram therefore silently rewrote the
hero's level tracks from an unrelated recording, and the README's alt text still
claimed the duration of the old one. Caught with a 19.8 s capture sitting where a
14 s one had been published from: the art changes, nothing fails, and the caption
becomes false.

So the 68 measured values live in `envelopes.json` with the duration and digest of
the audio they came from. A plain run reproduces the committed SVGs byte for byte.
Re-measuring is an explicit act that rewrites the pin, and it prints the duration
so the README's caption can be corrected in the same change.

Palette and shape come from the repo's own DESIGN.md; the accent (#FFB020) is
reserved for the live-capture indicator and appears nowhere else, per
DIRECTION.md. Radius stays at 6 because DESIGN.md forbids anything larger — the
world is an instrument panel, not a soft card.
"""
import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "assets" / "readme"
OUT.mkdir(parents=True, exist_ok=True)
PIN = OUT / "envelopes.json"

BG = "#0E1014"
RAISED = "#191C21"
LINE = "#24282F"
RULE = "#444A54"
FG = "#F5F6F7"
BODY = "#A2A7B0"
MUTED = "#7C828D"
DIM = "#5C626D"
ACCENT = "#FFB020"   # LIVE only
ERROR = "#C4553D"

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"

N = 68


def envelope(path, n=N):
    """`n` normalised RMS values over one recording, and its provenance."""
    with wave.open(str(path)) as w:
        rate, frames = w.getframerate(), w.getnframes()
        a = np.frombuffer(w.readframes(frames), dtype="<i2").astype(np.float64) / 32768
    k = len(a) // n
    e = np.sqrt((a[: k * n].reshape(n, k) ** 2).mean(axis=1))
    return (e / (e.max() or 1)), {
        "seconds": round(frames / rate, 1),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
    }


def measure(take: Path) -> dict:
    """Re-measure both legs of a capture and return a new pin."""
    legs, prov = {}, {}
    for leg in ("mic", "system"):
        wav = take / f"{leg}.wav"
        if not wav.exists():
            raise SystemExit(f"{wav} does not exist — --from-capture needs both legs")
        values, meta = envelope(wav)
        legs[leg] = [round(float(v), 5) for v in values]
        prov[leg] = meta
    return {"n": N, "source": prov, "envelopes": legs}


ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--from-capture", type=Path, metavar="DIR",
                help="re-measure from DIR/{mic,system}.wav and rewrite the pin. "
                     "Changes the published art, so it prints the new durations "
                     "for the README's captions")
args = ap.parse_args()

if args.from_capture:
    pin = measure(args.from_capture)
    PIN.write_text(json.dumps(pin, indent=2) + "\n")
    print(f"re-pinned from {args.from_capture}:")
    for leg, meta in pin["source"].items():
        print(f"  {leg:7s} {meta['seconds']}s  sha256:{meta['sha256']}")
    print("  UPDATE the README alt text if the durations changed.\n")
elif not PIN.exists():
    sys.exit(f"{PIN} is missing. Run with --from-capture DIR to create it.")
else:
    pin = json.loads(PIN.read_text())
    if pin.get("n") != N:
        sys.exit(f"{PIN} holds {pin.get('n')} values but this script draws {N}. "
                 f"Re-pin with --from-capture.")

MIC = np.asarray(pin["envelopes"]["mic"], dtype=np.float64)
SYS = np.asarray(pin["envelopes"]["system"], dtype=np.float64)


def bars(values, x0, baseline, width, gap, max_h, fill, min_h=1.5):
    """Vertical bars growing upward from a baseline."""
    out = []
    for i, v in enumerate(values):
        h = max(min_h, float(v) * max_h)
        x = x0 + i * (width + gap)
        out.append(
            f'<rect x="{x:.1f}" y="{baseline - h:.1f}" width="{width}" '
            f'height="{h:.1f}" rx="0.8" fill="{fill}"/>'
        )
    return "\n      ".join(out)


def text(x, y, s, size=14, fill=BODY, family=SANS, weight=None, ls=None, anchor=None):
    attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{family}"', f'font-size="{size}"', f'fill="{fill}"']
    if weight:
        attrs.append(f'font-weight="{weight}"')
    if ls:
        attrs.append(f'letter-spacing="{ls}"')
    if anchor:
        attrs.append(f'text-anchor="{anchor}"')
    return f'<text {" ".join(attrs)}>{s}</text>'


# --------------------------------------------------------------------------
# hero.svg — identity + the two real tracks the product captures
# --------------------------------------------------------------------------
W, H = 1200, 380
bar_w, bar_gap, max_h = 4.0, 2.4, 46
panel_x, panel_y, panel_w, panel_h = 636, 48, 508, 284
track_x = panel_x + 28

hero = f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     role="img" aria-labelledby="hero-title hero-desc">
  <title id="hero-title">local-meeting-notes — meeting notes with no bot and no cloud</title>
  <desc id="hero-desc">A meeting notetaker that captures system audio through a Core Audio process tap and the microphone separately, so the far end and the near end arrive as two streams. The panel on the right shows both level tracks from a real capture: the microphone track carries a constant room-noise floor, the system track is silent until audio plays, and both rise together during speech.</desc>

  <rect width="{W}" height="{H}" rx="6" fill="{BG}"/>

  <g id="identity">
    {text(56, 66, "macOS 14.4+ &#183; APPLE SILICON", 13, MUTED, MONO, ls=2.4)}
    {text(54, 142, "local-meeting-notes", 50, FG, SANS, weight=700)}
    {text(56, 190, "No bot joins the call. No audio leaves the Mac.", 18, BODY)}
    {text(56, 216, "The far end and your voice arrive as two separate streams.", 18, BODY)}

    <line x1="56" y1="252" x2="580" y2="252" stroke="{LINE}" stroke-width="1"/>

    {text(56, 284, "16 kHz", 14, FG, MONO)}
    {text(112, 284, "s16le mono", 12, MUTED, MONO)}
    {text(232, 284, "Core Audio tap", 14, FG, MONO)}
    {text(396, 284, "no virtual driver", 12, MUTED, MONO)}
    {text(56, 310, "network: none &#8212; capture, transcription and notes all stay on disk", 12, MUTED, MONO)}
  </g>

  <g id="level-panel">
    <rect x="{panel_x}" y="{panel_y}" width="{panel_w}" height="{panel_h}" rx="6" fill="{RAISED}"/>

    <circle cx="{panel_x + 28}" cy="{panel_y + 30}" r="4.5" fill="{ACCENT}"/>
    {text(panel_x + 42, panel_y + 35, "LIVE", 12, ACCENT, MONO, ls=2.2)}
    {text(panel_x + panel_w - 28, panel_y + 35, "real capture &#183; 14.0 s", 11, DIM, MONO, anchor="end")}

    <g id="track-mic">
      {text(track_x, panel_y + 74, "MIC", 11, BODY, MONO, ls=1.8)}
      {text(track_x + 42, panel_y + 74, "&#8594; me", 11, DIM, MONO)}
      <line x1="{track_x}" y1="{panel_y + 140}" x2="{panel_x + panel_w - 28}" y2="{panel_y + 140}" stroke="{LINE}" stroke-width="1"/>
      {bars(MIC, track_x, panel_y + 138, bar_w, bar_gap, max_h, MUTED)}
    </g>

    <g id="track-system">
      {text(track_x, panel_y + 182, "SYSTEM", 11, BODY, MONO, ls=1.8)}
      {text(track_x + 66, panel_y + 182, "&#8594; them", 11, DIM, MONO)}
      <line x1="{track_x}" y1="{panel_y + 248}" x2="{panel_x + panel_w - 28}" y2="{panel_y + 248}" stroke="{LINE}" stroke-width="1"/>
      {bars(SYS, track_x, panel_y + 246, bar_w, bar_gap, max_h, BODY)}
    </g>
  </g>
</svg>
"""
(OUT / "hero.svg").write_text(hero)

# --------------------------------------------------------------------------
# bleed.svg — the finding, as an annotated specimen
# --------------------------------------------------------------------------
W2, H2 = 1200, 430
bx = 56
bw, bg_, bh = 9.0, 5.0, 58
span = N * (bw + bg_) - bg_
burst_lo, burst_hi = 19, 32
brk_x0 = bx + burst_lo * (bw + bg_)
brk_x1 = bx + burst_hi * (bw + bg_) + bw

bleed = f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="{W2}" height="{H2}" viewBox="0 0 {W2} {H2}"
     role="img" aria-labelledby="bleed-title bleed-desc">
  <title id="bleed-title">Speaker bleed inverts the Me/Them split</title>
  <desc id="bleed-desc">Two level tracks from one real capture with the far end playing through speakers. Both tracks rise during the same interval because the microphone is hearing the speakers. Envelope correlation measured plus 0.929, and the resulting transcript places every sentence on both legs — once labelled Me and once labelled Them.</desc>

  <rect width="{W2}" height="{H2}" rx="6" fill="{BG}"/>

  {text(56, 58, "MEASURED, NOT ASSUMED", 12, MUTED, MONO, ls=2.4)}
  {text(54, 96, "On speakers, the two-stream split stops working", 27, FG, SANS, weight=700)}

  <g id="tracks">
    <line x1="{bx}" y1="{176}" x2="{bx + span}" y2="{176}" stroke="{LINE}" stroke-width="1"/>
    {bars(MIC, bx, 174, bw, bg_, bh, MUTED)}
    {text(bx + span + 18, 178, "MIC", 11, BODY, MONO, ls=1.8)}

    <line x1="{bx}" y1="{256}" x2="{bx + span}" y2="{256}" stroke="{LINE}" stroke-width="1"/>
    {bars(SYS, bx, 254, bw, bg_, bh, BODY)}
    {text(bx + span + 18, 258, "SYSTEM", 11, BODY, MONO, ls=1.8)}
  </g>

  <g id="annotation">
    <rect x="{brk_x0}" y="112" width="{brk_x1 - brk_x0}" height="152" rx="3"
          fill="none" stroke="{ERROR}" stroke-width="1.5" stroke-dasharray="3 3"/>
    {text(brk_x0, 300, "both tracks rise together &#8212; the mic is hearing the speakers", 12, ERROR, MONO)}
  </g>

  <line x1="56" y1="330" x2="1144" y2="330" stroke="{LINE}" stroke-width="1"/>

  <g id="readout">
    {text(56, 372, "+0.929", 30, FG, MONO, weight=700)}
    {text(184, 366, "peak envelope correlation", 12, MUTED, MONO)}
    {text(184, 384, "acoustic component &#8722;25 ms &#183; three runs agree", 12, DIM, MONO)}
  </g>

  <g id="consequence" transform="translate(560 0)">
    {text(0, 356, "[00:00.00]", 12, DIM, MONO)}
    {text(88, 356, "Me", 12, BODY, MONO)}
    {text(128, 356, "The quarterly numbers came in ahead of plan.", 12, BODY, MONO)}
    {text(0, 378, "[00:00.36]", 12, DIM, MONO)}
    {text(88, 378, "Them", 12, ERROR, MONO)}
    {text(128, 378, "The quarterly numbers came in ahead of plan.", 12, ERROR, MONO)}
    {text(0, 402, "one speaker, two labels &#8212; a dialogue that never happened", 11, MUTED, MONO)}
  </g>
</svg>
"""
(OUT / "bleed.svg").write_text(bleed)

# --------------------------------------------------------------------------
# pipeline.svg — how the two legs meet
# --------------------------------------------------------------------------
W3, H3 = 1200, 280


def box(x, y, w, h, title, sub, mono_sub=True, fill=RAISED):
    return f"""<g>
      <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{LINE}" stroke-width="1"/>
      {text(x + 18, y + 32, title, 14, FG, SANS, weight=600)}
      {text(x + 18, y + 54, sub, 11, MUTED, MONO if mono_sub else SANS)}
    </g>"""


def arrow(x0, y, x1):
    return (
        f'<line x1="{x0}" y1="{y}" x2="{x1 - 7}" y2="{y}" stroke="{RULE}" stroke-width="1.5"/>'
        f'<path d="M {x1 - 7} {y - 4} L {x1} {y} L {x1 - 7} {y + 4} Z" fill="{RULE}"/>'
    )


pipeline = f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="{W3}" height="{H3}" viewBox="0 0 {W3} {H3}"
     role="img" aria-labelledby="pipe-title pipe-desc">
  <title id="pipe-title">Capture architecture: two legs into one transcript</title>
  <desc id="pipe-desc">System audio is captured by a vendored Swift binary using a Core Audio process tap and piped as sixteen kilohertz PCM into the Python daemon. The microphone is captured in the same process through sounddevice. Both legs are transcribed locally by MLX Whisper. The microphone transcript then passes three filters — is there voiced audio behind this segment, is that audio the far end returning through the room, and is it the operator's own voice — before the two legs are interleaved into a transcript that either carries Me and Them labels or declares itself unattributed. Nothing leaves the machine.</desc>

  <rect width="{W3}" height="{H3}" rx="6" fill="{BG}"/>

  {text(56, 48, "CAPTURE ARCHITECTURE", 12, MUTED, MONO, ls=2.4)}

  {box(56, 74, 232, 76, "System audio", "audiotee &#183; Core Audio tap")}
  {box(56, 170, 232, 76, "Microphone", "sounddevice")}

  {arrow(288, 112, 356)}
  {arrow(288, 208, 356)}

  {box(356, 74, 236, 172, "dual_capture.py", "16 kHz s16le &#183; both legs", fill=RAISED)}
  {text(374, 152, "timestamps each block on arrival", 11, DIM, MONO)}
  {text(374, 172, "measures drift and bleed", 11, DIM, MONO)}
  {text(374, 192, "gates: voicing, echo, voiceprint", 11, DIM, MONO)}

  {arrow(592, 160, 660)}

  {box(660, 122, 220, 76, "MLX Whisper", "on-GPU, weights cached local")}

  {arrow(880, 160, 948)}

  {box(948, 122, 196, 76, "transcript.json", "Me / Them, or unattributed")}

  <line x1="56" y1="264" x2="1144" y2="264" stroke="{LINE}" stroke-width="1"/>
  {text(56, 258, "the pipe between the Swift tap and the Python daemon is ordinary stdout &#8212; no IPC, no driver, no network", 11, MUTED, MONO)}
</svg>
"""
(OUT / "pipeline.svg").write_text(pipeline)

for f in ("hero.svg", "bleed.svg", "pipeline.svg"):
    print(f"{f:14s} {(OUT / f).stat().st_size:>6d} bytes")
