# Vision — NERO Manual Execution V1

Status: implementation candidate, **not physically commissioned**. DEV keeps
all physical commands blocked. The sole current guarded driver is unchanged.

## Architecture

- The existing operator panel and speed declaration remain the client.
- Authenticated, explicitly configured local maintenance WebGUI -> Core ->
  private same-UID owner socket -> ManualEngine in the sole guarded CAN
  owner. No second SDK/CAN writer, no raw command HTTP endpoint.
- The ManualEngine converts the declared direction and speed to Twist using
  the existing SI conversion. The official MoveIt Servo performs kinematics.
- A compiled ARM64 rclcpp relay validates each Servo trajectory's endpoint
  and sample GID, finite seven-axis points and absolute time window, and
  forwards the complete unmodified trajectory to the official JTC.
- JTC performs timing/interpolation, not Vision. The relay consumes its
  current reference, checks publisher GID, fresh Servo status and valid
  window horizon, and sends positions/velocities through a private inherited
  SOCK_SEQPACKET. It rejects duplicate/replaced publishers and active
  FollowJointTrajectory action goals in the manual controller namespace.
- The existing native AgileX ROS position-command function is the final
  hardware port. The dedicated manual admission state machine shares the
  same TX lock and HOLD latch; legacy arbitrary setpoint topics stay
  blocked. Drive enable uses the vendor SDK within the same owner.
- DDS graph/GID attribution and same-UID sockets are not cryptographic
  isolation against a malicious local process or functional safety.
  Deployment needs an exclusive trusted manual pipeline.

## Session and commands

The optional local-only HTTP command route is disabled by default and
requires authentication as operator, exact loopback Origin, same-origin
request header, a configured Core manual owner socket, and one-use local
seat0 confirmation before enable. Do not proxy this listener. A dedicated
approval directory is required, separate from diagnostic-clear approvals.
The browser prepares an operation ID; the local approval tool records
one-use authorization for 60 s. No enable is issued by the approval tool.

ENABLE is a single explicit SDK invocation. The UI does not display enabled
drives from a service result. The owner requires two consecutive distinct
fresh feedback sets after that invocation, all seven enable bits, normal
arm state and zero fault mask, before READY. If drives are already enabled
and normal, no enable is sent. Partial enable and stale feedback reject.
No implicit reset, disable or auto-enable; no retry after uncertain outcome.

Keyboard input uses a short owner-side lease (300 ms design value), with
monotonic sequence, fresh request timestamps and one session binding.
Key release sends zero Twist; return to READY requires actual settled
feedback and recent valid controller references. Stale feedback, lease
expiry, invalid reference or limits violation latches HOLD. Explicit HOLD
uses the existing guarded callback; no automatic recovery. A session can
expire while idle without disabling drives. The proposed watchdog and
tracking envelope are not physical stopping-time guarantees.

The owner requires explicit motion limits in an accepted profile (not the
draft GUI maximums), checks actual SDK limits and real driver feedback.
Manual Core composition excludes inspection and diagnostic-clear
composition. The native ports require a nonblocking commissioning
authority confirming the accepted live model, TCP, scene, controller and
Servo TWIST state. The owner extension exposes an explicit composition
factory, **not** a mutable commissioning parameter or an enabled-by-default
CLI. No accepted real pipeline authority or physical profile is created
in this commit.

## Tests

- Official Servo 2.12.4 ARM64, standard ros2_control JTC on GenericSystem,
  dedicated localhost ROS domain 224, all output simulated.
- Final native relay smoke: 127 complete forwarded windows, 301 sampled
  JTC references, 262 source-checked references over the inherited socket.
  Observed Servo status codes 0 and 1. No hardware driver launched.
- Backend tests use fake SDK ports, real Core/private socket/HTTP
  boundaries, check local confirmation, authentication, actor binding,
  explicit enable readback, sequence, lease, release, HOLD, tracking
  envelope, lost feedback and absence of automatic retry.
- Browser fixture exercises two-step enable and held key, declaration,
  release and HOLD. The default DEV listener remains read-only for NERO.
- Live acceptance of the real arm has **not** been performed.

## DDS startup discovery regression

