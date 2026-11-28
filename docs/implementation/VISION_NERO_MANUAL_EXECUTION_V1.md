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

## Station-derived offline review candidate

The private review bundle generator now binds the previously documented
post-calibration assembly, unchanged SRDF and scene, historical firmware
limit observation, recorded stationary raised pose, and the nine installed
NERO collision meshes. The candidate URDF changes only the geometry-free
fixed TCP joint. Its proposed reference is the center of the mechanical
mount face with the factory flange axes, not the camera optical center.
The actual operator TCP selection and physical clearance acceptance remain
open. Factory moving joints and collision meshes are unchanged.

The candidate derives position bounds from the intersection of recorded
controller, SDK and model limits; recorded controller maximum velocities
are not approved manual operating speeds. The local preparation tool
checks the installed SDK against its archived reference without opening
a CAN interface. Symlink-installed collision meshes must resolve to the
exact relative filenames in an explicitly named source package. Changes
to a model, scene, manifest or installed mesh are rejected on reloading
the candidate. This is consistency checking, not cryptographic operator
approval. The candidate has no executable physical owner configuration.

The existing isolated GenericSystem smoke fixture accepts the private
candidate explicitly. It reads back both the table and attached tool from
the Servo PSM, checks composed primitive transforms, unchanged allowed
collision matrix and touch links, and verifies the timestamp-aligned
observer. The simulated observation now preserves the mock broadcaster's
original timestamp instead of making a cached sample appear fresh.
The test executor is joined before its ROS handles are destroyed.

Validation on VENTUNO: NERO API/owner tests 84/84, including ten new
candidate-bundle tests; actual ROS message/scene tests 6/6. The complete
candidate dynamic fixture passed (120 trajectory windows, 232 sampled JTC
references, 279 Relay samples, 50 time-aligned scene updates, Servo status
0 and 4). Both independent observed state and the full station scene were
verified; loss of feedback and scene change latched admission. A previous
attempt correctly failed the existing feedback-age limit. The earlier
stationary fixture exposed an executor cleanup race, fixed in the final
passing dynamic run.

The replayed raised pose has no modeled collision, but minimum self
clearance is about 4.49 mm (flange/link5); the model predicts proximity
deceleration. The maximum simulated joint displacement was only
0.0007116 rad. This passes software transport/observation, not a practical
motion-speed envelope or a physical clearance test. No collision threshold
was reduced. The model still contains a diagnostic Sony proxy and the
candidate table transform, rather than a formally approved as-built
station release.

At the start of this work the physical guarded owner was not available:
the boot receiver identity check rejected the currently enumerated USB
device. No receiver configuration, operational service, actuator state,
production or baseline was changed. The actual AgileX receiver and fresh
feedback must be restored before a separate supervised physical acceptance.

## Real feedback — stationary shadow acceptance

The original AgileX USB-CAN receiver became available after the operator
restored the USB hub and restarted VENTUNO. The receiver preflight passed
without configuration changes. The existing guarded owner remains the
sole operational CAN owner, with legacy motion and auto-enable disabled.

The new station_live_shadow.py utility subscribes to the existing joint,
arm and motor diagnostics in local domain 181. Its only service request
there is GetParameters on the guarded owner. The pinned real JointState
is copied with its original source timestamp into isolated domain 232.
The official Servo PlanningSceneMonitor loads the exact offline review
bundle, with its own separate scene input and unused command topics.
No controller manager, relay, motion publisher, command-type selection,
SDK owner or CAN socket is created in the shadow runtime. It is not a
commissioning launcher and cannot grant physical execution authority.

The stationary review requires the seven drives to be disabled and
fault-free, unchanged actual joint position, source identity, bounded
source age and receipt gaps, archived position limits and a matching full
PSM readback. A snapshot of motor diagnostics is not equivalent to
checking fresh per-axis SDK caches at every future motion command.
The scene service has no usable source state stamp; equality is checked
in a stationary pose, not presented as dynamic physical validation.

