# Brand decision — YAWN

Decided by the operator 2026-08-03.

**YAWN — Yet Another Whisper Notetaker.** The W is the engine: transcription
runs on Whisper, locally. The name carries the project's own register —
self-aware, anti-hype — and the tagline does the explaining. Lineage: the
operator asked for something in the "not another notetaker" vein; the "Notta"
variation is already a shipping cloud notetaker, which both disqualified it
and confirmed the vein.

What the name changes now:

- The delivery site is the Cloudflare Pages project `yawn-site`, live at
  **`https://yawn-site.pages.dev`** (the DMG itself in R2 — Pages caps served
  files at 25 MB and the DMG is 1.7 GB).

  **Corrected 2026-08-05.** This file previously said the site lives at
  `yawn.ninochavez.com`. That hostname does not resolve, and neither does
  `ninochavez.com`; the operator's domain is `ninochavez.co`. Verified against
  the Cloudflare API, the project carries exactly one domain,
  `yawn-site.pages.dev` — no custom domain is attached. Attaching
  `yawn.ninochavez.co` is a real option and an unmade decision, not a thing that
  already exists.
- Site, copy, and hand-off materials use YAWN.

What it deliberately does not change:

- The bundle identifier stays `com.ninochavez.local-meeting-notes` — signing
  identifiers, the release verifier's pinned constants, and every installed
  app-data root hang off it, so renaming it orphans installs for zero gain.
- The Cargo package, and therefore the signed main executable
  `Contents/MacOS/local-meeting-notes-desktop`, is unchanged for the same
  reason: `verify-release-bundle.py` pins that exact path.
- The preview and library-dev lanes keep their existing product names. Neither
  is distributed, both are engineer-only surfaces, and renaming them would put
  four more script literals and two contract pins at risk for no reader.
- Standalone-domain availability (yawn.app etc.) is unverified — check at a
  registrar before GA. The subdomain needs no check.

**Display rename executed 2026-08-05, at 0.3.0, as the deliberate change this
file scheduled.** The installed app is now **Yawn**: `productName`, the window
title, the tray entry, and both macOS permission prompts. The `.app` is
`Yawn.app` and the image is `Yawn-<version>-macos-arm64.dmg`. It rode a fresh
release-lane run rather than a retrofit — build contract pins updated first,
mechanical suite green before signing. The timing was chosen because every
install and app-data root on the operator's machine had just been removed, so
no live installation depended on the old name.
