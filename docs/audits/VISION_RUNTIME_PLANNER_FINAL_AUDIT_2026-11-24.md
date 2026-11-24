# Vision Runtime and Inspection Planner V1 — final integration audit

Date: 2026-11-24. Scope: Runtime PR #50 and Inspection Planner PR #52.
**Result: PASS for the reviewed software merge scope after the fixes below.**
The specimen-specific localization experiment in PR #51 is not a dependency
and is excluded from this integration. Station deployment and physical ETC3
acceptance remain separate.

## Reviewed revisions

| Input | Commit |
|---|---|
| Main before integration | `4e097b5220dfee6832c1daeb67d3978c6861699d` |
| Runtime with final corrections | `d02a58c93d309408b001cc3ff7929b482eb0ca9c` |
| Planner numerical and concurrency regressions | `cae951a` |
| Integrated source tested | `7045207f641e560c1ffe3388e87c13a99d60005e` |

The publication commit after that source revision adds this report and contract
clarifications only. The PR checks must be green on the exact published head
before merge. Merge order is Runtime into main, then Planner retargeted to main;
merge commits preserve the stacked history.

## Independent review and resolved findings

Three independent reviews covered Runtime evidence authentication, MoveIt
numerical/service boundaries, and strict Core transaction/replay behavior.

| Area | Finding / reviewed risk | Result |
|---|---|---|
| Runtime authentication | Verifier callbacks could mutate validated receipts or aliased geometry | Full before/after digest checks, one metadata snapshot, receipt-construction check |
| Runtime freshness | Older depth/TF could expire during authentication while RGB stayed fresh | Revalidate every source timestamp after the callback in S03 and S04; recheck readiness |
| Runtime identity | S04 could accept a different receipt with the same scene/frame/RGB time | Exact receipt reference must match the unique durable S03 acceptance |
| Readiness authentication | Former builder tuple omitted request/session/time/revisions | Complete typed `ReadinessReceipt` is authenticated; pre-merge contract correction documented |
| MoveIt geometry | A quaternion with allowed norm error could hide a 0.005 rad error under a 0.0001 rad limit | Normalize computation copies; compare relative rotation with stable `atan2` |
| Rotation edge cases | Tiny angles, antipodal quaternions and scaled tool rotation | Six regressions cover both service and retained-receipt paths; raw digested values stay unchanged |
| Core concurrency | Two S06 completions with different motion hashes | Exactly one durable proof/result wins; S07 binds the winning hash |
| Recovery | Restart races and an exception after a real commit | Late workers cannot accept S06; uncertain workers cannot dispatch S07 |
| Photography replay | Strict completed planning followed by original capture/S07 | Replayed proofs remain usable; S08 stays pending for its own evidence |

The Runtime review added eleven regressions, ten failing before its fixes.
The motion review added six regressions; Core review added four. No remaining
blocker was identified within the documented planning-only software scope.
The full Runtime findings are in the
[Runtime final audit](VISION_RUNTIME_V1_FINAL_AUDIT_2026-11-24.md).

## Verification evidence

| Check | Result |
|---|---|
| Clean Runtime branch, local Core suite | 631 executions PASS |
| Simulated final merge, local Core suite | 631 executions PASS, 4.265 s |
| Simulated final merge, local Planner suite | 110 tests PASS, 1.578 s |
| Simulated final merge, `compileall` and `git diff --check` | PASS |
| Integrated source, isolated ARM64 Core suite | 631 executions PASS, 22.465 s |
| Integrated source, isolated ARM64 Planner suite | 110 tests PASS, 5.652 s |
| Exact retained MoveIt evidence under corrected validators | Two segments PASS, ten trajectory points, ten additional checked states |
| Merge rehearsal | Both merges conflict-free; resulting tree equals integrated source tree |
| Rollback rehearsal | Reverting both merge commits restores the exact original main tree |

The 631 count is unittest executions, not 631 independent new cases. The total
integrated suite is **741 executions**. Python 3.12 and repository-pinned NumPy
1.26.4 / OpenCV 4.10.0.84 were used. ARM64 tests ran in the existing
`vision-core-codex:002` image as UID 1000, with no network, read-only filesystem
and source, dropped capabilities, two CPUs and 2 GiB RAM. No device mounts or
hardware operations were involved.

The saved MoveIt archive SHA-256 is
`ff4d02367ecc739dcfb19c028d4bbf06a168b41ca5d5ac38623dbc57bfa9b6f0`.
Revalidation reconstructed its typed objects and checked current snapshot,
segment, digest and chain rules without importing ROS. It reused recorded
receive timestamps only for historical consistency; no old state was promoted
to current evidence. See the
[simulation report](VISION_INSPECTION_PLANNER_MOVEIT_SIMULATION_2026-11-24.md).

## Merge and rollback rehearsal

A separate worktree started at the main revision above and performed `--no-ff`
merges of the corrected Runtime and integrated Planner. The tested resulting
tree was `0598db2a9aaa75309e4466ab4d193da79e1ce4ce`, exactly matching the integrated
source commit. Tests left that tree clean.

In the rehearsal only, `git revert -m 1` first reversed the Planner merge and
restored the Runtime tree, then reversed Runtime and restored main tree
`cc54d2c2697c1a2e113630df9db0bc02b5f8afe6`. This is a repository rollback check;
there was no station deployment to roll back. The subsequent report-only commit
is expected to add documentation to the final tree without changing tested code.

## Accepted scope and remaining integration inputs

This merge accepts S01–S04 Runtime software and S05–S06 plan preparation and
MoveIt validation. It preserves required recipe views and order, planar ECU
translation/yaw, independent source authentication and scene authority. It does
not infer missing calibration or promote synthetic fixtures to approved data.

The physical camera-to-table transform, approved ETC3 reference profile,
authenticated estimator and retained measurement binding remain needed for
real S03/S04. Sony optics, tool transform, current robot/scene evidence and a
production scene authority must be supplied before a real inspection plan is
accepted. S05 predicted coverage does not establish S08 measured coverage.

S07 currently retains its external `goal_verified` trust boundary. The later
execution integration must enforce the exact accepted motion artifact and
current scene/state, then bind feedback to that execution. This planning-only
module contains no trajectory execution client and does not claim that physical
execution or original-image capture has been implemented or accepted.

PR #51 remains experimental: its specimen-specific ROI/localization evidence
does not establish an approved absolute station transform or authenticated
Runtime geometry. Existing RGB-D communication acceptance need not be repeated
to merge these software modules. The active station checkout and frozen Guided
Positioning baseline are outside this merge operation.
