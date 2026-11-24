# VISION ECU PROFILES V1 — modular catalog, verification and controlled promotion

Status: owner authorized implementation; package and ETC3 PoC remain DRAFT until geometry is measured and owner approves activation.
Base GitHub main: 5cb9e83b5b0fee5aecb2cf1def54cecb2e6f3813, accepted Vision Core 0.1–0.4 and Thermal Inspection.
Authority: ADR_VISION_CORE_HARDWARE_INDEPENDENCE_2026-11-23.md, VISION_FOUNDATION_2026-11-14.md, VISION_INSPECTION_WORKFLOW_V1.md, frozen VGP V1.

## Goal
Core ECUProfile currently requires complete ECU geometry, view targets and orientation; real ECU profiles need a catalog that can represent and audit incompletely measured DRAFTs and only promote fully reviewed records into Core ECUProfile. Do not invent dimensions or use zero placeholders. ETC3 is first three-connector PoC measured on 2026-11-14 per docs/architecture/VISION_FOUNDATION_2026-11-14.md. Identity: two black and one gray connectors; no part number or definitive variant. Reported connector heights gray 69mm/black 65mm are unverified, unclear datum. Record only as field notes, NEVER as accepted physical geometry or collision envelope.

## Deliverables
- src/vision_modules/ecu_profiles/ package (init.py, models.py, catalog.py, verification.py, promotion.py or sensible consolidation) stdlib-only.
- config/ecu_profiles/etc3_poc_v1.json strictly typed schema V1. family ETC3, provisional variant marked not manufacturer/OE; status DRAFT, approved false, two black + one gray connectors with provisional distinct IDs, reported observations with sources/date/status, geometry fields null/empty, no PCB regions/views because unknown; no real serials, photos or private calibration.
- docs/implementation/VISION_ECU_PROFILES_V1.md implementation API, schema and prerequisites and ETC3 measurement checklist.
- .github/workflows/vision-ecu-profiles.yml Python 3.12 with pinned requirements-photography, entire tests/core and compileall both core and modules.
- tests/core/test_ecu_profiles.py with substantial positive/negative coverage.

## Requirements
1. ECUCatalog explicitly registers deeply immutable ECURecord version 1 with profile_id, family, variant, revision, status DRAFT/READY_FOR_REVIEW/APPROVED, declared_type, features, local geometry and evidence. Keys family+variant+revision unique; no overwrite with changed content; no auto family inference/variant substitution. Explicit operator declaration selects exact family and variant. Provisional ETC3 no OE/model ID claims.
2. Typed frozen connector specifications (IDs/color/count, optional local coordinates), envelope dimensions XYZ from same ECU-local datum (mm), regions xywh, view xyz and XYZW unit quaternion, tolerance and capture requirement. Measurement provenance status DRAFT_NOTE/MEASURED/VERIFIED with date, instrument, datum, uncertainty, reference. A DRAFT may omit unknown fields; APPROVED requires complete coherent envelope, PCB regions inside envelope, view positions/quats, measured references and approved calibration dependencies, positive dimensions/tolerance and finite bounded values. Connector landmarks if required for identity must have independently verified geometry before automatic comparison. Color/count alone is insufficient for final ECU identity.
3. Strict bounded JSON loader and canonical serializer: reject duplicate keys, unknown fields, incompatible schema, NaN/Inf, oversized >512 KiB input, non-UTF8, malformed identifiers and path traversal. Deterministic SHA256 of canonical record content excluding approval endorsement; ApprovalEvidence(profile_id,revision,digest,reviewer_id,time,reference) bound to immutable revision/content. This is correlation, NOT cryptographic signature or trusted identity by itself.
4. validate_draft reports ordered blockers for readiness. Promotion to core ECUProfile is only possible with typed approval and full measurements plus verified evidence; status APPROVED alone does not grant readiness. Approval must not auto-upgrade incomplete ETC3; no in-place revision edits. to_core_ecu_profile returns existing class with correct nominal_dimensions, max_height, pcb_regions, view_targets, unit quaternions, tolerances, capabilities and calibration_dependencies. It must pass existing validate_profiles/create_plan with synthetic station/camera/robot profiles. No edits to src/vision_core.
5. ECUObservation external vision evidence with source/ref/frame/session/time/scene/revision, feature IDs/color/count and quality/verified flag; verify_declared_ecu compares against exact declared family/variant, approved record and current observation, rejects stale/wrong frame/scene/revision/observations, no auto-guess or source self-attestation of hardware. For DRAFT ETC3 can describe "connector pattern matches" as a PRELIMINARY note only, never ACCEPTED for physical motion.
6. New version/revision required for any change to a released profile. Frozen catalog content digest checked again on lookup and promotion. Context/profile revision binding respects existing Core requirements.
7. Tests 20+ cases: ETC3 parse/roundtrip SHA, connector counts and uncertain heights as non-authoritative notes, no invented L/W/H/PCB/view, draft promotion blocked, exact operator declaration, wrong family/variant, changed digest, invalid schema/data/duplicates, bad dimensions/NaN, colors/IDs, source uncertainty, stale/wrong scene/frame/request and fake observations, review and approval, immutable old revision, positive synthetic complete record promotion to Core and repeatability, changed ECU pose changes scene targets while local views identical, no hardware command.
8. Provide ETC3 operator measurement checklist: body L/W/H, local reference corner and axes, connector x/y/z and max heights from SAME datum, PCB region xywh opened board, relative target xyz + quaternion and working distance, tolerance/instrument/uncertainty/references, exact variant/part if available, photo QA and calibration. Unknown fields NOT_READY, no hypothetical physical accuracy claims.
9. All 156 existing Core/Thermal tests PASS plus new tests. CI, no new Camera Service, no ROS/MoveIt motion/CAN and no changes to frozen VGP or active checkout. Draft PR only after independent audit; no merge or deployment without separate instruction.

