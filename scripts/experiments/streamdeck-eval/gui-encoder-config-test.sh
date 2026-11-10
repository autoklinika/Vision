#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/srv/vision-data/tools/streamdeck-eval
PROFILE="$BASE/runtime/config/opendeck/profiles/sd-<LOCAL_DECK_SERIAL>/Default.json"
BEFORE="$BASE/logs/Default.before-encoder-gui-test.json"
AFTER="$BASE/logs/Default.after-encoder-gui-test.json"
test -f "$PROFILE"
cp "$PROFILE" "$BEFORE"
export DISPLAY=:97
export XDG_CONFIG_HOME="$BASE/runtime/config"
export XDG_CACHE_HOME="$BASE/runtime/cache"
export XDG_DATA_HOME="$BASE/runtime/data"
export TMPDIR="$BASE/runtime/tmp"
export GDK_BACKEND=x11
export LIBGL_ALWAYS_SOFTWARE=1
export WEBKIT_DISABLE_COMPOSITING_MODE=1
export GSETTINGS_BACKEND=memory
APP_PID=""
XVFB_PID=""
cleanup() {
  if [ -n "$APP_PID" ]; then kill -INT "$APP_PID" 2>/dev/null || :; wait "$APP_PID" 2>/dev/null || :; fi
  if [ -n "$XVFB_PID" ]; then kill "$XVFB_PID" 2>/dev/null || :; wait "$XVFB_PID" 2>/dev/null || :; fi
  cp "$BEFORE" "$PROFILE"
  echo "ISOLATED_PROFILE_RESTORED=YES"
}
trap cleanup EXIT
"$BASE/pkg/usr/bin/Xvfb" :97 -screen 0 1440x900x24 -nolisten tcp >"$BASE/logs/xvfb-encoder-drag.log" 2>&1 &
XVFB_PID=$!
sleep 1
kill -0 "$XVFB_PID"
dbus-run-session -- timeout --signal=INT --kill-after=3 28 "$BASE/pkg/usr/bin/opendeck" >"$BASE/logs/opendeck-encoder-drag.log" 2>&1 &
APP_PID=$!
sleep 7
echo "OPENDECK_RUNNING=$(pgrep -f '^/srv/vision-data/tools/streamdeck-eval/pkg/usr/bin/opendeck$' | head -1)"
echo "=== XTEST DRAG DEVICE BRIGHTNESS TO ENCODER 1 ==="
python3 - <<'PY'
import ctypes,time
X=ctypes.CDLL('libX11.so.6')
T=ctypes.CDLL('libXtst.so.6')
X.XOpenDisplay.restype=ctypes.c_void_p
X.XOpenDisplay.argtypes=[ctypes.c_char_p]
X.XFlush.argtypes=[ctypes.c_void_p]
X.XCloseDisplay.argtypes=[ctypes.c_void_p]
T.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
T.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
D=X.XOpenDisplay(b':97')
assert D,'Cannot open display'
def move(x,y):
    assert T.XTestFakeMotionEvent(D,0,x,y,0)
    X.XFlush(D)
def button(pressed):
    assert T.XTestFakeButtonEvent(D,1,1 if pressed else 0,0)
    X.XFlush(D)
try:
    start=(1082,670) # Built-in Device Brightness; no physical rotation during GUI test
    end=(450,584)  # first Stream Deck Plus encoder
    move(*start)
    time.sleep(.25)
    button(True)
    time.sleep(.3)
    for i in range(1,37):
        t=i/36
        move(round(start[0]+(end[0]-start[0])*t),round(start[1]+(end[1]-start[1])*t))
        time.sleep(.035)
    time.sleep(.4)
    button(False)
    print('XTEST_DRAG=COMPLETED start='+str(start)+' end='+str(end),flush=True)
finally:
    X.XCloseDisplay(D)
PY
sleep 5
echo "=== PROFILE AFTER DRAG ==="
cp "$PROFILE" "$AFTER"
python3 - <<'PY'
import json
p='/srv/vision-data/tools/streamdeck-eval/logs/Default.after-encoder-gui-test.json'
d=json.load(open(p))
print('PROFILE_KEYS_NON_NULL=',[(i+1,type(x).__name__) for i,x in enumerate(d.get('keys',[])) if x is not None])
print('PROFILE_SLIDERS_NON_NULL=',[(i+1,type(x).__name__) for i,x in enumerate(d.get('sliders',[])) if x is not None])
print('PROFILE_ENCODER1=',json.dumps(d.get('sliders',[None])[0],ensure_ascii=False)[:1100])
PY
python3 - <<'PY'
from PIL import ImageGrab
p='/srv/vision-data/tools/streamdeck-eval/logs/opendeck-after-encoder-drag.png'
im=ImageGrab.grab(xdisplay=':97')
im.save(p)
print('AFTER_DRAG_SCREENSHOT='+p,flush=True)
PY
wait "$APP_PID" || :
echo 'OPENDECK_APP_ENDED=YES'