Observed acceptance: 207 joint observations, 135 arm and 136 motor
diagnostic observations; 160 real joint samples forwarded. Maximum
joint source age 48.25 ms, maximum receipt gap 58.21 ms; five full PSM
readbacks matched the seven measured joint positions exactly, including
the verified table and attached tool with unchanged collision permissions.
CAN counter changes: 17,237 received, no additional drops or errors,
zero transmitted. The isolated runtime was stopped after the test.

The current measured joint vector was also checked in the exact
candidate using the existing native offline proximity probe. No modeled
world or self collision was found; nearest world pair was table/Sony
(6.08 mm) and nearest self pair flange/link5 (8.42 mm).
The factory FK and unchanged arm kinematics agree numerically.
The proposed mechanical mount-face TCP was about 73.99 mm above the
modeled table. These values are model results, not independently
verified physical clearances. The proximity thresholds predict strong
deceleration in this parked configuration; no margin was reduced.

Actual mode remains WEB, with all drives disabled. The candidate is
still a review-only geometry/configuration. No live manual owner or
production launch has been installed. The operator's TCP reference
selection, explicit motion envelope, sufficient actual clearance and
separate supervised commissioning remain required.

## Single-owner composition and Precision V1 review profile

The manual composition module now defines one explicit inventory for
MoveIt Servo, the mechanical mount-face TCP and the owner-side Profile.
The existing guarded-driver extension receives the same-owner factory;
it constructs a RosPipelineMonitor and delegates to ManualRuntime with
the same Profile, model, contract, native HOLD and private IPC socket.
It does not instantiate a second SDK or CAN owner. The factory rejects a
fixture contract, an unrelated HOLD callback or a repeated attachment.
Its wiring tests use doubles, not an actual installed hardware owner.
The factory is not a service, physical commissioning entrypoint or
approval issuer. Only a separately commissioned caller may supply the
physical OwnerWiring; no diagnostic receipt is promoted into approval.

For the initial review, the operator selected the proposed mechanical
mount-face TCP (factory flange axes, not an optical camera center).
The provisional Precision V1 envelope is 5 mm/s linear, 2 deg/s angular,
0.02 rad/s maximum joint-reference velocity, and 0.005 rad tracking
limit. These are engineering choices for the software review, not
verified physical operating speeds. The seven joint position limits
come from the previously recorded intersection of SDK/URDF/firmware.
MoveIt planning velocity parameters are narrowed to the same cap; the
factory URDF, position bounds, manufacturer acceleration settings and
existing collision thresholds remain unchanged. The owner independently
checks references and measured feedback. Reference velocity is not
a guarantee of the firmware's actual stopping time or velocity.

The complete candidate fixture now reads back the explicit Servo,
kinematics and joint-limit parameters, as well as the verified scene.
MoveGroup request-default scaling parameters are not declared by Servo;
they are not part of this Servo configuration. With the new profile the
full isolated GenericSystem regression passed: 133 trajectory windows,
269 JTC references and 280 relay references within the declared envelope,
52 timestamp-aligned scene updates, feedback loss and scene change
latches. Servo status 4 still indicates proximity deceleration. This is
not a usable physical-speed or clearance acceptance.

WebGUI consumes the maximum speed reported by the owner through Core,
bounds the displayed declaration and disables presets exceeding it.
An envelope change releases held input; the client is not an actuator
authority. The legacy practice range remains available without an owner.

Validation: 91/91 NERO API tests, 6/6 ROS message/scene tests, TypeScript
typecheck, and 7/7 targeted WebGUI tests. Real NERO remained in WEB mode,
all seven drives disabled, zero transmitted CAN frames. No operational
service, physical configuration or baseline was changed. The actual
owner still needs separate, supervised commissioning with verified
as-built scene clearance, current firmware-limit provenance and a
reviewed operating profile. No merge or deployment.

## Local review deployment acceptance (no motion)

