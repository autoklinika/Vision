# Authenticated station WebGUI deployment

Scope: [issue #62](https://github.com/autoklinika/Vision/issues/62). This adds a deployable station client after API-03. The backend owns state, identity, permissions and ECU storage. The browser owns only presentation and local window preferences.

## Deployment boundary

`python -m vision_api.station` constructs the existing `ECULibraryService` once, an identity store once, and a `StationOwner` once. Waitress 3.0.2 provides the HTTP parser, four request workers and bounded request sizes on IPv4 loopback. A station build contains an explicit marker; deployment refuses a demo/LAB build. Built assets are loaded from a small allowlist at startup. HTTP requests never choose filesystem paths, read repository files, follow asset symlinks or expose source maps.

The existing `vision_api.server` LAB executable and API-01/02/03 wire contracts remain compatible. Its public `/api/v1/status` is still a legacy LAB-only boot report and never means station readiness. The deployed client obtains its actual station summary from the authenticated `/api/v1/station` route.

The only remote origin is an explicitly configured HTTPS origin behind a local reverse proxy. The application validates Host and browser Origin against the same exact configured origin, rejects cross-site API requests, and does not trust forwarding headers to establish authority. Local access uses `http://127.0.0.1:18490`, a browser secure context. Remote plain HTTP is not an allowed configuration. Tailscale Serve is the intended private TLS ingress; Funnel/public internet exposure is not part of this deployment.

## Identity and read permissions

Accounts live in a private 0600 file outside the repository and static root. Every account has only the `reader` role. Local provisioning uses scrypt with a fresh 32-byte salt, N=32768, r=8, p=1 and a bounded KDF lock. Passwords are never command-line arguments, response fields or log values. A generated initial credential is written to a separate 0600 file on the station.

Successful login creates a random 256-bit session cookie. The server keeps only its hash in memory, with at most 64 active sessions. Cookies use HttpOnly, SameSite=Strict, Path=/, an eight-hour Max-Age, and Secure at the HTTPS origin. The loopback cookie omits Secure for local browser compatibility. No credential is placed in localStorage or IndexedDB.

Sessions expire after eight hours absolutely or thirty minutes without an authenticated client request, whichever comes first. Automatic report polling counts as client activity; this is not a thirty-minute operator inactivity lock. Inspecting `/auth/session` alone does not prolong a session. Logout, service restart, account removal, or local password reset revokes the relevant session. The account file is checked for revocation before every protected request. Invalid or unreadable account state fails closed. Login attempts are bounded globally and for the trusted transport client key.

All station/session/event/library reads authenticate before touching their provider. The owner then delegates only the existing `session:read`, `events:read`, or `library:read` grant for that exact owner. The owner's internal readers are trusted composition helpers; they are not independent public authorization endpoints. There are no HTTP routes for binding Core, selecting an ECU, creating an inspection, editing/approving a profile, moving hardware, capture, restarting Linux or shutting it down.

## Station lifecycle

At startup the owner has no active Core binding. This is reported honestly as `NO_ACTIVE_SESSION`, `coreConnection=NOT_CONNECTED`, `coreReadiness=UNKNOWN`, and null session IDs. A persistent library can be available while Core is not connected. Built-in catalog data keeps its existing DRAFT/NOT_READY status; no synthetic draft or inspection is inserted into the deployed store.

Trusted backend composition may call `StationOwner.bind_core(existing_engine)` with the actual already-owned Workflow. This does not construct Workflow, reopen a journal, replay events or issue commands. Replacement receives a fresh view ID. Cleanup uses the expected old view ID so a retired runtime cannot remove a newer binding. The registry lock is released before engine reads. A read checks its exact binding again before publication and rejects a concurrent cutover with 409. Engine/journal lifetime remains with its actual runtime owner; the adapter never closes it.

The initial service does not own an operational Runtime coordinator. Attaching the actual inspection owner remains explicit backend integration work. `SESSION_ACTIVE`, when bound, means a session is attached; it is not proof that a stage is running or the system is ready. Closing or logging out of any browser has no lifecycle effect on Core or the library.

## Additional HTTP contracts

| Route | Behavior |
| --- | --- |
| `POST /api/v1/auth/login` | Exact JSON `{username,password}`, same-origin Origin and `X-Vision-Client: webgui`; returns identity and Set-Cookie. |
| `GET /api/v1/auth/session` | Identity for an existing session, or 401. |
| `POST /api/v1/auth/logout` | Exact JSON `{}`, same-origin Origin and client header; revokes cookie and returns logout confirmation. |
| `GET /api/v1/station` | Protected station lifecycle summary. |
| Existing session/events routes | Existing API-02 schemas when Core is bound; 409 `NO_ACTIVE_SESSION` otherwise. |
| Existing library routes | Existing API-03 schemas with `source=STATION`, backed by the persistent library. |

Identity: exact fields `schema=vision.api.identity.v1`, `authenticated=true`, `username` (1–64 ASCII identifier characters), `role=reader`, `expiresAt` (UTC timestamp).

Logout: exact fields `schema=vision.api.logout.v1`, `loggedOut=true`.

Station: exact fields `schema=vision.api.station.v1`, `source=STATION`, `instanceId` (32 hexadecimal characters, fresh per process), `stationId=VENTUNO`, `capturedAt`, `state`, `coreConnection`, `coreReadiness=UNKNOWN`, `sessionId`, `sessionViewId`, `libraryId=vision-ecu-library`. `capturedAt` is report time, not hardware observation freshness.

Errors use the existing closed `vision.api.error.v1` envelope. Authentication returns 401 `ACCESS_DENIED`; throttling returns 429 `RATE_LIMITED` and a bounded Retry-After; no bound Core returns 409 `NO_ACTIVE_SESSION`. Host/origin/method/cursor/storage failures remain explicit and sanitized. All responses are no-store, nosniff and frame-protected. POST request bodies and headers are limited to 8192 bytes; the body bound accommodates JSON escaping of a maximum-size password. Credential and report bounds are also enforced by their existing validators.

## Client behavior and acceptance

`VITE_VISION_DEPLOYMENT=station npm run build` always creates the real authenticated station client. Query parameters cannot switch a station build to demo. The Win98 login resumes an existing HttpOnly session, signs in and signs out. Station summaries refresh every five seconds, identity every fifteen seconds, and library projections every fifteen seconds. A valid library view preserves browsing position; changed owner/view identities invalidate old selection. Protected data is removed when authentication or connectivity is lost and reacquired after recovery. The original LAB/demo shell remains available for isolated development.

Acceptance includes real KDF and session lifecycle tests, request/CSRF/static-root tests, binding-cutover tests, existing API regressions, and Chromium tests against the actual production build and WSGI server. Test accounts and library storage are temporary. The short-lived browser-test credential handoff file is private, ignored, denied by Vite and excluded from the deployment allowlist. Deployment evidence records the reviewed commit, CI/native results, running service, actual URLs and rollback target separately.
