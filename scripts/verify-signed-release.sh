#!/usr/bin/env bash
# Recheck a frozen signed and notarized app + DMG without Apple credentials.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLNAME="Local Meeting Notes"
APP="${1:-$ROOT/target/release/bundle/macos/$VOLNAME.app}"

die() { echo "signed release verification: BLOCKED — $*" >&2; exit 1; }

[[ -d "$APP" ]] || die "missing app bundle: $APP"
[[ -f "$APP/Contents/Info.plist" ]] || die "missing built Info.plist"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
DMG="${2:-$ROOT/target/release/bundle/macos/Local-Meeting-Notes-${VERSION}-macos-arm64.dmg}"
ADMISSION="${3:-product}"
[[ "$ADMISSION" == "product" || "$ADMISSION" == "internal-alpha" ]] \
  || die "admission must be product or internal-alpha"
[[ -f "$DMG" ]] || die "missing DMG: $DMG"

for tool in codesign hdiutil shasum spctl xcrun; do
  command -v "$tool" >/dev/null || die "$tool is unavailable"
done

codesign --verify --deep --strict "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose=4 "$APP"

codesign --verify --strict "$DMG"
xcrun stapler validate "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=4 "$DMG"

"$ROOT/scripts/verify-dmg-layout.sh" "$DMG"
"$ROOT/scripts/verify-release-bundle.py" "$APP" --signed --admission "$ADMISSION"

for relative in \
  "Contents/MacOS/local-meeting-notes-desktop" \
  "Contents/Resources/app-runtime.json" \
  "Contents/Resources/bin/audiotee" \
  "Contents/Resources/python-runtime/bin/python3.12"; do
  [[ -f "$APP/$relative" ]] || die "missing signed artifact: $relative"
  shasum -a 256 "$APP/$relative"
done
if [[ "$ADMISSION" == "internal-alpha" ]]; then
  [[ -f "$APP/Contents/Resources/bin/meeting-capture" ]] \
    || die "missing signed artifact: Contents/Resources/bin/meeting-capture"
  shasum -a 256 "$APP/Contents/Resources/bin/meeting-capture"
fi
shasum -a 256 "$DMG"

echo "signed release verification: PASS"
