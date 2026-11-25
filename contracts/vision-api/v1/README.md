# Vision API V1 — boot status and protected Core / ECU library reports

## API-03 protected ECU library reads

The library uses a separate `library:read` grant bound to one existing `ECULibraryService`. Session grants cannot authorize library reads. The ordinary LAB CLI remains default-deny; it does not initialize or discover a library.

| Exact GET target | Closed response |
| --- | --- |
| `/api/v1/library` | [library.schema.json](library.schema.json), first page |
| `/api/v1/library?view=<64hex>&after=<offset>` | Same library view, next/previous page |
| `/api/v1/library/entries/<32hex>?view=<64hex>` | [library-entry.schema.json](library-entry.schema.json), exact catalog or draft detail |
| `/api/v1/library/entries/<32hex>/history?view=<64hex>&after=<offset>` | [library-history.schema.json](library-history.schema.json), draft generation metadata |

Offsets are zero-based multiples of 50. Pages contain exactly the expected number of rows, up to 50; `nextAfter` is null at the end. The content-bound view includes committed generation ETags and all projected detail/history metadata. Every request rechecks authorization and captures the current bounded backend view. Changed views reject with `409 CURSOR_REJECTED`; the client must refresh. This is a pinned identity check, not a server snapshot cache or a database transaction spanning HTTP requests.

[Shared fixtures](library-fixtures.json) contain synthetic catalog, draft, 15-section structural summaries, physical states, workflows and two saved generations. Catalog records remain `NOT_READY / CATALOG_ONLY`; unsigned drafts remain `NOT_READY / UNSIGNED_DRAFT`. Section counts are `NOT_EVALUATED`, not a completeness or approval result. History contains IDs, ETags and revision labels, not old documents. No specimen selection, profile editing, release, asset download or operational readiness command is exposed. See the [implementation specification](../../../docs/implementation/VISION_API_ECU_LIBRARY_READ_V1.md).

Python and TypeScript validators check closed fields, exact identities, page counts, unique IDs, current-generation ETag position and cross-response source/library/view/entry correlation. Labels are bounded Unicode text with no path separators or General Category C characters. Three schemas express structural constraints; their comments identify additional application checks. Responses are limited to 131072 encoded bytes. Failures use the existing sanitized error envelope. Public boot and API-02 session/event contracts remain unchanged.

## API-02 protected read reports

`GET /api/v1/session` and `GET /api/v1/events?view=…&after=…&through=…` return the closed [session](session.schema.json) and [events](events.schema.json) contracts. They require per-request server authorization scoped to the fixed provider's session. The ordinary LAB CLI has no provider or authorizer, so protected reads are denied. The explicit synthetic test composition is outside production packages.

The [implementation specification](../../../docs/implementation/VISION_API_CORE_REPORTS_V1.md) defines synchronization, immutable extraction, exact cursors, authorization, redaction, freshness and deployment gates. [Shared fixtures](session-fixtures.json) are synthetic. Protected responses are bounded to 131072 bytes, at most 256 stages and 50 events per page. Additional errors: 401 ACCESS_DENIED, 409 CURSOR_REJECTED, 503 REPORT_UNAVAILABLE.

**Public boot status remains unchanged after API-02:** no session data, Core readiness always UNKNOWN. CORE_REPORT_NOT_CONNECTED describes this public API-only report, not whether a separate protected provider exists. API availability never establishes Vision readiness.

## API-01 foundation (historical scope)

Status: implementation candidate, isolated LAB only. Authority: [WebGUI client-only ADR](../../../docs/decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md).

## HTTP contract

`GET /api/v1/status` returns HTTP 200 and `application/json; charset=utf-8`, with the closed [status schema](status.schema.json). The reply proves that the local API transport responded; it does **not** establish Core, Runtime, device or inspection readiness. `reportTime` is the API process's UTC wall-clock timestamp, **not** a sensor observation. `observedAt` is null, `coreReadiness` UNKNOWN and `components` empty until a trusted provider is integrated by API-02. The fixed reason code is CORE_REPORT_NOT_CONNECTED. No protected data or hardware status is exposed. The response is a public-safe lab boot report, not a session or authorization.

All errors use [error.schema.json](error.schema.json) without raw exception messages. HTTP 400 BAD_REQUEST, 403 HOST_REJECTED / ORIGIN_REJECTED, 404 NOT_FOUND, 405 METHOD_NOT_ALLOWED (Allow: GET), 500 INTERNAL_ERROR. Unsupported methods never dispatch a command. Responses have no-store and close the connection. No CORS or redirects. Only exact path/version, without query. Malformed transport-level requests may be rejected before a complete HTTP response. The lab server binds IPv4 loopback only, accepts its exact Host, and rejects cross-origin requests. It has no filesystem routes or authentication. The two-second backend socket timeout is an inactivity limit, not an aggregate request deadline; the single-process HTTPServer is a local LAB tool, not a hardened production HTTP service. The client uses a three-second fetch/body deadline and a 4096-byte decoded response limit; it aborts rejected responses even when headers fail before body consumption.

The API-only client maps a valid result to API AVAILABLE (last report, not continuous monitoring), system readiness UNKNOWN. It never silently falls back to DEMO. Failed or invalid responses remove the last displayed successful report and produce UNAVAILABLE / UNKNOWN. Use explicit Refresh to re-read; no automatic control operations. Secure context (HTTPS remotely or trustworthy loopback) required. The API-only report may be shown before real authentication because it contains no protected information. API-02 and later protected routes require explicit server-side authorization, schema review, transport security and a trusted report provider. No production binding/TLS, real Core or ECU integration in API-01.

Shared [fixtures](status-fixtures.json) are synthetic, not measured hardware data. Wire contract changes require both provider and client review/tests. No source of motion, capture, workflow or readiness decisions is introduced in the client.
