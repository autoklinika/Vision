# Vision Inspection Workflow V1
**Status:** PRELIMINARILY ACCEPTED — owner-approved flow; details marked TBD are refined during implementation.
**Date:** 2026-11-23. **Authority:** ADR-VISION-CORE-001 (ACCEPTED).
**Scope:** orchestrated ECU/PCB inspection; VGP V1 remains frozen and is not deployed or modified by this document.

## Invariants
- Core coordinates sessions and stage dependencies; hardware operations belong to external ROS 2/MoveIt 2/vendor drivers and thin adapters.
- A stage starts only when **every required predecessor** has verified terminal success and the current readiness/context checks pass. Dispatch ACK or progress feedback is **not** completion.
- Verify `session_id`, `step_id`, `request_id`, profile revisions, scene revision, observation timestamp/frame, evidence freshness and integrity before accepting a result.
- On a failed gate, stale evidence, cancellation or ambiguous timeout: fail closed, record reason, block dependent stages. No implicit retry or automatic motion/PARK after an error.
- StationProfile defines fixed, accepted geometry; a current vision observation defines dynamic ECU geometry. Inspection targets are ECU-relative; joint values are not stored as view definitions.
- Record commands, rejections, transitions, observations/result references and operator decisions in a durable audit trail. Raw images and station-specific calibration remain private.
- Operator declares ECU; vision verifies it but never silently substitutes another ECU type.
- Hold remains the agreed laboratory operational convention under on-site operator supervision. It is not implemented by Foundation.

## Ordered V1 stages and successful-completion evidence
| ID | Stage | Verified completion / exit gate |
| --- | --- | --- |
| S01 | Station preparation | Required capabilities available; approved profiles, calibrations, current device state and readiness accepted |
| S02 | ECU selection | Operator-declared ECU type/variant and inspection scenario pinned to versioned profile |
| S03 | ECU localization | Fresh RGB-D observation: scene frame, pose/orientation, PCB/obstacles, geometry, quality, timestamp and revisions |
| S04 | ECU verification | Observed features/geometry match selected ECUProfile within tolerances; mismatches require operator resolution |
| S05 | View preparation | ECU-relative targets, PCB coverage plan and capture requirements validated and versioned |
| S06 | Motion planning | MoveIt 2 result: valid IK, collision checks, current PlanningScene, profile/scene/context binding |
| S07 | Photography | For each view: robot goal completed AND actual state verified, capture confirmed, file transferred and integrity verified |
| S08 | Image quality | OpenCV-derived focus, exposure, field of view and coverage evidence accepted; originals preserved |
| S09 | Parking | Authorized return to PARK, terminal motion success and independently checked actual robot state |
| S10 | Archiving | Immutable original files, derived copies, manifests/hashes, profile versions, observations and session audit persisted |
| S11 | Completion | Operator receives a complete session summary, outcomes, exceptions and archive reference |

The default V1 scenario is sequential S01→S11. An explicit versioned dependency graph may later enable independent work without bypassing gates. Failure handling and recovery are **not** shortcuts through the graph. In particular S09 after an earlier failure is a separate *operator-approved recovery process*, not an automatic dependency bypass.

## Fault/recovery policy
All stage instances use PENDING / READY / RUNNING / SUCCEEDED / FAILED / BLOCKED / CANCELLED / TIMED_OUT. SUCCEEDED means **verified evidence** matched the request and current context, not simply ACK. On restart replay the journal and reconcile external state before any new command; never re-execute motion/capture based solely on a previously persisted RUNNING state. In Foundation, unresolved recovery remains BLOCKED until explicitly revalidated. Retries for side-effecting operations require a later, explicit policy and reconciliation.

## Versioned profiles
- StationProfile — fixed calibrated geometry, approved PARK and immutable calibration revision.
- VisionSensorProfile — sensor capability, ROS topics/frames, intrinsics/extrinsics and freshness requirements.
- CaptureDeviceProfile — RAW/JPEG, autofocus, shutter, transfer/integrity capability.
- ToolProfile — body/lens/mount geometry, TCP, optical axis and collision geometry.
- RobotProfile — URDF/SRDF/group/controller, capabilities, HOLD and PARK support.
- ECUProfile — declared ECU type/variant, nominal envelope, connector features, PCB regions, ECU-local view targets, tolerances and capture/QA requirements.
Every profile has identifier, schema version, revision, required capabilities, calibration dependencies and approval status. Actual geometry comes from current observations, never as a substitute from ECUProfile.

## Deliveries
**Core 0.1 Foundation:** offline session/stage state machine, gates, evidence contract, capabilities/profile validation, persistent audit and synthetic mocks. No ROS, robot, camera, image collection or production integration.
**Core 0.2 Photography:** connect accepted VGP V1 through adapters; capture and OpenCV QA without modifying VGP V1.
**Core 0.3 Repeatable Inspection:** repeatable ECU-relative views, PCB coverage, policy-controlled recapture and reproducibility.
**Vision Intelligence (later):** local AI/PCB component and construction comparison. Not a blocker for earlier phases.

## TBD — refine with evidence during implementation
- Numeric timestamp staleness thresholds per sensor and task; uncertainty budgets and confidence thresholds.
- ECU-specific tolerance bands, dimensional references and photographs, view density and coverage targets.
- Camera RAW/AF/zoom transport behavior, exact file format, transfer timeout and recovery rules.
- Precise OpenCV metrics and acceptance thresholds for blur/exposure/registration/coverage.
- Final ROS 2 action/service/topic bindings, synchronization and actual-state verification.
- Operator UI decisions, post-failure authorized PARK, retention, backup/export and archive naming.
- Parallel-stage dependency policy and any operator-approved automated retry conditions.

No TBD may be turned into an implicit permissive default.