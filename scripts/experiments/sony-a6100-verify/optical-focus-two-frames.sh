#!/usr/bin/env bash
# Two stills, one relative focus step, original mode restored on exit.
set -euo pipefail
BASE=/srv/vision-data/tools/sony-a6100-verify
G="$BASE/root/usr/bin/gphoto2"
export LD_LIBRARY_PATH="$BASE/root/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
PORT=usb:001,009
OUT="/srv/vision-data/vision/sessions/focus-step-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
cam() { timeout 25s "$G" --port="$PORT" --camera="USB PTP Class Camera" "$@"; }
if ! lsusb -d 054c:0f0d | grep -q ILCE-6100A; then echo "CAMERA_OFFLINE"; exit 2; fi
initial="$(cam --get-config=/main/capturesettings/focusmode | sed -n 's/^Current: //p' | head -1)"
echo "INITIAL_FOCUS_MODE=$initial"
case "$initial" in Manual|Automatic|AF-A|AF-C|DMF) ;; *) echo "UNKNOWN_FOCUS_MODE"; exit 3;; esac
restore=0
finish() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$restore" -eq 1 ]]; then
    echo "RESTORE_FOCUS_MODE=$initial"
    cam "--set-config=/main/capturesettings/focusmode=$initial" || echo "RESTORE_COMMAND_FAILED"
    result="$(cam --get-config=/main/capturesettings/focusmode | sed -n 's/^Current: //p' | head -1)" || result=UNVERIFIED
    echo "RESTORED_FOCUS_MODE=$result"
    if [[ "$result" == "$initial" ]]; then echo "RESTORE=PASS"; else echo "RESTORE=FAIL"; status=10; fi
  fi
  echo "SESSION=$OUT"
  echo "SESSION_EXIT=$status"
  exit "$status"
}
trap finish EXIT
if [[ "$initial" != Manual ]]; then
  restore=1
  cam --set-config=/main/capturesettings/focusmode=Manual
fi
mode="$(cam --get-config=/main/capturesettings/focusmode | sed -n 's/^Current: //p' | head -1)"
[[ "$mode" == Manual ]] || { echo "MANUAL_MODE_NOT_SET"; exit 4; }
echo "MANUAL_FOCUS_CONFIRMED=PASS"
capture() {
  local idx="$1" rc=0
  echo "CAPTURE_${idx}=START"
  ( cd "$OUT"; timeout 65s "$G" --port="$PORT" --camera="USB PTP Class Camera" --keep "--filename=image_${idx}.%C" --capture-image-and-download ) >"$OUT/gphoto_${idx}.log" 2>&1 || rc=$?
  cat "$OUT/gphoto_${idx}.log"
  [[ "$rc" -eq 0 ]] || { echo "CAPTURE_${idx}=FAILED_EXIT_$rc"; return 5; }
  [[ -s "$OUT/image_${idx}.jpg" || -s "$OUT/image_${idx}.arw" ]] || { echo "CAPTURE_${idx}=NO_IMAGE"; return 6; }
  echo "CAPTURE_${idx}=PASS"
}
capture 1
echo "FOCUS_PLUS_ONE=START"
cam --set-config=/main/actions/manualfocus=1
echo "FOCUS_PLUS_ONE=ACCEPTED"
sleep 1
capture 2
echo "=== FILES ==="
find "$OUT" -maxdepth 1 -type f -printf "%f %s bytes\n"
sha256sum "$OUT"/image_*.jpg
echo "TWO_FRAME_CAPTURE=PASS"
