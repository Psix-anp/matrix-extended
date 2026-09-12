#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="${SYNAPSE_DATA_DIR:-$ROOT/.ci/synapse-data}"
IMAGE="${SYNAPSE_IMAGE:-matrixdotorg/synapse:v1.160.0}"
SERVER_NAME="${MATRIX_SERVER_NAME:-matrix.test}"

rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"

docker run --rm \
  -e SYNAPSE_SERVER_NAME="$SERVER_NAME" \
  -e SYNAPSE_REPORT_STATS=no \
  -e UID="$(id -u)" \
  -e GID="$(id -g)" \
  -v "$DATA_DIR:/data" \
  "$IMAGE" generate

python "$ROOT/ci/scripts/prepare-synapse.py" \
  "$DATA_DIR/homeserver.yaml" \
  "$ROOT/.ci/synapse-shared-secret"
