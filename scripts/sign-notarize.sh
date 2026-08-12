#!/usr/bin/env bash
# Developer ID signing -> notarized app -> signed, notarized, stapled DMG.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="filmroom-notary"
EXPECTED_TEAM_ID="34VZ63G58M"
EXPECTED_IDENTIFIER="com.ninochavez.local-meeting-notes"
PYTHON_SIGNING_IDENTIFIER="${EXPECTED_IDENTIFIER}.python-runtime"
VOLNAME="Yawn"
PYTHON_ENTITLEMENTS="$ROOT/apps/desktop/src-tauri/python-entitlements.plist"
CAPTURE_ENTITLEMENTS="$ROOT/apps/desktop/src-tauri/capture-entitlements.plist"

die() { echo "sign-notarize: $*" >&2; exit 1; }

identity() {
  security find-identity -v -p codesigning \
    | awk -F'"' -v team="($EXPECTED_TEAM_ID)" \
        '/Developer ID Application/ && index($2, team) {print $2; exit}'
}

cmd="${1:-preflight}"
shift || true

if [[ "$cmd" == "preflight" ]]; then
  status=0
  for tool in codesign ditto file hdiutil security shasum spctl xcrun; do
    if command -v "$tool" >/dev/null; then
      echo "tool: PASS — $tool"
    else
      echo "tool: BLOCKED — $tool is unavailable" >&2
      status=1
    fi
  done
  if xcrun notarytool --version >/dev/null 2>&1 \
    && xcrun --find stapler >/dev/null 2>&1; then
    echo "Apple notarization tools: PASS"
  else
    echo "Apple notarization tools: BLOCKED — notarytool or stapler is unavailable" >&2
    status=1
  fi
  IDENTITY="$(identity)"
  if [[ -n "$IDENTITY" ]]; then
    echo "Developer ID Application identity: PASS — $IDENTITY"
  else
    echo "Developer ID Application identity: BLOCKED — Team $EXPECTED_TEAM_ID is unavailable" >&2
    status=1
  fi
  if xcrun notarytool history \
      --keychain-profile "$PROFILE" --output-format json >/dev/null 2>&1; then
    echo "notary profile: PASS — $PROFILE is accepted by Apple"
  else
    echo "notary profile: BLOCKED — $PROFILE is missing or rejected" >&2
    status=1
  fi
  if [[ "$status" == "0" ]]; then
    echo "signing preflight: PASS"
  else
    echo "signing preflight: BLOCKED" >&2
  fi
  exit "$status"
fi

[[ "$cmd" == "run" || "$cmd" == "run-alpha" ]] \
  || die "usage: sign-notarize.sh [preflight|run|run-alpha] [app]"
APP="${1:-$ROOT/target/release/bundle/macos/$VOLNAME.app}"
[[ -d "$APP" ]] || die "no app bundle at $APP"
[[ -f "$PYTHON_ENTITLEMENTS" ]] || die "missing Python entitlements"
[[ -f "$CAPTURE_ENTITLEMENTS" ]] || die "missing capture entitlements"
ADMISSION="product"
if [[ "$cmd" == "run-alpha" ]]; then
  ADMISSION="internal-alpha"
fi

"$ROOT/scripts/verify-release-bundle.py" "$APP" --admission "$ADMISSION"
IDENTITY="$(identity)"
[[ -n "$IDENTITY" ]] || die "Developer ID Application identity for Team $EXPECTED_TEAM_ID is unavailable"
xcrun notarytool history --keychain-profile "$PROFILE" --output-format json \
  >/dev/null 2>&1 || die "notary profile $PROFILE is missing or rejected"
echo "identity: $IDENTITY"

STAGE="$(mktemp -d /tmp/local-meeting-notes-sign.XXXXXX)"
cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT

echo "== signing nested Mach-O files"
find "$APP" -type f -print0 \
  | while IFS= read -r -d '' path; do
      case "$(file -b "$path")" in Mach-O*) printf '%s\0' "$path" ;; esac
    done > "$STAGE/machos" || true
