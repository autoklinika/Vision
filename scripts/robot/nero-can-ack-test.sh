#!/usr/bin/env bash
# NERO diagnostic: sequential receive-only tests, with CAN ACK enabled on one channel.
set -Eeuo pipefail
if (( EUID != 0 )); then echo "ERROR: run via sudo bash"; exit 1; fi
LOG=/tmp/vision-nero-can-ack-report.log
exec > >(tee "$LOG") 2>&1
echo "NERO CAN ACK TEST $(date --iso-8601=seconds)"
echo "No CAN data/control frames transmitted by this script."
restore_passive() {
  echo "RESTORE_PASSIVE_START"
  for ch in can0 can1 can2; do
    if ip link set "$ch" down && ip link set "$ch" type can bitrate 1000000 listen-only on && ip link set "$ch" up; then
      echo "RESTORED $ch listen-only"
    else
      echo "RESTORE_FAILED $ch; inspect manually"
    fi
  done
  echo "RESTORE_PASSIVE_DONE"
}
trap restore_passive EXIT
trap 'exit 130' INT TERM
for ch in can0 can1 can2; do ip link show "$ch" >/dev/null; done
ip link set can0 down
ip link set can0 type can bitrate 1000000 listen-only on
ip link set can0 up
for ch in can1 can2; do
  echo "TEST_START $ch at 1000000 bit/s, normal mode, 10s"
  ip link set "$ch" down
  ip link set "$ch" type can bitrate 1000000 listen-only off
  ip link set "$ch" up
  ip -details -statistics link show "$ch"
  python3 - "$ch" <<'PY'
import socket, struct, select, sys, time, collections
ch = sys.argv[1]
s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
s.bind((ch,))
ids = collections.Counter()
count = 0
errors = 0
end = time.monotonic() + 10
while time.monotonic() < end:
    ready, _, _ = select.select([s], [], [], min(0.5, max(0, end-time.monotonic())))
    if not ready:
        continue
    raw = s.recv(72)
    if len(raw) < 16:
        continue
    can_id, dlc = struct.unpack("=IB", raw[:5])
    frame_id = can_id & (0x1FFFFFFF if can_id & 0x80000000 else 0x7FF)
    ids[hex(frame_id)] += 1
    count += 1
    errors += bool(can_id & 0x20000000)
    if count <= 5:
        print("FRAME", ch, hex(can_id), "dlc", dlc, "data", raw[8:8+min(dlc,8)].hex(), flush=True)
s.close()
print("RESULT", ch, "frames", count, "error_frames", errors, "ids", ids.most_common(12), flush=True)
PY
  ip -statistics link show "$ch"
  ip link set "$ch" down
  ip link set "$ch" type can bitrate 1000000 listen-only on
  ip link set "$ch" up
  echo "TEST_DONE $ch"
done
echo "TESTS_COMPLETE; passive restore follows"
