# Vision / OAK-D Pro AF — height reference 50.4 mm, IR OFF / DOT A-B measurements

Date: 2026-11-13 (VENTUNO Q). Branch: feature/oak-optics-ir-af-roi-20261113 (PR #23), based on PR #22 and ADR-VISION-ARCH-001. Status: EXPERIMENTAL_MEASUREMENTS_COMPLETE / METROLOGICAL_VERIFICATION_PENDING / PROD_RESTORED_PASS.

## Purpose and setup

A printed ChArUco reference board and a red cylindrical element of externally measured **50.4 mm height** were placed on a fixed table in view of the overhead OAK-D Pro AF. Red element at left of board. Do not assume camera-to-table or camera-to-NERO transform has been calibrated.

We previously confirmed 17/17 ArUco markers and 24/24 ChArUco corners in the best RGB image; the board dimensions/square pitch must still be confirmed physically before quantitative ChArUco scaling. The real 50.4 mm element is the only height reference in this test.

Camera: VENTUNO Q, DepthAI 3.12.0, OAK USB3 SUPER. Same RGB 1920x1080/30 and stereo depth 1280x800/30 pipeline with rectification and left-right-check enabled, extended disparity disabled. No on-camera NN or robot motion. 3D points kept in stereo_left_rectified_optical.

Published intrinsics from prior successful physical ImgFrame.getTransformation for THIS device/output: fx 796.596252 px, fy 796.739502 px, cx 634.994690 px, cy 378.508850 px. These are reported optics, not a physical metrology certificate.

## Method

- The fixed depth-only ROI [410, 312, 510, 388] (xyxy pixels) was selected on an earlier actual RAW16 rectified-left depth screenshot. RGB coordinates are NOT blindly used for depth.
- RANSAC fits one dominant table plane from a frame at the beginning of the run. Plane is frozen for the phases to avoid optimizing the plane independently for each IR setting.
- Per-frame height candidates are valid uint16 depth points within 32–80 mm above the table in the fixed ROI; the PRIMARY estimator was locked before testing as the 75th percentile (p75) to reduce mixing with sidewall pixels. Also recorded p10/p25/median/p90/p95 and count. The p75 estimator is exploratory, not validated as the physical height of the top face.
- A nearby, independent tabletop ROI [270:440, 270:390] is used to monitor a local offset; we also calculate the secondary adjusted height = p75 height minus local tabletop offset for EACH frame. This is a diagnostic correction, not a replacement for a properly calibrated plane.
- Each 13-s phase in the first complete A-B-A-B-A test provided 61 valid height samples after 2.5 s settle. Second test: 18-s warmup, 12-s phases, 55–56 samples per phase, 7 phases.
- No raw images or face/object RGB pictures were posted to GitHub. Full per-frame scalar-only outputs remain locally in /srv/vision-data/staging/oak-calibration-check-20261113, mode 0600.
- USB single owner: production service stopped before the direct DepthAI pipeline, then restarted in finally. IR Dot/Flood both requested OFF on exit, SDK returned true/true; there is no independent optical proof of hardware emitter state.

## First complete comparison: OFF / DOT15 / OFF / DOT15 / OFF

61 samples in each of 5 phases, 305 total.

| Phase | p75 height vs frozen plane, mm | Error vs 50.4 mm | p75 with nearby tabletop offset, mm | Valid depth pixels in ROI |
|---|---:|---:|---:|---:|
| OFF 1 | 51.066 | +0.666 | 50.953 | 88.276% |
| DOT 15% #1 | 47.651 | -2.749 | 49.321 | 95.211% |
| OFF 2 | 49.458 | -0.942 | 50.705 | 88.908% |
| DOT 15% #2 | 44.962 | -5.438 | 49.133 | 95.329% |
| OFF 3 | 49.694 | -0.706 | 50.819 | 89.026% |

The very first attempt was automatically aborted and production was restored because the ChArUco detector found only 5 markers in a low-sharpness RGB sample. The RGB focus level changed between startups. That first abort produced 61 scalar samples and is retained separately. Later visual inspection confirmed the board and red element remained in the field of view. Marker count was retained as a diagnostic warning in the later tests because the depth-only ROI does not depend on RGB marker detection.

## Additional IR intensity sweep: OFF / 5% / OFF / 10% / OFF / 15% / OFF

18 s warmup prior to phase 1; 7 phases of 12 s; **386 valid samples** total. The initial OFF RGB marker check returned 17 ArUco and 24 ChArUco corners.

| IR setting | p75 height (mm) | Error (mm) | Locally corrected p75 (mm) | Valid depth ROI (%) | Median depth points in target |
|---|---:|---:|---:|---:|---:|
| OFF 1 | 51.289 | +0.889 | 51.503 | 88.921 | 512 |
| DOT 5% | 46.798 | -3.602 | 49.250 | 94.605 | 1300 |
| OFF 2 | 51.108 | +0.708 | 51.225 | 89.092 | 491 |
| DOT 10% | 46.581 | -3.819 | 49.293 | 95.329 | 1393 |
| OFF 3 | 50.816 | +0.416 | 50.954 | 89.224 | 474 |
| DOT 15% | 46.268 | -4.132 | 48.996 | 95.329 | 1395 |
| OFF 4 | 51.282 | +0.882 | 51.251 | 89.013 | 504 |

Summary of four OFF runs: median of phase medians = **51.195 mm**, raw error **+0.795 mm** (method-dependent), ROI valid pixels **89.053%**. Dot 5% improved this fraction to **94.605%** (+5.55 percentage points). Dot 10% and 15% gave **95.329%**, almost saturated already at 10%.

The dot projector increased the count of target-candidate depth points roughly from 500 to 1300–1400. That may include newly visible oblique sidewalls, altering the p75 population and making the estimate biased low. The nearby tabletop offset also changed by approx. 2–3 mm with IR; after per-frame local offset correction, dot phases still estimate **49.00–49.29 mm** instead of 50.4 mm. It is therefore INAPPROPRIATE to conclude directly that IR improves or worsens intrinsic depth sensor accuracy; this is the error of the current ROI/percentile estimator under changing point coverage and geometry, and may also include systematics/scene/illumination influences.

At no phase was an independent calibrated Z-axis reference created, so no metrological accuracy or repeatability specification can be certified. Per-phase p75 standard deviation ~1.0–1.8 mm; frames are temporally correlated and are NOT independent samples for confidence claims. Board-marker counts fluctuated (12–17 in intensity sweep) even with acceptable RGB sharpness; this remains a diagnostic concern.

## Performance and safety

- Depth ~29.2–29.6 FPS; RGB ~30.0–30.4 FPS throughout. OAK chip ~54–55.3°C during both sequences, below test abort threshold 62°C.
- No loss of USB3 enumeration, and test completed. Depth sequence gaps ~9–13 per 12-s phase observed from the consumer, not ignored. Does NOT prove long-term frame stability or reliable USB reconnect after cold boot.
- Both infrared emitters returned OFF-command acknowledgments true/true at the end.
- Production camera.service restored and checked: active/running, single owner, 0 systemd restarts, RGB **30.0 FPS**, depth **29.3 FPS**, SUPER, chip **54.9°C**, error=null; deployed camera_service_prod.py SHA256 **db90162c49951ac2aa1df78ac5b4b6002d13b0166f573c7785f0242ed9a00316** unchanged.
- Zero changes to production camera files, E-STOP or STOP, Vision Core, NERO, embedded NN, GPU Resource Manager.

## Technical conclusions / next gate

1. Current static tabletop plane and high-percentile ROI estimator can read around 50.4 mm with IR OFF, but measured variation and systematic shifts prohibit calling this calibrated millimeter accuracy.
2. Dot projector increases valid depth coverage greatly even at 5%, while height estimator underestimates 50.4 mm during ON phases. Do NOT enable Dot automatically in a precision measurement profile before changing geometry estimator and re-testing.
3. Next perception change: segment top disk separately from sidewalls, fit a top plane constrained near-parallel to the table plane, then estimate signed plane-to-plane separation with uncertainty and residual quality. Verify output with A/B IR and repeatability at multiple known heights.
4. Confirm true printed square dimensions/flatness; then inspect ChArUco corner reprojection and camera intrinsics using the physically measured print. Need factory depth geometry and cross-camera rectification validation before any table/NERO transformation.
5. Full 2–3h soak with Perception load and USB/controller cold-start/reconnect tests remain PENDING.
6. Keep results and scripts exclusively on private NVMe, and this aggregated technical report in the open GitHub PR. No main merge without explicit owner approval.

**Overall:** DATA_ACQUISITION_PASS, IR_ON_OFF_PASS, PRODUCTION_RESTORE_PASS, ABSOLUTE_50P4_METROLOGY_PENDING; robot coordinates INVALID/UNAVAILABLE.
