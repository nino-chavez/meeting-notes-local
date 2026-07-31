#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$REPO/apps/desktop/vendor"
STAGE="$REPO/apps/desktop/runtime"
DOWNLOADS="$VENDOR/downloads"
PYTHON_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20260718/cpython-3.12.13%2B20260718-aarch64-apple-darwin-install_only.tar.gz'
PYTHON_SHA256='62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b'

if [[ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]]; then
  echo "boundary runtime build requires macOS arm64" >&2
  exit 1
fi

verify() {
  [[ -x "$STAGE/python-runtime/bin/python3.12" ]]
  [[ -x "$STAGE/bin/audiotee" ]]
  [[ -f "$STAGE/app-runtime.json" ]]
  (cd "$STAGE" && "$STAGE/python-runtime/bin/python3.12" -E -s -B -c \
    'import numpy; import worker.main; print(numpy.__version__)' \
    1>/dev/null)
  LMN_PACKAGED_RUNTIME_ROOT="$STAGE" \
  LMN_TAP_TEST_BINARY="$STAGE/bin/audiotee" \
    "$STAGE/python-runtime/bin/python3.12" -E -s -B -m unittest discover \
      -s "$REPO/worker/tests" -v
}

case "${1:-build}" in
  verify)
    verify
    exit 0
    ;;
  build) ;;
  *)
    echo "usage: worker/build_runtime.sh [build|verify]" >&2
    exit 64
    ;;
esac

mkdir -p "$DOWNLOADS"
ARCHIVE="$DOWNLOADS/cpython-3.12.13-arm64.tar.gz"
if [[ ! -f "$ARCHIVE" ]] || ! echo "$PYTHON_SHA256  $ARCHIVE" | shasum -a 256 -c - >/dev/null 2>&1; then
  curl -fL --max-time 300 -o "$ARCHIVE" "$PYTHON_URL"
fi
echo "$PYTHON_SHA256  $ARCHIVE" | shasum -a 256 -c -

rm -rf "$VENDOR/python-runtime" "$STAGE"
mkdir -p "$STAGE/bin" "$STAGE/worker" "$STAGE/spike" "$STAGE/notes"
tar -xzf "$ARCHIVE" -C "$VENDOR"
mv "$VENDOR/python" "$VENDOR/python-runtime"
"$VENDOR/python-runtime/bin/python3" -m pip install --quiet --require-hashes \
  -r "$REPO/worker/requirements-runtime.lock"

cp -R "$VENDOR/python-runtime" "$STAGE/python-runtime"
cp "$REPO/worker/__init__.py" "$REPO/worker/main.py" \
  "$REPO/worker/adapters.py" "$REPO/worker/storage.py" "$STAGE/worker/"
cp "$REPO/spike/verify_capture.py" "$REPO/spike/capture_health.py" \
  "$REPO/spike/dual_capture.py" "$REPO/spike/speaker_gate.py" \
  "$REPO/spike/aec_bound.py" "$STAGE/spike/"
cp "$REPO/notes/transcript.py" "$REPO/notes/summarize.py" "$STAGE/notes/"

swift build -c release --product audiotee --package-path "$REPO/capture/audiotee"
cp "$REPO/capture/audiotee/.build/arm64-apple-macosx/release/audiotee" \
  "$STAGE/bin/audiotee"
chmod 0755 "$STAGE/bin/audiotee"
printf '%s\n' 'phase-2-boundary-no-encoder-model' > "$STAGE/encoder-unavailable.identity"
python3 "$REPO/worker/build_manifest.py" "$STAGE"

verify
