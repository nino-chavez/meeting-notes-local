#!/usr/bin/env bash
# Build the drag-to-Applications DMG layout without signing credentials.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLNAME="Yawn"
APP="${1:-$ROOT/target/release/bundle/macos/$VOLNAME.app}"

die() { echo "build-dmg: $*" >&2; exit 1; }

[[ -d "$APP" ]] || die "no app bundle at $APP"
PLIST="$APP/Contents/Info.plist"
[[ -f "$PLIST" ]] || die "missing app Info.plist at $PLIST"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST")"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] \
  || die "unsafe app version: $VERSION"
DMG="${2:-$ROOT/target/release/bundle/macos/Yawn-${VERSION}-macos-arm64.dmg}"
[[ "$DMG" == *.dmg ]] || die "output must end in .dmg: $DMG"
[[ "$DMG" != "$APP" && "$DMG" != "$APP/"* ]] \
  || die "DMG output cannot be inside the app bundle"

for tool in ditto hdiutil; do
  command -v "$tool" >/dev/null || die "$tool is unavailable"
done

STAGE="$(mktemp -d /tmp/local-meeting-notes-dmg.XXXXXX)"
cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT

mkdir -p "$(dirname "$DMG")" "$STAGE/volume"
ditto "$APP" "$STAGE/volume/$VOLNAME.app"
ln -s /Applications "$STAGE/volume/Applications"

hdiutil create \
  -volname "$VOLNAME" \
  -srcfolder "$STAGE/volume" \
  -ov \
  -format UDZO \
  "$DMG" >/dev/null

echo "DMG layout built: $DMG"
