# Vision — NERO Servo Bridge V1 (locked integration)

Scope: bridge the official MoveIt Servo trajectory protocol to the existing
guarded NERO owner's arbitration contract, without enabling or moving the
physical arm. This extends NERO TCP Control V1 in draft PR #81.

## Interface and owner boundary

- Existing guarded ROS owner remains the sole CAN owner.
- MoveIt Servo emits trajectory_msgs/JointTrajectory, whereas the existing
  guarded trajectory check takes sensor_msgs/JointState-style name and
  position vectors. These are not interchangeable controller protocols.
- nero_servo_bridge.py decodes the complete timed trajectory, checks its
  seven unique joints, finite vectors, frame, monotonic time offsets,
  bounded horizon, freshness and expiry; reorders each point to J1–J7
  and retains all absolute times.
- LockedBridge selects the first not-expired point only for calling the
  existing arbiter's admission check. It rejects repeated/older windows and
  a changed source. It does not interpolate, retime, execute, or publish
  a command. can_execute is always false.
- CandidateReceiver binds the unique Servo trajectory publisher endpoint,
  and uses sample GID matching when available. Jazzy on VENTUNO does not
  expose publisher_gid in Python MessageInfo, so this non-actuating
  monitor reports GRAPH_ONLY. Graph attribution is not authentication
  and is not sufficient to authorize actuator commands.
- An optional receiver is wired into the versioned replacement guarded
  diagnostics class. Parameter servo_candidate_monitor_enabled defaults
  to false. The receiver is not a separately executable CAN owner.
  The running driver, its guarded trajectory callback, HOLD service and
  deployment are unchanged.
- No new hardware enable, reset, movement or execution interface is exposed.

## Offline integration and live read-only feedback

The upstream ARM64 Servo binary from the existing isolated NVMe overlay
runs in localhost domain 223, with its candidate trajectory output in
a test-only namespace. No actuator, ros2_control controller or real
control topic is used.

tools/lab/nero_servo/servo_smoke.py supports:
- --guarded-bridge: synthetic joint feedback, real upstream Servo, typed ROS
  candidate subscription, exact installed NeroCommandArbiter code and a
  fake read-only SDK. Tests BASE X and TOOL YAW, then the arbiter's latched
  STOP/HOLD state. The synthetic SDK has no motion command methods.
- --live-observer: reads the existing private read-only NERO observation,
  retains its joint-state timestamps, and copies fresh samples into
  the isolated Servo domain. No Twist publisher is created. It checks
  the model via GetPlanningScene. The two test options cannot be combined.

A first measurement exposed callback backlog in the fixture; the fixture
now uses latest-sample QoS and drains callbacks independently of its sample
rate. Servo's rolling-window header need not equal current time; expiry
must be evaluated using header plus time_from_start, not merely the
header or the last position. This is test evidence, not a measured
physical controller scheduling guarantee.

Recorded results on VENTUNO:
- 101 BASE X and 100 TOOL YAW valid locked windows.
- No permission to execute; the existing arbiter's HOLD latch remained
  effective after a new candidate. The observed source attribution was
  GRAPH_ONLY.
- Live model readback: 7/7 positions, 17 distinct observed source samples,
  maximum compared position error 0 rad; zero Twist publishers.
- The first receiver test revealed missing publisher_gid in Jazzy callback
  metadata; the subsequent synthetic feedback test revealed a test-clock
  ordering error. Both are accounted for in the final non-actuating test.
- No actual motion or enable operation was issued.

## Remaining commissioning boundary

This is a functional read-only bridge and validated candidate protocol,
not yet a physical trajectory controller. A production execution transport
must preserve Servo timing, establish trustworthy source/lease ownership,
validate the complete moving window against the accepted station geometry,
honor local operator supervision and existing HOLD, and provide measured
drive enable, TCP feedback and watchdog behavior. Do not connect the
capture-only output directly to a raw hardware topic or blindly send the
last trajectory point. No real motion/drive-enable integration is
commissioned by this commit. The active DEV control panel remains locked.
