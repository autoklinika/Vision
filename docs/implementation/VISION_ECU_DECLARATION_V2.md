# ECU Library V2 — simplified authoring (stages 1–2)

Owner decision: simplify the operator's work to identification, geometry,
reference photographs and inspection preferences. The templates, shot
generator, runtime/localization integration and physical acceptance are
separate future modules. This change implements none of them.

## Audit of the 15 V1 sections

| V1 section | Decision for everyday authoring |
| --- | --- |
| 01 metadata | Retain stable identity in Core; generated profile ID, first revision r1; next revision chosen by Core. |
| 02 identity | Keep manufacturer, family, variant, part numbers, optional name and aliases. |
| 03 physical states | Keep actual declared configurations; no fabricated source or verification. |
| 04 coordinate systems | Keep in advanced V1; future station/localization integration owns transformations. |
| 05 geometry | Keep raw maximum XYZ in mm per declared state. Each dimension may be unknown. |
| 06 connectors / landmarks | Advanced evidence, not a required input to a basic profile. Future localization can derive or request it. |
| 07 reference assets | Keep private image associations with category/state. Core owns actual file digest, MIME and bytes. |
| 08 recognition | Keep advanced V1 contract; future recognition module owns rules, not this form. |
| 09 localization | Keep advanced V1 contract; future localization module owns algorithm parameters. |
| 10 PCB / ROI | Retain a requested ROI preference; future modules define actual regions. |
| 11 photography | Retain requested template and view categories; actual poses and quaternions are not invented. |
| 12 thermal | Deferred, not required for the simple declaration. |
| 13 workflows | Deferred shared templates and Core compilation; no executable workflow generated. |
| 14 validation | Deferred policy configuration; Core continues to own all validation and release gates. |
| 15 provenance / release | Actual advanced evidence preserved. Private image hashes and saved-generation history are system-managed; no fictional measurement sources, uncertainty or approval. |

## Data ownership

The small closed vision.ecu-declaration.v2 authoring record is an optional
member of the existing immutable draft generation, covered by its snapshot
integrity digest. The existing V1 document continues to own the identity.
The declaration adds human family/variant labels, up to three standard
physical states, raw XYZ measurements (positive or null), up to 32 actual
managed photo associations, optional planned template preference and
inspection options/notes. A V1 document paired with a declaration has empty
technical sections; the two models never hold conflicting geometry. The
existing 64 KiB V1 document limit, 16 KiB declaration budget, total history
budget and private image limits apply. No separate database or operational
source of truth is created.

The basic mode creates a generated stable request ID, normalized family and
variant IDs (spaces become underscores), and r1. The Core rejects another
basic creation of an existing family/variant; the explicit clone operation
selects the next available numeric revision. A new basic generation is
saved with the same ETag, lifecycle and store locking rules. Archive/restore
and history remain non-destructive. Legacy technical data is never silently
converted. A legacy ACTIVE unsigned draft with empty technical sections and
compatible identity may explicitly adopt the basic model on Save, preserving
its original identity keys, revision and all older generations. Populated V1
profiles remain available via the advanced editor. Basic drafts cannot be
submitted for V1 review or published; future compilation is intentionally
absent. Basic preferences are not inspection readiness. The standard PCB
label is marked planned, not an installed executable template.

The default GUI shows four sections. Operator can create/save a partial
profile with only family and variant, with unknown measurements left blank.
Photos can be imported after initial save using the existing bounded JPEG/PNG
transport; the next save attaches the private content-addressed file to a
declared state/category. Core validates new associations against stored
bytes. Removing an association does not delete the stored file. Saved photo
preview checks the current saved ETag and digest. Historical view/comparison
includes declaration values. All ordinary edits use the Core API, no local
browser persistence.

## Compatibility and deployment

New Core/API/WebGUI must be upgraded together. Existing snapshots remain
readable without modification. Old versions cannot read a new declaration
generation; preserve a consistent private library backup before deployment,
and do not roll back just the binaries after new-format data has been
written. All tests use synthetic data; no real profile is prefilled or
automatically migrated and no hardware services are started.
