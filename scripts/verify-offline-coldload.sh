#!/usr/bin/env bash
# Prove the packaged speaker-encoder candidate cold-loads with the network denied.
#
# macOS sandbox-exec applies a (deny network*) profile to the packaged Python.
# The gate is proven to bite first — a socket probe under the same profile must
# fail — before the cold-load result counts, so a silently ignored profile
# cannot produce a vacuous pass. "Cold" means a fresh interpreter process, not
# a rebooted page cache: the same definition the spike's cold-load numbers use.
set -euo pipefail

APP="${1:?usage: verify-offline-coldload.sh <app-bundle>}"
RES="$APP/Contents/Resources"
PY="$RES/python-runtime/bin/python3.12"
[[ -x "$PY" ]] || { echo "offline cold load: BLOCKED — no packaged Python at $PY" >&2; exit 1; }

ENCODER_PATH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["encoder"]["path"])' \
  "$RES/app-runtime.json")"
if [[ "$ENCODER_PATH" == "encoder-unavailable.identity" ]]; then
  echo "offline cold load: BLOCKED — this bundle packages no encoder candidate" >&2
  exit 1
fi

SB="$(mktemp /tmp/lmn-deny-network.XXXXXX.sb)"
trap 'rm -f "$SB"' EXIT
cat > "$SB" <<'PROFILE'
(version 1)
(allow default)
(deny network*)
PROFILE

if sandbox-exec -f "$SB" "$PY" -E -s -B -c \
  'import socket; socket.create_connection(("1.1.1.1", 443), timeout=4)' 2>/dev/null; then
  echo "offline cold load: BLOCKED — deny-network profile did not bite" >&2
  exit 1
fi
echo "deny-network control: PASS — socket connection refused under the profile"

(cd "$RES" && sandbox-exec -f "$SB" "$PY" -E -s -B -c "
import json, time
from pathlib import Path
t0 = time.perf_counter()
import numpy as np
import onnxruntime
from worker.fbank import fbank_features
from worker.main import load_manifest
t_import = time.perf_counter()
load_manifest(Path('app-runtime.json'))
t_manifest = time.perf_counter()
session = onnxruntime.InferenceSession('$ENCODER_PATH', providers=['CPUExecutionProvider'])
t_session = time.perf_counter()
features = fbank_features(np.zeros(3 * 16000, dtype=np.float32))
embedding = session.run(None, {'features': features[np.newaxis, ...],
                               'lengths': np.ones(1, dtype=np.float32)})[0]
t_first = time.perf_counter()
assert embedding.shape[-1] == 192, embedding.shape
print(json.dumps({
    'schema': 'encoder-offline-coldload/1',
    'import_seconds': round(t_import - t0, 4),
    'manifest_seconds': round(t_manifest - t_import, 4),
    'session_seconds': round(t_session - t_manifest, 4),
    'first_inference_seconds': round(t_first - t_session, 4),
    'total_seconds': round(t_first - t0, 4),
}))
")
echo "offline cold load: PASS"
