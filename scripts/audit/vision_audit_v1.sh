#!/usr/bin/env bash
# Vision hardware/software snapshot. Read-only; no sudo, package installs, or service restarts.
set -u
export LC_ALL=C

section() {
    printf '\n===== %s =====\n' "$1"
}

optional() {
    local executable="$1"
    shift
    if command -v "$executable" >/dev/null 2>&1; then
        "$executable" "$@" 2>&1 || printf 'Command failed: %s\n' "$executable"
    else
        printf 'NOT INSTALLED: %s\n' "$executable"
    fi
}

section 'AUDIT METADATA'
printf 'Audit timestamp UTC: '
date -u '+%Y-%m-%dT%H:%M:%SZ'
printf 'Hostname: '
hostname
printf 'Script: vision_audit_v1 (read-only)\n'

section 'OPERATING SYSTEM'
if [ -r /etc/os-release ]; then
    grep -E '^(PRETTY_NAME|VERSION_ID|ID)=' /etc/os-release
fi
uname -srmo
optional uptime

section 'CPU / MEMORY'
if command -v lscpu >/dev/null 2>&1; then
    lscpu | head -n 45
else
    head -n 40 /proc/cpuinfo
fi
optional free -h
if [ -r /proc/swaps ]; then
    cat /proc/swaps
fi

section 'STORAGE (NVME PRESENCE IS NOT ASSUMED)'
optional lsblk -e7 -o NAME,TYPE,SIZE,TRAN,FSTYPE,MOUNTPOINTS,MODEL
optional df -hT
optional findmnt -no SOURCE,TARGET,FSTYPE /

section 'VIDEO / ACCELERATOR DEVICE NODES'
for dev in /dev/dri /dev/kgsl* /dev/video* /dev/media* /dev/accel* /dev/fastrpc* /dev/adsprpc*; do
    if [ -e "$dev" ]; then
        ls -ld "$dev"
    fi
done
optional lsusb
optional lspci
optional v4l2-ctl --list-devices

section 'LIBRARIES (DISCOVERY ONLY, NOT PERFORMANCE VALIDATION)'
if command -v ldconfig >/dev/null 2>&1; then
    ldconfig -p 2>/dev/null | grep -Ei 'qnn|fastrpc|adsprpc|opencv|gphoto|vulkan|opencl' | head -n 80 || true
else
    printf 'ldconfig not available\n'
fi
if command -v dpkg-query >/dev/null 2>&1; then
    dpkg-query -W -f='${binary:Package}\t${Version}\n' 2>/dev/null |
        grep -Ei 'qcom|qualcomm|qnn|hexagon|fast.?rpc|opencv|gphoto|libcamera|v4l|linux-image' |
        head -n 100 || true
fi

section 'PYTHON / OPENCV'
optional python3 --version
if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import importlib.util; print("cv2 available:", importlib.util.find_spec("cv2") is not None)'
fi

section 'RUNTIME / SERVICES'
optional git --version
optional gh --version
optional docker --version
optional tailscale version
for service in ssh tailscaled NetworkManager docker; do
    if command -v systemctl >/dev/null 2>&1; then
        printf '%s: ' "$service"
        systemctl is-active "$service" 2>&1 || true
    fi
done
if command -v systemctl >/dev/null 2>&1; then
    systemctl --no-pager --plain --type=service --state=failed 2>&1 || true
fi

section 'THERMAL SENSORS (UP TO 16)'
counter=0
for zone in /sys/class/thermal/thermal_zone*; do
    [ -d "$zone" ] || continue
    counter=$((counter + 1))
    [ "$counter" -le 16 ] || break
    printf '%s ' "${zone##*/}"
    if [ -r "$zone/type" ]; then
        tr '\n' ' ' < "$zone/type"
    fi
    if [ -r "$zone/temp" ]; then
        printf ' raw_temperature='
        cat "$zone/temp"
    else
        printf '\n'
    fi
done

section 'LIMITATIONS'
printf '%s\n' 'No functional GPU/NPU inference test, Sony tethered capture, radiometry validation, robot operation or disk write test was performed.'
printf '%s\n' 'Review report for sensitive hardware or network identifiers before sharing or committing.'
