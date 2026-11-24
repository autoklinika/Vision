# Vision Desktop Shell V1 (GUI-01)

WebGUI is only a client of the entire Vision system. This standalone React / TypeScript / Vite / 98.css package implements desktop presentation only. It does not implement Core, Runtime, Planner, workflow, ROS 2, MoveIt, device access or business state.

## Run and verify

Use Node 22.12+ (verified with Node 26.8.1) and npm. From `webgui/`:

```sh
npm ci --registry=https://registry.npmjs.org/
npm run dev
npm run lint
npm run typecheck
npm test
npm run build
# Browser binaries stay inside this isolated package:
PLAYWRIGHT_BROWSERS_PATH=.browser-cache npx playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=.browser-cache npm run test:browser
```

npm uses the official registry and package-local cache. No global installation, backend, hardware or external services are required. Dev and test servers bind only to loopback. Browser installation downloads test tooling; the application itself makes no API or hardware requests.

## Implemented

- Teal desktop, gray beveled controls, navy active title bars, original geometric SVG icons, Start menu and taskbar.
- Single instance per application, independent movable/resizable windows, focus stacking, minimize/maximize/restore/close. Title bars support arrow-key movement; resize handles support arrow-key resizing (Shift for larger steps). Start supports arrows, Home/End and Escape. All actions have native keyboard controls.
- Versioned, size-limited and validated local layout preferences; malformed/unknown data resets safely, blocked storage does not prevent use. Control Panel resets layout. Bounds are clamped after viewport changes, including small screens.
- System Status reads only the selected adapter. Distinct unavailable placeholders: ECU Library, Inspection Manager, Luxonis, NERO, Sony, Images, Event Viewer. Control Panel changes only local layout.
- Deterministic reducer/adapter tests and browser tests for lifecycle, keyboard, persistence, bounds, no external requests and fail-closed real mode.

## Architecture and adapter boundary

`src/shell/model.ts` is a pure presentation reducer; `Desktop.tsx` owns input/focus/rendering. `src/apps/` contains presentation views. `src/api/types.ts` defines a **client-side presentation interface**, not an approved backend wire contract. `readSnapshot()` is the only adapter operation; there are no command methods.

The default mode is explicitly `demo`. It loads `src/demo/adapter.ts` in a separate dynamic chunk and shows a persistent DEMO banner. Fixtures contain no production records, timestamps or fabricated readiness: readiness remains UNKNOWN. `?mode=real` (and every unrecognized mode) selects `src/api/realAdapter.ts`, which reports UNAVAILABLE without transport, endpoints or demo fallback. No local preferences select the adapter or store system data. All displayed system status comes from the adapter; no timer produces readiness.

## Limitations and proposed follow-up (not implemented)

GUI-02: approved original intro asset and login/startup presentation. GUI-03–06: profile editor (existing 15-section UX), inspection and media applications. GUI-07–08: reviewed shared API contracts, runtime payload validation, authorization, freshness/event continuity, reconnect, kiosk and system requests. There is no real transport, login, readiness assessment, device control, event journal, business-state persistence or production integration in GUI-01. Disabled controls are intentionally unavailable. Reset/close/reload only affect this client.

The unmodified 98.css fonts are FontStructions by lou, licensed CC BY-SA 3.0; attribution and upstream notices ship in `public/THIRD_PARTY_NOTICES.txt` and the build. No proprietary OS icons, logos or startup assets were copied. All application SVG icons were drawn in this package. Dependencies and their exact resolutions are recorded in `package-lock.json`; upstream license notices remain in installed packages (98.css MIT, React MIT, Vite MIT, TypeScript Apache-2.0). Hardware acceptance and production readiness are outside this change.

## Verification record

In this isolated clone: `npm run typecheck`, `npm run lint`, `npm test` (6 tests), `npm run build`, and `PLAYWRIGHT_BROWSERS_PATH=.browser-cache npm run test:browser` (3 Chromium tests) passed. `npm audit` reported 0 vulnerabilities after tooling patch updates. The desktop screenshot was inspected. No backend or hardware acceptance is claimed.
