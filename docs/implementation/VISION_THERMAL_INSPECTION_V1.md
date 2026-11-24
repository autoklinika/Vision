# VISION THERMAL INSPECTION V1 — offline module, implementation contract

Status: Implementation candidate, owner authorized creation; DO NOT MERGE or deploy without review.
Parent: Vision Core 0.4 modular extensions PR #43, branch feat/vision-core-004-extensibility-foundation.
Hardware: model and mounting of future thermal camera NOT YET SELECTED. No thermal images, radiometric dataset, camera API, calibration nor physical tests.

## Goal
Prove that a previously unknown modality (thermography) can be added as a packaged module via VISION-CORE-004 ModuleSpec/StageSpec/ScenarioSpec and a thin trusted adapter WITHOUT any edit to src/vision_core or legacy S01–S11. The module supports two modes: relative thermal intensity and claimed radiometric temperature samples. A color-mapped thermogram is NOT a measured temperature and must not be used for absolute thresholding. No direct ROS, USB, CAN, vendor SDK or movement driver.

## Package
- src/vision_modules/__init__.py, src/vision_modules/thermal.py (stdlib).
- A ThermalProfile extends generic Profile and declares expected frame, capabilities, radiometry/relative allowed mode and calibration dependency. It is versioned, immutable, explicit, pinned by existing Workflow fingerprint and Context.profile_revisions.
- Predefined ModuleSpec id thermal-inspection, version 1, profile kind thermal, required capability thermal.frame, permitted and required stages THERMAL_CAPTURE and THERMAL_QA.
- make_thermal_scenario() inserts THERMAL_CAPTURE after S08, THERMAL_QA after THERMAL_CAPTURE, makes S09 depend on BOTH S08 and THERMAL_QA, retains S01-S11 checks and chain; no silent bypass or automatic PARK after an error. Another module can be added by declaring its own profile and stages, not editing Workflow.
- ThermalFrame typed, session/request/context, plan hash, timestamps/frame id, source capture ref, verified ACK+transfer, native original bytes with vendor source hash, decoded intensity u16 or normalized f32 Kelvin pixel array, checksum, width/height, calibration reference, emissivity and reflected temperature metadata (required in radiometric case). The map may be derived; preserve original untouched separately. Do not pretend normalized Kelvin can be generated without vendor-specific calibration.
- ThermalInspectionSession validates selected workflow stage, current profile, capture capabilities, plan hash, scene/context, timing after dispatch, transferred byte lengths, hashes, calibration metadata and limits (pixel count ~2M, raw <=32MiB). Archive both native original and derived map immutably, verify via Archive; only then create ModuleReceipt and complete THERMAL_CAPTURE with explicit checks. No caller can bypass the receipt via generic success.
- ThermalQA uses explicit ThermalQualityPolicy. For relative intensity, only numeric validity, dynamic range and saturation fraction, no absolute K. For radiometric_f32_kelvin, validates finite positive samples, reasonable declared Kelvin range and emissivity/reflected temperature/calibration metadata. Store audit-friendly QA JSON with source SHA, generated SHA, capture source and policy revision; create receipt and complete THERMAL_QA; no claim of metrological accuracy without physical validation.
- On error: fail closed, no automatic retry, no robot motion or parking. All error and success references recorded in existing SQLite session journal. S09/S10 cannot proceed if mandatory thermal stages failed or absent.
- tests/core/test_thermal_inspection.py with synthetic base profile, relative and radiometric data, original retention, QA, wrong frame/scene/session/request/plan, wrong hash, stale, ACK-only, no RAW, invalid radiometric calibration/emissivity/reflection/NaN, duplicate result, native original vs derived separation, missing capability, no thermal plugin legacy unaffected, replay of session and archived file digest, full end-to-end S01-S11 with RGB-D+Sony+thermal and separate PARK. All Core 0.1–0.4 regressions pass.
- .github/workflows/vision-thermal-inspection.yml Python 3.12, pinned requirements-photography.txt, run test discovery tests/core and compileall src/vision_core src/vision_modules tests/core.
- NO changes to src/vision_core. Do not modify VGP V1, ROS, Sony real settings, calibration files, private images or active main.


## Implemented offline API and trust boundary

Register `vision_modules.thermal.MODULE` in a `ModuleRegistry`, add an approved
`ThermalProfile` to the workflow profiles, and select `make_thermal_scenario()`.
The profile pins the thermal frame ID, mode, calibration reference, and, for
radiometry, the measurement calibration dependency. Calibration references name
entries in the profile's versioned `calibration_dependencies` and must match the
workflow's available calibrations. The thermal frame ID is independent of the
scene observation frame; both are explicitly checked.

Start `THERMAL_CAPTURE` with a unique request, then pass a `ThermalFrame` to
`ThermalInspectionSession(workflow, archive).accept_frame(frame)`. The frame
contains the full context, plan digest, source identity, provenance, ACK and
transfer status, separately hashed original and little-endian map bytes, and
radiometric metadata when applicable. Capture validation precedes archive
writes. The module writes immutable original, map and canonical capture JSON,
verifies them, and submits a typed Core receipt and stage evidence. A write
failure may leave immutable partial files; the stage fails and requires a new
session, never an automatic retry. Existing photography manifests are untouched.

Start `THERMAL_QA`, then call `assess(ThermalQualityPolicy(...))` with explicit
size, invalid and saturation limits and either relative dynamic range or Kelvin
bounds. The returned immutable QA JSON reference identifies the capture JSON
hash, source, calibration, policy and statistics. Radiometric out-of-range
samples count toward the saturation fraction; non-finite, non-positive or above
5000 K samples count toward invalid fraction. The 5000 K bound is a rejection
limit for unreasonable metadata and pixels, not a physical calibration or
acceptance threshold. Relative values are intensity only. Both stages must
succeed before S09; PARK remains a separate explicit workflow action.

Core's generic module receipt interface assumes the adapter calling it is
trusted: arbitrary code with direct access to Workflow can submit its own
receipt and checks. Deployments must restrict that authority to this validating
session; the generic Core interface cannot authenticate this module or prove
physical measurement. The adapter supplies the native bytes, normalization,
source provenance, ACK, transfer status and calibration claims. SHA-256 checks
integrity and binding, not the truth of those claims. Kelvin encoding does not
establish radiometric accuracy. There is no selected camera model, optics,
extrinsics, or physical validation yet. Mounting, TF, timing and temperature
calibration need later physical validation. Optional co-registration with Sony
is not claimed. No hardware driver or vendor normalization is implemented.


Radiometric profiles require a measurement calibration distinct from the geometric
calibration reference, with both dependencies approved at their pinned revisions.
Capture and QA JSON record both names and revisions. Quality-policy fractions must
be below 0.5 and relative dynamic range must be positive. These are structural QA
bounds, not validated physical tolerances; usable tolerances require later physical
calibration.

S10's existing photography archive creates the immutable `manifest-v1.json`. Its
`events` include `module_verified` entries for both thermal stages; each event's
`data.reference` and `data.payload_sha256` identify and verify the corresponding
thermal JSON. Capture JSON identifies the original native and derived map files and
their hashes; QA JSON binds back to the capture and those hashes. The thermal module
does not overwrite or create a separate manifest.
