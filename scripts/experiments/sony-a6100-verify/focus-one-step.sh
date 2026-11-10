#!/usr/bin/env bash
set -euo pipefail
BASE=/srv/vision-data/tools/sony-a6100-verify
G="$BASE/root/usr/bin/gphoto2"
export LD_LIBRARY_PATH="$BASE/root/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
PORT=usb:001,009
cam() { timeout 22s "$G" --port="$PORT" --camera="USB PTP Class Camera" "$@"; }
if ! lsusb -d 054c:0f0d | grep -q ILCE-6100A; then echo "ABORT_NO_CAMERA"; exit 2; fi
read_mode() { cam --get-config=/main/capturesettings/focusmode | sed -n 's/^Current: //p' | head -1; }
ORIGINAL="$(read_mode)"
echo "FOCUS_MODE_BEFORE=$ORIGINAL"
case "$ORIGINAL" in Manual|Automatic|AF-A|AF-C|DMF) ;; *) echo "ABORT_UNRECOGNIZED_MODE"; exit 3;; esac
restore=0
cleanup() {
  if [[ "$restore" == 1 ]]; then
    echo "RESTORE_FOCUS_MODE_TO=$ORIGINAL"
    if cam "--set-config=/main/capturesettings/focusmode=$ORIGINAL"; then
      echo "RESTORE_COMMAND=PASS"
    else
      echo "RESTORE_COMMAND=FAIL"
    fi
    local after=""
    after="$(read_mode || true)"
    echo "FOCUS_MODE_AFTER=$after"
    if [[ "$after" == "$ORIGINAL" ]]; then echo "RESTORE_VERIFIED=PASS"; else echo "RESTORE_VERIFIED=FAIL"; fi
  fi
}
trap cleanup EXIT
if [[ "$ORIGINAL" != "Manual" ]]; then
  restore=1
  echo "SWITCH_TO_MANUAL=START"
  cam "--set-config=/main/capturesettings/focusmode=Manual"
  echo "SWITCH_TO_MANUAL=COMMAND_OK"
  NOW="$(read_mode)"
  echo "FOCUS_MODE_IN_TEST=$NOW"
  [[ "$NOW" == Manual ]] || { echo "ABORT_MF_NOT_CONFIRMED"; exit 4; }
fi
echo "FOCUS_COMMAND=ONE_STEP_PLUS_1"
cam "--set-config=/main/actions/manualfocus=1"
echo "FOCUS_COMMAND_RESULT=ACCEPTED"
echo "MANUALFOCUS_PROPERTY_AFTER:"
cam --get-config=/main/actions/manualfocus | head -14
echo "FOCUS_TEST_COMPLETED"
