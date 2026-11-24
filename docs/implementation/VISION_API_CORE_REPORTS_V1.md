# API-02 — protected Core / Runtime read reports

Scope: [issue #58](https://github.com/autoklinika/Vision/issues/58), based on API-01 commit `21c3229a7c6904488197d130290f35efae7777f3`. This implements the read integration and explicit composition seams. Connecting the active station owner and production identity/session management remain separate deployment gates.

## Authority and composition

WebGUI is only a client of Vision. Core / Runtime own all workflow state, transitions, evidence, validation, authorization decisions and device operations. This change adds no operational HTTP command and no client workflow engine.

The trusted backend composition owner supplies one **already constructed** `Workflow`, normally `VisionRuntimeCoordinator.engine`, to `CoreReportProvider(engine, source=...)`, and supplies a server-side authorizer to `make_server(port, provider=..., authorizer=...)`. No HTTP read constructs a Workflow, opens a journal, replays a session, dispatches work or calls start/ack/complete/stop. The provider is fixed for the server lifetime and gets a new random `viewId` on construction. Changing the active session requires the owner to compose a new provider/server; it cannot be done by the browser.

`source` is explicitly `STATION` or `SYNTHETIC_TEST`. The test harness is the only composition included in this stage. Its data is visibly labelled synthetic. The ordinary `python -m vision_api.server` command provides neither a provider nor an authorizer and therefore denies protected reads. It does not attach itself to a running station.

## Consistent reads

The journal's reentrant owner lock now covers complete Workflow mutations, including memory changes after the database commit in `start()`. It also covers Runtime's complete public operations and the private recording/poison paths used by photography. Immutable reads use that same lock. A reentrant read during a mutation is unavailable rather than publishing intermediate state.

A deferred SQLite read transaction pins a committed view across the SELECTs and rolls back to release it. It performs no INSERT/UPDATE/DELETE and creates no journal events. The projection compares durable effective stage states with the existing engine's memory. Inconsistency, persistence uncertainty, an already open transaction, a closed database or a busy owner produce unavailability. Reads do not repair or reconcile state. A new engine or external owner must not be silently substituted to obtain a report.

The snapshot is a frozen dataclass containing tuples of frozen stage records. It reports stages in actual scenario order, including additional stages (maximum 256). `state` is the current effective state. `historicalSuccess` independently records whether success was committed previously. Invalidation can yield current `BLOCKED` with historical success. `lastAckSequence` is acknowledgement history; it never implies `SUCCEEDED`.

The read clock is separate from the engine's evidence clock. `capturedAt` records extraction of the point-in-time projection. It is not a sensor observation time, freshness guarantee, live heartbeat or readiness assessment. There is no overall READY derivation.

## HTTP contracts

| Route | Access | Result |
| --- | --- | --- |
| `GET /api/v1/status` | Public-safe LAB boot report | Existing API-01 contract: readiness UNKNOWN, no session data. |
| `GET /api/v1/session` | `session:read` grant for the bound session | Closed `vision.api.session.v1` projection. |
| `GET /api/v1/events?view=…&after=…&through=…` | `events:read` grant for the bound session | Closed `vision.api.events.v1` journal page. |

Schemas and a shared synthetic fixture are in `contracts/vision-api/v1/`. Python and TypeScript perform closed-schema and cross-field validation: canonical valid UTC dates, exact source/schema, unique stage IDs including S01–S11, safe integers, invalidation/current-state consistency, success/history consistency and event-kind/state semantics. JSON Schemas describe structure; application validators also enforce relationships and correlations.

The first events request uses `after=0`, `through=session.journalSequence` and `view=session.viewId`. Subsequent requests use `nextAfterSequence` with the same upper sequence and view. Each page has at most 50 events. All rows in that prefix are represented; unrecognised kinds become `OTHER`, unrecognised stages become null. Only sequence, stage, approved kind, timestamp and an applicable transition state are exported. Arbitrary `event.data`, request IDs, reasons, file paths, references, measurements and secrets are omitted. Newly appended events do not appear in the pinned prefix; Refresh session requests a new report.

The browser checks source/session/view/range correlation before combining reports. A new provider, wrong cursor or malformed page clears the protected view. Sequence numbers define journal order; timestamps need not be monotonic. One bounded page is retained in browser memory; Load more replaces it. No session data is persisted in browser storage.

## Authorization boundary

`Credentials` passes bounded Authorization/Cookie values only to the injected trusted authorizer. Duplicate credential headers are rejected. `X-User`, `X-Authorized`, query parameters, loopback and browser mode grant no access. Credentials and authorizer exceptions are neither logged nor returned.

Only an exact immutable `ReadGrant` with the required scope and provider session ID authorizes a read. Missing callbacks, exceptions, booleans, truthy strings, wrong sessions and missing scopes deny before provider access. An authorized read without a provider is unavailable. No built-in users, default tokens, test-token CLI switches, login routes, production secrets or client credential storage are included.

Protected browser fetches use same-origin credentials so a future server-managed HttpOnly session can be used. API-02 does not implement that identity/session lifecycle. Public boot fetches still omit credentials. Authorization is re-evaluated for every protected request.

Errors use the existing closed envelope: `401 ACCESS_DENIED`, `409 CURSOR_REJECTED`, `503 REPORT_UNAVAILABLE`. Existing path/method/transport errors remain unchanged. Provider/database/authorization exceptions are sanitised. No CORS, redirects, body-bearing GETs, route aliases or write methods are supported. The opt-in Vite proxy enumerates exact routes and is not a general proxy.

## Client behavior

System Status, Inspection Manager and Event Viewer share one transient view. Refresh session reads the session and first event page. Opening or closing a window sends no protected request. Starting a refresh/page load clears previous protected data; denial, invalid schema, provider mismatch or transport failure leaves it unavailable. DEMO and invalid modes have no protected read capability or fallback.

The Win98 desktop remains presentation only. It displays reported current states, historical success, ACK sequences and sanitised events. No start, stop, motion, capture, approval or readiness controls are added. Closing/reloading the browser cannot mutate the backend session.

## Limits and deployment gates

- Public response limit: 4096 decoded bytes. Protected response limit: 131072 decoded bytes. Client timeout: three seconds across fetch and body; early-rejected responses are also aborted/cancelled.
- Owner-lock acquisition limit: 0.25 seconds, **not** a deadline for the SQL query. SQL output/Python materialization is bounded; query cost depends on journal size. Indexing/retention and production service budgets need separate evaluation.
- Backend socket timeout: two seconds of inactivity, not an aggregate HTTP deadline. The serial loopback HTTPServer remains a LAB adapter. No LAN binding, TLS, deployment service, identity provider or operational station lifecycle is delivered.
- No ROS, CAN, PTP, robot motion, camera capture, systemd changes or active-station checkout changes are part of this stage.

## Verification and reproduction

Core/API tests use actual Workflow and Journal with synthetic evidence: pending/running/ACK/success/failure/block/invalidation, persistence uncertainty, additional stages, immutable reads, no writes/replay/construction/redispatch, deterministic post-commit concurrency, redaction, pages, authorization and HTTP boundaries.

`tests/api/serve_projection_fixture.py` constructs its engine before serving, labels it `SYNTHETIC_TEST`, and writes random credentials to an ignored private test file. No credential is printed, served by HTTP or bundled. Playwright injects the test cookie using its privileged test context, verifies initial denial and reads actual synthetic Core through the real HTTP adapter/proxy. Reload tests compare backend states and journal sequence before and after reload.

Commands (repository root, then webgui):

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests/api -v
cd webgui
npm run typecheck
npm run lint
npm test
npm run test:browser
npm run build
GUI_BUILD_SMOKE=1 npm run test:browser
VISION_API_INTEGRATION=1 npm run test:browser -- --grep 'actual API:'
VISION_API_INTEGRATION=1 GUI_BUILD_SMOKE=1 npm run test:browser -- --grep 'actual API:'
VISION_PROJECTION_INTEGRATION=1 npm run test:browser -- --grep 'actual Core:'
VISION_PROJECTION_INTEGRATION=1 GUI_BUILD_SMOKE=1 npm run test:browser -- --grep 'actual Core:'
```

GitHub runs existing backend regression workflows and the extended API/WebGUI workflow. Final acceptance uses the same reviewed head on VENTUNO ARM64 in isolated NVMe staging. Exact-head CI/ARM64 evidence is recorded in the PR, not claimed as active-station integration.
