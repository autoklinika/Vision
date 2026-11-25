# Authenticated station WebGUI deployment

> **Aktualizacja UI, 25.11.2026:** [Workspace V2](../ux/VISION_WORKSPACE_V2.md) zastępuje styl Windows 98, menu Start, zarządzanie oknami i zapis ich geometrii. Poniższe opisy tego wyglądu są historyczne. Zasady odpowiedzialności Core, uwierzytelniania, raportów i prywatności pozostają obowiązujące. Status wdrożenia jest odrębny od implementacji.

This document describes the original reader-only deployment. The proposed session lifecycle extension is documented in [VISION-RUNTIME-002](VISION_RUNTIME_002_STATION_SESSION.md); it adds explicit operator permission and new bounded operations without changing the legacy read schemas.

Scope: [initial deployment #62](https://github.com/autoklinika/Vision/issues/62), [independent Core connection #64](https://github.com/autoklinika/Vision/issues/64), and [Settings/password change #67](https://github.com/autoklinika/Vision/issues/67). The backend owns state, identity, permissions and ECU storage. The browser owns only presentation and local window preferences.

## Deployment boundary

`python -m vision_station.service` runs the independent Core host. It owns one persistent `ECULibraryService`, its `StationOwner` read adapter, and any explicitly attached real `VisionRuntimeCoordinator`. It starts idle, without constructing a Workflow or inventing specimen/profile/calibration data.

`python -m vision_api.station --core-socket ...` owns browser identity and presentation. It constructs a `RemoteStationOwner` transport client; it never opens the library or owns a Runtime. Authenticated reads travel over the private local Unix socket. Waitress 3.0.2 provides the HTTP parser, four request workers and bounded request sizes on IPv4 loopback. A station build contains an explicit marker; deployment refuses a demo/LAB build. Built assets are loaded from a small allowlist at startup. HTTP requests never choose filesystem paths, read repository files, follow asset symlinks or expose source maps.

The existing `vision_api.server` LAB executable and API-01/02/03 wire contracts remain compatible. Its public `/api/v1/status` is still a legacy LAB-only boot report and never means station readiness. The deployed client obtains its actual station summary from the authenticated `/api/v1/station` route.

The only remote origin is an explicitly configured HTTPS origin behind a local reverse proxy. The application validates Host and browser Origin against the same exact configured origin, rejects cross-site API requests, and does not trust forwarding headers to establish authority. Local access uses `http://127.0.0.1:18490`, a browser secure context. Remote plain HTTP is not an allowed configuration. Tailscale Serve is the intended private TLS ingress; Funnel/public internet exposure is not part of this deployment.

## Identity and read permissions

Accounts live in a private 0600 file outside the repository and static root. Every account has only the `reader` role. Local provisioning uses scrypt with a fresh 32-byte salt, N=32768, r=8, p=1 and a bounded KDF lock. Passwords are never command-line arguments, response fields or log values. A generated initial credential is written to a separate 0600 file on the station.

Successful login creates a random 256-bit session cookie. The server keeps only its hash in memory, with at most 64 active sessions. Cookies use HttpOnly, SameSite=Strict, Path=/, an eight-hour Max-Age, and Secure at the HTTPS origin. The loopback cookie omits Secure for local browser compatibility. No credential is placed in localStorage or IndexedDB.

Sessions expire after eight hours absolutely or thirty minutes without an authenticated client request, whichever comes first. Automatic report polling counts as client activity; this is not a thirty-minute operator inactivity lock. Inspecting `/auth/session` alone does not prolong a session. Logout, service restart, account removal, or local password reset revokes the relevant session. The account file is checked for revocation before every protected request. Invalid or unreadable account state fails closed. Login attempts are bounded globally and for the trusted transport client key.

An authenticated reader may change their own password in Settings. The account is selected exclusively from the authenticated session. The backend requires the current password, applies the existing minimum of 12 characters and maximum of 1024 UTF-8 bytes, and rejects an unchanged password. A successful atomic update generates a new salt and revokes every session for that account, including the requesting session. Other accounts retain their credentials and sessions. The UI returns to sign-in and never stores passwords in browser storage.

Credential changes share the private account-file lock with local provisioning. The backend rechecks the credential fingerprint and session before publishing so a concurrent reset/removal cannot be overwritten using an old session. Changes have separate throttling. A wrong current password preserves the session and returns `CURRENT_PASSWORD_INVALID`; session expiry remains `ACCESS_DENIED`. A storage or connection failure can leave the outcome unconfirmed, so the UI does not claim success or automatically repeat the write. None of these identity operations contacts Core, the ECU library or equipment.

All station/session/event/library reads authenticate before touching their provider. The owner then delegates only the existing `session:read`, `events:read`, or `library:read` grant for that exact owner. The owner's internal readers are trusted composition helpers; they are not independent public authorization endpoints. There are no HTTP routes for binding Core, selecting an ECU, creating an inspection, editing/approving a profile, moving hardware, capture, restarting Linux or shutting it down.

## Station lifecycle

At Core host startup there is no active inspection. A live reply reports `NO_ACTIVE_SESSION`, `coreConnection=CONNECTED`, `coreReadiness=UNKNOWN`, and null session IDs. The station instance ID belongs to the Core process, not an HTTP worker or browser. A fresh proxy/API process observes the same Core identity. Built-in catalog data keeps its existing DRAFT/NOT_READY status; no synthetic draft or inspection is inserted into the deployed store.

The Unix transport accepts only bounded station/session/events/library reads. It is private to the station UID, with a 0700 parent directory, 0600 socket, peer credential checks and an exclusive service lock. It exposes no attach, session creation, runtime mutation, hardware, filesystem-path or shutdown operation. Responses use the existing validated projections; invalid, unavailable or untrusted peers fail closed. Browser credentials never cross this transport.

If Core cannot be reached, the API returns a valid `NOT_CONNECTED` / `NO_ACTIVE_SESSION` station summary with its stable disconnected instance ID. In this fallback, `NO_ACTIVE_SESSION` means no reachable session binding; it does not assert that the actual Core has stopped an inspection. The UI shows its inspection state as unavailable. Session and library reads fail unavailable rather than returning cached Core data or creating a second owner. The desktop remains usable and retries automatically. Connection/instance changes remove old session and library views.

Trusted Core host composition may attach an existing real `VisionRuntimeCoordinator`; its already-owned Workflow is supplied to `StationOwner.bind_core(existing_engine)`. Binding does not construct Workflow, reopen a journal, replay events or issue commands. Replacement receives a fresh view ID. Cleanup uses the expected old view ID so a retired runtime cannot remove a newer binding. The registry lock is released before engine reads. A read checks its exact binding again before publication and rejects a concurrent cutover with 409. Engine/journal lifetime remains with its actual runtime owner; the read adapter never closes it.

The deployed host is real and idle. Starting an actual specimen inspection still requires the approved ECU/reference selection and trusted Runtime inputs; those prerequisites are not supplied by this read integration. `SESSION_ACTIVE`, when bound, means a session is attached; it is not proof that a stage is running or the system is ready. Closing or logging out of any browser, or restarting the WebGUI/API service, has no lifecycle effect on Core or the library.

## Additional HTTP contracts

| Route | Behavior |
| --- | --- |
| `POST /api/v1/auth/login` | Exact JSON `{username,password}`, same-origin Origin and `X-Vision-Client: webgui`; returns identity and Set-Cookie. |
| `GET /api/v1/auth/session` | Identity for an existing session, or 401. |
| `POST /api/v1/auth/logout` | Exact JSON `{}`, same-origin Origin and client header; revokes cookie and returns logout confirmation. |
| `POST /api/v1/auth/password` | Exact JSON `{currentPassword,newPassword}`, authenticated own account, same-origin Origin and client header; updates password, revokes all own sessions and clears the cookie. |
| `GET /api/v1/station` | Protected station lifecycle summary. |
| Existing session/events routes | Existing API-02 schemas for an attached inspection; 409 `NO_ACTIVE_SESSION` for connected idle Core; 503 if Core is unavailable. |
| Existing library routes | Existing API-03 schemas with `source=STATION`, backed by the persistent library. |

Identity: exact fields `schema=vision.api.identity.v1`, `authenticated=true`, `username` (1–64 ASCII identifier characters), `role=reader`, `expiresAt` (UTC timestamp).

Logout: exact fields `schema=vision.api.logout.v1`, `loggedOut=true`.

Password change: exact fields `schema=vision.api.password-change.v1`, `changed=true`. Errors distinguish 403 `CURRENT_PASSWORD_INVALID`, 400 `PASSWORD_REJECTED`, 401 `ACCESS_DENIED`, 429 `RATE_LIMITED`, and 503 `REPORT_UNAVAILABLE`. No username, password, hash, salt or credential fingerprint appears in the password-change response.

Station: exact fields `schema=vision.api.station.v1`, `source=STATION`, `instanceId` (32 hexadecimal characters; Core process while connected, stable proxy fallback while disconnected), `stationId=VENTUNO`, `capturedAt`, `state`, `coreConnection`, `coreReadiness=UNKNOWN`, `sessionId`, `sessionViewId`, `libraryId=vision-ecu-library`. `capturedAt` is report time, not hardware observation freshness. `CONNECTED + NO_ACTIVE_SESSION` is valid and has null session identifiers; an active session requires connected Core and both identifiers.

Errors use the existing closed `vision.api.error.v1` envelope. Authentication returns 401 `ACCESS_DENIED`; throttling returns 429 `RATE_LIMITED` and a bounded Retry-After; no bound Core returns 409 `NO_ACTIVE_SESSION`. Host/origin/method/cursor/storage failures remain explicit and sanitized. All responses are no-store, nosniff and frame-protected. Request headers are limited to 8192 bytes and POST bodies to 16384 bytes; the body bound accommodates JSON escaping of both maximum-size passwords. Credential and report bounds are also enforced by their existing validators.

## Client behavior and acceptance

`VITE_VISION_DEPLOYMENT=station npm run build` always creates the real authenticated station client. Query parameters cannot switch a station build to demo. The Win98 login resumes an existing HttpOnly session, signs in and signs out. Station summaries refresh every five seconds, identity every fifteen seconds, and library projections every fifteen seconds. A valid library view preserves browsing position; changed owner/view identities invalidate old selection. Protected data is removed when authentication or connectivity is lost and reacquired after recovery. The original LAB/demo shell remains available for isolated development.

Settings is available from a desktop icon and Start menu. Its first function is Change password, with current/new/confirmation fields and backend-owned validation. Success invalidates the current authenticated view and requires the new password at sign-in. The desktop layout format and existing app identifiers remain compatible. Connection lost also offers a full interface reload so an already-open browser tab can obtain a new deployed bundle.

Authenticated fetches explicitly use `referrerPolicy: same-origin` while retaining `mode: same-origin`, same-origin cookies and rejected redirects. Under the document's `no-referrer` policy, Firefox otherwise sends `Origin: null` for these POSTs; the backend correctly rejects that origin before checking credentials. The explicit request policy preserves the browser-generated same-origin header without accepting null origins or enabling cross-origin access. A 403 host/origin rejection is a transport failure, not an incorrect password or confirmed logout. See [Referrer-Policy and Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy#effect_on_the_origin_header).

Acceptance includes real KDF and session lifecycle tests, request/CSRF/static-root tests, binding-cutover tests, private IPC/owner lifecycle tests, existing API regressions, and Chromium/Firefox tests against the actual production build, WSGI server and separate Core host process. Each browser's station suite starts its own temporary fixture so account mutations and login-rate budgets remain isolated. Test accounts and library storage are temporary. The short-lived browser-test credential handoff file is private, ignored, denied by Vite and excluded from the deployment allowlist. Deployment evidence records the reviewed commit, CI/native results, running services, actual URLs and rollback target separately.
