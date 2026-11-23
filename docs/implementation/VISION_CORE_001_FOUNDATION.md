# VISION-CORE-001 — Foundation (Codex execution package)
**Date:** 2026-11-23 · **Status:** IN IMPLEMENTATION / NOT ACCEPTED · **Base:** current `main`.
**Specifications:** `docs/workflows/VISION_INSPECTION_WORKFLOW_V1.md`; `docs/architecture/ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md`; `docs/process/REPOSITORY_HYGIENE_V1.md`.
**Working mode:** isolated new Git worktree, single small PR, no deployment and no automatic merge.

## Explicit deliverables
1. Implement a minimal Python 3.12 standard-library-only importable `vision_core` module in `src/vision_core/`, with no ROS/DepthAI/CAN/PTP/AgileX imports.
2. Define typed, versioned, manufacturer-neutral models for: sessions, stages, operation context, evidence/results, events and errors.
3. Define six revisioned/approved profiles with required capabilities and calibration dependencies; validate missing, mismatched or unapproved metadata as NOT_READY.
4. Implement an explicit Workflow Engine for S01…S11 with fail-closed predecessor gates and state transitions. ACK is nonterminal; only correlated and validated evidence can complete a stage.
5. Detect scene/profile/observation/context changes, invalidate the pending plan and dependent readiness. Prevent stale/mismatched results from opening gates.
6. Record append-only, durable SQLite events including denied starts, dispatch/ack, accepted/rejected results and transitions. Maintain session/request correlation; safe crash/replay behavior (no implicit redispatch of RUNNING actions).
7. Establish thin typed protocol boundaries for external sensor, scene, motion and capture adapters; implement **only inert mocks**. No fake implementation of MoveIt/ROS internals.
8. Include deterministic offline unit tests, synthetic fixtures, simple developer instructions and minimal CI (Linux, Python 3.12; no hardware permissions).

## Minimum acceptance matrix (automated)
- A complete synthetically verified S01…S11 session succeeds in dependency order, with audit entries.
- A dependent stage cannot start before all required earlier stages are **verified SUCCEEDED**.
- ACK/progress, missing evidence, malformed correlation IDs, stale timestamp, mismatched scene/profile revision, missing frame_id or absent quality deny success.
- Failure, cancellation, timeout, capability absence and unapproved/incomplete calibration block dependent stages.
- Changing ECU observation/scene/tool/robot/sensor/capture profile invalidates prior motion plan; no old plan can be dispatched.
- Two synthetic RGB-D sensor profiles and two capture-device capability profiles use the same Workflow code; RAW-required with JPEG-only fails.
- Restart from SQLite does not reissue side effects, infer SUCCEEDED, automatically retry or park; unfinished side-effecting stages require explicit reconciliation.
- Invalid state transitions are rejected; audit is append-only and stable across restart; tests require no physical devices.
- No writes to any existing VGP baseline, runtime service, ROS installation, live controller or production storage; no client photos/logs/calibration in diff.

## Suggested minimalist layout (not a rigid one-class-per-file requirement)
```text
src/vision_core/
  __init__.py
  models.py        # IDs, context, verified results, stage states
  profiles.py      # versioned profiles + capability validation
  workflow.py      # dependency gates/state machine
  journal.py       # durable SQLite event append/replay
  ports.py         # vendor-neutral typed interfaces
tests/core/        # synthetic only
docs/workflows/VISION_INSPECTION_WORKFLOW_V1.md
docs/implementation/VISION_CORE_001_FOUNDATION.md
.github/workflows/vision-core-offline.yml
```
No ROS node, daemon, web server, general camera service, perception engine, alternative trajectory executor or local AI bridge in 0.1. Avoid additional frameworks and premature abstractions.

## Codex instructions
Read ADR and both documents first. Keep existing code untouched except the smallest necessary doc/CI integration. Implement and run tests in the isolated checkout. Capture actual commands and exit statuses. Review `git diff --check`, `git status`, changed paths and likely secrets before push. Do not start devices, daemons, `ros2` commands or production services. Do not publish private VGP, TF or physical ECU values. Commit only if the offline suite passes; open a draft PR, with an honest test report. Never merge.

## Owner review
**NOT ACCEPTED until owner sign-off.** Audit of state-machine gates, durability, reconciliation, profile/capability independence, confidential-data hygiene and CI is mandatory. Any physical action belongs to future separate approvals and packages.