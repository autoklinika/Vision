# NERO joint reference-limit preflight V1

2026-11-27: the actual encoder feedback was compared to the installed
pyAgxArm NeroFW.V121 SDK configuration and the official NERO URDF at
agx_arm_ros revision 5051114. These are reference software limits, not
a fresh query of firmware-configured limits or mechanical travel.

Three fresh samples reported J4 = 2.204734817704277 rad (126.322 deg),
above SDK 2.146755 rad (123.000 deg) and URDF 2.14 rad (122.613 deg).
The six other joints were within both sets of reference limits.
The arm reported state 6 (joint brakes not released), mask zero, with
all seven drives disabled. No CAN command was issued.

The read-only TCP API now reports the seven positions, both reference
ranges and classification (within/outside/unknown). Missing or stale
feedback is not classified as normal. The GUI enable control requires
an in-range report, in addition to the existing owner session conditions.
The candidate native manual owner profile must be contained in both SDK
and model bounds. Neither the URDF nor SDK bounds were modified.

An in-range result does not commission physical motion. The installed
tool/scene and live Servo/JTC authority still require the previously
identified acceptance. Do not bypass the out-of-range condition or
attempt automatic return-to-park. Verify the observed condition and use
the manufacturer's supervised recovery procedure if necessary.
