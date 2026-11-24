# Vision Inspection Planner V1 — S05–S06

Status: final software integration audit passed; see the
[final audit](../audits/VISION_RUNTIME_PLANNER_FINAL_AUDIT_2026-11-24.md).
Station deployment remains separate. This module extends the existing Core and
Runtime. It does not complete the outstanding physical ETC3 S03/S04 acceptance.

## Purpose and dependency

`src/vision_planner` turns an accepted Runtime selection and localization into
a calibrated photography plan, then asks the official MoveIt stack to plan its
required camera poses. Core remains the only S01–S11 state-machine owner.

The branch is based on Runtime PR #50. The specimen-specific localization
experiment in PR #51 is not a dependency or a trusted source of station pose.
Actual ETC3 geometry, camera–table calibration, and Sony/tool calibration can be
provided later through the existing versioned profile and provenance contracts.
Missing inputs produce a blocked or failed stage; they are never filled with
synthetic values by the runtime module.

## What each part does

| Component | Responsibility |
|---|---|
| `preparation.py` | Revalidate approved reference/record/recipe, accepted S03/S04 observation, capture calibration and policy; create the existing Core InspectionPlan |
| `geometry.py` | Project the useful rectified image onto an explicit PCB plane; compute conservative footprint geometry |
| `moveit_adapter.py` | Optional ROS 2 service adapter for scene, IK, state validity, FK and motion planning |
| `coordinator.py` | Authenticate all inputs, dispatch S05/S06 through Core, correlate complete results, and submit atomic preparation/motion proofs |
| `vision_core/planning.py` | Immutable proof contracts used by the opt-in strict planning gate |

Importing the package has no ROS, device, filesystem, or actuator side effects.
ROS message imports occur only in `MoveItAdapter.from_node`. The caller owns
the ROS node, executor, explicit service names, and domain configuration.

## S05: recipe, calibration and predicted coverage

Inputs are the existing `VisionRuntimeCoordinator`, a `CameraCalibration` and
a `PlanningPolicy`. Runtime must already have accepted S01 through S04. The
builder rechecks the released record and reference assets, recompiles the exact
selected physical state and recipe, and verifies the observation against the
durable S03 and S04 references. Changing an accepted observation object while
retaining the same scene label does not create another accepted localization.

The capture calibration describes the photography camera/lens configuration:
image dimensions, rectified intrinsics `fx/fy/cx/cy`, useful image rectangle,
calibration identifier/revision, capture-profile revision, configuration hash,
and independent provenance. This is separate from the Luxonis localization
calibration. The useful rectangle uses continuous pixel-boundary coordinates.
Changing lens, zoom, focus configuration or a derived rectification/crop requires
a matching calibration/configuration binding from the external verifier.

`PlanningPolicy` supplies explicit RAW requirements, minimum coverage, per-view
ROI requirements, a PCB plane in ECU-local millimetres, QA-policy references,
and provenance. No default Sony focal length, PCB height, coverage threshold or
tool offset is inferred. The external policy verifier must resolve numerical
limits against the selected QA policies and physical evidence.

Camera poses map optical coordinates (+X right, +Y down, +Z forward) into the
ECU-local frame. All four useful-image boundary rays must intersect the PCB
plane in front of the camera. Horizon crossings, degenerate intersections,
nonrectified images and invalid geometry are rejected. An axis-aligned rectangle
is inscribed in each projected quadrilateral. Its entire area is inside that
quadrilateral; the enclosing bounding box is never counted as covered area.
Core's exact union/intersection calculation handles overlapping footprints,
overlapping required regions and uncovered gaps.

This is intentionally conservative for oblique or rotated views. It can reject
a sufficient real field of view; it must not accept an uncovered corner by
using an oversized bounding rectangle. The selected aim point must be inside
the useful image and on the specified PCB plane. Camera-to-aim distance must
fall inside the approved recipe's working-distance interval.

`PreparedInspection` contains:

- the unchanged Core `InspectionPlan` and its digest;
- the full optics and policy values;
- original reference-view ID to Core-view ID mapping;
- predicted footprints and total/per-ROI coverage;
- selected record, reference, observation and preparation hashes.

Required views remain in approved record order. The compiler's required-ID list
is a set of requirements and can have a different order. V1 does not remove
required views or reorder them automatically to shorten a path: PhotographySession
and the accepted recipe require the original sequence. Reducing or reordering
that sequence is a later approved recipe/contract change. Consequently V1 makes
no global minimum-view or shortest-motion claim.

