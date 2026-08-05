# Yawn distribution runbook

Status, 2026-08-05: the current cohort DMG is **0.3.0**, the first build whose
installed name is **Yawn**. The display rename was the deliberate 0.3.0-class
change recorded in `docs/brand.md`: `productName`, the window title, the tray
entry, and the two macOS permission prompts now read Yawn, while the bundle
identifier stays `com.ninochavez.local-meeting-notes` so signing identity,
verifier constants, TCC grants, and the app-data root are untouched. The
`.app` is `Yawn.app` and the image is `Yawn-<version>-macos-arm64.dmg`; the
preview and library-dev lanes deliberately keep their old product names, since
neither is distributed. The Cargo package — and therefore the signed main
executable, `Contents/MacOS/local-meeting-notes-desktop` — is also unchanged.

**0.2.2's evidence does not transfer to 0.3.0.** 0.2.2 was the first build
carrying the admitted ONNX speaker encoder with guided voice setup registered
end to end, and its own record stands: commit `f63d38a`, DMG SHA-256
`eec3e611aceef12e932e870197fba26d612b02a9a8f94eb41f070a8f838c89f4`, signed,
notarized, stapled, `verify-signed-release.sh … internal-alpha` PASS. It never
received its interactive operator run, so that gate is still open and is now
0.3.0's to close, not a box 0.2.2 already ticked. Its R2 object was deleted
when 0.3.0 replaced it, because a differently-named image would otherwise have
kept serving an app called "Local Meeting Notes" from a live URL nothing linked.
The first cohort download still supplies the waived transferred-build
Gatekeeper field receipt — record it in `spike/encoder-packaging/RESULTS.md`
when it arrives.

Earlier record: a signed and notarized internal transcript-alpha DMG exists for
commit `5fe9aecd4f53204dc6e82573fd4b4dde37efd6d1`. Its SHA-256 is
`f5f091811d337acae4c7dc25db5638e2675e30552ed1793af1dc82c7c734385a`.
The frozen app and DMG pass independent signature, Gatekeeper, runtime, and DMG
layout verification. The main app and capture helper carry Apple's required
audio-input entitlement. A hardware attempt reached local transcription and
then failed closed because human-readable library output entered the worker's
JSON-only protocol channel. The corrected worker isolates protocol output, and
the packaged-runtime regression now invokes the real transcript model. The
corrected installed build then completed two-leg capture and local transcription
on real hardware, and the completed transcript screen returned after a true quit
and fresh launch. The unchanged installed alpha is byte-bound to the original capture
attempt. Its one-day deadline, `2026-08-02T10:20:01-0500`, passed; a launch after that
time completed automatic retention and produced an `audio-deletion/1` `removed`
receipt with SHA-256 `59a500cb4f6c5e05e22425ba2f90c38629d300249b41628f5efb613bb029f4d5`,
observed at approximately `2026-08-02T20:24:47-0500`. Both bound microphone and
system WAVs are absent. The exact retained transcript artifact remains present, JSON-readable, and
digest-matched; its text was not inspected or emitted. This closes automatic deletion
only. This artifact is not cleared for team distribution: clean transfer, Gatekeeper,
permissions, capture, and recovery on another Mac or genuinely clean account remain
open; PR #2 and the release remain draft, and no release verdict is recorded.

This is a how-to for the release operator. It assumes a clean release commit,
Apple-silicon macOS, Xcode command-line tools, and access to the existing
Developer ID and notarization credentials. It does not assume knowledge of the
project's implementation history.

## Two release lanes

Both lanes produce a versioned, signed, notarized DMG for Apple-silicon Macs
running macOS 14.4 or later. Installation is drag-to-Applications. Updates are
manual for the first release.

The first lane is an **internal transcript alpha**. It is for capture,
permission, recovery, retention, and transcript feedback. It carries runtime
admission `internal-alpha`, shows that label in the application, and never
presents an automatic note as ready. It requires manual Start and Stop,
headphones, one operator at the microphone, and nobody else in the room. It is
not a beta and does not satisfy the automatic-note gate.

