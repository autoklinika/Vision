#!/usr/bin/env bash
# Run as arduino AFTER read-only verify passes. Capture exactly 1 still.
# --keep is intentional: never delete captures on camera after download.
set -euo pipefail
BASE="/srv/vision-data/tools/sony-a6100-verify"
GPHOTO="$BASE/root/usr/bin/gphoto2"
export LD_LIBRARY_PATH="$BASE/root/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mapfile -t nodes < <(for p in /sys/bus/usb/devices/[0-9]*; do
  [[ -r "$p/idVendor" && -r "$p/idProduct" ]] || continue
  [[ "$(cat "$p/idVendor")" == "054c" && "$(cat "$p/idProduct")" == "0f0d" ]] || continue
  printf '%03d,%03d\n' "$(cat "$p/busnum")" "$(cat "$p/devnum")"
done)
if (( ${#nodes[@]} != 1 )); then echo "Expected exactly one Sony 054c:0f0d"; exit 2; fi
PORT="usb:${nodes[0]}"
NODE="/dev/bus/usb/${nodes[0]%,*}/${nodes[0]#*,}"
[[ -w "$NODE" ]] || { echo "ACCESS_DENIED: $NODE"; exit 3; }
OUT="/srv/vision-data/vision/sessions/sony-a6100-test-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
cd "$OUT"
echo "CAMERA=$PORT"
echo "SESSION=$OUT"
echo "CAPTURE_POLICY=ONE_SHOT_KEEP_ON_CAMERA"
# Each invocation requests exactly one capture. No focusing/settings changes.
set +e
timeout 90s "$GPHOTO" --port="$PORT" --camera="USB PTP Class Camera" --keep --filename="sony_a6100_test.%C" --capture-image-and-download 2>&1 | tee capture.log
rc=${PIPESTATUS[0]}
set -e
echo "CAPTURE_EXIT_CODE=$rc"
echo "FILES_CAPTURED:"
find "$OUT" -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
if (( rc != 0 )); then echo "CAPTURE=FAIL_OR_INCOMPLETE"; exit "$rc"; fi
count=$(find "$OUT" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.arw' -o -iname '*.raw' \) | wc -l)
if (( count < 1 )); then echo "CAPTURE=UNVERIFIED_NO_IMAGE"; exit 4; fi
find "$OUT" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.arw' -o -iname '*.raw' \) -exec sha256sum {} +
echo "CAPTURE=PASS"
