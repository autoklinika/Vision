# Vision Runtime V1 — final software audit

Date: 2026-11-24. Scope: PR #50, S01–S04 coordinator and ROS2 observation builder.
Baseline reviewed: `bea1d9d81f0967aac7280dbd37cf2624b3b8fb30`.

The final audit reproduced and fixed authentication-boundary and durable-evidence
defects before the planned merge. This report supplements the earlier
[implementation audit](VISION_RUNTIME_V1_PREMERGE_AUDIT_2026-11-24.md) and
[read-only Luxonis acceptance](VISION_RUNTIME_LUXONIS_LIVE_READONLY_ACCEPTANCE_2026-11-24.md).
It establishes software behavior, not physical S03/S04 acceptance.

## Findings and corrections

| Finding reproduced | Correction |
|---|---|
| A verifier could change a validated receipt and return `True`; S01 accepted `quality=False` and S03 accepted a changed position | Compare the full selected context and receipt digest before and after authentication; reject mutation |
| An aliased geometry list could change from x=0 to x=999 during builder verification | Check the complete measurement binding digest across authentication and receipt construction |
| Caller-owned profile or calibration maps could change during verification | Authenticate and emit one owned metadata snapshot |
| A slow verifier could expire depth at age 10.02 s while RGB at age 9.97 s passed the 10 s limit | Revalidate all observation timestamps after authentication in both S03 and S04; revalidate readiness as well |
| S04 could accept another receipt sharing scene, frame and RGB time with S03 | Require exact full-receipt identity with the unique durable S03 acceptance event |
| Builder readiness verification omitted request, session, time and revision maps | Verify the complete typed `ReadinessReceipt` instead of the former four-item tuple |

The callback signature remains `verifier(kind, payload) -> bool`. The readiness
payload type change is intentional before the first V1 merge. See the
[adapter contract](../implementation/VISION_RUNTIME_ROS2_LUXONIS_ADAPTER_V1.md).

## Verification

- Eleven new regression tests cover mutation, metadata aliasing, stream expiry,
  exact S03/S04 evidence identity and complete readiness authentication.
- Ten of those eleven regressions failed against the pre-fix implementation.
- The full Core/Runtime/profile/library/photography suite passes **631 test
  executions**, including the eleven new cases, with Python 3.12 and the pinned
  NumPy/OpenCV dependencies.
- `git diff --check` passes. The tests use controlled fixtures without ROS,
  devices, camera acquisition or robot commands.

The count is the unittest execution count, not a claim of 631 independent new
cases. Tests import fixture modules without importing their TestCase classes.
PR CI must pass on the published final head before merging.

## Acceptance boundary

No remaining blocker was identified in the reviewed trust/receipt paths after
the corrections. The authenticated external estimator, source verifier and
retained evidence remain integration inputs; digest equality alone cannot
authenticate a sensor or approve a physical measurement.

The absolute camera-to-table transform and real ETC3 reference profile remain
pending approval. Existing RGB-D communication evidence is retained; this audit
does not repeat camera tests or promote experimental localization to trusted
Runtime evidence. No production checkout or frozen Guided Positioning baseline
is changed by the software merge.
