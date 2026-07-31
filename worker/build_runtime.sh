#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$REPO/apps/desktop/vendor"
STAGE="$REPO/apps/desktop/runtime"
DOWNLOADS="$VENDOR/downloads"
PYTHON_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20260718/cpython-3.12.13%2B20260718-aarch64-apple-darwin-install_only.tar.gz'
PYTHON_SHA256='62aeee6161d57303a71a138b75fd5cc6fb8c89c4b1d9c7f0a052d89fa0b6652b'
WHISPER_REVISION='a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb'
WHISPER_CONFIG_SHA256='b34fc29e4e11e0a25e812775dd67f4dd16fc2c8eb43d28ae25ff7d660ecb6379'
WHISPER_WEIGHTS_SHA256='951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6'
WHISPER_DEFAULT="$HOME/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/snapshots/$WHISPER_REVISION"
WHISPER_SOURCE="${LMN_WHISPER_MODEL_DIR:-$WHISPER_DEFAULT}"

if [[ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]]; then
  echo "boundary runtime build requires macOS arm64" >&2
  exit 1
fi

verify() {
  [[ -x "$STAGE/python-runtime/bin/python3.12" ]]
  [[ -x "$STAGE/bin/audiotee" ]]
  [[ -f "$STAGE/app-runtime.json" ]]
  (cd "$STAGE" && "$STAGE/python-runtime/bin/python3.12" -E -s -B -c \
    'import json, numpy; import worker.main; doc=json.load(open("app-runtime.json")); print(doc["admission"], numpy.__version__)' \
    1>/dev/null)
  local admission
  admission="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["admission"])' "$STAGE/app-runtime.json")"
  if [[ "$admission" == "internal-alpha" ]]; then
    [[ -x "$STAGE/bin/meeting-capture" ]]
    echo "$WHISPER_CONFIG_SHA256  $STAGE/models/whisper-large-v3-turbo/config.json" | shasum -a 256 -c - >/dev/null
    echo "$WHISPER_WEIGHTS_SHA256  $STAGE/models/whisper-large-v3-turbo/weights.safetensors" | shasum -a 256 -c - >/dev/null
    (cd "$STAGE" && "$STAGE/python-runtime/bin/python3.12" -E -s -B -c \
      'import mlx.core, mlx_whisper, worker.transcription' 1>/dev/null)
    LMN_PACKAGED_RUNTIME_ROOT="$STAGE" \
      LMN_TAP_TEST_BINARY="$STAGE/bin/audiotee" \
      LMN_MEETING_CAPTURE_TEST_BINARY="$STAGE/bin/meeting-capture" \
      "$STAGE/python-runtime/bin/python3.12" -E -s -B -m unittest discover \
        -s "$REPO/worker/tests" -v
  else
    LMN_PACKAGED_RUNTIME_ROOT="$STAGE" \
      LMN_TAP_TEST_BINARY="$STAGE/bin/audiotee" \
      "$STAGE/python-runtime/bin/python3.12" -E -s -B -m unittest discover \
        -s "$REPO/worker/tests" -v
  fi
}

mode="${1:-build}"
case "$mode" in
  verify)
    verify
    exit 0
    ;;
  build|build-alpha) ;;
  *)
    echo "usage: worker/build_runtime.sh [build|build-alpha|verify]" >&2
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
mkdir -p "$STAGE/bin" "$STAGE/worker" "$STAGE/spike" "$STAGE/notes" "$STAGE/models"
tar -xzf "$ARCHIVE" -C "$VENDOR"
mv "$VENDOR/python" "$VENDOR/python-runtime"
if [[ "$mode" == "build-alpha" ]]; then
  "$VENDOR/python-runtime/bin/python3" -m pip install --quiet --require-hashes \
    --only-binary=:all: \
    -r "$REPO/worker/requirements-alpha.lock"
  "$VENDOR/python-runtime/bin/python3" -m pip install --quiet --require-hashes \
    --only-binary=:all: --no-deps \
    -r "$REPO/worker/requirements-mlx-whisper.lock"
else
  "$VENDOR/python-runtime/bin/python3" -m pip install --quiet --require-hashes \
    --only-binary=:all: \
    -r "$REPO/worker/requirements-runtime.lock"
fi

cp -R "$VENDOR/python-runtime" "$STAGE/python-runtime"
cp "$REPO/worker/__init__.py" "$REPO/worker/main.py" \
  "$REPO/worker/adapters.py" "$REPO/worker/storage.py" \
  "$REPO/worker/transcription.py" "$STAGE/worker/"
cp "$REPO/spike/verify_capture.py" "$REPO/spike/capture_health.py" \
  "$REPO/spike/dual_capture.py" "$REPO/spike/speaker_gate.py" \
  "$REPO/spike/aec_bound.py" "$STAGE/spike/"
cp "$REPO/notes/transcript.py" "$REPO/notes/summarize.py" "$STAGE/notes/"

swift build -c release --product audiotee --package-path "$REPO/capture/audiotee"
cp "$REPO/capture/audiotee/.build/arm64-apple-macosx/release/audiotee" \
  "$STAGE/bin/audiotee"
chmod 0755 "$STAGE/bin/audiotee"
if [[ "$mode" == "build-alpha" ]]; then
  [[ -f "$WHISPER_SOURCE/config.json" && -f "$WHISPER_SOURCE/weights.safetensors" ]] || {
    echo "fixed Whisper snapshot $WHISPER_REVISION is unavailable" >&2
    exit 1
  }
  echo "$WHISPER_CONFIG_SHA256  $WHISPER_SOURCE/config.json" | shasum -a 256 -c -
  echo "$WHISPER_WEIGHTS_SHA256  $WHISPER_SOURCE/weights.safetensors" | shasum -a 256 -c -
  mkdir -p "$STAGE/models/whisper-large-v3-turbo"
  cp -L "$WHISPER_SOURCE/config.json" "$WHISPER_SOURCE/weights.safetensors" \
    "$STAGE/models/whisper-large-v3-turbo/"
  swift build -c release --product meeting-capture --package-path "$REPO/capture/audiotee"
  cp "$REPO/capture/audiotee/.build/arm64-apple-macosx/release/meeting-capture" \
    "$STAGE/bin/meeting-capture"
  chmod 0755 "$STAGE/bin/meeting-capture"
fi
printf '%s\n' 'phase-2-boundary-no-encoder-model' > "$STAGE/encoder-unavailable.identity"
if [[ "$mode" == "build-alpha" ]]; then
  python3 "$REPO/worker/build_manifest.py" "$STAGE" --admission internal-alpha
else
  python3 "$REPO/worker/build_manifest.py" "$STAGE"
fi

verify