The review-only Core specialization consumes the validated private
station candidate and the existing passive NERO observation directory.
It exposes the proposed Precision envelope and real drive state, but no
manual transport, inspection runtime, IR or clear transport. The local
authenticated review HTTP listener is mutually exclusive with the
physical-command listener and rejects manual POST requests before they
reach Core. A mismatched Core response cannot appear commissioned.
WebGUI explicitly labels this mode as review-only.

A bounded test on VENTUNO compiled the station WebGUI, created a private
temporary library and temporary operator identity, started the real Core
IPC server and loopback HTTP server, loaded built HTML and its linked
assets, authenticated, and checked actual NERO telemetry and position
bounds. The proposed profile was reported as 5 mm/s and 2 deg/s; all
actuation capabilities remained false. A valid manual request was
rejected by HTTP (403) and a direct request to the isolated Core was
rejected as NOT_COMMISSIONED. The temporary server and account were
removed after the test. This is an HTTP/IPC deployment smoke test,
not an interactive browser acceptance or a persistent installed service.

The CAN counter increased by 2158 received frames with no new drops,
errors or transmitted frames. Operational service PIDs were unchanged.
The initial pre-bound HTTP socket was corrected to use the Waitress
sockets interface; the subsequent complete test passed. The review
receipt is private on VENTUNO. The physical owner was not replaced.
No change to the original geometry, calibration, production, or baseline.

Physical commissioning remains separate: the robot must be in a verified
clear working pose with an operator present, and the proposed profile,
as-built clearances and firmware-limit provenance must be accepted.
The existing guard and local confirmation are not bypassed.

## MANUAL starts from the measured position, not PARK or HOME

Operator decision: MANUAL must accept the current measured seven-axis
position, regardless of earlier positioning through the factory panel or
Vision. PARK and HOME are separate future functions, not prerequisites
or automatic startup destinations. This does not imply that every direction
is feasible at every pose: existing position, collision and feedback
interlocks still apply.

The new stationary-seed helper requires two distinct fresh stationary SDK
observations inside the position envelope. It constructs only the virtual
GenericSystem initial position values, leaving the factory moving-joint
geometry, mechanical TCP and scene unchanged. It does not send an actuator
setpoint. The live owner must also independently verify a fresh,
source-attributed JTC state and reference against its actual SDK feedback.
The controller witness has a 100 ms maximum age and 0.001 rad position
agreement threshold; the existing stationary velocity threshold is
0.01 rad/s. These are software admission tolerances, not independently
validated physical accuracy.

The manual engine verifies this agreement before ENABLE, at observed
enable completion, at the beginning of each new JOG and before its first
Twist. An old JTC position cannot make an idle session available or admit
a new jog. During a jog, the existing independent tracking and reference
envelope checks remain in force. A changed initial position requires a
fresh virtual interpolation context, not a physical correction toward an
old reference. No automatic recovery or movement to PARK/HOME is added.

Acceptance on VENTUNO: 105/105 NERO API/owner tests and 6/6 ROS
message/scene tests passed. A read-only live shadow collected current
joint observations (157 forwarded; maximum observed age 31.01 ms);
the first shadow attempt encountered incomplete DDS discovery and the
bounded discovery wait was corrected without relaxing source identity.
Two separate isolated GenericSystem fixtures initialized from different
recorded station joint vectors, each with zero numerical error in the
initial JTC state/reference comparison. The first was a stationary test
with a replay of the current measured position; the other replayed an
earlier raised pose and completed the dynamic Servo/JTC/Relay test
(129 windows, 263 JTC references, 280 relay references and 55 matched
scene updates). Loss of feedback and scene-change latching passed.
All replay tests were software-only; replay receipts cannot authorize
motion. The real CAN owner and operational services remain unchanged.
The actual single-owner commissioning startup still has to call the
live-seed builder and verify the resulting JTC context before admission.
No physical manual runtime was installed or activated by this step.
