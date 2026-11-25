# Vision ECU Review & Release V1

Status: implementation candidate; offline review workflow, not commissioned
station activation. Base: main a5c2416. It is independent of the proposed
WebGUI draft editor PR: the underlying DraftStore format is unchanged.

## Responsibilities and authority

An ECURecord (the precise catalog definition) and a ReferenceProfile (the
reference geometry, observations, assets and inspection recipe) are different
artifacts. Both need independent approval; the selected reference must match
the exact released catalog profile ID, family, variant and revision.
The original editable reference stays an unsigned DRAFT in the existing
history. Review creates a separate immutable REVIEW_READY snapshot and
APPROVED publishes into the existing append-only release stores. The catalog
model's established intermediate spelling is READY_FOR_REVIEW. The review
report uses REVIEW_READY for either kind. An unsigned candidate does not
compile for execution or set physical station readiness.

ReferenceReviewService is a trusted local composition, not a browser API.
It uses the existing IdentityStore, explicitly configured disjoint account
allowlists for submission and approval, and requires operator role in both.
There is no default promotion or reviewer account. Each decision uses a
current authenticated session and rechecks it before publication. The
reviewer is distinct from the submitting account; this does not authenticate
who collected every measurement or edited every draft generation. The
operator/recenzent must inspect source provenance and content independently.
The private same-UID storage and local account/configuration administration
remain the trust boundary; SHA-256 detects changes, not hostile local
rewrites of content plus hashes or false human attestations.

## Workflow

1. Prepare a new unsigned catalog revision with actual measurements and
   independent provenance for envelope, identity landmarks, PCB regions,
   view positions/orientations, capabilities and calibration revisions.
   Built-in DRAFT revisions are immutable and must not be replaced in place.
2. Submit the catalog candidate using an author session. The existing
   validate_draft rules and explicit commissioning capabilities/calibrations
   must pass. An immutable private review envelope pins the exact record.
3. A separate authorized reviewer examines the envelope and explicitly
   approves that exact review ID with a human decision reference. The existing
   ReleaseStore publishes the matching approved ECURecord. No automatic
   registration into the live Core catalog takes place.
4. Prepare the matching unsigned reference draft in the existing library.
   Record actual verified sources and select an exact physical state and
   photo-inspection recipe. The matching readiness policy row must exist,
   with approved=false. Author-supplied approval flags/digests are rejected.
5. Submit the draft by its current ETag. The review service freezes the
   REVIEW_READY snapshot, its original draft content digest/ETag, the exact
   released ECURecord digest, configuration and verified material manifest.
   Existing compiler content checks run without producing an execution
   bundle. The public compile_profile still requires an actual approved
   reference in ReferenceReleaseStore.
6. A separate reviewer inspects the exact content and image bytes, then
   approves the review ID. The service rechecks the draft ETag and hash,
   matching approved catalog, configuration, actual material bytes and
   compiler requirements. It sets only the requested scope's approval flag,
   creates the existing content/approval digests and publishes atomically.
   The original draft and previous generations are not modified.
7. Explicit commissioning can load the two matching released snapshots
   into the accepted Runtime composition. This package does not do that.

The review envelope's canonical SHA-256 is its ID. Storage uses private
0700 directories, 0600 files, exclusive publication, fsync and no overwrite.
A changed ETag or changed declared environment makes a pending review stale.
A conflicting release is rejected. The review can be inspected after approval
by comparing it to the exact published snapshot; duplicate approval is
rejected. Hash corruption, missing or changed evidence and revoked credentials
block publication. Asset bytes are rechecked at approval, not assumed valid
just because a pending review exists. Approved release state is not a promise
that the referenced evidence is currently present or that equipment is ready.
The normal runtime compiler rechecks the approved reference and asset hashes.

## Reference materials

V1 intentionally supports managed JPEG/PNG reference images for the existing
photo-inspection compiler. The existing library ingest decodes the image,
checks dimensions and size, and stores it by SHA-256 with UNVERIFIED status.
The author supplies the source metadata; a reviewer confirms the actual
specimen, viewpoint, datum, image relevance and source evidence. The service
verifies each declared image via the existing read/decode/hash path, exact
managed relative path assets/<sha256>, size, MIME, verified source declaration,
private/controlled privacy class and complete manifest. It also invokes the
existing compiler's required-asset checks. It does not infer physical
provenance, correct identity or calibration from a matching hash.

Materials are bounded to 32 images and 64 MiB total per reference, with
existing per-image 8 MiB/dimension limits. No arbitrary URLs, filesystem
paths, PDFs, collision-model or thermal-file publication in this first review
workflow. Review envelopes are limited to 1 MiB; review and catalog release
directories have bounded capacity. No automatic pruning or revocation is
introduced. Keep the private stores backed up. Only one configured review
composition may write these namespaces (using the existing DraftStore owner
transaction); direct local file administration is outside this trust boundary.

## Offline workspace and actual ETC3 preparation

Use the local review CLI in a separately staged private workspace, never as a
second live Core owner. It does not automatically initialize credentials or
copy operational data. Preparation copies only the built-in declared catalog
identity, connector colors and FIELD_NOTE observations; geometry,
coordinates, calibration and execution capabilities are left unfilled.
For the actual ETC3, the new unsigned candidate may use a new profile ID and
revision matching the future catalog/reference release. The declared top-PCB
physical state is unverified. Prior 65/69 mm field notes remain field notes,
not an envelope or motion constraint.

Example (choose a new private path outside source, on the intended NVMe):

```sh
PYTHONPATH=src python -B -m vision_station.review_cli --workspace /private/new-ecu-review prepare \
  --family ETC3 --variant provisional_3connector --base-revision v1 \
  --profile-id etc3_poc_v2 --revision v2 --display-name 'ETC3 PCB exposed top'
PYTHONPATH=src python -B -m vision_station.review_cli --workspace /private/new-ecu-review status
```

The workspace contains catalog-candidate.json, the existing private library
format, separate reviews/catalog-release/reference-release directories,
incoming images and review-workspace.json. Configuration starts with empty
author/reviewer allowlists and no assumed calibration or capabilities.
The owner must explicitly configure distinct authorized accounts and create a
local accounts.json with the existing identity provisioning mechanism. Do
not copy browser cookies, credentials or synthetic approved fixtures into the
workspace. Use the existing library methods to fill and save the reference
draft with its ETag, and update the measured catalog candidate privately.

The local CLI has status, ingest-image, submit-catalog, submit-reference,
inspect, export-review-image and approve operations. Authenticated
commands accept --username before the subcommand and prompt for the
password; approvals require a deliberate typed confirmation and a decision
reference. Inspect the full immutable review and export its individual
images locally before approving. The CLI's status is the unsigned working
catalog diagnostic, not its released status; inspect the exact review ID
for release status. The GUI review screen and a commissioned station adapter
are separate follow-up work after the draft editor merge. No account, hardware
service, operational library or release was modified by the implementation.

## Validation

Synthetic tests exercise catalog and reference approval with actual separate
IdentityStore sessions, decodable PNG material, the existing release stores
and real compile_profile. Negative cases cover unsigned candidate execution,
missing catalog release, duplicate revisions, stale ETags/configuration,
source image corruption, wrong MIME/path/manifest, geometry mismatch,
unauthorized/revoked accounts and private-directory/integrity bounds.
The real ETC3 built-in draft is verified to remain blocked. The local
preparation test verifies no invented geometry or promoted field notes.
