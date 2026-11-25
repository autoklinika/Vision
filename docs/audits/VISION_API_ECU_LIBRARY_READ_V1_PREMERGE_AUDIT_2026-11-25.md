# API-03 ECU library read integration — premerge audit

Date: 2026-11-25. Scope: [issue #60](https://github.com/autoklinika/Vision/issues/60), API-02 base `32e4fc6b24b930ad738f1907ee1a96f26115092b`. This document records source and local verification. Commit-bound CI and isolated ARM64 acceptance evidence is recorded in the associated pull request before merge.

## Authority result

WebGUI remains a read-only client. The change introduces no operational HTTP command, editor, release approval, specimen selection, automatic identification, hardware connection or station deployment. Protected reads use the existing library backend and separate library authorization. Public boot and session/event contracts retain their existing behavior.

## Findings and resolution

| Area | Review and implemented resolution |
| --- | --- |
| Authoritative source | Uses existing `ECULibraryService` and persisted draft lineage. Does not substitute the separate in-memory reference registry or invent an approved-release index. |
| Read side effects | Opens an existing lock read-only; does not create `.lock`, directories, asset files, profiles or repair records. Empty-store and filesystem-snapshot tests pass. |
| Concurrent reads/writes | Existing owner lock plus shared filesystem lock. Writer contention and reentrant owner mutation become bounded unavailability. Catalog append during extraction rejects the view. |
| Integrity | Full committed lineage checked before projection, including unsigned-draft status and unchanged identity across all generations. No partial report after corrupt/missing ancestor. |
| Resource bounds | 256 catalog records +256 drafts, 4096 aggregate generations, 8 MiB aggregate reads, bounded directory enumeration, bounded collections and 50-row pages. Encoded response overflow fails before headers. |
| Authority separation | Exact typed `LibraryReadGrant`, fixed library binding, per-request authorization before extraction. Session grants, booleans, truthy strings, injected client headers and wrong-library grants fail. |
| View correlation | Content-bound view includes generation history. A→B→A invalidates previous selectors; page/detail/history use one exact source/library/view/entry identity. |
| Projection | Named allowlist only. No raw profile, provenance, field-note values, filesystem paths, asset URLs/bytes, credentials or exception text. Explicit display labels remain owner-authored data. |
| Readiness | Catalog-only and unsigned drafts are NOT_READY. All section counts are NOT_EVALUATED. A declared verification flag is not approval or a station readiness result. |
| Wire parity | Review found and fixed JavaScript status coercion, terminal-newline regex acceptance, Unicode code-point length mismatch and label/control/color constraints. Python, TypeScript and new JSON schemas now share the relevant constraints. |
| History semantics | History is saved generations within an immutable draft revision identity. Current ETag appears only at the end of the final page; old document bodies are not returned. |
| Client behavior | Explicit Refresh, no polling, no protected data persistence or fallback. Every failed load clears prior protected list/detail/history. DEMO and invalid modes have no library capability. |
| Test credentials | Random ignored 0600 file, no stdout/HTTP/bundle exposure. Test-only composition outside production packages, SIGTERM cleanup and CI absence checks. |

## Verification completed before candidate publication

- Independent source review of backend extraction, locking, HTTP routing, authorization, mapping, Python/TypeScript validators and schema boundaries.
- **65/65 Python API/projection tests passed**, retaining API-01/API-02 coverage and adding API-03 backend/HTTP tests. These include actual persisted library construction and actual loopback HTTP reads with synthetic content.
- The 20 new backend-projection tests passed independently. The full 65-test API suite also passed under independent review.
- Independent JSON Schema Draft 2020-12 schema checks and validation of all four shared synthetic reports passed. Terminal-newline cases in identity/view fields are rejected.
- TypeScript validators loaded using Node accepted the shared backend fixture and rejected the reviewed malformed cases.
- `git diff --check` passed.

The local interpreter lacks OpenCV. Existing backend image tests are therefore verified by the unchanged ECU library CI workflow and the VENTUNO acceptance environment, where OpenCV is installed. Local missing-dependency errors are not counted as passing tests.

## Final acceptance gates

Before merge, the same reviewed commit must pass the existing GitHub workflow suite and isolated VENTUNO NVMe ARM64 acceptance. The API/WebGUI gate includes TypeScript, ESLint, Vitest, brand-import tests, DEV/build browser regressions, actual API-01 and Core/API-02 integration, and actual ECU library integration in both DEV and build. The actual library test checks denial before authorization, catalog and draft details, all 15 sections, exact two-generation history, UI bounds, no browser persistence and reload isolation. Its screenshot is reviewed separately.

This file intentionally does not embed a future commit hash or claim pending CI/native tests passed. The PR records exact head SHA, workflow IDs, test results, native log digest and observed cleanup. Merge acceptance requires those records to match the reviewed head. The active station checkout and services remain outside the test scope.

## Remaining scope boundaries

The reference editor, contextual readiness validation command, approved-release browsing, asset access, real identity/session lifecycle and active-station composition remain future work. The serial loopback HTTPServer and per-lock waits are LAB constraints, not production service guarantees. History hashes do not authenticate data against a privileged local writer who recomputes them.
