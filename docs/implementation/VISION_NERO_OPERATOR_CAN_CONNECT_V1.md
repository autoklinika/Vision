# NERO operator CAN connection — V1

Operator decision (2026-11-28): CAN ownership is requested explicitly in the
MANUAL Control panel. Startup and polling never request a mode switch. ENABLE
is a separate operation and requires independently observed CAN mode.

The firmware V121 SDK (applicable to Nero 1.22) implements CAN takeover inside
disable(). A supervised isolated SDK call on the real station confirmed the
transition from Ethernet 0x03 to CAN_CTRL 0x01 with all seven drives remaining
disabled. The GUI command uses the existing native owner, not a second SDK
instance or raw CAN frames. It invokes disable(timeout=0.) once, then checks
fresh mode, drive, velocity and joint-position feedback.

The private manual transport requires an authenticated local operator, idle
Core and idle native owner, no active motion binding, fresh stationary
feedback, all drives disabled and no active drive faults. The action does not
grant a manual session, bypass ENABLE admission, or require Servo to be
motion-ready. It is not available in a passwordless or review-only listener.
A rejected or unverified operation is never retried automatically.

The independent live telemetry drives the displayed mode; successful command
response does not optimistically change it. The physical button path still
requires native owner commissioning and supervised acceptance. No production
deployment, PARK/HOME, startup takeover, or actual drive activation is included.