Implementation notes: Build a robust practical V1 catalog, avoid generic plugin framework. Preserve historical accepted frozen VGP V1. Only synthetic geometry in unit tests; ETC3 PoC remains not yet runnable.


## Implemented API and limitations

`vision_modules.ecu_profiles` exposes frozen `ECURecord`, `Connector`, `Measurement`, `Provenance`, `ViewTarget`, `FieldNote`, `ApprovalEvidence`, `ECUCatalog`, `Declaration`, `ECUObservation`, and `ObservedConnector`. `load_json(bytes_or_text)` strictly decodes the version 1 JSON shape shown in the PoC; every field is required, with null or empty arrays representing unknowns. `canonical_json(record)` exports deterministic JSON. `record_sha256(record)` hashes canonical content without endorsement, normalizing status to `READY_FOR_REVIEW` so a reviewer can endorse the exact reviewed content before its status becomes `APPROVED`. The hash is a correlation mechanism, not a signature or proof of identity. Reviewers must independently authenticate and retain their evidence. A changed field requires a new revision.

Register records explicitly using `ECUCatalog.register`, then retrieve by exact family, variant, revision using `get`. The in-memory registry refuses differing content at the same key or profile ID/revision and rechecks content on lookup. It is not durable storage; use the local release store to preserve approved snapshots across restarts. Register only the final approved artifact in a given registry; the review artifact and release artifact are separate registry entries only in separate instances. No plugins or dynamic imports are used.

`validate_draft(record)` returns ordered geometry and evidence blockers. `to_core_ecu_profile(record, calibrations, catalog=catalog)` is a trusted-only compatibility conversion and requires the exact registered record and `APPROVED`, a matching typed endorsement, verified measurements with the ECU-local datum, independent evidence references for body, PCB, view and identity landmarks, complete orientations, and exact calibration revisions. `verify_declared_ecu` requires a registered catalog for approved records, an explicit `Declaration`, independent observation, and caller-supplied current session, frame, scene, time and freshness limit. It returns `PRELIMINARY` for a matching draft pattern and never accepts it as ready. Accepted identity requires verified landmark positions, not just colors and count. Observation producers and reviewer identity are external trust boundaries; the caller must authenticate their sources and verify calibration approval before supplying them. This module does not establish collision safety, hardware readiness, metrological accuracy, or issue motion or capture commands. Core remains responsible for its own scene and workflow checks.

The JSON input limit is 512 KiB; numeric values are finite and bounded to one million in absolute value. Catalog identifiers contain only ASCII letters, digits, underscore and hyphen. Observation frame IDs allow slash-separated nonempty safe segments, up to 255 characters. Region rectangles are x/y/width/height in the same ECU-local datum as the envelope, and must fit inside it; view positions may be outside the body. Calibration dependencies are explicit pairs of identifier and revision. Provenance requires a date and reference, and verified geometry additionally requires instrument, `ecu_local` datum and positive uncertainty. View tolerance is positive, quaternions are unit XYZW, and all included views require capture. Coordinates are millimetres. This V1 treats identity landmark uncertainty as the comparison radius; observation uncertainty is not modeled, so a real deployment needs an independently validated uncertainty policy before acceptance.

