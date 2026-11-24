# Vision API V1 — API-01 foundation

Status: implementation candidate, isolated LAB only. Authority: [WebGUI client-only ADR](../../../docs/decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md).

## HTTP contract

`GET /api/v1/status` returns HTTP 200 and `application/json; charset=utf-8`, with the closed [status schema](status.schema.json). The reply proves that the local API transport responded; it does **not** establish Core, Runtime, device or inspection readiness. `reportTime` is the API process's UTC wall-clock timestamp, **not** a sensor observation. `observedAt` is null, `coreReadiness` UNKNOWN and `components` empty until a trusted provider is integrated by API-02. The fixed reason code is CORE_REPORT_NOT_CONNECTED. No protected data or hardware status is exposed. The response is a public-safe lab boot report, not a session or authorization.

All errors use [error.schema.json](error.schema.json) without raw exception messages. HTTP 400 BAD_REQUEST, 403 HOST_REJECTED / ORIGIN_REJECTED, 404 NOT_FOUND, 405 METHOD_NOT_ALLOWED (Allow: GET), 500 INTERNAL_ERROR. Unsupported methods never dispatch a command. Responses have no-store and close the connection. No CORS or redirects. Only exact path/version, without query. Malformed transport-level requests may be rejected before a complete HTTP response. The lab server binds IPv4 loopback only, accepts its exact Host, and rejects cross-origin requests. It has no filesystem routes or authentication.

The API-only client maps a valid result to API AVAILABLE (last report, not continuous monitoring), system readiness UNKNOWN. It never silently falls back to DEMO. Failed or invalid responses remove the last displayed successful report and produce UNAVAILABLE / UNKNOWN. Use explicit Refresh to re-read; no automatic control operations. Secure context (HTTPS remotely or trustworthy loopback) required. The API-only report may be shown before real authentication because it contains no protected information. API-02 and later protected routes require explicit server-side authorization, schema review, transport security and a trusted report provider. No production binding/TLS, real Core or ECU integration in API-01.

Shared [fixtures](status-fixtures.json) are synthetic, not measured hardware data. Wire contract changes require both provider and client review/tests. No source of motion, capture, workflow or readiness decisions is introduced in the client.
