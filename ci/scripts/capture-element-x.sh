#!/usr/bin/env bash
set -euo pipefail

mkdir -p docs/images .ci/android-debug

debug_capture() {
  adb exec-out screencap -p > .ci/android-debug/failure.png 2>/dev/null || true
  adb shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
  adb pull /sdcard/window.xml .ci/android-debug/window.xml >/dev/null 2>&1 || true
  adb logcat -d -t 500 > .ci/android-debug/logcat.txt 2>/dev/null || true
}
trap debug_capture ERR

adb install -r "$GITHUB_WORKSPACE/.ci/element-x.apk"
adb shell pm grant io.element.android.x android.permission.POST_NOTIFICATIONS || true

MATRIX_PASSWORD="$(python -c 'import json; print(json.load(open(".ci/matrix-passwords.json"))["user_password"])')"
"$HOME/.maestro/bin/maestro" test ci/maestro/element-x-login.yaml \
  -e MATRIX_URL=http://10.0.2.2:8008 \
  -e MATRIX_USERNAME=ha_user \
  -e MATRIX_PASSWORD="$MATRIX_PASSWORD"

python ci/scripts/send-doc-messages.py
sleep 5
adb exec-out screencap -p > docs/images/matrix-extended-element-x-inbox.png

"$HOME/.maestro/bin/maestro" test ci/maestro/element-x-room.yaml
sleep 2
adb exec-out screencap -p > docs/images/matrix-extended-element-x-chat.png

"$HOME/.maestro/bin/maestro" test ci/maestro/element-x-video.yaml
sleep 2
adb exec-out screencap -p > docs/images/matrix-extended-element-x-video.png

"$HOME/.maestro/bin/maestro" test ci/maestro/element-x-voice.yaml
sleep 2
adb exec-out screencap -p > docs/images/matrix-extended-element-x-voice.png

trap - ERR
