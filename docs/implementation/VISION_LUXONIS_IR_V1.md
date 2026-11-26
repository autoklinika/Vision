# Luxonis — manual IR control V1

Operator request, 2026-11-26: add manual IR controls to the existing Luxonis
tab, without changing the accepted navigation or VGP image resolution.

DepthAI ROS v3 documents `driver.i_enable_ir` as an initialization parameter,
and `driver.r_laser_dot_intensity` / `driver.r_floodlight_intensity` as runtime
parameters (normalized 0–1). Enable the driver capability in the local
installed profile, but explicitly initialize both intensity values to zero.
Only these three local YAML values differ from the frozen VGP profile;
resolution, calibration and all archived sources stay unchanged.

The UI exposes independent Dot and Flood switches. ON is 0.6 (60%); OFF is
0.0. These are runtime-only settings, not saved preferences: both are off
after camera startup/restart. The GUI derives switch state from current
driver parameters or the newer validated command readback. A driver readback
is confirmation of the parameter, not an independent measurement of IR power.

The closed POST `/api/v1/devices/luxonis/ir` accepts only current Core
instance ID, channel dot/flood, and a boolean. Same-origin operator
authorization precedes IPC. The Core admits a command only while idle,
with no recovery marker, a fresh unambiguous standalone /oak in domain
186, USB detection, both image endpoints and supported live IR parameters.
DEV additionally requires a separate read-only production Core idle check.
This is an explicit manual diagnostic action; it does not provide an
inspection authorization or expose arbitrary ROS parameters.

The bounded adapter uses the fixed existing /oak GetParameters and
SetParametersAtomically services. It changes only the selected runtime
parameter and checks both channels before/after. It verifies the unique
camera node, exact stream endpoints and standalone systemd owner. No driver
restart per toggle, no second device owner, no retries on uncertain outcomes.
The web process does not import ROS or execute commands. The feature is
explicitly enabled in the Core composition, disabled by default elsewhere.

Configuration: `/srv/vision-data/config/luxonis/rgbd.yaml` (private installed
copy, backed up before modification). The permanent service retains its
autostart and watchdog. The only required camera restart is the initial
configuration change enabling the IR runtime feature with zero intensity.