The single verified publisher may briefly have Fast DDS placeholder node
metadata before its identity is discovered. The native relay discards
such samples before the first verified GID; it does not pin them or
clear an already latched fault. After pinning, identity loss, replacement,
multiple publishers and a mismatched known identity still fail closed.
Start the pipeline only after its expected endpoints have been discovered.
A duplicate-publisher test in the isolated GenericSystem fixture verified
that reference delivery stops and does not resume automatically when the
extra publisher disappears.

The complete candidate planning scene (table plus attached tool) was
read back from the Servo planning scene monitor during the isolated
Servo/JTC regression. A valid static state is not evidence of usable
manual speed: near-contact deceleration with the original Servo collision
thresholds can make simulated motion very small. Neither a successful
relay test nor this correction commissions a physical motion profile.
Private station geometry, measured state and full test evidence remain
on the station NVMe, outside Git.

## Physical commissioning still required

Connect the approved station profile and live collision scene to the
official pipeline and implement the concrete pipeline-authority composition.
Use the exact existing installed tool transform; do not guess it or
recalibrate accepted station components unnecessarily. The existing local
mount reconciliation records explicitly unverified tool geometry/clearance;
this implementation does not promote those hypotheses into approved data.

After that, with the operator present, perform controlled owner replacement
(single CAN owner), verify the actual feedback/enable and HOLD behavior and
accepted speed envelope; verify JTC timing and tracking on the physical arm.
Until then no physical command listener/owner factory is enabled, the
existing physical HOLD and operational services are unchanged, and no
actuation claim is made.

## Observed-feedback pipeline admission

The next implementation candidate separates the measured arm state from
the virtual interpolation state. `Routes.physical()` fixes the Servo
joint-state input to the existing guarded NERO feedback topic.
The namespaced JTC uses GenericSystem only as a timing/interpolation
component; its synthetic joint states are not admissible Servo feedback.

`Contract`, `PipelineAuthority` and `RosPipelineMonitor` provide a
concrete read-only observation interface for explicit composition. Before
readiness, the monitor requires the expected source endpoints, Servo
configuration and expanded model, the independently accepted collision
scene fingerprint, actual joint-state agreement, the active official JTC,
the virtual interpolation hardware inventory, and a trusted TWIST-mode
bootstrap confirmation. The native ports additionally compare observed
positions against the owner's fresh SDK cache.

Service reads are asynchronous, in a separate mutually exclusive callback
group; the motion admission callback reads cached evidence only. A
configuration/source mismatch or expiry after verified readiness latches
the observer. Restoration of a publisher or feedback does not auto-rearm.
The existing native relay retains per-sample output GID checks.

The fingerprint covers full collision-relevant scene readback: world and
attached geometry, octomap, allowed-collision entries, fixed transforms,
padding and scale. Dynamic joint states and cosmetic data are excluded.
The expected fingerprint and parameter inventory must come from separate
validation, never blind acceptance of a live readback. A strict comparison
can conservatively reject reordered but otherwise equivalent scene data.

This is not a functional-safety certification. ROS graph metadata is not
cryptographic attribution, and the TWIST confirmation is supplied by the
trusted bootstrap, not a continuous upstream command-type query.
Independent fixture and station contracts cannot be interchanged.

`ManualRuntime` now requires the concrete station monitor and matching
loaded model. During startup its engine stays IDLE until complete evidence
is observed; no initialization command enables drives. No deployment
entrypoint or accepted physical profile is supplied by this change.

Validation on VENTUNO: NERO API/owner tests 62/62; ROS PlanningScene
serialization tests 4/4. These include stale/duplicate/replaced sources,
changed collision permissions, missing endpoints, wrong model/state
routing, SDK disagreement and collision-scene fingerprint sensitivity.
The expanded live-ROS GenericSystem integration attempt was blocked
before execution, so the new service/graph observation adapter still
requires end-to-end ROS acceptance. Physical commissioning has not
been performed. Operational services, geometry and the frozen baseline
remain unchanged.

## Integrated ROS observation regression

The `servo_jtc_smoke.py` fixture now supports `--observe-stationary`
and `--observe-pipeline` in the same isolated GenericSystem domain.
The observation node has its own executor. The fixture uses an independent
synthetic feedback publisher and a distant synthetic obstacle, not the
real station scene or physical feedback. It verifies that the PSM follows
the independently observed state while JTC is stationary.

