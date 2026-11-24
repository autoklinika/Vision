# VISION-CORE-004 — Modular Extensions & Workflow Definitions

**Decision:** Owner-approved design direction, pending implementation review.
**Parent:** GitHub main at 7026da76e503c8bb72e2e70f7c5845fd15fa0b95 (Vision Core 0.1–0.3 accepted offline).
**Status:** offline implementation; DO NOT MERGE or deploy without full tests and owner review.
**Contract:** ADR-VISION-CORE-001 and VISION_INSPECTION_WORKFLOW_V1.

## Goal
Adding a new sensor, modality or inspection stage should not require rewriting the stable session/event journal, gating logic, device drivers, or a second workflow engine. The accepted S01–S11 sequential scenario is a fixed compatibility baseline; new modules are explicitly selected, approved, versioned, capability-checked and fail closed. Module developers provide a metadata descriptor and adapter, not a replacement Core.

## Desired architecture
- A declarative immutable `ModuleSpec` with identity, version, profile kind, required capabilities, verified stage IDs/permissions. Registration **explicit only** from trusted installed modules, no device discovery, dynamic code eval/import, entrypoint scanning or automatic activation.
- `StageSpec`: typed bounded ID, dependency graph (explicit predecessor IDs), required evidence checks, owner module or builtin, and where appropriate evidence contract marker. `ScenarioSpec`: immutable versioned graph; reject duplicate IDs, missing dependencies, cycles, unsupported module, missing required station stages, nonapproved descriptor and stage/module identity mismatch. Check all required predecessor SUCCEEDED before dispatch. Failure blocks its transitive dependents, not unrelated branches. Every nonlegacy stage should require a *verified typed module receipt* bound to session, request, stage, module id/version, scene/profile context and payload hash. ACK cannot substitute receipt. No bypass via generic Evidence boolean claims. No silent fallback to another module.
- Workflow 0.4 is a generalization of **existing** `vision_core.workflow.Workflow` (NOT new second engine). Old constructor/behavior and all 79 tests unchanged; optional keyword args `scenario`, `registry` give scenario-specific stage/validation/config. Preserve S05/S06/S07/S08 plan hash binding, fail-closed SQLite transaction, restart/replay and owner-approved HOLD convention. Dynamic dependency graph and stage checks must be used for both old and custom scenarios. Avoid new service, ROS adapter, CAN commands, camera driver.
- `Profile` registry: old strict exact 6 kinds in legacy mode. In a selected scenario, allow only explicitly required extra module profile kinds, exactly matching context.profile_revisions and registered module descriptors. Do not allow stray, unknown, unapproved, uncalibrated profiles. All profile contents, descriptors, graph edges, stage checks, module versions, selected capabilities and max_age pin to durable session fingerprint; any change requires new session. Existing `repeatability.create_plan` must remain correct with extra profiles (ECU-local targets, orientation) when a modular scenario is selected. No guess for thermal measurement from visual image.
- `ModuleReceipt` / result validator: independently supplied and verified externally, typed immutable: session_id, step_id, request_id, module_id, module_version, profile_revision, context, timestamp (after dispatch), payload SHA-256 and reference, terminal success. Its acceptance must create a correlated durable journal event and be checked before `Workflow.complete`; no generic evidence bypass or duplicate/stale receipt. If receipt is fake, trusted adapter boundary remains documented; Core validates only structural/correlation and file integrity. No executing hardware commands within Core.
- Tests: full 79 regressions, legacy scenario exact 11 stages; DAG two parallel branches join with dependency gating, failure blocks descendants but not unrelated branch; unknown module/unsupported caps/missing calibration/duplicate module IDs or stage IDs/invalid graph reject before dispatch; typed module receipt bypass/duplicate/stale/context/restart rejects; same-version changed descriptor, profile revision changed, changes max_age, fail-closed persistence; synthetic Thermal and fictional future sensor should register on *same code path* without modifying core; environment network/device-free.
- CI add `.github/workflows/vision-core-extensions.yml` Python 3.12 pinned `requirements-photography.txt`, full test discovery and compileall; existing workflows remain green.

