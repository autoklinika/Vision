#!/usr/bin/env bash
# One-time administrator action for Vision Remote MCP.
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo 'Run via sudo' >&2; exit 1; }
BASE=/srv/vision-data/tools/remote-agent
source="$(findmnt -rn --mountpoint /srv/vision-data -o SOURCE 2>/dev/null || true)"
fs="$(findmnt -rn --mountpoint /srv/vision-data -o FSTYPE 2>/dev/null || true)"
uuid="$(lsblk -dn -o UUID /dev/nvme0n1p1 2>/dev/null | tr -d '[:space:]')"
label="$(lsblk -dn -o LABEL /dev/nvme0n1p1 2>/dev/null | tr -d '[:space:]')"
if [[ "$source" != /dev/nvme0n1p1 || "$fs" != ext4 || "$uuid" != 80f1f04c-490c-49cd-8c7a-1baf56bf0c9d || "$label" != VISION_DATA ]]; then
  echo "REFUSING_SETUP: expected NVMe not mounted" >&2
  exit 77
fi
/bin/bash "$BASE/service/verify-nvme.sh"
test -s "$BASE/service/vision-remote-mcp.service"
test -s "$BASE/service/logrotate.conf"
install -o root -g root -m 0644 "$BASE/service/vision-remote-mcp.service" /etc/systemd/system/vision-remote-mcp.service
install -o root -g root -m 0644 "$BASE/service/logrotate.conf" /etc/logrotate.d/vision-remote-mcp
systemctl daemon-reload
systemctl enable --now vision-remote-mcp.service
echo "MCP_UNIT_ENABLED=$(systemctl is-enabled vision-remote-mcp.service)"
echo "MCP_UNIT_ACTIVE=$(systemctl is-active vision-remote-mcp.service)"
echo "MCP_SETUP=PASS"