The alpha lane's main window carries the reviewed internal-alpha surface
command set — capture, Library and exact search, content-free voice status,
preserve-first migration, confirmed reset, and the one-meeting audio-deletion
boundary — the same list the Preview window grants, with enrollment mutation
and profile activation absent from both. This was decided 2026-08-04 after the
0.2.0 coworker-cohort DMG shipped with the shell's record entry and search
gated on the dev-only preview lane flag, so neither was reachable on any
machine while the mechanical release suite stayed green. Two pins now hold the
boundary: `main_window_has_only_named_commands_and_no_generic_capability`
freezes the exact list, and `shipped_shell_is_permitted_every_command_it_invokes`
fails any build whose shell invokes a command its window capability does not
grant. The first fixed cohort version is 0.2.1.

The second lane is the **internal beta** described by the accepted vertical
slice. It carries `product` runtime admission and remains blocked until the
private automatic-note admission receipt exists for the exact build and model
digests.

No signed package expands its stated operating envelope.

## What must be true before signing

Start from an exact commit with no untracked executable code. Build the fixed
runtime and the `.app`, then run:

```bash
scripts/verify-release-bundle.py \
  "target/release/bundle/macos/Yawn.app"
```

That command must report `PASS`. It checks the built permission text, bundle
identity, macOS version, arm64-only executables, arm64-compatible native libraries,
packaged Python, NumPy native code,
worker import, runtime inventory, and `admission: product`.

The current `worker/build_runtime.sh` intentionally produces
`admission: boundary-test`. Renaming that value is not a release step. Live
capture, transcription, note creation, a closed executable inventory, and the
fixed model set must work before the product-runtime builder may issue product
admission.

For the transcript-only lane, build the fixed offline runtime and verify the
explicit alpha admission:

```bash
worker/build_runtime.sh build-alpha
scripts/verify-release-bundle.py \
  --admission internal-alpha \
  "target/release/bundle/macos/Yawn.app"
```

`internal-alpha` is not an alias for `product`. The default verifier still
requires `product`, so an alpha can enter the signing path only through the
explicit alpha command.

## Encoder-candidate lane (admission evidence, not a release)

`worker/build_runtime.sh build-alpha-encoder` builds the alpha runtime plus
the preferred ONNX speaker-encoder candidate: onnxruntime from the hash-pinned
`worker/requirements-encoder.lock`, and the converted ECAPA model at
`models/speaker-encoder/ecapa-tdnn.onnx`, accepted only if it matches the
pinned digest of the deterministic export
(`spike/encoder-packaging/export_onnx.py` from the pinned checkpoint; two
independent exports reproduce the digest byte-identically). The manifest's
`encoder` entry then names that artifact and binds its digest; the
`encoder-unavailable.identity` file remains in the bundle as a fixed resource,
but the manifest — not that file — is what every consumer reads.

This lane exists to produce the evidence admission check 2 requires
(`spike/encoder-packaging/RESULTS.md`), on the real signing path:

1. Build and sign exactly as for the alpha lane; `verify-release-bundle.py`
   additionally re-derives the packaged encoder's digest against its own
   pinned constant and exercises onnxruntime inside the packaged Python —
   after signing, that exercise is the same empty-entitlement control that
   caught `llvmlite`, now covering onnxruntime's dylibs.
2. `scripts/verify-offline-coldload.sh "<app>"` — cold-loads the encoder
   under a deny-network sandbox profile, after first proving the profile
   actually refuses a socket connection.
3. `<Resources>/python-runtime/bin/python3.12 -E -s -B
   scripts/measure-encoder-beside-mlx.py <Resources>` — peak RSS with the
   encoder session co-resident with MLX transcription of synthetic audio.

Until 2026-08-04 a `build-alpha-encoder` bundle was admission evidence only,
never a distribution candidate. The operator's admission verdict
(`spike/encoder-packaging/RESULTS.md` § "Admission verdict") changed that:
**from 0.2.2 the cohort DMG is built with `build-alpha-encoder`**, shipping
the admitted ONNX encoder in the runtime. The transferred-build Gatekeeper
check was waived in that ruling; the first cohort download of an
encoder-carrying DMG supplies the field receipt and should be noted in
RESULTS.md when it arrives. Admission of the encoder is not admission of
enrolment: the recorder and profile operations stay unregistered until their
own operator decisions.

