#!/usr/bin/env bash
set -Eeuo pipefail
BASE=/srv/vision-data/tools/streamdeck-eval
export XDG_CONFIG_HOME="$BASE/runtime/config" XDG_CACHE_HOME="$BASE/runtime/cache" XDG_DATA_HOME="$BASE/runtime/data" TMPDIR="$BASE/runtime/tmp"
export DISPLAY=:97 GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1
"$BASE/pkg/usr/bin/Xvfb" :97 -screen 0 1280x800x24 -nolisten tcp >"$BASE/logs/xvfb-fd.log" 2>&1 & XPID=$!
cleanup() { kill "$XPID" 2>/dev/null || :; wait "$XPID" 2>/dev/null || :; }
trap cleanup EXIT
sleep 1
if ! kill -0 "$XPID" 2>/dev/null; then echo XVFB=FAIL; exit 2; fi
DBUS_SESSION_BUS_ADDRESS= dbus-run-session -- timeout --signal=INT --kill-after=4 14 "$BASE/pkg/usr/bin/opendeck" >"$BASE/logs/opendeck-fd.log" 2>&1 & APID=$!
sleep 5
echo '=== ACTIVE OPENDECK ==='
FOUND=0
for pid in $(pgrep -f '^/srv/vision-data/tools/streamdeck-eval/pkg/usr/bin/opendeck$' || :); do
  echo "OPENDECK_PID=$pid"
  for fd in /proc/$pid/fd/*; do
    target=$(readlink "$fd" 2>/dev/null || :)
    if [ "$target" = /dev/hidraw0 ]; then echo "STREAMDECK_HID_FD=OPEN fd=${fd##*/}"; FOUND=1; fi
  done
done
if [ "$FOUND" -eq 0 ]; then echo 'STREAMDECK_HID_FD=NOT_OBSERVED'; fi
wait "$APID" || true
echo '=== ELGATO LOG ==='
grep -iE 'opendeck::elgato|HidError|hidraw|stream.?deck' "$BASE/logs/opendeck-fd.log" | tail -20 || true
