# API-02 independent pre-merge audit — 2026-11-25

Scope: issue #58, based on main `21c3229`. This source-audit record requires final exact-head GitHub CI and VENTUNO ARM64 evidence in the PR before merge. It does not attest deployment to an active station.

## Audited boundaries

- Existing Core authority; no construction/replay/mutation by HTTP reads.
- Shared owner lock covering post-commit publication, Runtime operations and photography recording/poison paths.
- Immutable committed projections, memory/durable-state consistency and failure on uncertain persistence.
- Distinct current state, historical success and ACK; actual scenario stages.
- Default-deny authorization, exact typed grants, route scopes, fixed session binding; no loopback identity or production test tokens.
- Closed bounded reports, field redaction, pinned pages and provider/cursor correlation.
- Win98 client's transient shared view, failure clearing, mode isolation, body deadlines/cancellation.
- Public API-01 status remains separate from protected data.

## Findings resolved before CI submission

1. **Private recording paths:** photography calls `_record()` directly. Locking only public methods would leave a gap around recording failure and poisoning. Serialization now includes these and private transition/completion helpers.
2. **Session validator parity:** the client initially lacked Python's invalidation/current-state and success/history checks. Both now reject invalidated reports containing non-BLOCKED states and SUCCEEDED without historical success; regressions cover both.
3. **ACK/event semantics:** a malformed `ack` could carry SUCCEEDED. Both validators now permit state only for transitions or accepted localization (fixed SUCCEEDED). All other kinds require null.
4. **Fixture cleanup:** exclusive credential-file creation failure must not remove a pre-existing file. Cleanup now removes only a file this process created.

## Verification at source-audit time

- Independent reviewer ran the combined Core/API suite: **34 tests PASS**. Root also ran this suite successfully before the final semantic fixture amendment; CI reruns it.
- Core implementer verified 16 new projection tests, 14 existing Workflow tests and 21 targeted hardening/uncertainty/extension tests.
- Independent source review identified no remaining blocking defect.
- Frontend type checking, lint, unit/browser tests, full backend CI and native ARM64 acceptance remain explicit gates. Actual results and reviewed commit belong in the PR before merge.

The partial local checkout lacked existing template/config fixtures and cv2; attempted full-local runs are not counted as a completed full-regression gate. GitHub uses the complete checkout and dependencies.

## Material limits

The adapter remains loopback LAB. The 0.25-second timeout bounds lock acquisition, not total SQL execution; the socket timeout measures inactivity. Query scaling, TLS/deployment, production identity/session management and attachment to the station engine are separate gates. Synthetic fixture success is not hardware readiness or active-station evidence.