## Check Apple release access

Run the host-level preflight:

```bash
scripts/sign-notarize.sh preflight
```

It must find both:

- the Developer ID Application identity for Team `34VZ63G58M`;
- the Apple-accepted `filmroom-notary` keychain profile.

A restricted terminal process may see zero identities even when the release
keychain is present. Treat the host-level command as the release check. The
preflight reads credential state; it does not print or copy credential
material.

## Sign and notarize the exact app

Run:

```bash
scripts/sign-notarize.sh run \
  "target/release/bundle/macos/Yawn.app"
```

For the transcript-only lane, use the explicit command:

```bash
scripts/sign-notarize.sh run-alpha \
  "target/release/bundle/macos/Yawn.app"
```

The script follows the same two-submission sequence used by Film Room:

1. Refuse a runtime whose admission does not match the selected lane before
   changing the app.
2. Sign every nested Mach-O with Developer ID, hardened runtime, and a secure
   timestamp.
3. Rebuild the alpha runtime manifest from those exact signed bytes.
4. Sign and strictly verify the outer app.
5. Exercise the signed packaged runtime with the closed entitlement allowlist.
6. Submit the app to Apple, staple it, and pass Gatekeeper.
7. Build and verify the drag-to-Applications DMG.
8. Sign, submit, staple, and Gatekeeper-check the DMG.
9. Recheck the frozen app and DMG without relying on release credentials.

The preserved empty-entitlement control failed when `llvmlite` changed an
allocated page to executable memory. Re-signing only the packaged `python3.12`
with `com.apple.security.cs.allow-unsigned-executable-memory` made the identical
offline-runtime import pass. That one key is the closed allowlist. The Tauri
executable, Swift audio tap, libraries, and every other packaged executable
remain entitlement-free; this app does not carry Film Room's library-validation
exception.

The output name is derived from the built app version:

```text
target/release/bundle/macos/Yawn-<version>-macos-arm64.dmg
```

### Two traps that cost a lane run on 2026-08-05

**Never pipe this script into `tail`, `head`, or anything else.** A pipeline
reports the *last* command's exit status, so `sign-notarize.sh … | tail -40`
returns 0 even when the lane aborts. On 2026-08-05 the lane died at
`verify-dmg-layout.sh` and reported success; the app was notarized and stapled
but the DMG was never signed, notarized, or stapled, and only reading the log
text revealed it. Redirect to a file and check `$?` instead.

**`hdiutil: attach failed - Resource temporarily unavailable` means the image is
already claimed, not that it is corrupt.** A previous failed or interrupted
attach can leave the DMG half-attached with no mountpoint, and every later
attach fails against it. It is invisible in `mount`; look in `hdiutil info` for
the image path, then `hdiutil detach <device> -force`. Do not rebuild the DMG or
re-sign anything to "fix" this — nothing is wrong with the artifact.

## Recheck a frozen artifact

Anyone with the artifact and Apple command-line tools can run:

```bash
scripts/verify-signed-release.sh \
  "target/release/bundle/macos/Yawn.app" \
  "target/release/bundle/macos/Yawn-<version>-macos-arm64.dmg" \
  internal-alpha
```

This checks strict signatures, staples, Gatekeeper, the mounted DMG layout, the
runtime, every Mach-O signing authority, the closed entitlement allowlist, and
the release hashes. Omit the final `internal-alpha` argument only for a product
release.

## Prove installation on another Mac

Use an Apple-silicon Mac or genuinely clean macOS account with no source
checkout, Homebrew, prior app data, prior permission grants, or external Python
or model runtime.

Record only release evidence:

