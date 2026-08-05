#!/usr/bin/env bash
# Mount a DMG read-only and prove the assisted-test installer layout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLNAME="Yawn"
DEFAULT_APP="$ROOT/target/release/bundle/macos/$VOLNAME.app"

die() { echo "verify-dmg-layout: $*" >&2; exit 1; }

if [[ -f "$DEFAULT_APP/Contents/Info.plist" ]]; then
  VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$DEFAULT_APP/Contents/Info.plist")"
else
  VERSION="0.1.0"
fi
DMG="${1:-$ROOT/target/release/bundle/macos/Yawn-${VERSION}-macos-arm64.dmg}"
[[ -f "$DMG" ]] || die "missing DMG: $DMG"
command -v hdiutil >/dev/null || die "hdiutil is unavailable"

MOUNT="$(mktemp -d /tmp/local-meeting-notes-dmg-mount.XXXXXX)"
attached=0
cleanup() {
  if [[ "$attached" == "1" ]]; then
    hdiutil detach "$MOUNT" -quiet || true
  fi
  rmdir "$MOUNT" 2>/dev/null || true
}
trap cleanup EXIT

hdiutil attach "$DMG" -readonly -nobrowse -mountpoint "$MOUNT" >/dev/null
attached=1

APP="$MOUNT/$VOLNAME.app"
[[ -d "$APP" ]] || die "mounted image is missing $VOLNAME.app"
[[ -f "$APP/Contents/Info.plist" ]] || die "mounted app is missing Contents/Info.plist"
[[ -L "$MOUNT/Applications" ]] || die "mounted image is missing Applications link"
[[ "$(readlink "$MOUNT/Applications")" == "/Applications" ]] \
  || die "Applications link does not target /Applications"

unexpected="$(
  find "$MOUNT" -mindepth 1 -maxdepth 1 \
    ! -name "$VOLNAME.app" \
    ! -name Applications \
    ! -name .DS_Store \
    ! -name .Trashes \
    ! -name .fseventsd \
    -print
)"
[[ -z "$unexpected" ]] || die "unexpected top-level DMG content: $unexpected"

hdiutil detach "$MOUNT" -quiet
attached=0
rmdir "$MOUNT"
trap - EXIT

echo "DMG layout verification: PASS — app plus drag-to-Applications link"
