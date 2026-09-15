#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="${HA_CONFIG_DIR:-$ROOT/.ci/ha-config}"
MEDIA_DIR="$CONFIG_DIR/matrix-e2e-media"
LOCAL_MEDIA_DIR="$CONFIG_DIR/media"
TEST_IMAGE_COMPONENT_DIR="$CONFIG_DIR/custom_components/matrix_extended_test_image"

rm -rf "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/custom_components" "$MEDIA_DIR" "$LOCAL_MEDIA_DIR" "$TEST_IMAGE_COMPONENT_DIR"
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
    # HA 2026.9 demo STT advertises stereo input only. Generate two identical
    # PCM16 channels so the real-stack fixture matches the provider contract.
    frames.extend(struct.pack("<hh", sample, sample))
with wave.open(str(path), "wb") as output:
    output.setnchannels(2)
    output.setsampwidth(2)
    output.setframerate(rate)
    output.writeframes(bytes(frames))
PY
cp "$MEDIA_DIR/matrix-e2e-voice.wav" "$LOCAL_MEDIA_DIR/matrix-e2e-voice.wav"

cat > "$TEST_IMAGE_COMPONENT_DIR/manifest.json" <<'JSON'
{
  "domain": "matrix_extended_test_image",
  "name": "Matrix Extended test image Media Source",
  "version": "0.0.0",
  "dependencies": ["media_source", "image"],
  "codeowners": []
}
JSON

cat > "$TEST_IMAGE_COMPONENT_DIR/__init__.py" <<'PY'
"""Disposable real-stack Media Source fixture for Matrix Extended tests."""

from base64 import b64decode
from typing import override

from homeassistant.components.image import ImageEntity
from homeassistant.components.image.const import DATA_COMPONENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

DOMAIN = "matrix_extended_test_image"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)
_TEST_IMAGE = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
)


class MatrixExtendedRegressionImage(ImageEntity):
    """Deterministic finite image used by the real-stack regression."""

    _attr_name = "Matrix Extended Regression"
    _attr_unique_id = "matrix_extended_regression"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass)
        self.entity_id = "image.matrix_extended_regression"

    @override
    async def async_image(self) -> bytes | None:
        return _TEST_IMAGE


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Load the disposable test integration and add its image entity."""
    hass.data[DATA_COMPONENT].async_add_entities([MatrixExtendedRegressionImage(hass)])
    return True
PY

cat > "$TEST_IMAGE_COMPONENT_DIR/media_source.py" <<'PY'
"""Media Source fixture that intentionally resolves to image_proxy_stream."""

from typing import override

from homeassistant.components.media_player import BrowseError
from homeassistant.components.media_source import MediaSource, MediaSourceItem, PlayMedia
from homeassistant.core import HomeAssistant

DOMAIN = "matrix_extended_test_image"


async def async_get_media_source(hass: HomeAssistant) -> "MatrixExtendedTestImageSource":
    """Return the disposable image Media Source."""
    return MatrixExtendedTestImageSource(hass)


class MatrixExtendedTestImageSource(MediaSource):
    """Resolve the fixture image entity to HA's streaming image proxy."""

    name = "Matrix Extended test image"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    @override
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        return PlayMedia(f"/api/image_proxy_stream/{item.identifier}", "image/png")

    @override
    async def async_browse_media(self, item: MediaSourceItem):
        raise BrowseError("Matrix Extended test image source is resolve-only")
PY

cat > "$CONFIG_DIR/configuration.yaml" <<'YAML'
homeassistant:
  allowlist_external_dirs:
    - /config/matrix-e2e-media
  media_dirs:
    local: /config/media

default_config:

demo:

matrix_extended_test_image:

counter:
  matrix_reaction:
    name: Matrix reaction executions
    initial: 0
    step: 1

input_boolean:
  matrix_command_target:
    name: Matrix command target
    initial: false
  matrix_denied_target:
    name: Matrix denied command target
    initial: false

logger:
  default: info
  logs:
    custom_components.matrix_extended: debug
YAML
