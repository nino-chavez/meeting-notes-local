# Local Meeting Notes distribution runbook

Status: the Mac release credentials and packaging tools are available. No
distributable build exists yet. The current staged app contains a
`boundary-test` runtime, and the release verifier refuses to sign it.

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

For the transcript-only lane, build the fixed offline runtime and verify the
explicit alpha admission:

```bash
worker/build_runtime.sh build-alpha
scripts/verify-release-bundle.py \
  --admission internal-alpha \
  "target/release/bundle/macos/Local Meeting Notes.app"
```

`internal-alpha` is not an alias for `product`. The default verifier still
requires `product`, so an alpha can enter the signing path only through the
explicit alpha command.

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

For the transcript-only lane, use the explicit command:

```bash
scripts/sign-notarize.sh run-alpha \
  "target/release/bundle/macos/Local Meeting Notes.app"
```

The script follows the same two-submission sequence used by Film Room:

1. Refuse a runtime whose admission does not match the selected lane before
   changing the app.
2. Sign every nested Mach-O with Developer ID, hardened runtime, and a secure
   timestamp.
3. Rebuild the alpha runtime manifest from those exact signed bytes.
4. Sign and strictly verify the outer app.
5. Exercise the signed packaged runtime with no entitlements.
6. Submit the app to Apple, staple it, and pass Gatekeeper.
7. Build and verify the drag-to-Applications DMG.
8. Sign, submit, staple, and Gatekeeper-check the DMG.
9. Recheck the frozen app and DMG without relying on release credentials.

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
  "target/release/bundle/macos/Local-Meeting-Notes-<version>-macos-arm64.dmg" \
  internal-alpha
```

This checks strict signatures, staples, Gatekeeper, the mounted DMG layout, the
runtime, every Mach-O signing authority, the empty entitlement allowlist, and
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

## Human release gates

Signing and notarization prove package identity and Apple trust. They do not
prove that the notes are useful.

Before an internal alpha is shared, the unchanged installed build needs a
consented, content-free hardware receipt proving two-leg Start and Stop,
post-meeting transcript creation, quit/reopen recovery, and the configured
audio deletion. This receipt is mechanical evidence only.

Before an internal beta meeting, the unchanged installed build must also have
the private automatic-note admission receipt required by
`docs/vertical-slice.md`. The operator records that receipt against the exact
build and model digests. The private canary and its content stay outside Git.

The first release may use manual replacement. Before distributing a second
version, prove upgrade from the immediately previous app-data schema, injected
migration failure, and rollback without destroying the only copy of a meeting.
