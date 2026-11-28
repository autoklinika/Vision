#!/usr/bin/env bash
# Explicit diagnostic owner composition; no auto-enable, no move commands.
set -Eeo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source /opt/ros/jazzy/setup.bash
source /srv/vision-data/experiments/ros2-nero-offline-20261116/install/setup.bash
source /srv/vision-data/experiments/nero-stop-hold-integration-20261117/ws/install/setup.bash
export ROS_DOMAIN_ID=181 ROS_LOCALHOST_ONLY=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"
exec /usr/bin/python3 -B -m vision_station.ros_nero_can_owner --ros-args -p arm_type:=nero -p effector_type:=none -p physical_hold_enabled:=true -p auto_enable:=false -p control_enabled:=false -r __ns:=/nero_guarded
