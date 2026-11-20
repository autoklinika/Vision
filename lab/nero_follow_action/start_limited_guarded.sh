#!/usr/bin/env bash
# NERO: one C7 ROS2 limited FollowJointTrajectory action with operator HOLD preserved.
set -Eeo pipefail
ROOT=/srv/vision-data/experiments/c7-nero-follow-action-20261120
source /opt/ros/jazzy/setup.bash
source /srv/vision-data/experiments/ros2-nero-offline-20261116/install/setup.bash
source "$ROOT/ws/install/setup.bash"
source "$ROOT/config/one_shot_mode.env"
export ROS_DOMAIN_ID=181 ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
case "$VISION_NERO_LAB_SINGLE_SEGMENT_ENABLED" in
  true|false) : ;;
  *) echo BAD_ARM_MODE >&2; exit 3;;
esac
if ! ip -details link show can0 | grep -q 'bitrate 1000000'; then
 echo WRONG_CAN_BITRATE >&2; exit 4
fi
exec ros2 run agx_arm_ctrl vision_nero_single_segment --ros-args \
  -p arm_type:=nero -p effector_type:=none -p auto_enable:=false \
  -p control_enabled:=false -p physical_hold_enabled:=true \
  -p physical_single_segment_enabled:="$VISION_NERO_LAB_SINGLE_SEGMENT_ENABLED" \
  -p one_shot_authorization_file:="$ROOT/validation/one_shot_j2_authorization_20261120.json" \
  -r __ns:=/nero_guarded