## ETC3 measurement checklist

The PoC is a provisional three-connector specimen, not a manufacturer variant. Two black and one gray connectors were reported on 2026-11-14. The gray 69 mm and black 65 mm reports are uncertain field notes with unknown datum; neither is an envelope nor a maximum height. No body dimensions, board regions, targets, orientations, part number, calibration, or acceptance thresholds are known.

Before review, record and independently verify:

1. Body length, width and maximum height; establish a single local reference corner, axes and units.
2. Connector landmarks and maximum protrusion heights from that same datum, including identity-distinguishing geometry.
3. Open-board PCB region rectangles and their relation to the body datum.
4. Required local view positions, unit XYZW orientations and working distances; justify capture and tolerance requirements.
5. Instruments, dates, uncertainties, independent source references and verified calibration revisions for each measurement; document photo QA and calibration evidence.
6. Exact manufacturer variant and part identification if available, and a human review of the canonical digest and release revision.

Unknowns stay unknown and block promotion. No real serials, private photos or calibration artifacts belong in this public record.

## Audit remediation and operational activation

Every body, PCB, view pose and identity landmark reference is checked against all other categories; references may repeat within a category. Each view has separate verified `orientation_provenance` in the ECU-local datum, independently referenced from its position. Reviewers must assess view tolerance against the intended camera positioning process and validate the landmark uncertainty used as the identity comparison radius; these numbers are supplied evidence, not automatically established accuracy. Optical-center coordinates need not fall inside a PCB rectangle. Actual spatial coverage is verified separately by Core after capture.

`ECUCatalog.select` requires an exact typed declaration. Approved verification compares the observation with all other registered approved variants in the family and reports ambiguity when another fits. The catalog must contain the complete relevant approved population; omission of a variant cannot be detected by this module. Draft matches remain preliminary.

`ReleaseStore` publishes canonical approved snapshots once per profile ID and revision using exclusive atomic publication and fsync, and checks canonical content and approval digest on read. `to_core_approved` requires both the matching catalog record and snapshot. `select_and_plan_verified` additionally binds a fresh verified identity observation, declaration, Core context and Core pose observation, then returns a plan and identity receipt. Direct Core `create_plan` and `to_core_ecu_profile` remain low-level trusted interfaces; operational adapters must use the guard. Neither the receipt nor a digest is a signature or proof of reviewer or sensor identity. External owner authentication, directory permissions, release history protection, source authentication, calibration approval and a complete catalog remain required. A party able to rewrite the store and approval evidence can forge a consistent snapshot. No hardware is commanded by this API.

ETC3 measurements and operator acceptance checklist (Polish): [ETC3 PoC V1](../profiles/ETC3_POC_V1_PL.md).

### Dodatkowe zabezpieczenia po audycie końcowym

Porównanie alternatywnych wariantów nie wykorzystuje nazw wewnętrznych
connector_id jako cechy rozpoznawczej. Wykonywane jest jednoznaczne dopasowanie
rzeczywistych kolorów i położeń złączy. W przypadku kilku możliwych wariantów
wynik to AMBIGUOUS, nie automatyczny wybór. Katalog musi obejmować wszystkie
istotne dopuszczone warianty; nierozpoznanego wariantu spoza katalogu nie można
wykluczyć programowo.

ReleaseStore tworzy i publikuje pliki wyłącznie względem już otwartego
deskryptora katalogu. Zmiana ścieżki na inną lub dowiązanie symboliczne po
otwarciu nie przekierowuje zapisu. Wyłączność rewizji wynika z atomowego
tworzenia dowiązania i fsync. Po awarii procesu mogą pozostać pliki
tymczasowe, które wymagają osobnego administracyjnego przeglądu; bez niego
nie należy wnioskować o udanym wydaniu.

Wersja V1 nadal nie uwierzytelnia podpisu recenzenta ani źródła obserwacji.
Zaufanie do operatora, katalogu zweryfikowanych wariantów, przyrządów i
kalibracji jest obowiązkiem przyszłej integracji produkcyjnej.

[Polska karta ETC3 PoC](../profiles/ETC3_POC_V1_PL.md).
