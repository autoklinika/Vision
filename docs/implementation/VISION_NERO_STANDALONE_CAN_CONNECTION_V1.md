# Standalone operator CAN connection — V1

Replaces the GUI dependency on the MANUAL movement runtime. The NERO owner
already provides feedback and HOLD; no MoveIt Servo or trajectory controller
is required for requesting CAN_CTRL.

- Independent GET/POST /api/v1/devices/nero/can-connection.
- Explicit authenticated operator, same-origin POST and fresh operation ID.
- Core checks both its own idle lifecycle and the separate production idle
  interlock. No coexisting manual or clear transport in this composition.
- Private same-UID socket in the single diagnostic guarded ROS owner. The
  owner serializes the operation with HOLD and verifies fresh SDK samples,
  disabled drives, zero motion, no fault, and CAN / WEB / standby mode.
- One invocation of firmware SDK disable(timeout=0.), bounded independent
  readback; never enables drives or issues any trajectory. Already CAN is
  idempotent and emits no command. No TX on startup, polls or retries.
- The GUI displays independent ROS mode readback and does not infer a mode
  transition from the HTTP response. Existing MANUAL movement admission
  remains unchanged.
- DEV must use real operator authentication, not synthetic preview identity.
  Production stays on its current release. Lab owner launch retains the
  original ROS node name, local domain, feedback and HOLD, with a rollback
  to the old diagnostic launch. No physical WEB transition is forced for
  testing while the arm is already in CAN.
