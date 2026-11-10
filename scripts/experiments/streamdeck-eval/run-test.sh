#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/srv/vision-data/tools/streamdeck-eval
export XDG_CONFIG_HOME="$BASE/runtime/config"
export XDG_CACHE_HOME="$BASE/runtime/cache"
export XDG_DATA_HOME="$BASE/runtime/data"
export TMPDIR="$BASE/runtime/tmp"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" "$TMPDIR" "$BASE/logs"
if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  echo 'BRAK SESJI GRAFICZNEJ: zaloguj się do pulpitu GNOME jako arduino albo użyj run-headless-test.sh.' >&2
  exit 2
fi
if [ ! -r /dev/hidraw0 ] || [ ! -w /dev/hidraw0 ]; then
  echo 'BRAK UPRAWNIEN HID: potrzebne tymczasowe ACL dla /dev/hidraw0 (bez trwałej reguły udev).' >&2
  exit 3
fi
exec "$BASE/pkg/usr/bin/opendeck" "$@"
