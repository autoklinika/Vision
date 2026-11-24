# Vision ECU library backend V1

This package is an offline Python service. An ECU catalog record is a declared ECU description; a ReferenceProfile draft is an editable, unsigned reference snapshot. An approved released reference is governed by the existing `ecu_reference` release facilities. A per-specimen inspection session is a separate concept and is not implemented here. No transport, server, GUI, hardware access, or motion is provided. A future WebGUI can call these methods through a thin adapter with its own authentication and authorization.

```python
from vision_modules.ecu_library_backend import ECULibraryService

service = ECULibraryService('/private/vision-library')
catalog = service.list_catalog()
detail = service.catalog_detail('ETC3', 'provisional_3connector', 'v1')
draft = service.create_draft('ETC3', 'provisional_3connector', 'v1',
                             'my_profile', 'r1', 'My ECU')
document = draft['profile']
document['metadata']['display_name'] = 'Revised name'
draft = service.update_draft('my_profile', document, draft['etag'])
report = service.validate_profile(document, 'closed', 'inspection', 'verify_identity')
```

`list_catalog(query='')` returns catalog summaries and `catalog_detail(family, variant, revision)` performs exact selection. The built-in config is always loaded; an optional `catalog_dir` adds explicit JSON records. Files are bounded to 512 KiB and symlinks are rejected. Catalog field notes are unverified; they are not copied into new drafts as measurements. `list_profiles(query='', status=None)` lists drafts. `get_draft(profile_id)` returns a document and ETag, `clone_draft(profile_id, new_profile_id, new_revision)` makes a new unsigned revision, and `history(profile_id)` returns immutable saved snapshots and their ETags. Draft IDs use ASCII letters, digits, underscore and hyphen, starting with a letter or digit. Revision identity is unique per family and variant. `update_draft` requires the most recent ETag; conflicts raise `FileExistsError`. Other invalid requests raise `ValueError`, and absent records raise `FileNotFoundError`.

`validate_profile(document, state_id, recipe_id, scope, capabilities=None, calibrations=None, asset_ids_verified=None)` accepts a mapping or raw JSON and returns `valid`, `status`, `diagnostic_kind`, `errors`, and `blockers`. Parse errors are distinct from readiness failures. Readiness is delegated to the reference engine; an unsigned draft cannot pass. `section_schema()` returns all 15 section descriptors, nested row field templates, enum constraints, and the original template. Templates indicate fields, not permission to bypass the authoritative validator or evidence requirements.

`ingest_reference_image(data)` accepts JPEG or PNG bytes up to 8 MiB, decodes content with the pinned photography dependencies, and returns the SHA-256, byte count, MIME, relative path and unverified status. `read_reference_image(sha)` returns `(bytes, mime)` after checking the content hash. Ingestion does not update a profile or establish review. Assets must be reviewed through a separate controlled process.

The required explicit data root must be outside the repository and is initialized only on service construction. Application directories are mode 0700, files 0600; writes use temporary files, fsync, and atomic publication. Draft snapshots are append-only within this service and protected from concurrent service writers by a filesystem lock. This is local private storage, not a defense against a malicious local user who can modify the storage directory or its ancestors. Backups, retention, access control, release authorization, and trusted asset review remain the operator's responsibility. Never treat a catalog entry, file hash, draft, or unverified image as a signed release. Existing templates and project configuration are read-only inputs.

Each committed draft points atomically to an immutable, uniquely identified history snapshot. Snapshots link to their preceding committed generation; history follows that chain, so interrupted writes can leave orphan snapshots that are invisible to reads and history. Each generation has a persistent ETag, including when content is reverted. Canonical profiles and stored snapshots are limited to 512 KiB. Image headers are checked before decoding and decoded dimensions are checked again: at most 30,000,000 pixels and 30,000 pixels per dimension are accepted.

Reads, updates and history verify the entire committed lineage from the current pointer to the root. Missing or malformed snapshots, mismatched keys or generations, invalid hashes, cycles and chains longer than 4096 revisions are rejected; an update cannot extend a chain already at that limit. Each snapshot contains a profile SHA-256 and a snapshot SHA-256 over deterministic JSON of every other wrapper field, including the key, generation and previous link. These unkeyed hashes detect corruption or edits that do not also recompute the hashes; they do not authenticate the lineage against someone able to rewrite the store, its hashes or the current pointer. Protect the storage directory and use trusted external backups where stronger assurance is required.
