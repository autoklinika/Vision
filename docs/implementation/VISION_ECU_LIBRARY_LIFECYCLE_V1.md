# ECU library lifecycle V1

## Saved profiles and review
The existing Core draft store owns immutable document generations. Archive,
restore, submit and withdraw are ETag-guarded transitions committed as new
generations. The document remains unchanged. ACTIVE drafts can be edited;
ARCHIVED and REVIEW_READY drafts are read-only until explicitly restored or
withdrawn. RELEASED drafts are immutable and carry the exact approved release
digest. Cloning creates a new unsigned revision. Legacy generations without
lifecycle metadata are ACTIVE. No delete or browser-side approval exists.

The operator can inspect any committed generation and compare it with the
current or another exact profile of the same family and variant. Comparisons
display up to 256 field differences and explicitly flag truncation. Search
covers all authorized pages (up to 512 entries); the manufacturer/part-number
projection has a 1024-byte ASCII JSON budget per entry and reports incomplete
legacy metadata. The browser is never the approval or inspection owner.

## Independent review and publication
Submitting requires a saved workflow. Export produces a
vision.reference-review-request.v1 JSON envelope containing key, submittedEtag
and document. The independent review process returns
vision.reference-reviewed.v1 with key, submittedEtag, an approved document
and proof (canonical base64). Only independent endorsement fields may differ
from the submitted unsigned document. Core checks the exact generation,
document, approved scopes, matching approved ECU catalog record, immutable
release stores, assets, calibrations and capabilities. Current compilation
supports photo_inspection only.

The trusted local owner must supply ReviewAuthority to CoreHost (or service.main).
No authority is configured by default. Ed25519ReviewVerifier supports explicitly
enrolled reviewer public keys (32-byte raw keys) using OpenSSL. The signature
covers review_intent_bytes(ReviewIntent): the domain prefix
vision-reference-review-v1 followed by a NUL and compact sorted ASCII JSON of
the complete intent, including the exact ETag, draft/release/catalog digests,
reviewer identity/reference/date and sorted approved scopes. Signing keys and
evidence review belong outside the station. Owner configuration must establish
reviewer independence and provenance; a signature alone is not measurement
verification. This implementation does not enroll real reviewers or assert
physical approval. An authenticated operator may import a package only when
Core exposes reviewAvailable. There is no trust key supplied by the browser.

Publication first compiles all scopes against a private temporary release store,
then publishes the immutable exact release and commits its digest to the
private draft history. An interrupted publication can be explicitly retried
against the same submitted ETag; an uncommitted release is not offered by the
managed path. RuntimeComposition.from_released_references can be supplied
through a trusted composition_factory. It reconstructs managed choices from
committed release markers and verifies them against the release stores, and
refreshes the choices after publication when the configured stores match.
An approved choice is not a readiness receipt or permission to start motion.
The normal Runtime session validation remains mandatory.

## Deployment and rollback
Core/API/WebGUI must be upgraded together for the new lifecycle contracts.
New code reads legacy snapshots; old code is not guaranteed to read generations
carrying lifecycle metadata. Before deployment preserve a consistent private
library backup and the prior release. Once new-format generations exist, do
not roll back only the binary; use a compatible forward fix or an explicitly
approved data recovery plan. Real catalog/reference releases, reviewer
enrollment, station calibrations, trusted Runtime composition and readiness
receipts are separate commissioning prerequisites. Synthetic tests exercise
the interfaces without creating a real approved ECU profile or moving hardware.
