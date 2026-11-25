# VISION-RUNTIME-002 — Station Session Orchestration

Status: implementation candidate; no station deployment or equipment acceptance.
Base: main 562a539. This package extends the existing independent Core host,
not a second Workflow or an equipment executor.

## Scope and current station behavior

- Core owns a single inspection session, its declaration, release selection,
  persistent journal and binding to the existing read model.
- Authenticated inspection report lists the fixed VENTUNO device availability
  diagnostics (Luxonis, NERO, MoveIt, Sony), separate from verified readiness.
  In the default launcher, fixed systemd user services are queried read-only.
  ACTIVE is service liveness only; Sony and all actual readiness remain UNKNOWN.
- The default service has no commissioned RuntimeComposition. A private
  session root alone does not enable a workflow. ETC3 DRAFT/NOT_READY is not
  an available execution recipe. Neither fixture profiles nor permissive
  verification callbacks may be used on the station.
- An explicitly installed trusted composition supplies an approved catalog
  release and ReferenceLibrary/release/assets, five approved station profiles,
  calibration revisions, capabilities, current physical readiness provider,
  independently verifiable post-dispatch S01 ReadinessReceipt provider and
  trust verifier. It uses the Core-owned catalog and existing compile_profile
  and VisionRuntimeCoordinator. The launcher main() accepts trusted Python
  composition/catalog_dir arguments for commissioning; no dynamic import,
  client paths, client receipts, invented calibrations or driver commands.
- When preflight passes and the operator explicitly chooses the exact
  versioned recipe, the session creates a real strict-planning Workflow,
  attaches it and dispatches S01. S02 is invoked only after the existing
  Runtime accepted S01. S03–S11 are not dispatched by this package.
- Start acknowledgement means a session exists, not that S01 or S02 passed;
  read their actual durable report. A failed/missing/untrusted receipt blocks
  dependent stages. This package does not provide the commissioned real
  readiness source, approved ETC3 or absolute TF; live S01/S02 are NOT accepted.

## Transport and permissions

Existing station/session/library read schemas remain unchanged. New endpoints:
- GET /api/v1/inspection — exact vision.api.inspection.v1 report:
  instance, session, readiness/availability with observation time,
  approved recipe options, blockers, start/close eligibility and intentToken.
- POST /api/v1/inspection/start — exact JSON instanceId, selectionId,
  intentToken; returns station report. Intent token rotates when a session
  is created or closed; old tokens cannot create another session.
- POST /api/v1/inspection/close — exact JSON instanceId, sessionId; returns
  station report. Only pre-localization idle/terminal sessions and fully
  completed S11 sessions can close. This is NOT HOLD, STOP, PARK, or abort
  of a running stage. No motion/capture commands or arbitrary attach endpoints.

All routes require authentication; both POST routes require explicit operator
role and existing exact Origin and X-Vision-Client checks. Existing accounts
remain reader. Local provision/reset supports --role operator; a reset with
no role argument and password rotation preserve the account role. Role is in
the credential fingerprint so old sessions are revoked on role changes.
The API passes the authenticated username, never a browser-supplied actor.
The private same-UID IPC is a trusted backend boundary; the new exact operation
allowlist carries intent only, not equipment commands. Existing arbitrary
writes remain denied. No browser cookie crosses IPC.

The Win98 System Status window now displays the report and explicit controls
for an operator. Reader sees diagnostics but cannot submit session commands.
Frontend never promotes a device or profile, never sends a receipt, never
retries a mutation automatically, and refreshes the authoritative state after
an ambiguous result. Runtime readiness does not follow from coreConnection.

## Persistence, failures and deployment

Commissioning provides an existing absolute private (0700) NVMe session root
and explicit trusted composition; existing systemd deployment is unchanged.
Each session uses a fresh directory and 0600 journal/intent; the durable
active-session marker is created exclusively before creation and kept if
any outcome is ambiguous. The exact operator and selection are persisted.
Core serializes starts and closes. The marker survives restarts: no auto-replay,
auto-resume, second owner or automatic recovery. A commissioned recovery
procedure must reconcile retained journals and external state before releasing
an interrupted marker; the UI cannot remove it. Closing a pre-localization
session invalidates its unfinished workflow before releasing the binding.
No original inspection files are deleted.

The short IPC deadline still applies. Trusted providers must be bounded; an
expired exchange or process fault must be treated as an unconfirmed outcome
and reconciled with Core reports. Do not retry an old start token. A large
reference library requires measurement of report latency before commissioning;
this implementation limits configured recipe options to 16 and revalidates
their release inputs; it does not implement asynchronous cached preflight.

Production activation is a separate decision after tests/merge, approved
station inputs and real readiness verification. Rollback selects the previous
Core/API/GUI release; never clear markers or delete private journals to make
rollback appear successful. Existing reader-only account files remain valid;
operator-bearing account files need an explicitly reviewed compatibility
procedure if downgrading to the old reader-only release. Do not mutate live
accounts as part of this software-only package.


## Local browser validation (2026-11-25)

The isolated station browser suite passed on VENTUNO Q / Ubuntu ARM64:
10 Chromium tests and 10 Firefox tests, plus TypeScript and ESLint checks.
The real fixture checks inspection blockers, the reader command boundary,
authentication/password rotation, independent clients and unchanged Core
ownership. Other scenarios use deterministic API fixtures. This is software
validation, not commissioned device readiness or physical workflow acceptance.

Playwright 1.65.1 uses Chromium revision 1255 and Firefox revision 1572. Both
were already installed in a previous NVMe development worktree; absence from
the remote agent's default cache did not mean absence from the host. Set
PLAYWRIGHT_BROWSERS_PATH to the existing NVMe browser cache when running both
commands from webgui (with a station build and the test Python environment):

```sh
npm run test:station -- --browser=chromium
npm run test:station -- --browser=firefox
```

Inspection assertions reuse the real password-rotation test's first login.
A separate login would exceed the shared fixture's production limit of five
client login attempts per minute. The test retains all readiness and password
assertions; production authentication limits and application behavior are
unchanged. The fixture uses its own Core process, temporary accounts/data and
port 18491, separate from the operational station.