Core's current `ObservedECU` represents translation plus yaw. S05 rejects ECU
roll/pitch beyond numerical roundoff instead of silently discarding tilt. Full
six-axis object localization requires a separate Core contract extension.

Predicted S05 coverage is **not S08 measured coverage**. S08 still requires
verified spatial evidence bound to the actual captured originals, with its own
focus, exposure and coverage checks.

## S06: official MoveIt planning services

The adapter creates exactly five kinds of service clients:

| Service | Use |
|---|---|
| `GetPlanningScene` | Complete scene snapshots and fresh source robot state |
| `GetPositionIK` | Collision-aware IK for the calibrated camera goal transformed to the selected robot link |
| `GetStateValidity` | Start, goal and bounded intermediate-state collision/constraint checks |
| `GetPositionFK` | Independent camera-pose check of the IK and trajectory endpoint |
| `GetMotionPlan` | A time-parameterized trajectory from the explicit seed to the joint goal |

An explicitly configured `joint_state_topic` additionally enables a read-only
JointState subscription. On the tested Jazzy stack, GetPlanningScene does not
preserve the source state's timestamp/velocities. The adapter therefore needs
the actual source topic to cross-check scene positions and retain the original
stamp and velocities. A receive timestamp is never substituted for source time.

There is no ExecuteTrajectory, FollowJointTrajectory, driver command, shutter,
controller enable or PARK call in this adapter. It does not create a separate
motion-planning engine or Camera Service.

`AdapterConfig` pins the planning group/link, explicit joint bounds and dynamic
limits, model revision, tool calibration, optical-to-link transform, service
mapping, tolerances and bounded deadlines. For camera goal `T_scene_camera`:

```text
T_scene_link = T_scene_camera × inverse(T_link_camera)
```

Positions cross the ROS boundary in metres; the Vision API and profile geometry
remain in millimetres. Quaternions are xyzw and joint positions are radians.
The camera frame is never assumed to coincide with link7 or another tool link.

Quaternions within the accepted numerical unit-norm tolerance are normalized in
owned computation copies before rotating translations or comparing orientations.
The angle check uses the normalized relative quaternion and `atan2`, preserving
small resolvable rotations and treating antipodal quaternions as equivalent.
Raw receipt values remain unchanged in their authenticated digests.

Each segment must contain the requested start state, a reachable IK goal, a
successful timed trajectory, a matching final FK pose, and the exact scene and
configuration hashes. Joint bounds are checked explicitly; a generic state
validity response alone is not treated as proof of all model bounds. Position,
velocity, acceleration, duration and finite-difference bounds are checked, as
are rest endpoints, point counts and joint order. Missing derivative arrays,
partial results and acknowledgement futures are rejected.

The start-velocity tolerance is explicit and hashed, with default 1e-6 rad/s.
The synthetic Jazzy acceptance used 0.001 rad/s because the installed time
parameterizer returned a 0.0005 rad/s first point for a zero requested seed.
The last point still requires rest within 1e-6 rad/s, all scaled velocity and
acceleration limits still apply, and trajectory values are never rewritten.
The smoke override is not automatically approved for a physical configuration.

Bounded joint-space interpolation samples supplement MoveIt's own collision
checking. This is a discrete collision check with explicit resolution, not a
continuous swept-volume or physical-safety guarantee. An external execution
layer must preserve the validated trajectory, constraints and controller
semantics before any later real movement.

The live measured robot state remains stationary during planning. The predicted
endpoint of one trajectory becomes the next planned segment's seed; it is not
misrepresented as a measured robot movement. All required segments must pass.
The coordinator does not retry failed motion requests automatically.

## Scene ownership, source time and trust

Scene digests cover world collision geometry and octomap, allowed collision
matrix, padding/scaling, fixed transforms, attached bodies, nonplanned joints
and multidof state. Current planned-group joints and source timestamps are
bound separately. Comparing before/after digests detects differences but cannot
prove there was no transient change between the two reads.

`SceneLease` therefore binds an externally controlled frozen scene to the
exact Core request/context, preparation hash, configuration hash, model name,
source, issue time and expiry. Its authority must hold the relevant scene
unchanged for the entire job and attest to the scene's relationship to Runtime's
localized revision, including the localized ECU and every required obstacle.
`SceneBinding` supplies the full accepted observation and preparation to that
verifier, not just the scene label. Freezing an unrelated or incomplete scene
does not satisfy the contract. **The current repository does not implement a production
scene-ownership server or its authenticator.** Without that supplied boundary,
S06 cannot be accepted by this coordinator. Synthetic tests use a clearly
identified synthetic authority.