- the exact commit, app version, and DMG SHA-256;
- transfer method and whether quarantine remained intact;
- Gatekeeper opening without a manual override;
- drag-to-Applications success;
- microphone and system-audio prompts attributed to Local Meeting Notes;
- clean refusal after denying either permission;
- successful two-leg Start and Stop after granting permission;
- quit, reopen, and recovery results;
- retention and deletion results;
- absence of an external runtime or unexpected network dependency.

Do not put meeting audio, transcript text, notes, voice profiles, Apple
credentials, or private review packets in a Git receipt.

### Content-free closure receipt

Keep the completed receipt outside Git beside the frozen artifact. It records only
release identity and outcomes; it must not contain a meeting identifier, app-data
path, audio, transcript text, note text, profile material, or credential material.
An agent may verify this shape and the public hashes. It may not invent the observed
outcomes or the release verdict.

```json
{
  "schema": "transcript-alpha-release-receipt/1",
  "recorded_at": "<RFC 3339>",
  "release": {
    "commit": "5fe9aecd4f53204dc6e82573fd4b4dde37efd6d1",
    "app_version": "0.1.0",
    "admission": "internal-alpha",
    "dmg_sha256": "f5f091811d337acae4c7dc25db5638e2675e30552ed1793af1dc82c7c734385a"
  },
  "automatic_deletion": {
    "observed_at": "<RFC 3339>",
    "installed_build_unchanged": true,
    "receipt_schema": "audio-deletion/1",
    "receipt_sha256": "<sha256>",
    "microphone_audio_absent": true,
    "system_audio_absent": true,
    "transcript_retained": true
  },
  "consented_hardware_run": {
    "participant_attestation_recorded": true,
    "headphones_attested": true,
    "operator_alone_attested": true,
    "two_leg_start_stop_succeeded": true,
    "post_meeting_transcript_created": true,
    "true_quit_fresh_launch_recovered_transcript": true,
    "transcript_text_inspected_for_receipt": false
  },
  "clean_transfer": {
    "target": "another-mac-or-clean-account",
    "quarantine_intact": true,
    "gatekeeper_opened_without_override": true,
    "drag_to_applications_succeeded": true,
    "prompts_attributed_to_app": true,
    "permission_denials_failed_closed": true,
    "two_leg_start_stop_succeeded": true,
    "post_meeting_transcript_created": true,
    "true_quit_fresh_launch_recovered_transcript": true,
    "retention_deletion_succeeded": true,
    "external_runtime_or_network_required": false
  },
  "operator_release_verdict": "accept-or-decline"
}
```

The deletion observation belongs to the original unchanged installed run. The clean
transfer may use the same exact DMG on the separate target. Rebuilding, reinstalling,
changing retention, manually deleting audio, or removing quarantine does not close
either gate; it starts a new evidence chain or records a failure.

## Human release gates

Signing and notarization prove package identity and Apple trust. They do not
prove that the notes are useful.

Before an internal alpha is shared, the unchanged installed build needs a
consented hardware receipt proving two-leg Start and Stop, post-meeting
transcript creation, quit/reopen recovery, and the configured audio deletion.
The current build has passed capture, transcript creation, and fresh-process
recovery. Its automatic deletion is mechanically closed: the unchanged executable is
byte-bound to the original capture attempt; after the `2026-08-02T10:20:01-0500`
deadline, a post-deadline launch produced the completed `audio-deletion/1` `removed`
receipt SHA-256 `59a500cb4f6c5e05e22425ba2f90c38629d300249b41628f5efb613bb029f4d5`,
observed at approximately `2026-08-02T20:24:47-0500`. Both bound microphone and
system WAVs are absent, and the exact retained transcript artifact is present, JSON-readable, and
digest-matched; its text was not inspected or emitted. Clean-machine transfer remains
open. This receipt is mechanical evidence only and is not a release verdict.

Before an internal beta meeting, the unchanged installed build must also have
the private automatic-note admission receipt required by
`docs/vertical-slice.md`. The operator records that receipt against the exact
build and model digests. The private canary and its content stay outside Git.

The first release may use manual replacement. Before distributing a second
version, prove upgrade from the immediately previous app-data schema, injected
migration failure, and rollback without destroying the only copy of a meeting.
