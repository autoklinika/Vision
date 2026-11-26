# NERO device workspace V1 — read-only telemetry

Owner request, 26.11.2026: implement the existing individual NERO tab.
This version reads actual robot feedback; drive enable/disable and keyboard
control are future, explicitly unimplemented actions. No new actuator access.

## Source and ownership

- Existing guarded NERO ROS 2 node, `/nero_guarded/agx_arm_ctrl_single_node`,
  local domain 181. The observer creates no driver, CAN socket, trajectory
  publisher, enable service client, action client or SetParameters client.
- Exact feedback topics: `/nero_guarded/feedback/joint_states` (JointState),
  `arm_status` and `motor_status` (DiagnosticArray). Reject duplicate nodes,
  ambiguous publishers, incorrect source, invalid names and stale timestamps.
  Unique ROS graph identity is diagnostic provenance, not DDS authentication.
- Position in radians, velocity rad/s and effort Nm follow the installed
  driver's JointState semantics. Display angles and angular velocities in
  degrees; use source timestamp rather than inventing values. The driver
  collects velocity/effort with the joint-state timestamp, not independently
  timestamped measurements. No TCP/world pose claim.
- Arm codes and individual joint limit / communication flags follow the
  installed SDK feedback mapping. Code 6 is joint brake not released.
  Motion code 0 is successful target feedback, NOT an independent proof of
  present standstill or an instruction to move.
- Per-axis driver enable, fault flags, driver and motor temperatures, bus
  voltage and reported bus current (A) are read from motor diagnostics.
  The SDK documents no bus-current sample on some 1.5 kg joint motors; zero
  cannot prove absence of current. STALE/unknown rows do not become zeros.
- Exact read-only GetParameters for `control_enabled`, `auto_enable` and
  `physical_hold_enabled`; these are configured values, not motor enable
  feedback, an asserted HOLD state or motion authorization.
- The observer reads the fixed CAN interface with
  `ip -details -statistics -json link show dev can0`; no CAN transmission,
  interface configuration or reset. Counters are cumulative interface counters.

## Data path and UI

The optional system-Python observer retains matched subscriptions during its
lifetime and writes only a small closed metadata snapshot in a private 0700
volatile runtime directory. No raw messages, serials, pose logs, credentials
or inspection evidence are stored. Snapshot TTL 3 s, individual feedback
packet TTL 2.5 s. Partial sources are displayed separately; malformed/stale
values are withheld. Core uses a read-only protected projection via same-UID
IPC `nero` with empty query. HTTP GET `/api/v1/devices/nero` requires an
authenticated account; POST and arbitrary topic/parameter queries are not
supported. The GUI polls only in the visible active tab and is never an owner
of robot control or readiness.

Fluent 2 keeps the previously accepted menu. The NERO tab shows connection,
arm and drive summaries, J1–J7 telemetry, arm and CAN diagnostics and the
guarded driver's reported parameters. Disabled future controls are labelled
planned. No keyboard event sends a robot command. No production or archived
hardware configuration is changed.

## Deployment and tests

Run only with explicit local ROS environment and an authorized observer
directory:
```sh
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=181 ROS_LOCALHOST_ONLY=1
export PYTHONPATH="<pinned-release>/src"
# directory is an existing private RuntimeDirectory (0700)
/usr/bin/python3 -B -m vision_station.ros_nero --directory "<private-tmpfs-directory>"
```
Core explicitly receives `--nero-directory`. DEV has its own supervised
observer as a dependency of the DEV preview; camera, existing NERO driver
and production services are independent and not restarted.

Offline parser and actual authenticated HTTP/IPC tests:
`python3 -B -m unittest discover -s tests/api -p test_nero.py`.
Synthetic ROS integration in unused local domain 219:
`ROS_LOCALHOST_ONLY=1 PYTHONPATH=src /usr/bin/python3 -B tests/ros/test_nero_observer.py`.
No motion or drive-enable test is part of this package. Live acceptance
requires only the existing feedback publishers and verifies unchanged
operational processes. It does not establish robot calibration, safety
certification or authorization to move.
