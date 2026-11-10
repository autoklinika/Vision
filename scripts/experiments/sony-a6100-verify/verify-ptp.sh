#!/usr/bin/env bash
# Run as arduino AFTER udev rule is active. Read-only camera session.
set -euo pipefail
BASE="/srv/vision-data/tools/sony-a6100-verify"
GPHOTO="$BASE/root/usr/bin/gphoto2"
export LD_LIBRARY_PATH="$BASE/root/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mapfile -t nodes < <(for p in /sys/bus/usb/devices/[0-9]*; do
  [[ -r "$p/idVendor" && -r "$p/idProduct" ]] || continue
  [[ "$(cat "$p/idVendor")" == "054c" && "$(cat "$p/idProduct")" == "0f0d" ]] || continue
  printf '%03d,%03d\n' "$(cat "$p/busnum")" "$(cat "$p/devnum")"
done)
if (( ${#nodes[@]} != 1 )); then echo "Expected exactly one Sony 054c:0f0d, found ${#nodes[@]}"; exit 2; fi
PORT="usb:${nodes[0]}"
NODE="/dev/bus/usb/${nodes[0]%,*}/${nodes[0]#*,}"
if [[ ! -w "$NODE" ]]; then
  echo "ACCESS_DENIED: $NODE not writable by $(id -un). Verify udev installation."
  ls -l "$NODE"
  exit 3
fi
echo "CAMERA_PORT=$PORT"
timeout 25s "$GPHOTO" --port="$PORT" --camera="USB PTP Class Camera" --summary
echo "PTP_READ_ONLY=PASS"