## Thermal integration contract (follow-up stacked PR after 0.4)
- Introduce Thermal Inspection as first actual opt-in module; no specified camera model yet, so do not fabricate hardware protocol, radiometric precision or performance.
- Thermal frame mode for relative heat maps; radiometric mode ONLY if declared sensor capability, calibration and units plus emissivity/reflected-temperature metadata with meaningful validity checks. Preserve raw manufacturer data and derivation/provenance, SHA-256, reference to actual capture. Thermogram rendered palette is not a temperature measurement.
- ThermalResult validates scene/profile/request/time/transfer/required format and underlying raw bytes. Thermal QA must not claim correct physical temperatures on the basis of an RGB frame. Two synthetic thermal stages in scenario, positioned before supervised PARK/S10. Legacy scenario without thermal module unaffected. Thermal failures block dependent stages.
- Next module should be possible by registering a descriptor and supplying an adapter, *without modifying* `workflow.py` again. Document API contract, limitations, profile migration and versioning.


## Offline implementation and migration

The existing `Workflow` accepts keyword-only `scenario` and `registry`. Default calls retain the original fingerprint, stage sequence and replay behavior. A scenario is an ordered topological list, with every S01–S11 stage retaining its mandatory checks and the direct preceding builtin dependency. Additional checks and edges are allowed. Module stages must descend from S03; attach their final stage as a dependency of a builtin stage when it must gate that stage. Failures block transitive descendants only. Registry selection is explicit, frozen at construction, and no discovery or adapter code is run. All selected descriptors, scenario, profiles, calibrations, requirements and freshness limit are recorded in the configuration manifest and pinned for the session. A changed configuration needs a new session.

For example, build an additive graph using the legacy `STAGES` and `CHECKS` exports, inserting synthetic stages after S03 and adding their join as an S04 dependency:

```python
from vision_core.extensions import ModuleRegistry, ModuleSpec, ScenarioSpec, StageSpec
from vision_core.workflow import STAGES, CHECKS

registry = ModuleRegistry()
registry.register(ModuleSpec('thermal', '1', 'thermal', {'heat'}, True, ('T1',)))
registry.register(ModuleSpec('vibration', '1', 'vibration', {'vibe'}, True, ('V1',)))
stages = []
for i, name in enumerate(STAGES):
    deps = [] if i == 0 else [STAGES[i - 1]]
    if name == 'S04':
        stages += [StageSpec('T1', ('S03',), {'verified'}, 'thermal'),
                   StageSpec('V1', ('S03',), {'verified'}, 'vibration')]
        deps += ['T1', 'V1']
    stages.append(StageSpec(name, tuple(deps), CHECKS[name]))
scenario = ScenarioSpec('example', '1', tuple(stages), ('thermal', 'vibration'))
# Supply approved thermal and vibration Profile objects with capabilities and
# calibration dependencies, and include both revisions in Context.
# workflow = Workflow(journal, context, profiles, calibrations, requirements,
#                     max_age, scenario=scenario, registry=registry)
```

After dispatch, a trusted external adapter supplies `ModuleReceipt` and the payload bytes to `workflow.verify_module_receipt(receipt, payload)`. The receipt names the session, stage, request, module and version, profile revision, full context, timestamp, SHA-256, reference and terminal success. The method checks correlation, freshness and the payload digest and records `module_verified` atomically; normal `complete(Evidence(...))` still requires the stage checks and the durable receipt. This validates the adapter's claim and byte integrity, not the physical truth or origin of a measurement. The synthetic descriptors above are not drivers or thermal measurement contracts.

Repeatability accepts explicitly selected module profile kinds throughout S05–S08, binding their metadata and calibration dependencies to the plan. Legacy calls retain the exact six-profile contract. Receipt references must match the completing evidence; payloads are capped at 128 MiB after receipt, and upstream adapters must enforce limits before allocation. The actual thermal driver and radiometric calibration are deferred to a separate follow-up module.

## Audit hardening and required-module semantics

- The full list of ModuleSpec.stage_ids is a **permission list**, not an assertion that every optional stage must run in every scenario. ModuleSpec.required_stage_ids specifies which of those stage IDs **must** appear whenever the module is selected. Each selected module stage must be a transitive predecessor of terminal S11; otherwise the scenario is rejected at construction time. Only genuinely optional, non-required stage IDs may be omitted.
- On restart, a changed scenario, selected-module descriptor, calibration, profile or freshness policy produces a durable context_invalidated event. Historical successful transitions remain in SQLite, but an invalidated session must expose all stages as BLOCKED for the *current* configuration. Old S11 success is not a valid result under a different scenario.
- ModuleReceipt payload hashes and references are correlated with the exact running stage and Evidence. These are integrity/correlation checks for a **trusted** adapter, not cryptographic authentication of the physical sensor.
- No module is discovered, installed, or activated automatically. The registry is explicitly populated before session creation and frozen for execution. Device-specific transports, physical calibration and measurement validity remain separate acceptance gates.
