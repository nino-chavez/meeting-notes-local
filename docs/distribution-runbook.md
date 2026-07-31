# Local Meeting Notes distribution runbook

Status: the Mac release credentials and packaging tools are available. No
distributable product build exists yet. The current app contains a
`boundary-test` runtime, and the release verifier refuses to sign it.

This is a how-to for the release operator. It assumes a clean release commit,
Apple-silicon macOS, Xcode command-line tools, and access to the existing
Developer ID and notarization credentials. It does not assume knowledge of the
project's implementation history.

## Supported first release

The first internal beta is a versioned, signed, notarized DMG for Apple-silicon
Macs running macOS 14.4 or later. Installation is drag-to-Applications. Updates
are manual for the first release.

The release stays within the accepted operating envelope: manual Start and
Stop, headphones, one enrolled operator, nobody else in the room, and local
post-meeting processing. A signed package does not expand that envelope.

## What must be true before signing

Start from an exact commit with no untracked executable code. Build the fixed
runtime and the `.app`, then run:

```bash
scripts/verify-release-bundle.py \
  "target/release/bundle/macos/Local Meeting Notes.app"
```

That command must report `PASS`. It checks the built permission text, bundle
identity, macOS version, arm64-only code, packaged Python, NumPy native code,
worker import, runtime inventory, and `admission: product`.

The current `worker/build_runtime.sh` intentionally produces
`admission: boundary-test`. Renaming that value is not a release step. Live
capture, transcription, note creation, a closed executable inventory, and the
fixed model set must work before the product-runtime builder may issue product
admission.

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
  "target/release/bundle/macos/Local Meeting Notes.app"
```

The script follows the same two-submission sequence used by Film Room:

1. Refuse a non-product runtime before changing the app.
2. Sign every nested Mach-O with Developer ID, hardened runtime, and a secure
   timestamp.
3. Sign and strictly verify the outer app.
4. Exercise the signed packaged runtime with no entitlements.
5. Submit the app to Apple, staple it, and pass Gatekeeper.
6. Build and verify the drag-to-Applications DMG.
7. Sign, submit, staple, and Gatekeeper-check the DMG.
8. Recheck the frozen app and DMG without relying on release credentials.

The first control uses no entitlements. Do not copy Film Room's Python
entitlements into this app. If the signed runtime exercise fails, preserve the
failure and identify the exact executable and missing capability. Add only the
smallest Python-only entitlement that a repeated A/B check proves necessary.
The Tauri executable, Swift audio tap, and libraries remain entitlement-free.

The output name is derived from the built app version:

```text
target/release/bundle/macos/Local-Meeting-Notes-<version>-macos-arm64.dmg
```

## Recheck a frozen artifact

Anyone with the artifact and Apple command-line tools can run:

```bash
scripts/verify-signed-release.sh \
  "target/release/bundle/macos/Local Meeting Notes.app" \
  "target/release/bundle/macos/Local-Meeting-Notes-<version>-macos-arm64.dmg"
```

This checks strict signatures, staples, Gatekeeper, the mounted DMG layout, the
runtime, every Mach-O signing authority, the empty entitlement allowlist, and
the release hashes.

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

## Human release gates

Signing and notarization prove package identity and Apple trust. They do not
prove that the notes are useful.

Before an internal beta meeting, the unchanged installed build must also have
the private automatic-note admission receipt required by
`docs/vertical-slice.md`. The operator records that receipt against the exact
build and model digests. The private canary and its content stay outside Git.

The first release may use manual replacement. Before distributing a second
version, prove upgrade from the immediately previous app-data schema, injected
migration failure, and rollback without destroying the only copy of a meeting.