count=0
while IFS= read -r -d '' path; do
  sign_args=(--force --options runtime --timestamp --sign "$IDENTITY")
  if [[ "$path" == "$APP/Contents/Resources/python-runtime/bin/python3.12" ]]; then
    sign_args+=(--identifier "$PYTHON_SIGNING_IDENTIFIER" --entitlements "$PYTHON_ENTITLEMENTS")
  elif [[ "$path" == "$APP/Contents/MacOS/local-meeting-notes-desktop" \
      || "$path" == "$APP/Contents/Resources/bin/meeting-capture" \
      || "$path" == "$APP/Contents/Resources/bin/permission-probe" ]]; then
    # permission-probe calls AVCaptureDevice.requestAccess, so it is a requesting
    # binary and needs the same audio-input entitlement. Omitting it is the exact
    # defect that shipped once already: the requester never appears in System
    # Settings, so the operator is given no way to grant what the app asked for.
    sign_args+=(--entitlements "$CAPTURE_ENTITLEMENTS")
  fi
  codesign "${sign_args[@]}" "$path"
  count=$((count + 1))
done < "$STAGE/machos"
[[ "$count" -gt 0 ]] || die "app contains no Mach-O files"
echo "   $count Mach-O files signed"

echo "== refreshing runtime manifests from signed bytes"
# Preserve the encoder entry across the refresh: the pre-sign verifier already
# pinned its digest, and rebuilding without it would silently reset a packaged
# encoder candidate back to the placeholder identity.
ENCODER_PATH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["encoder"]["path"])' \
  "$APP/Contents/Resources/app-runtime.json")"
MANIFEST_ARGS=()
if [[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["schema"])' \
    "$APP/Contents/Resources/app-runtime.json")" == "app-runtime/2" ]]; then
  MANIFEST_ARGS+=(--external-transcript-models)
fi
"$ROOT/worker/build_manifest.py" \
  "$APP/Contents/Resources" --admission "$ADMISSION" --exclude-note-runtime \
  --encoder "$ENCODER_PATH" "${MANIFEST_ARGS[@]}"

echo "== signing app bundle"
codesign --force --options runtime --timestamp \
  --entitlements "$CAPTURE_ENTITLEMENTS" --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict "$APP"
# macOS can briefly refuse the bundled runtime immediately after a large app has
# been re-signed, even though the same closed bundle verifies moments later.
# Keep that transient state inside the release lane rather than making an
# operator re-run signing and create duplicate Apple submissions. A real
# runtime defect still fails after the bounded retries below.
verified=0
for attempt in 1 2 3 4 5 6; do
  if "$ROOT/scripts/verify-release-bundle.py" "$APP" --signed --admission "$ADMISSION"; then
    verified=1
    break
  fi
  if [[ "$attempt" -lt 6 ]]; then
    echo "signed runtime is not ready for verification; retrying in 15 seconds"
    sleep 15
  fi
done
[[ "$verified" == "1" ]] || die "signed app failed release verification"

echo "== notarizing app"
ditto -c -k --keepParent "$APP" "$STAGE/app.zip"
xcrun notarytool submit "$STAGE/app.zip" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
spctl --assess --type execute --verbose=4 "$APP"

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
DMG="$ROOT/target/release/bundle/macos/Yawn-${VERSION}-macos-arm64.dmg"
echo "== building DMG"
"$ROOT/scripts/build-dmg.sh" "$APP" "$DMG"
"$ROOT/scripts/verify-dmg-layout.sh" "$DMG"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"

echo "== notarizing DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=4 "$DMG"

"$ROOT/scripts/verify-signed-release.sh" "$APP" "$DMG" "$ADMISSION"
# Durable checksum receipt: delivery surfaces must copy this file's value,
# never retype the hash by hand.
shasum -a 256 "$DMG" | tee "$DMG.sha256"
echo "DONE: $DMG"
