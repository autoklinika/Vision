# NERO controller limit observation — 2026-11-27

Observation: 10:06:19 CET, VENTUNO, firmware profile v121, installed pyAgxArm
1.0.0. The existing guarded SDK class was temporarily used as the sole CAN
owner during a bounded maintenance read. Both Core instances were idle, all
seven drives disabled, no reported fault mask, and no measured movement.
The original guarded service was restored and its live feedback verified.

The vendor get_joint_angle_vel_limits() returned fresh, axis-identified
angle limits and maximum joint velocity for all seven axes. Exactly seven
CAN query frames were transmitted. There were no enable, disable, position,
reset or configuration-write operations. Before/after encoder positions were
identical and all seven drive enable bits remained false.

| Joint | Controller angle interval (deg) | Controller max velocity (rad/s) |
| --- | --- | --- |
| J1 | -155 to 155 | 3.14 |
| J2 | -100 to 100 | 3.14 |
| J3 | -158 to 158 | 3.14 |
| J4 | -58 to 123 | 3.14 |
| J5 | -158 to 158 | 3.92 |
| J6 | -42 to 50 | 3.92 |
| J7 | -90 to 90 | 3.92 |

Controller position limits match installed SDK configuration to within
0.000001 rad (rounding). The official URDF has slightly more conservative
ranges, notably J4 upper 2.14 rad (122.612968 deg). Actual J4 was
2.204734817704277 rad (126.322 deg), 3.322 deg above the controller's
configured upper limit and 3.709032 deg above the model upper limit.
The other six measured joint positions were within all three references.

This observation is not a motion authorization. Do not enlarge the SDK,
URDF or controller limits or automatically retarget PARK to admit this
state. Establish the manufacturer's supported out-of-range recovery and
complete real manual pipeline commissioning separately.

Raw observation and query log retained privately on the VENTUNO NVMe,
in the staging worktree's .diagnostics-build/observed-controller-limits-02.
The query helper and its tests are reusable; the maintenance script is not
a deployed service and must only be run after exclusive ownership and idle,
disabled-drive preflight. The default deployed control API is unchanged.
