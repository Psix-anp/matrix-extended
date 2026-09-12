#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="${HA_CONFIG_DIR:-$ROOT/.ci/ha-config}"

rm -rf "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/custom_components"
cp -a "$ROOT/custom_components/matrix_extended" "$CONFIG_DIR/custom_components/matrix_extended"
cat > "$CONFIG_DIR/configuration.yaml" <<'YAML'
default_config:

logger:
  default: info
  logs:
    custom_components.matrix_extended: debug
YAML
