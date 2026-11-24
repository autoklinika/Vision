# ETC3 RGB-D localization — isolated laboratory diagnostic

**Status:** EXPERIMENTAL / PROVISIONAL. This is NOT the generic Vision ECU classifier, not an ECU Reference Profile release, and not a robot positioning authority. It is a read-only offline diagnostic for the owner-declared ETC3, following the accepted Vision Runtime V1 boundary.

The script loads previously recorded, RGB-aligned Luxonis 1920×1080 BGR images and 16UC1 millimeter depth frames. It tracks an operator-annotated gray connector from an independently retained historical image using SIFT/RANSAC; rejects unstable tracking and outlying depth; fits the current tabletop plane from observed 3D points; segments the visible ECU hull above that plane and reports camera-frame coordinates and provisional dimensions.

**No hardware access, ROS publishers, TF publication, MoveIt commands, motors, CAN, Sony capture or camera-driver restart are possible from this script.** It does not produce an APPROVED pose for Core S03/S04.

Run offline with valid *private* inputs:

```sh
python3 tools/lab/etc3_localization/localize_etc3_rgbd.py \
  --capture /private/rgbd-session \
  --reference /private/verified-operator-image/selected_rgb.jpg \
  --candidate /private/unapproved-table-tf-candidate.json \
  --out /private/results
```

The capture directory must contain an image-integrity manifest, eight matching RGB PNGs, eight depth PNGs and CameraInfo. The reference is an operator-identified exemplar **for this test only**. The script has deliberately explicit image coordinates `ROI`, `BOX` and `CROP`, taken from a fixed historical photograph; they are not reusable for an unknown or different ECU without independent review. The candidate calibration argument is optional; without it the script reports camera optical XYZ and locally measured table plane only.

Output is a JSON provenance/measurement record plus privately retained overlays. Metric precision is limited by camera calibration, depth quality, optics and timing; SIFT is visual registration, not ECU-variant verification. The hull is only visible geometry, not a safe MoveIt collision envelope. Candidate table coordinates must never be installed in the station TF tree.

Offline unit tests:

```sh
python3 -m unittest discover -s tools/lab/etc3_localization -p 'test_localize_etc3.py' -v
```

Dependencies are pinned in the repository `requirements-photography.txt`.

The measured results and explicit acceptance limits are in [the 24 November ETC3 live localization report](../../../docs/audits/VISION_ETC3_LIVE_RGBD_LOCALIZATION_2026-11-24.md). All raw images, depth frames, archived reference photos and full per-frame output remain on the private NVMe staging area, not in GitHub. Future production integration requires replacing specimen-specific ROI constants with approved ECU Reference Profile declarations and binding the estimator to authenticated synchronized ROS 2 observations.
