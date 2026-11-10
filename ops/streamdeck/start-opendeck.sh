#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT=/srv/vision-data/tools/streamdeck-prod
PKG=/srv/vision-data/tools/streamdeck-eval/pkg/usr/bin
export DISPLAY=:98
export GDK_BACKEND=x11
export XDG_CONFIG_HOME="$ROOT/config"
export XDG_CACHE_HOME="$ROOT/cache"
export XDG_DATA_HOME="$ROOT/data"
export TMPDIR="$ROOT/tmp"
export LIBGL_ALWAYS_SOFTWARE=1
export WEBKIT_DISABLE_COMPOSITING_MODE=1
export GSETTINGS_BACKEND=memory
mkdir -p "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$TMPDIR"
DECK_HID=""
for h in /sys/class/hidraw/hidraw*; do
  [[ -e "$h/device/uevent" ]] || continue
  if grep -iq "HID_ID=0003:00000FD9:00000084" "$h/device/uevent"; then
    DECK_HID="/dev/$(basename "$h")"
    break
  fi
done
if [[ -z "$DECK_HID" || ! -w "$DECK_HID" ]]; then
  echo "STREAM_DECK_PLUS_NOT_AVAILABLE_OR_ACCESS_DENIED hid=${DECK_HID:-none}" >&2
  exit 10
fi
echo "STREAM_DECK_HID=$DECK_HID"
"$PKG/Xvfb" :98 -screen 0 1440x900x24 -nolisten tcp -noreset &
XVFB=$!
APP=""
finish() {
  if [[ -n "$APP" ]]; then kill "$APP" 2>/dev/null || true; wait "$APP" 2>/dev/null || true; fi
  kill "$XVFB" 2>/dev/null || true
  wait "$XVFB" 2>/dev/null || true
}
trap finish EXIT INT TERM
sleep 0.8
kill -0 "$XVFB"
echo "OPENDECK_VISION_START streamdeck=0fd9:0084 profile=Default key=7(SW-STOP)"
dbus-run-session -- "$PKG/opendeck" &
APP=$!
wait "$APP"
