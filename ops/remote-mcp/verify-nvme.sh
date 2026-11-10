#!/usr/bin/env bash
# Preflight for vision-remote-mcp.service; read-only and fail-closed.
set -euo pipefail
ROOT=/srv/vision-data
PART=/dev/nvme0n1p1
UUID=80f1f04c-490c-49cd-8c7a-1baf56bf0c9d
label="$(lsblk -dn -o LABEL "$PART" 2>/dev/null | tr -d '[:space:]')"
uuid="$(lsblk -dn -o UUID "$PART" 2>/dev/null | tr -d '[:space:]')"
source="$(findmnt -rn --mountpoint "$ROOT" -o SOURCE 2>/dev/null || true)"
fstype="$(findmnt -rn --mountpoint "$ROOT" -o FSTYPE 2>/dev/null || true)"
options="$(findmnt -rn --mountpoint "$ROOT" -o OPTIONS 2>/dev/null || true)"
[[ "$source" == "$PART" && "$fstype" == ext4 && "$label" == VISION_DATA && "$uuid" == "$UUID" ]] || {
    echo "NVME_POLICY=BLOCKED: expected $PART ext4 VISION_DATA on $ROOT" >&2
    exit 77
}
[[ ",$options," == *,rw,* ]] || { echo 'NVME_POLICY=BLOCKED: not RW' >&2; exit 77; }
[[ -x "$ROOT/tools/node/bin/node" ]] || exit 78
[[ -f "$ROOT/tools/remote-agent/runtime/lib/node_modules/@wonderwhy-er/desktop-commander/dist/index.js" ]] || exit 78
[[ -d "$ROOT/tools/remote-agent/home/.desktop-commander-device" ]] || {
    echo 'REMOTE_IDENTITY=BLOCKED: authorized identity not available on NVMe' >&2
    exit 77
}
echo 'VISION_REMOTE_NVME=PASS'
