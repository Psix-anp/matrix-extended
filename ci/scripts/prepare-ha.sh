#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="${HA_CONFIG_DIR:-$ROOT/.ci/ha-config}"
MEDIA_DIR="$CONFIG_DIR/matrix-e2e-media"

rm -rf "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/custom_components" "$MEDIA_DIR"
cp -a "$ROOT/custom_components/matrix_extended" "$CONFIG_DIR/custom_components/matrix_extended"

python - "$MEDIA_DIR/matrix-e2e-voice.wav" <<'PY'
from pathlib import Path
import math
import struct
import sys
import wave

path = Path(sys.argv[1])
rate = 16_000
duration = 0.6
frames = bytearray()
for index in range(int(rate * duration)):
    sample = int(6_000 * math.sin(2 * math.pi * 440 * index / rate))
    frames.extend(struct.pack("<h", sample))
with wave.open(str(path), "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(rate)
    output.writeframes(bytes(frames))
PY

cat > "$CONFIG_DIR/configuration.yaml" <<'YAML'
homeassistant:
  allowlist_external_dirs:
    - /config/matrix-e2e-media

default_config:

counter:
  matrix_reaction:
    name: Matrix reaction executions
    initial: 0
    step: 1

logger:
  default: info
  logs:
    custom_components.matrix_extended: debug
YAML
