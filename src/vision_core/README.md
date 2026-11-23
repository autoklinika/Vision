# Vision Core 0.1 — offline foundation

Vision Core is a Python 3.12 standard-library-only library. It is **not** a ROS 2 node, hardware driver, camera service, executor, or production runtime.

## Model and workflow

Build six approved, revision-pinned profiles: `station`, `sensor`, `capture`, `tool`, `robot`, and a typed `ECUProfile` containing nominal geometry, PCB regions and ECU-relative view targets in millimetres. Select capability requirements and calibration revisions explicitly. Validate synthetic fixtures in `tests/core/test_workflow.py`.

Create a `Journal` and a `Workflow` with a unique session ID and a strictly positive observation freshness limit. **S01–S03 do not require an already-localized ECU.** Start with an unlocalized `Context`; S03 must complete with independently verified, timestamped `Evidence.context` identifying the current scene, frame and pinned profiles. Acceptance and promotion of the localized context are persisted together in the journal. S04 onwards uses that localized context.

Call `start(step_id, request_id)` for a new stage. `ack` does **not** complete the stage. `complete(evidence)` requires correlated terminal success, fresh evidence and every declared stage-specific proof. A failed or stale gate blocks dependent steps. Updating the context after planning invalidates incomplete work; this version does not implement an in-session replan/retry workflow. On restart, journal replay reconstructs verified stages and localizations; interrupted READY/RUNNING stages remain blocked pending external reconciliation.

## Run the offline tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests/core -v
python3 -m compileall -q src/vision_core tests/core
```

No camera, robot, ROS 2 installation, private ECU images or physical station geometry are required.

## Scope and limitations

The `Evidence.checks` set is a **claim made by a future trusted integration adapter**. Core verifies correlation, context, declared checks, freshness and workflow order; it does not itself measure focus, verify physical robot state, hash files, perform perception, activate HOLD, authorize recovery PARK or drive equipment. Numeric tolerances, capture controls, exact ROS 2 bindings and external-state reconciliation belong to later packages. SQLite files and artifact references must be stored privately with appropriate permissions. Do not treat successful offline tests as approval for unsupervised physical motion.

Plan-bound spatial coverage requires canonical per-view capture bindings derived from the
verified original file hashes, source identifiers and capture references. These bind a
coverage claim to acquired originals but do not independently authenticate the adapter or
prove that its measured footprints correspond to those images. Legacy unbound 0.2
photography remains supported and relies on the trusted coverage provider's view IDs.
