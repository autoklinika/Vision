#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/srv/vision-data/tools/streamdeck-eval
export DISPLAY=:97
export XDG_CONFIG_HOME="$BASE/runtime/config"
export XDG_CACHE_HOME="$BASE/runtime/cache"
export XDG_DATA_HOME="$BASE/runtime/data"
export TMPDIR="$BASE/runtime/tmp"
export GDK_BACKEND=x11
export LIBGL_ALWAYS_SOFTWARE=1
export WEBKIT_DISABLE_COMPOSITING_MODE=1
export GSETTINGS_BACKEND=memory
mkdir -p "$BASE/logs" "$TMPDIR"
"$BASE/pkg/usr/bin/Xvfb" :97 -screen 0 1440x900x24 -nolisten tcp >"$BASE/logs/xvfb-gui.log" 2>&1 &
XVFB_PID=$!
APP_PID=""
cleanup() {
  if [ -n "$APP_PID" ]; then kill -INT "$APP_PID" 2>/dev/null || :; wait "$APP_PID" 2>/dev/null || :; fi
  kill "$XVFB_PID" 2>/dev/null || :
  wait "$XVFB_PID" 2>/dev/null || :
}
trap cleanup EXIT
sleep 1
kill -0 "$XVFB_PID"
dbus-run-session -- timeout --signal=INT --kill-after=3 35 "$BASE/pkg/usr/bin/opendeck" >"$BASE/logs/opendeck-gui.log" 2>&1 &
APP_PID=$!
sleep 8
echo "=== OPENDECK_PROCESS ==="
pgrep -af '^/srv/vision-data/tools/streamdeck-eval/pkg/usr/bin/opendeck$' || :
echo "=== X11 WINDOWS ==="
xwininfo -root -tree | head -32 || :
echo "=== DEVICE HID OWNERS ==="
fuser /dev/hidraw0 2>&1 || :
echo "=== SCREENSHOT ==="
python3 - <<'PY'
from PIL import ImageGrab
try:
    im=ImageGrab.grab(xdisplay=':97')
    p='/srv/vision-data/tools/streamdeck-eval/logs/opendeck-gui.png'
    im.save(p)
    print('SCREENSHOT_SAVED',p,'RESOLUTION',im.size,flush=True)
except Exception as exc:
    print('SCREENSHOT_FAILURE',repr(exc),flush=True)
PY
echo "=== ISOLATED FILES ==="
find "$BASE/runtime/config" "$BASE/runtime/data" -maxdepth 4 -type f | head -35 || :
echo "=== APP LOG SNIPPET ==="
grep -Ei 'device|error|profile|plugin|configuration|loaded|connected|elgato' "$BASE/logs/opendeck-gui.log" | tail -22 || :
wait "$APP_PID" || :
echo GUI_TEST_CLEANUP=REQUESTED
