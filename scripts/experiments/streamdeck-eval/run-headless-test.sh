#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/srv/vision-data/tools/streamdeck-eval
export XDG_CONFIG_HOME="$BASE/runtime/config"
export XDG_CACHE_HOME="$BASE/runtime/cache"
export XDG_DATA_HOME="$BASE/runtime/data"
export TMPDIR="$BASE/runtime/tmp"
export DISPLAY=:97 GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$TMPDIR" "$BASE/logs"
if [ ! -r /dev/hidraw0 ] || [ ! -w /dev/hidraw0 ]; then
  echo 'BRAK UPRAWNIEN: /dev/hidraw0. Tymczasowo nadaj ACL użytkownikowi arduino.' >&2
  exit 3
fi
"$BASE/pkg/usr/bin/Xvfb" :97 -screen 0 1280x800x24 -nolisten tcp >"$BASE/logs/xvfb.log" 2>&1 &
XVFB_PID=$!
cleanup() { kill "$XVFB_PID" 2>/dev/null || :; wait "$XVFB_PID" 2>/dev/null || :; }
trap cleanup EXIT
sleep 1
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo 'XVFB_START=FAIL'; tail -20 "$BASE/logs/xvfb.log"; exit 4
fi
echo 'XVFB_START=PASS'
set +e
dbus-run-session -- timeout --signal=INT --kill-after=4 15 "$BASE/pkg/usr/bin/opendeck" >"$BASE/logs/opendeck-headless.log" 2>&1
RC=$?
set -e
echo "OPENDECK_TEST_EXIT=$RC (124 oznacza zaplanowany koniec 15-sekundowego testu)"
echo '=== URZADZENIE / BLE­DY HID ==='
grep -E 'opendeck::elgato|[Hh]id[Ee]rror|Permission denied|[Ff]ailed to connect|[Cc]onnected to|[Dd]evice' "$BASE/logs/opendeck-headless.log" | tail -18 || :
echo "LOG=$BASE/logs/opendeck-headless.log"
