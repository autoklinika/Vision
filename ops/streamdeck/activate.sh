#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/srv/vision-data/tools/streamdeck-prod
TARGET=/etc/udev/rules.d/71-vision-streamdeck-plus.rules
echo "Install specific 0fd9:0084 udev rule and enable arduino linger."
sudo install -m 0644 "$ROOT/systemd/71-vision-streamdeck-plus.rules" "$TARGET"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw --action=change
sudo loginctl enable-linger arduino
sleep 1
DECK_HID=""
for h in /sys/class/hidraw/hidraw*; do
  [[ -e "$h/device/uevent" ]] || continue
  if grep -iq "HID_ID=0003:00000FD9:00000084" "$h/device/uevent"; then
    DECK_HID="/dev/$(basename "$h")"
    break
  fi
done
if [[ -z "$DECK_HID" || ! -w "$DECK_HID" ]]; then
  echo "STREAM_DECK_PLUS_ACCESS_DENIED_OR_ABSENT ${DECK_HID:-none}" >&2
  exit 12
fi
echo "HID_ACCESS_OK $DECK_HID $(stat -c '%U:%G %a' "$DECK_HID")"
mkdir -p "$HOME/.config/systemd/user"
ln -sf "$ROOT/systemd/vision-opendeck.service" "$HOME/.config/systemd/user/vision-opendeck.service"
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
systemctl --user daemon-reload
systemctl --user enable --now vision-opendeck.service
systemctl --user status vision-opendeck.service --no-pager -l
