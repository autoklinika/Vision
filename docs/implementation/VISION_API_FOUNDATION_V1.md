# Vision API Foundation V1 — API-01

**Status: candidate for independent audit and CI; not a deployed service.** Implements the first transport boundary between the WebGUI and an actual Python API process, following [ADR-VISION-WEBGUI-001](../decisions/ADR_VISION_WEBGUI_CLIENT_ONLY_2026-11-24.md). No changes to the Core, Runtime, Planner, hardware adapters, active station or services.

## Design

- [Versioned wire contract](../../contracts/vision-api/v1/README.md), JSON Schema and shared synthetic fixtures.
- `src/vision_api/status.py` defines a closed, non-sensitive API-only boot status.
- `src/vision_api/server.py` exposes the exact GET route on loopback, with bounded response and socket timeout, explicit Host/Origin checks, no CORS, no redirects, structured generic errors and no file access or commands.
- `webgui/src/api/realAdapter.ts` issues only the same-origin GET, requires secure context and validates HTTP status, content type, final URL, bounded body, encoding, full closed wire shape and UTC timestamp. Failure produces UNKNOWN/UNAVAILABLE. No writes, auth, cookies, cross-origin fallback or demo substitution.
- The startup read is independent of the intro; both startup and desktop show API-only last-report status and explicit Refresh. The previous result is discarded during a new read and on failure. There is no claim of a live connection, sensor observation or readiness from a successful API reply.
- The Vite lab proxy is opt-in via a numeric loopback port and forwards only the exact status route. It is not a reverse proxy deployment plan. Do not expose the lab dev or preview server externally.

API AVAILABLE is explicitly **not** Vision READY. The real provider is not connected. API-02 must supply the trusted Core/Runtime report and session/event data through reviewed, separately versioned contracts. API-03 will expose the existing ECU Library service with server-side validation, revisions, ETag and authorization. Do not implement workflow state machines or reference-profile validation in the browser.

## Validation

From the root:

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests/api -v
```

From `webgui/` (with Node 24, locked dependencies, installed Chromium):

```sh
npm run typecheck
npm run lint
npm test
python3 -B tests/test_prepare_brand.py
npm run test:browser
npm run build
GUI_BUILD_SMOKE=1 npm run test:browser
VISION_API_INTEGRATION=1 npm run test:browser -- --grep 'actual API:'
VISION_API_INTEGRATION=1 GUI_BUILD_SMOKE=1 npm run test:browser -- --grep 'actual API:'
npm audit --registry=https://registry.npmjs.org/
```

The integration tests start and stop a real Python server and Vite on loopback, not a hardware simulator or production service. They validate actual HTTP success in DEV and the production build, simulated loss at the transport boundary and restored actual responses. Shared fixtures cover rejected fake readiness, wrong version, malformed dates and extra fields. Private branding tests remain separately opted in on VENTUNO. The new [GitHub Actions workflow](../../.github/workflows/vision-api-webgui-v1.yml) executes public/synthetic tests with no private assets. Existing backend CI remains unchanged.

Local development is only on VENTUNO Q / NVMe; GitHub development and CI are permitted. Never use AI Platform as a Vision programming or test host.

## Remaining gates

Independent review, successful GitHub CI and separate ARM64 VENTUNO acceptance are required before declaring integration accepted. This package has no production auth/TLS, protected endpoints, real Core provider, actual ECU service integration, physical Kiosk or motion/capture operations. A successful lab test is not authorization to start a service on VENTUNO or operate equipment.
