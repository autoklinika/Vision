# Vision Startup & Desktop V1 (GUI-02 + API-01)

WebGUI is **only a client of the entire Vision system**. This isolated React / TypeScript / Vite / 98.css package implements presentation. API-01 adds a read-only same-origin HTTP client for the API-only boot report. No authentication, hardware/ROS/MoveIt access, workflow or operational commands.

## Run and verify

Use Node 22.12+ and npm. From `webgui/`:

```sh
export NPM_CONFIG_CACHE="$PWD/.npm-cache"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.browser-cache"
npm ci --registry=https://registry.npmjs.org/
npx playwright install chromium
npm run dev
# In another terminal, with the same package-local environment:
npm run typecheck
npm run lint
npm test
python3 -B tests/test_prepare_brand.py
npm run test:browser
npm run build
GUI_BUILD_SMOKE=1 npm run test:browser
npm audit --registry=https://registry.npmjs.org/
```

No global installation or sudo. Servers bind to loopback. Browser installation downloads tooling. Runtime requests are limited to same-origin app resources, optional local brand files and the boot-status GET in explicit real mode. No external services or operational writes. Known ESLint 9 deprecation warning remains; dependencies were not migrated.

## Sequence and client boundaries

A. Optional original intro plays once for **3490 ms**, including the original black fade, centered on white with responsive scale. Skip is always available. Reduced motion displays the static original hold without mounting the GIF and disables the calm 160 ms dialog appearance transition.

B. `readClientReport()` starts the selected adapter read **before React mounts**, independently of asset loading/animation. Report shows source, connection, UNKNOWN readiness, observation availability and adapter reasons. Pending means no system status received; an accessible Win98 segmented indeterminate indicator has no numeric value. Reduced motion stops its movement. Completion ends only the client read, never establishes system initialization or readiness. Rejected/throwing reads or source mismatch produce UNKNOWN / UNAVAILABLE and an explicit client failure explanation. No percentages, simulated initialization or timer-derived readiness. The 2 s optional asset timeout affects presentation only. Read-only diagnostics remain accessible when the snapshot fails or never resolves.

C. Win98 login is presentation only: user/password inputs are disabled, outside any form; no credentials are collected, submitted or stored. **Continue to DEMO desktop** / **Open read-only view** are not authentication. Back returns to the report. Direct diagnostics can bypass the login presentation.

D. GUI-01 desktop retains window lifecycle, keyboard/pointer controls, layout persistence, Start and read-only apps. It receives the same report without an implicit additional read. Explicit Refresh API report discards the previous displayed result while awaiting the next read. Only local window layout is persisted. Closing/reloading cannot issue system commands.

Default remains explicitly `demo` for this isolated package, with a separate synthetic chunk and persistent DEMO banner. Only explicit `?mode=real` reads the versioned API. Invalid modes fail closed without network; never demo fallback. Mode stays visible throughout. `src/api/types.ts` is a client presentation interface; the [wire contract](../contracts/vision-api/v1/README.md) is separate. `readSnapshot()` is the only adapter operation.

## Optional private original preparation

Distribution rights are **not verified**. Original/derived brand bytes and manifest must not enter Git, public GitHub, screenshots/traces or published artifacts. `public/local-brand/` is explicitly ignored. Standard builds exclude private public assets even after preparation; only third-party notices are copied from `public/`. Build smoke uses missing assets and rejects intercepted synthetic substitutions. No publishing is authorized.

From `webgui/`, manually supply the authorized original (relative example for this isolated clone):

```sh
python3 scripts/prepare-brand.py ../../private-assets/VISION-handwriting-intro-PREVIEW.gif
# Explicit local verification, without screenshots/video/traces:
GUI_PRIVATE_ORIGINAL=1 npm run test:browser -- --grep 'private original'
```

Required original: SHA-256 `e18f9695ad38df61a4f8fdf4104e7d9b8b60456a2f454404cf9c819590f16adb`, 29462 bytes, 800×100, 29 encoded frames (supplied 47-frame original sequence), 3490 ms encoded duration.

