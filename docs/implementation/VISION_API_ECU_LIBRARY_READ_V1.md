# API-03 — protected ECU library read integration

Scope: [issue #60](https://github.com/autoklinika/Vision/issues/60), following API-02 main `32e4fc6b24b930ad738f1907ee1a96f26115092b`. This stage connects the existing library backend to a read-only Win98 browser window. It supplies composition seams and a synthetic integration harness; attaching the active station library and production identity service remains a deployment task.

## Authority and supported records

**WebGUI is only a client of Vision.** The library owner controls stored data, structural validation, revision governance and approvals. Core / Runtime own specimen sessions, identity verification, readiness and all operational decisions.

The source is the existing `vision_modules.ecu_library_backend.ECULibraryService`, with its in-memory catalog and persisted unsigned draft store. It is not the separate `ecu_reference.ReferenceLibrary` registry. The current service does not provide a persistent approved-release catalog. API-03 therefore makes no claim that released reference profiles are connected.

The trusted composition supplies an **already initialized** service to `LibraryReportProvider(service, library_id=..., source=...)`, then injects it and a separate `library_authorizer` into `make_server`. Neither a request nor the adapter creates a data root or calls the service constructor. The ordinary LAB CLI provides no library binding or authorizer and denies these reads.

Three concepts remain distinct:

| Concept | API-03 behavior |
| --- | --- |
| Catalog declaration | Shows exact family, variant, catalog revision and declared connector metadata. `NOT_READY / CATALOG_ONLY`, including catalog records whose catalog review status is APPROVED. |
| Reference draft | Shows exact profile identity, draft revision, generation ETag and limited structural details. `DRAFT / NOT_READY / UNSIGNED_DRAFT`. |
| Specimen inspection | Owned by Core / Runtime; browsing a reference does not declare, select, identify or create a specimen. |

The operator-declared ECU and later sensor verification remain separate from catalog browsing. No automatic identification or variant substitution is added.

## Consistent, nonmutating extraction

`LibraryReadModel(existing_service).capture()` returns frozen dataclasses and tuples. `DraftStore.read_snapshot()` uses the existing owner RLock and opens the existing filesystem `.lock` read-only, then takes a shared flock. It never uses the write transaction, O_CREAT, chmod, asset ingestion or a repair path. A new, empty store without `.lock` can produce an empty draft view without creating a lock. Existing drafts without their lock are unavailable.

The current pointer and complete committed history chain are verified before any data leaves the backend. Every generation must retain the same profile/family/variant/revision identity and satisfy the unsigned-draft invariant: DRAFT, not template-only, no approved scopes, release approval or released/content hash. Missing or corrupt ancestors, invalid hashes, duplicate identities, symlinks, cycles and inconsistent state reject the whole read. Interrupted-write orphan snapshots remain invisible because only committed lineage is traversed.

The catalog registry is checked before and after draft extraction; an intervening append rejects the mixed capture. The catalog is an append-only registry with immutable registered revisions. A point-in-time snapshot may become old immediately after extraction, so `capturedAt` describes extraction, never sensor freshness or continuous monitoring.

The SHA-256 `viewId` covers all projected catalog/draft/detail/history fields, including generation ETags. Saving A, then B, then A creates a new generation and a new view even if displayed content reverts. The opaque 32-hex `entryId` derives from record kind and exact profile/family/variant/revision identity. It is a selector, not an authorization credential. `libraryId` is a separate composition-owned identity.

Each detail or page request performs a fresh bounded capture and compares its view with the requested view. A changed view rejects as `409 CURSOR_REJECTED`; the server does not combine old list entries with new details or retain an unbounded snapshot cache. Reads have no operational side effects.

## Closed projection and limits

The [wire contracts](../../contracts/vision-api/v1/README.md) are under `contracts/vision-api/v1/` in the repository; the relative links below point there directly:

- [Library pages](../../contracts/vision-api/v1/library.schema.json): catalog and draft summaries, 50 rows per page.
- [Entry details](../../contracts/vision-api/v1/library-entry.schema.json): one exact selected entry.
- [Draft history](../../contracts/vision-api/v1/library-history.schema.json): 50 generation metadata rows per page, oldest first.

Catalog details contain connector IDs/colors, the unverified field-note count and envelope presence. Field-note text, reported dimensions and provenance are omitted. Draft details contain the 15 named sections as structural row counts, physical-state IDs/names with an explicitly **declared** verification flag, workflow IDs/state/scope and the history count. Scalar/mixed sections use null where a generic row count would be misleading.

`NOT_EVALUATED` means the adapter has not assessed a section's completeness or readiness. A positive count or `declaredVerified=true` never approves an unsigned draft. The real `evaluate_readiness` operation requires an exact state, recipe, scope and trusted capabilities/calibrations/verified assets; this read stage does not invent that context or invoke the operation. Format, lineage, integrity and unsigned-draft checks are authoritative backend validation, distinct from operational readiness evaluation.

No raw reference JSON, arbitrary policy/provenance strings, file paths, asset URLs, image bytes, measurement details, credentials or exception text are projected. Human display labels are explicit exported fields and must satisfy the supported API limits; the read projection cannot determine whether an owner has placed sensitive text inside an otherwise valid label.

| Limit | Behavior |
| --- | --- |
| Catalog and draft count | At most 256 each, 512 combined. |
| Draft directory enumeration | At most 512 entries examined. |
| History work per capture | At most 4096 total committed generations and 8 MiB aggregate file reads across all drafts. |
| Detail collections | At most 128 physical states, 128 workflows and 64 catalog connectors. |
| Wire strings | Identifiers: 1–64 ASCII letters/digits/underscore/hyphen, starting with a letter/digit. Labels: 1–160 Unicode code points, no path separators or Unicode General Category C characters. |
| Page size | 50; offsets are multiples of 50. `nextAfter` is null at the end. |
| HTTP response | At most 131072 encoded JSON bytes; excessive reports fail whole, including valid but unusually large Unicode detail. |
| Locks | Owner acquisition and shared filesystem-lock acquisition each wait at most 0.25 seconds. These are not aggregate filesystem/JSON-processing deadlines. |

The API intentionally supports a bounded subset of labels/identifiers accepted by the general profile parser. Unsupported content makes the view unavailable rather than being silently shortened or renamed. Large libraries and longer history require a separately designed indexed read service; no partial-success truncation is used here.

Checksums protect against accidental damage and unexpected mutation. As in the existing store, they are not a signature against a privileged local writer who rewrites all content and recomputes hashes. Storage ownership and approved-release signing remain outside this read adapter.

## Independent authorization and transport

Only an exact immutable `LibraryReadGrant` with `library:read` and the provider's `library_id` authorizes a request. A session `ReadGrant`, truthy boolean/string, wrong library, missing authorizer or authorizer exception denies **before extraction**. Authorized access without a provider is unavailable. Authorization runs again on every list, detail and history request.

Credentials are passed only to the injected authorizer; they never enter reports, logs, the library or application-managed localStorage/sessionStorage. Server-managed HttpOnly cookies remain in the browser cookie jar. Existing bounded Authorization/Cookie header rules apply. Client mode, localhost, `X-User`, `X-Authorized`, query strings and knowing a view/entry ID confer no authority.

All four exact route forms are listed in the [contract index](../../contracts/vision-api/v1/README.md). Unknown parameters, reordered/duplicated parameters, padded offsets, trailing slashes and path aliases are rejected. GET is the only supported method. Errors retain the closed envelope: 401 ACCESS_DENIED, 409 CURSOR_REJECTED, 503 REPORT_UNAVAILABLE, plus existing route/transport errors. There is no CORS, redirect, raw filesystem endpoint or credential injection route. Public boot status and protected session/event reports retain their previous contracts.

The Vite LAB proxy enumerates the exact library paths. It cannot become a general proxy to the backend. The browser uses the existing same-origin protected transport: secure context, GET, same-origin credentials, no-store, redirect rejection, fatal UTF-8 decoding, closed-schema validation, three-second fetch/body deadline and byte limit. A rejected response is cancelled even when failure occurs before body reading.

Vite's existing filesystem-deny defaults are preserved and extended to explicitly deny both private API-02/API-03 test credential filenames. Being gitignored or mode 0600 is not sufficient when the development server runs as the file owner. Actual integration tests attempt direct, encoded, transform-query and `/@fs/` reads before authentication and verify that no credential is returned. Production preview serves the build directory, which excludes these files.

The serial Python HTTPServer remains a loopback LAB adapter. Its two-second socket inactivity timeout is not an overall request deadline. TLS, deployment ingress, production identity/session lifecycle, active library ownership and production concurrency budgets remain separate deployment gates.

## Win98 client behavior

The ECU Library window replaces the placeholder with a read-only browser. **Refresh library** fetches one page; opening a window sends no protected request. Browsing an entry fetches exact details and, for drafts, the first history page. Overview, 15 sections and revision-history tabs display the backend result. Previous/next page controls retain only one bounded page in memory.

Starting a protected load clears the previously displayed protected data. Denial, transport/schema failure or stale view leaves no stale catalog/detail/history behind. The UI checks source, library ID, view ID, exact summary identity/ETag and history counts before combining responses. Reload discards this transient state and does not modify the library. DEMO and invalid client modes expose no library read methods and make no library request.

SYNTHETIC_TEST reports are visibly labelled. The reference-editor button stays unavailable until the separate editor/command stage is implemented. No edit, save, validate, approve, session selection, recipe execution, motion or capture control is added.

## Verification and acceptance

Backend/API tests cover noncreating reads, unchanged files, cross-owner writer locks, whole-lineage validation, aggregate limits, redaction, exact 15 sections, changed catalog snapshots, A→B→A, independent authorization, pagination, ETags, stale view rejection and actual HTTP round trips. Browser unit tests consume the same synthetic fixture as Python. Browser tests cover no automatic request, explicit browsing, errors clearing protected content, page/view correlation and the Win98 layout.

`tests/api/serve_library_fixture.py` creates a real `ECULibraryService` with synthetic data **before serving**, in a private temporary directory. It creates one catalog record and one draft with a physical state, workflow and two generations. A random cookie is written to an ignored file with mode 0600 and never printed, served or bundled. The test runner injects that cookie into its isolated browser context. SIGTERM cleanup removes the file and temporary store. This harness is outside production packages.

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests/api -v
cd webgui
npm run typecheck
npm run lint
npm test
npm run test:browser
npm run build
GUI_BUILD_SMOKE=1 npm run test:browser
VISION_LIBRARY_INTEGRATION=1 npm run test:browser -- --grep 'actual Library:'
VISION_LIBRARY_INTEGRATION=1 GUI_BUILD_SMOKE=1 npm run test:browser -- --grep 'actual Library:'
```

CI also retains the actual API-01 and Core/API-02 DEV/build integrations and all existing backend workflows. Final acceptance uses the reviewed commit on isolated VENTUNO NVMe ARM64 staging and records exact CI/ARM64 evidence in the pull request. Active checkout, systemd, ROS, CAN, PTP, cameras and physical motion are outside this stage.
