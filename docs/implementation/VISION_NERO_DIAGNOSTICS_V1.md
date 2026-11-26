# Vision — NERO Diagnostics V1

Owner approved the architecture on 26 November 2026. Scope is the existing
Fluent 2 NERO workspace. Production deployment, drive enable/disable,
keyboard control, controller reset and motion are explicitly out of scope.

## Data provenance and code catalog

The existing NERO telemetry contract remains unchanged. Core interprets three
separate manufacturer code families using the installed PyAgxArm 1.0.0 /
NeroFW.V121 definitions, not frontend heuristics or automotive DTC semantics.

- ARM_STATUS: one byte; known 0x00–0x0F, other values unknown.
- ARM_MASK: communication bits 0–6, angle-limit bits 8–14, bits 7 and 15
  reserved. SDK setter mapping is authoritative for the uint16 representation.
- DRIVE_STATUS: bits 0–5 and 7 are fault flags, bit 6 is enable state only.
  Mask 0xBF excludes enable from fault history.
- Vision severity policy is documented in nero_diagnostics.py. It is not
  firmware readiness or motion authorization.

The source definitions were checked in the local installed SDK
msgs/nero/default/feedback/arm_feedback_status.py, arm_feedback_low_spd.py,
drivers/nero/default/driver.py and local docs/nero/nero_api.md. Redundant
decoded flags must agree with raw values. Missing, stale, inconsistent or
ambiguous data never resolves an episode.

## Core, IPC, HTTP and storage

The independent Core owns the decoder, history worker, admission checks and
operation journal. Explicit --nero-history-directory points to an existing
private (0700) NVMe directory; the SQLite file is 0600, WAL, synchronous FULL.
History samples the existing protected observer independently of browser
polling. Changes create or resolve episodes; a recurrent fault gets a new ID.
firstSeen/lastSeen are observed feedback times, not an ECU internal DTC
timestamp. V1 passive motor feedback retains the ROS array publication
timestamp; only the new clear evidence has per-axis source-frame timestamps.
Persistent unchanged episodes update lastSeen on disk no more than every
five seconds and flush on orderly shutdown. Gaps keep last-observed ACTIVE
episodes. Brief transient events between observations can be missed.
No historical DTC memory API was identified in the installed SDK.

The immutable catalog identifier, code, severity and description are stored
with each episode. A future catalog change requires an explicit migration.
The history database is separate from the inspection journal and never goes
into Git. Retention is currently unbounded; review the policy after operational
experience. Clear attempts are reserved durably before dispatch, linked to
the current episodes in the scope, and recorded separately even when none
exist. A crash during dispatch yields UNVERIFIED and never auto-replays.

Authenticated routes:
- GET /api/v1/devices/nero/diagnostics
- GET /api/v1/devices/nero/history?source=ALL&status=ALL&before=0
  (source ALL/ARM/J1–J7, status ALL/ACTIVE/RESOLVED, descending ID cursor,
  up to 50 episodes)
- GET /api/v1/devices/nero/clear-history?source=ALL&before=0
  (scope filter, up to 20 attempts)
- POST /api/v1/devices/nero/clear (operator, exact same origin and WebGUI
  header; exact instanceId, operationId, scope: 1–7 or 255).

The HTTP and IPC layers reject malformed contracts. Clear admission checks
current Core instance, idle state, complete diagnostic coverage, all drives
reported disabled, CAN ERROR-ACTIVE, control/auto-enable disabled, and a
separate idle interlock. The lifecycle lock protects the owning Core against
concurrent inspection start. The read-only secondary Core interlock is not a
cross-process reservation: before real DEV commissioning there must be
exclusive maintenance ownership (no independent production inspection start).
The UI clearAvailable indicates configured Core admission, not proof of a
commissioned or currently reachable ROS service.

## Guarded owner extension and verification

tools/ros2/vision_nero_diagnostics_interfaces contains the typed ROS 2 message
and service. ros_nero_guarded_diagnostics.py is a versioned subclass of the
existing VisionNeroGuardedNode in the installed lab workspace. It must
REPLACE, never accompany, that owner. It adds the typed diagnostic evidence
topic and (only when explicitly commissioned) a narrowly scoped service:
  /nero_guarded/diagnostics/clear_joint_errors

No new CAN socket, generic SDK commands, reset, drive enable or trajectories.
The existing guarded HOLD behavior remains; a STOP invalidates a clear
verification and both use a serialized SDK transmit section. The new owner
uses a multi-threaded executor with a separate diagnostic callback group.
This executor and actual replacement-owner behavior have not been
commissioned on hardware; do not switch the operational unit during coding.

The driver defaults to diagnostics_clear_enabled=false. It independently
checks locked motion, no drive enable, fresh SDK evidence, CAN state and
one-use local approval. The local approval helper requires an interactive
terminal on an actual active, non-remote logind seat0 session. A grant binds
one operation ID and scope, expires after 60 s and is consumed once. This is
a local operator-presence workflow, not protection against a privileged or
same-UID process. A remote browser cannot create the grant. DDS graph
uniqueness is provenance, not DDS authentication. Local kiosk integration
of this approval workflow remains an operational acceptance item.

PyAgxArm clear_joint_error returns None, and its CAN send path may suppress
some transmission errors. The result records whether the SDK call was
invoked (or unknown if transport failed), never an unproven CAN ACK.
Before/after evidence includes the actual SDK arm timestamp and all seven
driver timestamps; no ROS publication timestamp is substituted. Samples are
bounded to 0.5 s of age. Two distinct consecutive post-command source-frame
sets with identical targeted fault state are needed for verification.
The SDK cache is mutable; individual read coherence is checked, but this is
not a synchronous hardware snapshot of all axes. Verification uses
independent fresh readback, not causal proof of controller acknowledgement.
The firmware-specific effectiveness of clear with disabled drives remains
unverified. No automatic retries, no motion authorization.

Results: CLEARED, PARTIAL, STILL_ACTIVE, NO_ACTIVE_FAULTS, UNVERIFIED,
REJECTED, FAILED, with per-axis results, scope, reason, before/after evidence
and operation ID. ARM_STATUS is displayed independently and is not reset
by a joint-clear operation.

## WebGUI

The existing NERO tab keeps Telemetry as default and introduces Diagnostics
and Fault history. Current entries are decoded by Core, with HEX family,
source, description, severity and coverage. History filters and cursors
are server-side. The operator prepares one explicit intent, locally approves
the ID and scope, and explicitly executes it; no automatic submission.
The clear result is independent of motion readiness. EN/PL translations are
included. Existing planned drive and keyboard controls remain disabled.

## Tests and DEV rollout

Build the interfaces only in an isolated NVMe workspace; tests for ROS use
local domain 219 and synthetic nodes. The actual VENTUNO domain 181 / CAN
owner is not modified or started by these tests.

- python3 -B -m unittest discover -s tests/api -p 'test_nero*.py'
- python3 -B -m unittest discover -s tests/api -p 'test_*.py'
- ROS tests/ros/test_nero_observer.py and test_nero_clear_service.py, with
  generated interfaces and isolated domain 219.
- WebGUI: typecheck, vitest, station build, focused browser regression.

For subsequent read-only DEV acceptance, configure a separate private
history directory and point the isolated Core at the existing read-only
observer. Do not configure any clear transport options yet. The new history
starts at that acceptance, not retroactively from older NERO snapshots.
Physical clear commissioning is separate, supervised locally, after checking
the sole-owner replacement, active local approval path and cross-Core
maintenance exclusion. No induced damaging fault or movement is required.