Importer invalidates stale outputs, verifies exact checksum/size and decoded dimensions/count/duration, parses GIF blocks and removes only NETSCAPE/ANIMEXTS loop application extensions. No GIF re-encoding. All 29 decoded frames and individual delays are compared with the original. Frame 12 is the complete white-background hold (990 ms); its composited pixels become the PNG logo, without recreation. Outputs: `intro.gif`, `logo.png`, `manifest.json` under ignored `public/local-brand/`. Manifest records checksums/timing, never source paths. Browser uses fixed same-origin URLs, rejects redirects, bounds streamed manifest/asset reads to 2048/300000 bytes, and verifies both derivatives against trusted `src/startup/brand-reference.json`, independently of manifest claims, before creating blob URLs. The importer uses the same reference. The GIF is pinned byte-for-byte. PNG uses RGB8, filter 0, deterministic stored DEFLATE blocks and no metadata; encoding does not depend on Pillow or zlib compressor versions. Its new SHA-256 is `65f1e7f2f909691467d7e4752b909b53676953043555c99e30a09cd6a2a4f7ea`; this deliberately replaces the earlier compressed PNG encoding while preserving frame 12 pixels.

Python 3/Pillow are optional for preparation only. Check: `python3 -c "from PIL import Image; print(Image.__version__)"`. If missing, skip preparation; the package and CI work without Pillow or original. Optionally use a private virtual environment; never install globally. No imitation is shipped as a production logo.

Missing/corrupt assets, invalid manifest/hash, decode failure or timeout show an explicit explanation and permit report/login/diagnostics/desktop. Failed import leaves no stale manifest. Delete `public/local-brand/` to remove derivatives locally; never force-add it.

## Tests and limitations

`src/startup/` separates report acquisition, asset verification and presentation. CI uses independent 8×8 geometric GIF/PNG fixtures only to prove substitution is rejected, never as authentic branding. Snapshot injection is confined to Playwright interception of dev modules (skipped in build smoke); there is no production verification bypass. Coverage includes sequence, duration, skip, reduced motion, missing/corrupt assets, failed/pending snapshot, disabled credentials, demo/real/invalid boundaries, no external requests and GUI-01 desktop regressions. Python parser tests use only the standard library. Private-original tests are explicit opt-in and verify full-duration rendering, dimensions, skip, reduced motion and one-byte mutation rejection without screenshots, video or traces.

No hardware/VENTUNO, live Core, auth, kiosk or production acceptance is claimed. Operational app windows remain unavailable placeholders. API-01 uses a versioned minimal boot-report schema and existing dependencies.

98.css fonts are FontStructions by lou, CC BY-SA 3.0; notices ship in `public/THIRD_PARTY_NOTICES.txt` and the build. GUI-01 SVG icons remain original geometric artwork. No proprietary OS icons/fonts added.

Historical baseline: [GUI-01 audit](docs/audit/GUI-01_AUDIT_2026-11-24.md). Historical implementation results: [GUI-02 audit](docs/audit/GUI-02_AUDIT_2026-11-24.md). Remediation evidence: [G02-R01–R03](docs/audit/GUI-02_REMEDIATION_2026-11-24.md).

## Secure context and release blocker

Remote clients require **HTTPS**; local verification may use trustworthy loopback (`localhost`/`127.0.0.1`). On insecure remote HTTP the client displays an accessible secure-context explanation before any brand fetch or digest; report and diagnostics remain available. There is no insecure fallback. Browser tests use a genuine non-local HTTP origin intercepted to the local test server, without relaxing Chromium security. TLS deployment and host configuration are outside this change.

Private brand distribution remains a **release blocker** pending rights and an approved delivery procedure. Standard builds deliberately exclude all private assets. This remediation is not independent acceptance, merge approval, or production/hardware acceptance. API-01 validates the boot-report schema and permits explicit refresh/retry. It labels the response as a last report rather than a live connection. API-02 will integrate authoritative Core/Runtime reports and define their freshness policy.

## API-01 isolated loopback integration

See [contract](../contracts/vision-api/v1/README.md) and [implementation](../docs/implementation/VISION_API_FOUNDATION_V1.md). From repository root, run `PYTHONPATH=src python3 -m vision_api.server --port 18491` only for an explicit isolated LAB. From webgui, start `VISION_API_LAB_PORT=18491 npm run dev` (or preview after build), and open `http://127.0.0.1:5173/?mode=real` if using Vite's default dev port. Do not expose either dev server or this API to the network. Stop both at the end of the test. CI's dedicated integration suite manages its own short-lived loopback processes. API AVAILABLE means the last validated HTTP reply only; Core is UNKNOWN and no protected data or device status is exposed. No authentication or production transport is implemented. Real API status tests and synthetic branding tests do not require original assets.
