#!/usr/bin/env bash
# C7 V1: isolated ROS 2 + MoveIt 2 IK QA of ETC3/PCB camera viewpoints.
# No physical robot API, no static TF publisher, no execution action.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ROS_OVERLAY="/srv/vision-data/experiments/vision-nero-moveit-20261117/ws/install/setup.bash"
SESSION="/srv/vision-data/calibration/sessions/20261119-vision-station-v1"
DEFAULT_OUTPUT_ROOT="$SESSION/validation/c7_v1_ik_perception_lab"
PROFILE="$REPO/config/lab/c7_v1_sony_tool_planonly.json"
COLLISION="$REPO/config/lab/c7_v1_sony_collision_proxies.json"
KIND=""
INPUT=""
OUTDIR=""
PID=""

usage() {
  cat <<'USAGE'
Usage:
  run_c7_v1_planonly_moveit.sh --scene /path/to/scene.json [--out-dir /path]
  run_c7_v1_planonly_moveit.sh --perception /path/to/perception.json [--out-dir /path]
  run_c7_v1_planonly_moveit.sh --legacy-etc3 /path/to/historical_etc3.json [--out-dir /path]

Inputs tagged camera-frame-only or historical ECU housing are archived as BLOCKED
without starting MoveIt. Real PCB planning requires explicit PCB-in-table-frame
metadata with traceable provenance. No robot execution is possible in this script.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scene|--perception|--legacy-etc3)
      if [[ -n "$KIND" || $# -lt 2 ]]; then echo 'Exactly one valid input required' >&2; exit 2; fi
      KIND="$1"; INPUT="$2"; shift 2;;
    --out-dir)
      if [[ $# -lt 2 ]]; then exit 2; fi
      OUTDIR="$2"; shift 2;;
    --help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2;;
  esac
done

if [[ -z "$KIND" || ! -f "$INPUT" ]]; then
  echo 'One existing input scene/perception path is required' >&2
  exit 2
fi
[[ -f "$PROFILE" && -f "$COLLISION" && -f "$ROS_OVERLAY" ]] || {
  echo 'Missing C7 LAB profile or local ROS MoveIt overlay' >&2
  exit 2
}
[[ "$(cat /sys/class/net/can0/statistics/tx_packets)" == "0" ]] || {
  echo 'CAN TX already nonzero — fail closed' >&2; exit 3;
}
ip -br link show can0 | grep -q 'DOWN' || {
  echo 'can0 not physically DOWN — fail closed' >&2; exit 3;
}

# All outputs under the explicitly selected NVMe tree, never into repo / eMMC.
if [[ -z "$OUTDIR" ]]; then
  OUTDIR="$(mktemp -d "$DEFAULT_OUTPUT_ROOT/run_$(date -u +%Y%m%dT%H%M%S)_XXXXXX")"
else
  [[ "$OUTDIR" == /srv/vision-data/* ]] || {
    echo 'Output must be on NVMe /srv/vision-data' >&2; exit 3;
  }
  mkdir -p "$OUTDIR"
  [[ ! -f "$OUTDIR/ik_result.json" ]] || {
    echo 'Output already exists: refuse overwrite' >&2; exit 3;
  }
fi
echo "C7_OUTPUT_DIRECTORY=$OUTDIR"
if [[ "$KIND" == "--scene" ]]; then
  SCENE="$INPUT"
else
  python3 "$REPO/scripts/lab/c7_v1_perception_adapter.py" \
      --input "$INPUT" --output "$OUTDIR/perception_import.json" \
      $( [[ "$KIND" == "--legacy-etc3" ]] && echo --legacy-etc3 || : )
  if ! python3 - "$OUTDIR/perception_import.json" "$OUTDIR/scene.json" <<'PY'
import json,sys
from pathlib import Path
source=Path(sys.argv[1]); output=Path(sys.argv[2])
record=json.loads(source.read_text())
if record.get('status')!='UNAPPROVED_PCB_SCENE_READY_FOR_OFFLINE_VIEWPOINTS':
    print('PERCEPTION_TO_PCB_SCENE_BLOCKED',record.get('status'),record.get('reason_codes'))
    sys.exit(4)
scene=record.get('scene')
if not isinstance(scene,dict) or scene.get('schema_version')!=1:
    sys.exit(4)
with output.open('x') as f:
    json.dump(scene,f,indent=2,ensure_ascii=False)
    f.write('\n')
PY
  then
    echo 'REAL_PERCEPTION_NOT_YET_TABLE_PCB_READY; plan-only MoveIt not started'
    exit 4
  fi
  SCENE="$OUTDIR/scene.json"
fi

python3 "$REPO/scripts/lab/c7_v1_photo_viewpoints.py" \
  --profile "$PROFILE" --scene "$SCENE" --output "$OUTDIR/viewpoints.json"

# Only now bring up the lab's private MoveIt model.
# ROS 2 Jazzy setup scripts reference environment keys that may be unset.
set +u
source /opt/ros/jazzy/setup.bash
source "$ROS_OVERLAY"
set -u
export ROS_DOMAIN_ID=201
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# An already-running /move_group may be somebody else's session: never attach.
if timeout 5 ros2 param get /move_group allow_trajectory_execution >/dev/null 2>&1; then
  echo 'Existing MoveIt instance in reserved lab domain. Refuse to reuse it.' >&2
  exit 3
fi

cleanup() {
  rc=$?
  trap - EXIT INT TERM
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    # setsid guarantees a dedicated process group; terminate launch and all its children.
    local pgid
    pgid="$(ps -o pgid= -p "$PID" | tr -d ' ')"
    if [[ "$pgid" == "$PID" && "$PID" != "$$" ]]; then
      kill -TERM -- "-$PID" 2>/dev/null || :
      for _ in $(seq 1 15); do
        if ! kill -0 -- "-$PID" 2>/dev/null; then break; fi
        sleep 0.5
      done
      if kill -0 -- "-$PID" 2>/dev/null; then
        kill -KILL -- "-$PID" 2>/dev/null || :
      fi
      wait "$PID" 2>/dev/null || :
    else
      echo "Unexpected launch PGID $pgid; refusing to kill unrelated processes" >&2
      exit 11
    fi
  fi
  local tx
  tx="$(cat /sys/class/net/can0/statistics/tx_packets)"
  echo "C7_AFTER_STOP can0_TX=$tx" >&2
  if [[ "$tx" != 0 ]]; then exit 9; fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

setsid ros2 launch agx_arm_moveit move_group.launch.py \
  arm_type:=nero effector_type:=none follow:=false \
  allow_trajectory_execution:=false diagnostic_scene:=false \
  > "$OUTDIR/move_group.log" 2>&1 &
PID=$!

ready=0
for _ in $(seq 1 30); do
  kill -0 "$PID" 2>/dev/null || { echo 'MoveIt launcher exited prematurely' >&2; exit 4; }
  if val="$(timeout 5 ros2 param get /move_group allow_trajectory_execution 2>/dev/null)"; then
    if [[ "$val" == *'Boolean value is: False'* ]]; then ready=1; break; fi
    echo 'MoveIt execution unexpectedly enabled — ABORT' >&2; exit 5
  fi
  sleep 0.5
done
[[ "$ready" == 1 ]] || { echo 'Isolated MoveIt not ready' >&2; exit 6; }

python3 -u "$REPO/scripts/lab/c7_v1_moveit_ik_check.py" \
  --candidates "$OUTDIR/viewpoints.json" \
  --profile "$PROFILE" --scene "$SCENE" --collision "$COLLISION" \
  --output "$OUTDIR/ik_result.json" | tee "$OUTDIR/ik_stdout.log"

echo 'C7_LAB_PIPELINE_COMPLETE: IK/Collision/Plans in ik_result.json; execution forbidden'
