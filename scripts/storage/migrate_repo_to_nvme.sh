#!/usr/bin/env bash
# Vision repository migration: eMMC -> NVMe, preserving ~/Vision symlink.
# Run as arduino, never with sudo. The previous copy is retained for rollback.
set -Eeuo pipefail
umask 077

SRC=/home/arduino/Vision
ROOT=/srv/vision-data
DST=/srv/vision-data/projects/Vision
DEVICE=/dev/nvme0n1p1
EXPECTED_LABEL=VISION_DATA
MODE="${1:---check}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[[ "$MODE" == --check || "$MODE" == --migrate ]] || fail 'Usage: bash migrate_repo_to_nvme.sh --check|--migrate'
[[ "$(id -un)" == arduino ]] || fail 'Run this as user arduino without sudo.'
[[ -d "$ROOT" ]] || fail "Missing mountpoint directory: $ROOT"
mount_source="$(findmnt -rn --mountpoint "$ROOT" -o SOURCE 2>/dev/null || true)"
mount_fstype="$(findmnt -rn --mountpoint "$ROOT" -o FSTYPE 2>/dev/null || true)"
[[ -n "$mount_source" ]] || fail "NVMe is NOT mounted on $ROOT (fail-closed)."
[[ "$mount_fstype" == ext4 ]] || fail "Wrong filesystem: $mount_fstype (expected ext4)."
[[ -b "$DEVICE" ]] || fail "Expected NVMe partition not available: $DEVICE"
[[ "$(readlink -f -- "${mount_source%%\[*}")" == "$(readlink -f -- "$DEVICE")" ]] || fail "Unexpected mount source: $mount_source"
label="$(lsblk -dn -o LABEL "$DEVICE" | tr -d '[:space:]')"
[[ "$label" == "$EXPECTED_LABEL" ]] || fail "Unexpected partition label: $label"
[[ -w "$ROOT" ]] || fail "NVMe mount is not writable by $(id -un)."

if [[ -L "$SRC" ]]; then
    [[ "$(readlink -- "$SRC")" == "$DST" ]] || fail "The existing symlink points somewhere else: $SRC"
    [[ -d "$DST/.git" ]] || fail "Symlink exists, but target has no git repository: $DST"
    info "ALREADY_MIGRATED: $SRC -> $DST"
    info "NVME_MOUNT=PASS"
    exit 0
fi

[[ -d "$SRC/.git" ]] || fail "Source is not a normal Git clone: $SRC"
[[ ! -e "$DST" && ! -L "$DST" ]] || fail "Target already exists; not overwriting: $DST"
STAGE="${ROOT}/projects/.Vision-migration-staging"
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] || fail "Old staging directory exists: $STAGE"

remote="$(git -C "$SRC" remote get-url origin 2>/dev/null || true)"
case "$remote" in
    git@github.com:autoklinika/Vision.git|https://github.com/autoklinika/Vision|https://github.com/autoklinika/Vision.git) ;;
    *) fail "Unexpected git origin: $remote" ;;
esac
[[ -z "$(git -C "$SRC" status --porcelain -uall)" ]] || fail 'Git has changes/untracked files. Review them before migration.'

info "NVME_MOUNT=PASS ($mount_source, $mount_fstype, $label)"
info "GIT_SOURCE=PASS ($remote)"
info "DESTINATION=$DST"
[[ "$MODE" == --migrate ]] || { info 'PREFLIGHT=PASS; run again with --migrate'; exit 0; }

mkdir -p -- "${ROOT}/projects"
cp -a -- "$SRC" "$STAGE"
diff -qr -- "$SRC" "$STAGE" >/dev/null || fail "Copy verification failed; source untouched; staging remains: $STAGE"
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$(git -C "$STAGE" rev-parse HEAD)" ]] || fail 'Copied repository commit differs.'
mv -- "$STAGE" "$DST"
BACKUP="${SRC}.pre-nvme-$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$BACKUP" && ! -L "$BACKUP" ]] || fail "Backup path collision: $BACKUP"
mv -- "$SRC" "$BACKUP"
if ! ln -s -- "$DST" "$SRC"; then
    mv -- "$BACKUP" "$SRC"
    fail 'Symlink creation failed; restored source directory.'
fi

[[ "$(readlink -- "$SRC")" == "$DST" ]] || fail 'Post-migration symlink verification failed.'
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$(git -C "$BACKUP" rev-parse HEAD)" ]] || fail 'Post-migration git HEAD verification failed.'
[[ -z "$(git -C "$SRC" status --porcelain -uall)" ]] || fail 'Post-migration git status is dirty.'

info "MIGRATION=PASS"
info "SOURCE=$SRC (symlink)"
info "DESTINATION=$DST (NVMe)"
info "ROLLBACK_BACKUP=$BACKUP (eMMC; do NOT delete until you have validated VS Code and git)"
info 'Reopen the folder in VS Code after migration, and run: cd /home/arduino/Vision'
