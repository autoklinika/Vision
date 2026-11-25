# Vision ECU Draft Editor V1 (Core/API/WebGUI)

Status: candidate; draft-authoring only, not production acceptance.
Base: a5c2416 (Runtime session orchestration). The same independent Core Host
owns the ECU library and the draft editor. No second store, approval authority,
device driver, Runtime or Workflow is constructed by the editor.

## Workflow

In ECU Library, browse a catalog record or unsigned reference draft and open
the reference editor. Explicit operator permission is required. A catalog
record is not a reference profile; Create draft initializes the V1 template
with the selected catalog identity and a new profile ID/revision. A saved
draft can be loaded, edited, validated and saved as a new immutable storage
generation using its current ETag. Clone saved revision uses the existing
backend clone operation, with a required source ETag, a different revision and
a new profile key. History remains available through the existing library
read projection; the source is not overwritten.

This first UI is a technical, section-by-section JSON editor for all 15
existing sections. It retains unsaved text only in component memory, including
text in other sections. It does not persist draft content in browser storage,
interpret domain geometry, or auto-fill unknown measurements. It validates
JSON syntax locally for convenience; the Core validator remains authoritative
for types, cross references, fixed policies and the unsigned-draft contract.
The existing backend schema and measurement conventions are unchanged.
A failed or ambiguous save is never automatically retried; reload the latest
generation (or check the requested key after an ambiguous create). Closing an
editor with unsaved changes requires confirmation. Closing the desktop, logout
or station owner cutover discards in-memory editor state.

The validation endpoint evaluates a declared state, recipe and scope using
the existing backend with no supplied capabilities, calibration or verified
assets. It reports INVALID_DOCUMENT or structural validity with NOT_READY.
It cannot approve any profile. Core rejects release endorsements, digest,
approved status/scope, and in-place identity or revision changes on save.
The browser also cannot publish assets, approve real measurement provenance,
or attach a recipe to Runtime. Preparing the actual ETC3 measurements and the
independent review/release workflow are separate packages.

## Wire contract

All five exact POST paths under /api/v1/library/editor/ require authenticated
operator role, exact origin and X-Vision-Client webgui. No reader access to full
draft documents; legacy reader projections and their routes are unchanged.
Both HTTP and private same-UID IPC reject unknown fields and operations. The
request contains the current Core instanceId; no actor, filesystem path,
hardware evidence or arbitrary operation is accepted by this transport.

| Operation | Additional JSON fields |
|---|---|
| open | key |
| create | family, variant, catalogRevision, key, revision, displayName |
| save | key, etag, document |
| clone | key, etag, newKey, newRevision |
| validate | key, document, stateId, recipeId, scope |

Successful open/create/save/clone returns vision.api.ecu-draft.v1 with source
STATION, instanceId, key, etag and the complete unsigned document. Validate
returns vision.api.ecu-draft-validation.v1 with source, instanceId, key, valid,
status, errors and blockers. Validity and readiness are distinct; diagnostic
lists are bounded to 64 messages (256 characters per message).
Mutations during an active or recovery-required inspection are rejected.
The owner lifecycle lock and existing DraftStore transaction serialize writes
and ETag checks. A stale instance/ETag, duplicate revision or unsuitable
station state returns 409 DRAFT_CONFLICT; missing key/record returns 404
DRAFT_NOT_FOUND. Bad shape/invalid write returns 400 BAD_REQUEST; unavailable
transport remains an unconfirmed outcome.

Editor documents are capped at 64 KiB serialized ASCII JSON, under the
existing 128 KiB protected response limit. The station HTTP parser and private
IPC envelope allow at most 128 KiB for editor requests. Existing HTTP routes
retain their smaller semantic body limit (16 KiB); legacy IPC requests retain
an 8 KiB canonical envelope limit. There is no binary upload. Existing library
read projection bounds are checked before publishing a draft, including
bounded total history and compatible projected identifiers/labels. A history
budget conflict blocks the mutation; the editor does not prune data.

## Boundaries and rollout

No real ETC3 measurements or synthetic approvals are installed. Existing
accounts are not promoted: an owner-approved local operator provisioning
step is required before the operator can access the editor. A reader may
continue browsing existing library reports. Changes are in the isolated
VENTUNO worktree; merge/deployment are separate. Prior releases cannot edit
through these new routes, but read the same unsigned store. Rollback must
preserve the private library, history and identities. History records saved
generations and ETags, not a new cryptographically authenticated author log.
No automatic hardware calls are part of this package.

## Tests

The API suite includes real IPC and authenticated WSGI requests against a
disposable Core-owned store, conflict and concurrency regressions, validation,
revision history, permission, active/recovery gates, bounded sizes, and
protected identity/approval invariants. The dedicated Playwright editor
configuration uses an explicit temporary operator, a separate server on
18492, synthetic draft data, and no production accounts or equipment.
The regular station suite remains reader-only. Build station mode before
running the editor scenario in both Chromium and Firefox:

```sh
VITE_VISION_DEPLOYMENT=station npm run build
npx playwright test --config playwright.editor.config.ts --browser=chromium
npx playwright test --config playwright.editor.config.ts --browser=firefox
```
