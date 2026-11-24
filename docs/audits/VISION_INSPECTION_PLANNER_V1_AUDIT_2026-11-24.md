# Vision Inspection Planner V1 — implementation audit

Date: 2026-11-24. Scope: isolated development of S05/S06 above Runtime PR #50.
Status: implementation reviewed and offline tests passed; isolated MoveIt
simulation passed. This is not physical ETC3 or production execution acceptance.

This report records the initial implementation checks. The subsequent
[final integration audit](VISION_RUNTIME_PLANNER_FINAL_AUDIT_2026-11-24.md)
adds Runtime authentication fixes, normalized rotation checks and concurrency/
recovery regressions, with final totals of 631 Core and 110 planner executions.

## Implemented scope

- S05 uses the released record/reference and accepted Runtime observation to
  create the existing Core plan, bind Sony optics/QA policy, map required view
  IDs, and check conservative predicted PCB coverage and working distance.
- S06 uses official MoveIt services to obtain complete chained trajectories,
  with IK, FK, joint/dynamic limits, source state, scene ownership and collision
  checks. The module contains no execution or capture command.
- New opt-in Core strict mode persists preparation and motion proofs atomically
  with accepted results, retains the existing configuration-pin behavior, and
  rejects generic success labels for S05/S06. Existing callers keep legacy mode.
- Scene verification receives the full accepted observation, preparation,
  configuration and snapshot. A production scene authority remains an external
  integration input and must verify scene completeness as well as ownership.

Implementation details and integration examples are in
[the S05/S06 contract](../implementation/VISION_INSPECTION_PLANNER_V1_S05_S06.md).

## Verification results

| Check | Result |
|---|---|
| Existing Core/Runtime/profile/library/photography tests | 620 executions, PASS |
| New planner tests | 100 tests, PASS |
| Python compilation | PASS |
| `git diff --check` | PASS |
| Independent isolated ARM64 Docker rerun | 620 Core + 100 planner, PASS; network disabled, read-only source/filesystem, no capabilities |
| Official NERO MoveIt services in isolated synthetic domain | PASS; two planned camera poses, unreachable and collision rejection |

The new 100 tests comprise 22 optical/preparation tests, 29 service-boundary
tests, 24 coordinator integration tests, 21 strict Core/replay tests and four
independent adversarial callback/timing regressions. Existing tests may include
repeated execution of imported fixtures; the 620 number is an execution count,
not a claim of 620 independent new cases. New fixture helpers avoid imported
TestCase rediscovery.

Local verification used Python 3.12 with the repository-pinned NumPy 1.26.4 and
OpenCV 4.10.0.84. CI executes both suites without ROS or connected devices.
The separate ARM64 rerun used the existing `vision-core-codex:002` image,
unprivileged UID 1000, two CPU cores, a 2 GiB memory limit and no network or
hardware-device mounts. Core completed in 16.381 seconds and planner tests in
5.057 seconds. Both exited 0; the staged diff check also passed.

## Findings reproduced and fixed

| Finding | Correction / regression |
|---|---|
| Full camera/QA preparation could be changed and rehashed inside a verifier | Hash the entire authenticated payload before and after every callback; reject changed inputs |
| A scene lease could expire while the final callback was running | Check lease validity after the callback and before accepting S06 |
| Robot source state could become stale during authentication while Runtime observation remained fresh | Independently recheck final source-state age against the adapter limit |
| A fresh service reply could hide stale/absent measured robot state | Separate `received_at` from source JointState time; explicit read-only source subscription and scene-position cross-check |
| Installed Jazzy GetPlanningScene omitted source timestamp and velocities | Preserve actual source-topic values; never substitute receive time or presumed zero velocities |
| Installed Jazzy time parameterization produced a nonzero first velocity | Keep trajectory values unchanged; explicit hashed start-velocity tolerance, strict default, declared synthetic smoke override |
| Per-segment limits did not bound a complete multi-view job | Cap aggregate points, scalar values and serialized authentication data |
| Serialization/copying could precede resource bounds | Check shapes, joint count/name bounds and cumulative scene budgets before hashing/retaining copies |
| A motion result could bind a changed preparation while retaining the Core plan hash | Atomic S05 preparation hash; strict S06 must match its durable S05 proof |
| Generic S06 labels or replay downgrade could bypass the new planner | Typed strict proofs, configuration pin, durable replay validation and S07 dispatch check |

Core rejects request/context mismatch, changed scene/configuration, untrusted
sources, invalid or old evidence, partial trajectories, missing derivatives,
bad joint names/bounds, discontinuous segment seeds, wrong FK endpoints,
uncovered ROI regions and unsupported ECU tilt. Failure prevents downstream
dispatch; there is no automatic side-effect retry.

An additional independent numerical geometry audit projected 1200 rectangle
corners from 300 deterministic camera poses using a separate NumPy rotation
matrix oracle. All remained in the calibrated image, with maximum numerical
excursion about 7.1e-14 pixels. This scratch audit is not included in the unit
test counts and is not a physical accuracy measurement.

## Actual MoveIt simulation

The [separate simulation report](VISION_INSPECTION_PLANNER_MOVEIT_SIMULATION_2026-11-24.md)
records the installed ROS 2 Jazzy / MoveIt versions, two five-point trajectories,
five sampled validity checks per trajectory, rejection of an unreachable goal,
and rejection after insertion of a synthetic collision object. Synthetic
measured state and scene stayed unchanged during the successful planning job.

Execution was explicitly disabled. Only the owned synthetic MoveIt process
group was started and subsequently stopped. The existing robot, camera and
prior MoveIt processes remained present. Raw simulation output is retained
privately; its SHA-256 is
`ff4d02367ecc739dcfb19c028d4bbf06a168b41ca5d5ac38623dbc57bfa9b6f0`.

## Scope and remaining integration inputs

The module preserves all approved required views and their order; count/order
optimization is not implemented in V1. It would require a deliberate recipe
and Core/PhotographySession contract change. No global optimality is claimed.

The physical ETC3 profile and absolute camera–table transform remain pending.
Current Core localization is planar (translation plus yaw). Sony calibrated
intrinsics/configuration, the PCB plane, tool/optical transform, model limits,
and trusted scene/observation authentication must be supplied for the real
station. These inputs can be versioned and entered later; test fixtures are
never promoted automatically to real approved data.

The planner does not itself convert Runtime obstacle references into production
PlanningScene geometry or host a scene-ownership service. Its authority must
confirm that the selected ECU and required obstacles are represented correctly.
Snapshot hashes alone cannot prove no transient scene mutation occurred.

Collision checks use MoveIt and explicitly bounded interpolation samples. They
are not continuous collision or metrology guarantees. Planned S05 coverage is
not S08 measured coverage of actual originals. No S07/S08 hardware integration,
Sony transfer, automatic PARK or production deployment is included in this PR.

The active project checkout was not changed. The frozen Guided Positioning V1
SHA256SUMS audit passed for all 1790 listed entries during this task. No raw
camera images, private ECU geometry, serial numbers, network addresses or
device-session logs are included in the feature commit.
