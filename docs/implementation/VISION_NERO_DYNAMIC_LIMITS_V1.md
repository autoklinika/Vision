# NERO dynamic joint limits and current starting state

2026-11-27 operator confirmed that the robot has changed physical position
since PARK V1. PARK is a saved target only, never a teleoperation start
requirement. Every new manual jog starts with the fresh measured joint vector.

The old Vision duplicate SDK and URDF joint tables have been removed.
The optional explicit Core model-URDF and SDK-profile inputs select the
installed manufacturer's description and existing driver's SDK profile.
The preflight reloads limits from the SDK configuration factory and URDF,
with SDK version, firmware profile and SHA-256 of the URDF as provenance.
It does not instantiate an SDK arm or open CAN. Missing/incompatible model
or SDK data yields UNKNOWN, preserving measured positions but withholding
reference ranges. The WebGUI has no embedded reference table.

For eventual manual owner composition, Profile.from_robot_model derives
position limits from the actual owner's SDK configuration and the loaded
expanded robot_description. ManualRuntime independently verifies any
approved profile against those sources. No PARK joint vector is consumed.
Approved speed/tracking caps and the live scene/Servo authority remain
independent requirements. No active motion owner change in this revision.

On VENTUNO the installed pyAgxArm 1.0.0, v121 and official NERO URDF
still report J4 software upper bounds 2.146755 and 2.14 rad, respectively.
The actual position was 2.204734817704277 rad. These reference values
do NOT establish the hardware controller's configured travel limits.

SDK exposes get_joint_angle_vel_limits(joint_index); it sends a read
request to the controller. It is not exposed by the running passive
guarded ROS driver. Actual controller limits have not been queried in
this revision. Future retrieval must use the sole owner and cannot
silently override the SDK/model or commission movement from this pose.

Tests exercise source changes, missing sources, incomplete or incompatible
model, two distinct valid starting states and out-of-range classification.
No physical enable, movement, CAN query, or limit change is issued.