Source robot-state time and service-receive time are separate fields. A recent
service reply does not refresh old JointState data. A source sample slightly
before S06 dispatch is valid if it is within the explicit freshness limit; the
snapshot receive time must follow dispatch. Missing measured velocities are
not replaced with presumed zeros by the coordinator.

`trust_verifier(kind, payload)` authenticates complete typed values:

- `preparation`: request and full calibrated S05 preparation;
- `motion_setup`: request, preparation, adapter config and model/tool provenance;
- `scene_lease`: context, full accepted observation/preparation, lease, configuration and observed scene;
- `motion_binding`: full correlated trajectories and initial/final snapshots.

`True` is required; hashes and `approved=True` are not self-authentication. The
coordinator verifies the payload digest before and after each callback, and
rechecks clocks after callbacks. A verifier that changes a payload, runs beyond
the scene lease, or lets the source state become stale cannot accept the job.
Production code must not supply an always-true verifier.

Resource limits apply both per segment and to the complete job: at most 8192
trajectory points, 262144 scalar trajectory values and 8 MiB serialized binding
data, in addition to bounded Core view/coverage geometry and adapter scene,
point, sample and service-deadline limits.

## Core integration and replay

Create a new `VisionRuntimeCoordinator(..., strict_planning=True)` before S01.
The strict setting is part of Core's durable configuration pin. Legacy callers
with the default `False` retain their existing behavior and configuration
fingerprint; Planner requires strict mode and cannot be attached retroactively
to a legacy session.

```python
from vision_planner import InspectionPlanner

# runtime already completed S01–S04 with strict_planning=True.
# The application supplies approved optics/policy/setup and real verifiers.
planner = InspectionPlanner(runtime, trust_verifier=planning_verifier)
prepared = planner.prepare(
    s05_request, camera_calibration=approved_capture_calibration,
    policy=approved_photography_policy,
)
motion = planner.plan_motion(
    s06_request, backend=moveit_adapter, setup=approved_motion_setup,
    scene_lease_factory=scene_owner.acquire,
)
```

S05 submits `PreparationProof` with the existing verified Core plan. S06 submits
`PlanningProof` binding that exact preparation and inspection plan to the motion
digest. Core writes each proof and its result in one existing transaction.
Generic check labels cannot complete strict S05/S06. Replays restore both hashes;
a strict-mode downgrade or uncertain write/commit prevents further dispatch.
Strict S07 checks unique durable S05/S06 proofs, their ordering, freshness and
configuration again. Planning success leaves S07 pending; no action is sent.

This is a planning gate, not an execution adapter. S07 `MotionResult` retains its
existing external `goal_verified` trust boundary and inspection context. A later
execution integration must load the exact `accepted_motion_hash`, authenticate
its retained trajectory, verify the current scene/state, and bind execution and
feedback to that accepted artifact. This PR does not implement those device-side
checks or claim that an existing generic S07 result proves their completion.

The full `PreparedInspection` and `MotionPlan` artifacts belong in the private
session archive of the integrating application. Core persists their hashes and
correlated proof metadata. Automatic recovery of a partly completed planning
session is not implemented. An unresolved RUNNING stage stays blocked on
restart, and rehydrating an accepted observation/artifact requires independent
verification against its original durable binding.

## Verification

```bash
python -m pip install -r requirements-photography.txt
PYTHONPATH=src python -m unittest discover -s tests/core -q
PYTHONPATH=src:tests/core:tests/planner python -m unittest discover -s tests/planner -v
python -m compileall -q src tests/core tests/planner tools/lab/inspection_planner
git diff --check
```

The CI workflow runs these offline checks without ROS or devices. The optional
`tools/lab/inspection_planner/moveit_smoke.py` is an isolated synthetic MoveIt
acceptance probe, described in the audit report. Its results are not physical
ETC3, table-transform, camera-metrology or robot-motion acceptance.

## Primary interface references

- [MoveIt motion planning and trajectory results](https://moveit.picknik.ai/main/doc/concepts/motion_planning.html)
- [MoveIt Planning Scene Monitor](https://moveit.picknik.ai/main/doc/concepts/planning_scene_monitor.html)
- [Official MoveIt ROS 2 message/service definitions](https://github.com/moveit/moveit_msgs/tree/ros2)

The actual service fields were also checked against installed ROS 2 Jazzy
`moveit_msgs` on VENTUNO; the linked concept pages track upstream Rolling.
