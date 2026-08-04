# Brand decision — YAWN

Decided by the operator 2026-08-03.

**YAWN — Yet Another Whisper Notetaker.** The W is the engine: transcription
runs on Whisper, locally. The name carries the project's own register —
self-aware, anti-hype — and the tagline does the explaining. Lineage: the
operator asked for something in the "not another notetaker" vein; the "Notta"
variation is already a shipping cloud notetaker, which both disqualified it
and confirmed the vein.

What the name changes now:

- The delivery site lives at `yawn.ninochavez.com` (Cloudflare Pages; the
  DMG itself in R2 — Pages caps served files at 25 MB and the DMG is 1.7 GB).
- Site, copy, and hand-off materials use YAWN.

What it deliberately does not change yet:

- The bundle identifier stays `com.ninochavez.local-meeting-notes` — signing
  identifiers, the release verifier's pinned constants, and every installed
  app-data root hang off it, so renaming it orphans installs for zero gain.
- The app's display name stays "Local Meeting Notes" for the 0.2.0 cohort
  DMG — `productName` is pinned by the build contract, and renaming it means
  a deliberate pin update plus a fresh release-lane run. Candidate change for
  0.3.0, not a retrofit.
- Standalone-domain availability (yawn.app etc.) is unverified — check at a
  registrar before GA. The subdomain needs no check.
