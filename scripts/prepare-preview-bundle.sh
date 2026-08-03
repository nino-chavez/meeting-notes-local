#!/usr/bin/env bash
# Give the locally packaged Preview the same microphone entitlement boundary as
# the installed alpha, without notarizing or promoting it as a release.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${LMN_PREVIEW_APP:-$ROOT/target/release/bundle/macos/Local Meeting Notes Preview.app}"
RESOURCES="$APP/Contents/Resources"
MAIN="$APP/Contents/MacOS/local-meeting-notes-desktop"
CAPTURE="$RESOURCES/bin/meeting-capture"
ENTITLEMENTS="$ROOT/apps/desktop/src-tauri/capture-entitlements.plist"
EXPECTED_TEAM_ID="34VZ63G58M"
FORBIDDEN_NOTE_RUNTIME_RESOURCES=(
  "note-bridge.py"
  "note-runtime-project.json"
  "note-validator.zip"
)

die() {
  echo "prepare-preview-bundle: $*" >&2
  exit 1
}

require_bundle() {
  [[ -d "$APP" ]] || die "Preview app is missing: $APP"
  [[ -x "$MAIN" ]] || die "Preview app executable is missing"
  [[ -x "$CAPTURE" ]] || die "Preview meeting-capture helper is missing"
  [[ -x "$RESOURCES/python-runtime/bin/python3.12" ]] \
    || die "Preview Python runtime is missing"
  [[ -f "$ENTITLEMENTS" ]] || die "capture entitlements are missing"
}

has_audio_input_entitlement() {
  codesign -d --entitlements :- "$1" 2>/dev/null \
    | plutil -extract 'com\.apple\.security\.device\.audio-input' raw -o - - \
    | grep -qx true
}

require_note_runtime_absent() {
  local resource path
  for resource in "${FORBIDDEN_NOTE_RUNTIME_RESOURCES[@]}"; do
    path="$RESOURCES/$resource"
    [[ ! -e "$path" && ! -L "$path" ]] \
      || die "Preview bundle contains a test-only note runtime resource: $resource"
  done
}

verify_bundle() {
  require_note_runtime_absent
  codesign --verify --deep --strict "$APP"
  has_audio_input_entitlement "$APP" \
    || die "Preview app is missing the audio-input entitlement"
  has_audio_input_entitlement "$MAIN" \
    || die "Preview executable is missing the audio-input entitlement"
  has_audio_input_entitlement "$CAPTURE" \
    || die "Preview meeting-capture helper is missing the audio-input entitlement"
}

sign_bundle() {
  local identity
  identity="$(
    security find-identity -v -p codesigning 2>/dev/null \
      | awk -F'"' -v team="($EXPECTED_TEAM_ID)" \
          '/Developer ID Application/ && index($2, team) {print $2; exit}'
  )"
  [[ -n "$identity" ]] || identity="-"

  # Finder/Gatekeeper provenance attributes are not product content, but they
  # make strict verification report an otherwise byte-identical bundle as
  # modified. Remove bundle metadata before creating the final code seals.
  xattr -cr "$APP"
  codesign --force --sign "$identity" --entitlements "$ENTITLEMENTS" "$CAPTURE"
  "$RESOURCES/python-runtime/bin/python3.12" -E -s -B \
    "$ROOT/worker/build_manifest.py" "$RESOURCES" --admission internal-alpha \
    --exclude-note-runtime
  # Sign the enclosing app last. Signing CFBundleExecutable as a standalone
  # path first makes it seal the surrounding bundle; replacing the outer
  # signature afterward then invalidates that inner resource seal.
  codesign --force --sign "$identity" --entitlements "$ENTITLEMENTS" "$APP"
  verify_bundle
}

require_bundle
case "${1:-sign}" in
  sign) sign_bundle ;;
  verify) verify_bundle ;;
  *) die "usage: prepare-preview-bundle.sh [sign|verify]" ;;
esac
