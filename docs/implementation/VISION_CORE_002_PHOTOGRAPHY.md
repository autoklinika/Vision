# VISION-CORE-002 — Photography
**Date:** 2026-11-23 · **Status:** IMPLEMENTATION IN PROGRESS / NOT ACCEPTED
**Dependency:** VISION-CORE-001 (#39, unmerged); this 0.2 feature branch is based on #39 and must NOT be merged before its dependency is accepted and merged.
**Authority:** ADR-VISION-CORE-001; VISION_INSPECTION_WORKFLOW_V1; frozen VGP V1; ADR-VISION-SONY-001 is *PROPOSED*, not a proven unattended capture transport.

## Goal
Implement and test a **working, isolated photography pipeline** on synthetic images and inert adapter ports. Keep hardware ownership with VGP/MoveIt 2 and the vendor camera driver. No legacy C8/C9, no camera daemon, no perception service, no physical actions. Design minimal contracts that the later approved VGP and Sony adapters can satisfy without changing Core.

## Scope and deliverables
1. Versioned, typed photo plan: one or more ECU-relative view IDs/targets, session+request+scene+profile correlation, explicit capture requirements and destination. Do not record robot joint angles as view targets.
2. Neutral `VGPPort` and `CapturePort` contracts / transport-agnostic adapters for an existing verified VGP motion-result and camera capture-result, not a replacement planner or controller. No ROS device access in this package.
3. Offline `PhotographyRunner` or equivalent, bound to running Core S07 and successful predecessor S06. Per-view: require verified terminal positioning AND current actual robot state, then capture ACK, then verified transfer and file integrity, linked to request and view. Multiple views are sequential in V1. Duplicate/late/mismatched results cannot silently succeed. On ambiguous timeout or partial failure: stop, journal fault and block dependent stages; no autonomous retry or PARK.
4. Store camera originals **as read-only preserved bytes** in session-scoped private directory via atomic writes and verified SHA-256, no replacement, no symlink traversal, no accidental publish. Preserve RAW/ARW without decoding; JPEG/PNG can be QA inputs. Partial files must not be treated as success. Session manifest includes file hashes, provenance, revisions, relative view ID, timestamps, QA and status.
5. Add actual OpenCV quality evaluator: JPEG/PNG decode, Laplacian focus variance, exposure/clipping, geometry/dimensions and reasonable FOV/crop checks with explicit configurable thresholds. Assessment remains diagnostic unless policy thresholds are supplied. Do NOT claim OpenCV alone proves PCB coverage or physical positioning; no automatic AI.
6. Integrate Core S07→S08→S10 gates with verified evidence references and durable audit: S07 only after all view files transferred & checked, S08 only after QA passes, S10 only after the manifest/originals survive integrity verification and are archived. S09 PARK still separate, never auto-run on error. S11 summary remains Foundation.
7. Inert mocks and synthetic test images; no real ECU imagery, private geometry, serials, IP addresses, or calibration on public GitHub.
8. Dependencies: minimal `opencv-python-headless` and `numpy` for QA only (pin versions for CI); keep core importable without cv2. PYTHONPATH=src test, isolated Python 3.12 environment, CI extending Foundation offline job. Documentation with command to run tests and known limitations.

## Non-negotiable acceptance cases
- 2+ synthetic view capture session: no stage S07 success until all correlated motion+transfer proofs verified; S08 QA and S10 persist.
- Distinguish shutter ACK vs original bytes present; fail closed if any promised original (including RAW-required) missing.
- Raw bytes preserved unchanged and SHA-256 verified after write + on archive replay; derived QA never modifies originals.
- Scene, session, profile, frame or stale observation mismatch, wrong view/request, stale/duplicate capture results, robot goal without actual-state proof, timeouts/partial file, bad JPEG, poor exposure/blur, missing required RAW: all block completion with journal reason. No auto retries.
- Store operations do not overwrite existing originals or trust symlinks/path traversal; manifest is atomic and no false-completed sessions.
- Same inspection plan works with two different mocked capture-device profiles and neutral motion adapters.
- No ROS/MoveIt vendor driver import in core; no service creation, real CAN, live NERO or Sony, and no VGP snapshot modification.
- Compatibility: 0.1 tests remain passing. Both local and GitHub CI actual PASS, with correct test counts.

## Delivery
Code/tests/docs/CI on isolated branch, separate draft PR **targeting feat/vision-core-001-foundation** until #39 is merged. No merge without owner's explicit acceptance. Label any unresolved transport detail TBD; never invent a Sony production binding or assert real VGP integration passed.


## Offline implementation and acceptance boundaries

Install `python -m pip install -r requirements-photography.txt` (numpy 1.26.4 and opencv-python-headless 4.10.0.84); run `PYTHONPATH=src python3 -m unittest discover -s tests/core -v`. Core imports do not require OpenCV. Tests use generated images and inert results only. CI is configured for Python 3.12; its remote result requires an actual GitHub run.

`PhotographySession` accepts correlated, externally supplied motion and capture results; it never dispatches hardware operations. Construct it only after verified S06 and starting S07. Supply each motion result and then its transferred originals in plan order, complete S07, start S08, and supply explicit quality policy and independently verified spatial coverage proof. S09 remains a separately supervised workflow stage. Start S10 only after S09 succeeds, then call `archive_session`. Any failure blocks dependents; interrupted work needs external reconciliation and is not retried. The Foundation API also accepts generic Evidence directly: integrators must use this orchestration and enforce the adapter trust boundary, as the generic workflow cannot independently authenticate external assertions.

The caller chooses a private existing archive root and protects it with operating-system access controls. Original bytes and derived copies are separate read-only files, published without replacement and hash checked. Read-only permissions are not immutable against a privileged owner; replay must recheck hashes and protect the journal and manifest against unauthorized alteration. A failure can leave incomplete files, which are never marked complete and require operator cleanup/reconciliation. The manifest has status `prepared` and contains a snapshot of journal events taken during S10, before the manifest is published. It is not a full post-completion audit: manifest verification, the `archive_verified` event, and the final S10 success transition are recorded subsequently in the durable journal. Archive retention, backup, tamper-resistant signing, and cross-process coordination are outside this implementation.

Focus variance and pixel clipping are image heuristics, not calibrated optical measurements. ROI checks establish only pixel bounds, not physical field of view or PCB coverage. Thresholds must be selected and validated for each use; no defaults or automatic coverage inference are supplied. JPEG/PNG decoding depends on OpenCV and cannot establish that an image depicts the intended ECU. RAW bytes are preserved without decoding or claims about their internal validity. External motion/coverage results require a trusted, independently verified adapter and operational validation; no live VGP, camera, robot, or production transport has been tested. Sony staged transfer remains unresolved and needs a future approved transport adapter; shutter ACK alone is never accepted as original transfer.
