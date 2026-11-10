#!/usr/bin/env bash
# One-time privileged installation. Does NOT start camera capture.
set -euo pipefail
if (( EUID != 0 )); then
  echo "Run: sudo bash /srv/vision-data/tools/sony-a6100-verify/install-udev.sh"
  exit 2
fi
SRC="/srv/vision-data/tools/sony-a6100-verify/99-vision-sony-a6100.rules"
DST="/etc/udev/rules.d/99-vision-sony-a6100.rules"
if [[ -e "$DST" ]] && ! cmp -s "$SRC" "$DST"; then
  echo "STOP: existing $DST differs; refusing to replace."
  exit 3
fi
install -o root -g root -m 0644 "$SRC" "$DST"
udevadm control --reload-rules
echo "RULE_INSTALLED=$DST"
# Only Sony A6100 PC Remote nodes; don't reset/reenumerate every USB device.
timeout 20s udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=054c --attr-match=idProduct=0f0d --settle
echo "UDEV_CHANGE_TRIGGERED=YES"
for d in /sys/bus/usb/devices/[0-9]*; do
  [[ -r "$d/idVendor" && -r "$d/idProduct" ]] || continue
  [[ "$(cat "$d/idVendor")" == "054c" && "$(cat "$d/idProduct")" == "0f0d" ]] || continue
  bus=$(printf "%03d" "$(cat "$d/busnum")")
  dev=$(printf "%03d" "$(cat "$d/devnum")")
  node="/dev/bus/usb/$bus/$dev"
  stat -c 'SONY_USB_NODE=%n OWNER=%U GROUP=%G MODE=%a' "$node"
done
echo "INSTALL_STEP=COMPLETE"
