# Vision ECU Draft Editor V1 (Core/API/WebGUI)

Status: candidate; universal unsigned reference authoring, not production acceptance.
Base: a5c2416 (Runtime session orchestration). The same independent Core Host
owns the ECU library and draft editor. No second operational store, approval
authority, device driver, Runtime or Workflow is constructed by the editor.

## Workflow and user interface

Open ECU Library with explicit operator permission. Choose New profile to
create an empty unsigned reference for any declared family and variant, or
browse an existing catalog record and create a draft based on its identity.
Creating a reference does not register or approve a catalog ECURecord. No
measured values, physical state or inspection recipe are prefilled. Opening
an existing draft loads its exact stored document and ETag.

The editor uses dedicated controls for every supported field in the 15-section
reference V1 schema, not raw JSON. The presentation schema is separate from
Core's authoritative validation. It covers metadata, declared identity,
physical states, coordinate systems, geometry, connectors/landmarks, reference
assets, recognition/localization rules, PCB regions, photographic and thermal
recipes, inspection workflows, validation policies and source/calibration
provenance. It renders nested collections, XYZ/XYZW and rectangle fields,
enumerations, checkboxes, named numeric thresholds, units and reference lists
derived from the same working document. Fixed policies, release status,
identity keys and approval fields are read-only. Existing enum/reference values
are never silently replaced; an unresolved reference remains visible until
corrected. Unknown nested fields fail closed instead of disappearing on save.

Users may save structurally valid incomplete profiles: empty sections and
optional null values are allowed by the existing V1 schema. An incomplete
required field in an added row must be filled or that row explicitly removed
before saving. Numeric input accepts decimal comma or point, preserves explicit
zero and never invents a measurement. The local form identifies the first
incomplete field and opens its section. Core remains authoritative for
types, dimensions, cross references, fixed policies and draft invariants.
The Check structure operation needs no fabricated state/recipe; scope
diagnostics use a user-selected declared state and workflow. These checks
report NOT_READY even when structurally valid. No approval is performed.

Save creates an immutable generation with an ETag. Clone saved revision
requires the exact saved source ETag, new profile ID and different revision.
History remains in the existing library projection. Failed/ambiguous mutations
are not automatically retried. Reload the current version or check the exact
requested key. Closing the editor, its window, resetting the desktop or signing
out requires confirmation when unsaved changes are present; pending editor
requests guard normal window close. Unsaved fields persist across sections and
minimization in component memory, not browser storage. Auth loss, Core owner
cutover or a forced browser shutdown can discard unsaved fields.

## Reference image import

The operator can select a local JPEG/PNG, enter an asset ID and choose the
declared state and source. The browser sends the actual bytes, never a local
filesystem path. The Core owner checks the current instance and draft ETag,
the idle/recovery gate, image format and dimensions, and delegates decoding
and content-addressed storage to the existing library image-ingest service.
Core returns the actual SHA-256, managed relative path, byte count, MIME and
UNVERIFIED status. The form inserts those returned values and the manifest
entry; it does not mark evidence verified or save the draft automatically.
Imported bytes may remain as unattached private assets if a draft is discarded
or an outcome is ambiguous. There is no automatic deletion.

Saved images can be previewed by the exact saved profile ID, ETag and asset ID.
The owner checks the managed path, bytes, hash and MIME and decodes the image.
The proxy validates the bounded response and hash. No arbitrary path or URL
fetch, file browsing, live camera acquisition or asset verification authority
is provided. Other asset types have metadata forms but no binary importer.
A hash or successful preview does not authenticate physical provenance.

The V1 UI image limit is 2 MiB per image and 8 megapixels, with maximum edge
8192 pixels. The import capacity is 256 managed files and 256 MiB total,
with content-addressed deduplication. This is a deliberately bounded reference
image editor, not a RAW or full-resolution photograph transfer pipeline.
Deployment requires the existing photography image decoder (OpenCV and NumPy)
in the Core environment. CI installs the pinned photography dependencies.

## Wire contract

All nine exact POST paths under /api/v1/library/editor/ require authenticated
operator role, exact origin and X-Vision-Client webgui. Legacy reader projections
and routes remain unchanged; readers cannot access full draft documents or
private image data. HTTP and private same-UID IPC reject unknown fields and
operations. Every request includes the current Core instanceId.

| Operation | Additional JSON fields |
|---|---|
| open | key |
| create | family, variant, catalogRevision, key, revision, displayName |
| create_empty | family, variant, key, revision, displayName |
| save | key, etag, document |
| clone | key, etag, newKey, newRevision |
| validate | key, document, stateId, recipeId, scope |
| validate_structure | key, document |
| asset_import | key, etag, data (canonical base64 JPEG/PNG) |
| asset_preview | key, etag, assetId |

Document operations return vision.api.ecu-draft.v1 with source STATION,
instanceId, key, etag and the complete unsigned document. Both validation
operations return vision.api.ecu-draft-validation.v1 with source, instanceId,
key, valid, status, errors and blockers. Validity and readiness are distinct;
diagnostic lists are bounded to 64 messages (256 characters per message).
Asset operations return vision.api.ecu-draft-asset.v1 with source STATION,
instanceId, key, sha256, relativePath, bytes, mime, status UNVERIFIED. Preview
adds assetId and canonical base64 data. Mutations during active or
recovery-required inspections are rejected. The owner lifecycle lock and
existing DraftStore transaction serialize writes and ETag checks.

A stale instance/ETag, duplicate revision, unsuitable station state or storage
capacity conflict returns 409 DRAFT_CONFLICT; missing keys/records return
404 DRAFT_NOT_FOUND. Invalid shape/content returns 400 BAD_REQUEST; unavailable
transport remains an unconfirmed outcome. Documents are capped at 64 KiB
canonical ASCII JSON and 128 KiB semantic editor request budget; image
import/preview uses an explicit 3 MiB framed limit. Other protected responses
retain the 128 KiB bound, older HTTP routes retain their 16 KiB body limit,
and legacy IPC operations retain the 8 KiB canonical request bound. All
framing/worker/deadline and peer checks remain in place. Existing library
read-projection and history budget constraints are checked before publishing.

## Boundaries and rollout

No real ECU profile is created or modified by this code change. All tests use
temporary synthetic data. Existing accounts are not promoted: an owner-approved
local operator provisioning step is required to use the editor. Review and
release approval are a separate package. The editor never activates a
reference for execution, supplies fake evidence or calls hardware. Changes
remain isolated until CI, audit and approved deployment. Rollback preserves
the private library, asset bytes, history and identity data. History records
saved generations/ETags, not cryptographically authenticated author logs.

## Tests

Use the existing independent Core and HTTP fixture on port 18492, with
temporary operator account, private data and no device access. The full form
fixture and imported image are synthetic. Unit tests cover lossless
round-trip of all 15 sections including nested records, nullable values,
numeric parsing, reference lists and duplicate threshold rejection. API/IPC
tests cover empty creation, structural validation, ETag conflicts, history,
authorization, approval guards and image integrity/size. Playwright tests
exercise all 15 forms, partial authoring, linked source/state/geometry,
invalid numeric inputs, close protection, image import and preview, stale
ETags, new revision, history and retained data. The normal station browser
suite remains reader-only.

```sh
VITE_VISION_DEPLOYMENT=station npm run build
npx playwright test --config playwright.editor.config.ts --browser=chromium
npx playwright test --config playwright.editor.config.ts --browser=firefox
```
