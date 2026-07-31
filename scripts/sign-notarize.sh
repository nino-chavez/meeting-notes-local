#!/usr/bin/env bash
# Developer ID signing -> notarized app -> signed, notarized, stapled DMG.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="filmroom-notary"
EXPECTED_TEAM_ID="34VZ63G58M"
VOLNAME="Local Meeting Notes"

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
  codesign --force --options runtime --timestamp --sign "$IDENTITY" "$path"
  count=$((count + 1))
done < "$STAGE/machos"
[[ "$count" -gt 0 ]] || die "app contains no Mach-O files"
echo "   $count Mach-O files signed"

if [[ "$ADMISSION" == "internal-alpha" ]]; then
  echo "== refreshing runtime manifest from signed bytes"
  "$ROOT/worker/build_manifest.py" \
    "$APP/Contents/Resources" --admission "$ADMISSION"
fi

echo "== signing app bundle"
codesign --force --options runtime --timestamp --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict "$APP"
"$ROOT/scripts/verify-release-bundle.py" "$APP" --signed --admission "$ADMISSION"

echo "== notarizing app"
ditto -c -k --keepParent "$APP" "$STAGE/app.zip"
xcrun notarytool submit "$STAGE/app.zip" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
spctl --assess --type execute --verbose=4 "$APP"

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
DMG="$ROOT/target/release/bundle/macos/Local-Meeting-Notes-${VERSION}-macos-arm64.dmg"
echo "== building DMG"
"$ROOT/scripts/build-dmg.sh" "$APP" "$DMG"
"$ROOT/scripts/verify-dmg-layout.sh" "$DMG"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"

echo "== notarizing DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=4 "$DMG"

"$ROOT/scripts/verify-signed-release.sh" "$APP" "$DMG" "$ADMISSION"
echo "DONE: $DMG"
