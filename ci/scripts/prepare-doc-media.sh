#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=".ci/ha-config/www"
mkdir -p "$OUT_DIR"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc=size=640x360:rate=25" \
  -f lavfi -i "sine=frequency=660:sample_rate=48000" \
  -t 3 \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p \
  -c:a aac -b:a 64k -shortest \
  "$OUT_DIR/matrix-demo-video.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc=size=640x360:rate=1" \
  -frames:v 1 \
  "$OUT_DIR/matrix-demo-image.jpg"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=3.1" \
  -c:a libopus -b:a 32k \
  "$OUT_DIR/matrix-demo-voice.ogg"

for file in matrix-demo-video.mp4 matrix-demo-image.jpg matrix-demo-voice.ogg; do
  test -s "$OUT_DIR/$file"
done

echo "Documentation media fixtures ready in $OUT_DIR"
