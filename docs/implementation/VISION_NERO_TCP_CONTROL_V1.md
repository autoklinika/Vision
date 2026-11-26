# Vision — NERO TCP Control V1

Status: DEV UI and offline MoveIt Servo integration; real drive-enable and
physical teleoperation are not commissioned. This extends draft PR #81.
The previous NERO telemetry, diagnostics and fault history remain unchanged.

## Operator panel

- Control / Sterowanie is a fourth NERO tab.
- The seven drive-enable indicators are real Core-projected feedback.
- Declared linear TCP speed: integer 1–100 mm/s, initial 10 mm/s.
- Declared angular TCP speed: integer 1–30 deg/s, initial 5 deg/s.
- Draft presets (linear/angular): Precision 5/2, Normal 25/10, Fast 50/20.
  These are proposed UI ranges, not certified hardware limits.
- Reference frames BASE (base_link) and TOOL (tcp_link). The official
  NERO model uses the arm group and tcp_link. The physical camera/tool
  transform needs commissioning; the offline model uses zero TCP offset.
- Arrow Up/Down: X+/X−; Left/Right: Y−/Y+; Page Up/Down: Z+/Z−;
  Q/E: Roll−/Roll+; R/F: Pitch−/Pitch+; T/G: Yaw−/Yaw+.
- An explicit local keyboard-input test highlights the selected direction
  and declared speed. It performs no HTTP POST, ROS publication, IK, or
  hardware actuation. Release, Esc/Space, blur and visibility loss clear
  the preview. The key map is Vision's, not a claim about the exact
  upstream keyboard demo's mappings.
- Real enable and WebGUI HOLD are visibly disabled. The existing Stream
  Deck HOLD path remains independent and unchanged. No drive disable
  button, automatic enable or firmware reset is introduced.
- Actual TCP speed is unavailable (not a fabricated zero). It requires
  a fresh validated TCP transform and measured TCP velocity.

## Core/API

GET /api/v1/devices/nero/control is a closed authenticated read-only
projection; it exposes drive-enable feedback, the declared UI ranges,
and explicit LOCKED/NOT_COMMISSIONED/NOT_CONNECTED capability state.
It never authorizes movement. IPC operation nero_tcp takes no arguments.
No actuator POST endpoint or production transport exists in this revision.
The browser declaration is not yet submitted to a real motion owner.

nero_tcp.twist_intent validates axis, direction, reference frame and
integer declaration, converts mm/s to m/s and deg/s to rad/s, and returns
a single-axis Cartesian velocity vector. This helper does not implement
inverse kinematics and is used only in the offline Servo fixture.

## Official MoveIt Servo 2.12.4 test

The VENTUNO ARM64 apt package is extracted to an isolated NVMe overlay,
not installed into /opt/ros. It contains upstream servo_node and
servo_keyboard_input. The test uses the official local AgileX URDF/SRDF
and KDL group arm, speed_units, synthetic JointState data, and a dedicated
local ROS domain 223. Its trajectory output is a capture-only topic;
no controller, SDK, CAN access or real motion is instantiated.

The smoke check selects TWIST mode and exercises BASE X and TOOL YAW at
the default declared 10 mm/s and 5 deg/s. It checks finite seven-joint
trajectory output, excluding the tiny synthetic state jitter used to
drive the state monitor. Collision checks are enabled for the test model;
there is no real station planning scene, validated camera collision mesh
or measured TCP. The observed status was 1 (deceleration near singularity).
No claim is made that physical speeds, collision avoidance on the station,
or hardware HOLD were validated. Smoothing was disabled in this isolated
smoke test. The live configuration must be determined in acceptance.

The fixture is tools/lab/nero_servo/servo_smoke.py. It requires an explicit
NVMe overlay and local ROS domain 223; the real domain 181 is not used.
The official package and generated logs/models are local build artifacts
and excluded from version control.

## Remaining hardware integration

The active guarded ROS driver currently has no enable/motion admission path.
Implement and commission a single-owner transport coordinated with Core,
the existing HOLD latch, local operator supervision, fresh feedback,
watchdog/lease expiry, the approved tool transform and current planning
scene. A real motion path needs explicit enable readback and a separate
acceptance of the Servo-to-existing-controller trajectory bridge.
The keyboard test is not that bridge. Retain the existing locked default
and never substitute a second direct CAN writer.