Corrections found by executing actual ROS 2 Jazzy components:
- Generated numeric JointState fields are arrays; convert to a tuple
  before validation and joint-name reordering.
- Hash normalized message fields in canonical JSON instead of hashing
  CDR bytes. Repeated equivalent PSM responses had different binary hashes.
- Recognize the official generated Servo private-node state subscription
  and pin its DDS endpoint. Reject replacement or a subscription to the
  synthetic JTC state.
- Maintain independently observed live feedback freshness without
  extending the full configuration/scene evidence lease. Reject a gap,
  replay, source replacement, or state disagreement.

Validation on VENTUNO: NERO API/owner tests 67/67; ROS scene and JointState
tests 6/6. Stationary integration passed: stable scene identity, independent
state, verified monitor, feedback-loss latch without auto-resume, and scene
change latch. Separately, the original Servo/JTC transport regression passed
with 128 windows, 300 sampled JTC references and 263 source-checked relay
samples (Servo status 0 and 1).

**Dynamic observation acceptance is still blocked.** The full PSM service
response does not contain a usable state timestamp. A diagnostic run found
a live input age of about 2.5 ms, while the cached scene batch was about
244 ms old; the joint comparison exceeded its 0.005 rad fixture tolerance.
An experimental state-only service poll also produced late responses (one
observed scene state age about 286 ms), including with a dedicated executor.
That experiment is archived locally, not enabled in the candidate. The
conservative mismatch and freshness checks remain active. No tolerances
were relaxed to obtain a passing dynamic result.

The successful stationary and transport tests are separate evidence, not
an end-to-end dynamic acceptance. A reliable timestamped PSM state
observation or independently verified bounded-latency architecture is
required before dynamic acceptance and supervised hardware commissioning.
No operational service or hardware control was changed by these tests.

## Time-aligned dynamic observation — software fixture accepted

The earlier dynamic failure compared a historical, un-stamped
GetPlanningScene state to a different, current JointState. The installed
Servo 2.12.4 PlanningSceneMonitor also publishes maintained-scene updates
on its own publish_planning_scene topic. A diagnostic probe confirmed
source stamps in state-change diffs and also found zero-stamped or retained
snapshots. The latter are not accepted as fresh motion evidence.

The observation authority now maintains a bounded 256-sample history
(maximum horizon 650 ms with the existing default configuration). It
associates the unstamped service state with an observed configuration
inside the bounded request window, using the existing comparison
tolerance; this is a bounded configuration match, not a proof of its
exact acquisition time. The PSM state-change publication is independently
checked against the corresponding source timestamp in the history and
the pinned publisher identity. A changed state without a timely
timestamped witness expires admission. Duplicate/late samples cannot
renew an expired witness. Initial snapshots from before subscription
are not admitted as current observations. The live feedback age limit
remains 150 ms, full configuration/scene evidence age limit remains
500 ms and comparison tolerances remain unchanged. The actual SDK
position comparison remains independent of the historical scene match.

The isolated test keeps the official Servo collision checks, JTC
interpolation and native per-sample relay unchanged. A change to PSM
publication settings was not executed, so this result does not depend
on changing upstream parameters. Geometry and calibration are unchanged.

Validation on VENTUNO:
- NERO API/owner tests 74/74; actual ROS message/scene tests 6/6.
- First complete dynamic fixture: 137 windows, 284 JTC references,
  280 relay samples, 26 time-aligned scene updates.
- Final regression: 137 windows, 290 JTC references, 279 relay samples,
  28 time-aligned scene updates, Servo status 0/1.
- Both complete fixtures verified independent observed state, stable
  scene identity, dynamic readiness, loss-of-feedback latch without
  auto-resume, and scene-change latch after explicit fixture reconstruction.

The diagnostic RViz software-rendered preview was consuming about three
CPU cores. Earlier integration runs with that preview open failed the
existing evidence deadline. The two complete passing runs were performed
after stopping only that diagnostic visualization; operational services
were not restarted. The high-load condition is not accepted. The station
must preserve sufficient compute capacity for the manual pipeline.

This supersedes the earlier blocked dynamic **software fixture** result.
The fixture has a synthetic obstacle and synthetic observed feedback;
it does not constitute real-station geometry/TCP, speed envelope, or
physical execution acceptance. No physical deployment, motion or merge.
