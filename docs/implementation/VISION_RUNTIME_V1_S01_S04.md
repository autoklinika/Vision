# Vision Runtime V1: Stage A S01–S04

This offline coordinator binds one operator declaration to an approved catalog record, ECU release, approved reference release, physical state, recipe, assets, and compiled Core ECU profile before creating a Core Workflow. The operator selects the type; observation never selects it. S02 rechecks the releases and compilation and records a digest of the selection and operator. No real ETC3 approval is implied by the synthetic test fixtures.

The caller supplies the Core Journal, approved profiles, clock, calibration IDs, trusted transform configuration, capabilities, and an independent `trust_verifier(kind, receipt)` callback. This callback is a security boundary: it must authenticate the sensor or device source, verify the referenced content and measurement uncertainties, and confirm the actual transform and device state. A receipt, a SHA-256-shaped reference, or a quality flag alone does not authenticate anything. The runtime has no sensor adapter and cannot establish provenance itself. References are `sha256:<lowercase hex>` and identify externally retained data; the journal contains hashes of the full selection and receipt, not raw images.

Each method accepts a correlated Core `Request` and starts its stage once. S01 validates readiness and calibrations; S02 pins selection; S03 checks synchronized fresh RGB, depth, CameraInfo and TF references, transform frames, envelope, connector landmarks, PCB and obstacle references, and promotes the localized context atomically in Core; S04 verifies the same receipt against the declaration and catalog, including ambiguity. A validation failure stops the running stage as FAILED and blocks descendants. A failed session requires a new session. Core rejects reused request IDs and reconciles interrupted work on restart. After restart, S04 fails closed because the in-memory receipt is not reconstructed from its journal hash.

Timestamps must be at or after dispatch and within the configured freshness limit. Use `begin(stage, request)` to dispatch before acquiring a receipt, then pass that same request and the acquired receipt to the stage method. The stage method can also dispatch directly when the receipt timestamp meets the dispatch requirement. No ROS bridge, WebGUI, hardware motion, capture, or S05 action is implemented here. `MockSensorPort` records requests only and produces no receipt.

Stage C1 evaluates required selected-state reference features against the approved ECU record and externally verified local measurements. Only `rgbd_landmark` rules with controlled connector IDs, matching colors, verified metric reference sources and bounded uncertainties are supported; other required methods and unsupported feature correspondences fail closed. Identity and pose quality policies must be present and verified. The ECU catalog ambiguity check remains mandatory. Envelope and connector uncertainties cannot expand the approved geometry limits.

The ROS observation builder requires an external estimator and a single independent `binding` verification over the exact RGBD packet, geometry, source proof, session, request, scene and calibration context. Its receipt includes a binding reference, geometry reference and source proof; the coordinator's external trust verifier must retrieve and cross-check that retained binding against the complete receipt and current context. A raw image receipt is not measurement authorization. Full automated visual feature detection is not implemented. A read-only ROS2 live camera and adapter test passed on 2026-11-24, but it was not a physical S03/S04 ECU-localization success; see the dedicated live acceptance report. Permissive verifier callbacks in tests are synthetic test doubles only.

## Final audit: authentication and durable observation identity

Independent verification must leave its input unchanged. The coordinator compares
the full selection/receipt digest before and after the callback, and revalidates
readiness or every observation source timestamp after it returns. A slow callback
cannot keep an expired depth or TF sample valid merely because RGB is still fresh.
S04 requires the current complete receipt digest to equal the unique durable S03
`localization_accepted` evidence reference; matching scene, frame and RGB time
alone is insufficient. These checks do not replace the external verifier's duty
to authenticate retained source data and the actual station configuration.

See the [final Runtime audit](../audits/VISION_RUNTIME_V1_FINAL_AUDIT_2026-11-24.md)
for the reproduced defects and regression results.
