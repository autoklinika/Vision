# Device Readiness V1

Diagnostic presentation only. The independent Core owns inspection decisions.
A diagnostic status is neither an authenticated Runtime readiness receipt nor
authorization for motion. The existing Runtime composition, approval and
freshness gates are unchanged; diagnostic observations cannot authorize start.

## Read-only inputs

- systemd service liveness and passive USB enumeration remain independent.
- An optional local ROS 2 Jazzy observer uses the existing domain 181 (localhost)
  and exact installed topic/publisher bindings. It does not publish application
  topics, use ROS service/action clients, start drivers, or access CAN/USB.
  Graph identity and endpoint uniqueness are diagnostic provenance, not security
  authentication. It pins the endpoint over each sample window.
- NERO: source-stamped joint1–joint7 feedback, arm DiagnosticArray status,
  and seven motor diagnostics; fresh explicit arm fault or disabled motors
  means NOT_READY. READY requires current valid axes, normal arm and enabled
  motors. This does not override the guarded service's trajectory restrictions.
- OAK / OAK800: exact corresponding RGB and metric-depth topics; current,
  valid image layouts and bounded positive depth pixel samples, with at most
  0.5 s RGB/depth timestamp difference. This verifies stream availability,
  not camera calibration or ECU localization.
- MoveIt: existing move_group monitored planning scene, current actual
  NERO joint feedback, scene joint states within 0.05 rad of feedback and
  fresh base_link → link7 TF. This verifies diagnostic planning data only,
  not calibrated collision geometry or executable trajectories.
- Sony: no accepted live acquisition diagnostics, so UNKNOWN.
- Known stopped monitored service is NOT_READY; unknown service state,
  unverified, missing or stale observations remain UNKNOWN. Conflicting
  active scene alternatives cannot establish readiness.

## Observer and transport

Run the observer with system Python and ROS Jazzy environment in a separately
supervised process, using a private NVMe directory and report filename:

```sh
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=181 ROS_LOCALHOST_ONLY=1
export PYTHONPATH="<pinned-release>/src:${PYTHONPATH:-}"
/usr/bin/python3 -B -m vision_station.ros_readiness --report "<private-dir>/readiness.json"
```

The observer uses bounded periodic sampling windows (1.5 s, then 0.75 s idle).
It subscribes only to discovered expected publishers, keeps metadata only and
unsubscribes after the first sample of each image stream per window. Source
timestamps must be at most 2 s old at sampling; the report and evidence expire
after at most 5 s at Core. The 0600 local JSON is atomically replaced, bounded
to 8 KiB, validated for ownership, freshness and fixed reason codes. The
HTTP/socket request path never waits for DDS discovery or image data.

Pass `--readiness-report <same-private-file>` to the independent Core service.
Without the explicit observer file, no positive ROS readiness is inferred.
`--diagnostics-disabled` is incompatible with this option and continues to
isolate fixture tests. The optional `readinessReason` wire field accepts only
device-appropriate enumerated codes consistent with readiness. Legacy reports
without the field still validate. No image payloads, joint positions or raw
diagnostics enter the API or GUI.

DEV uses a separate Core, library and local observer report. Only real
read-only VENTUNO diagnostics are shared. Production needs explicit observer
supervision and a coordinated Core/API release; a WebGUI-only update is not
sufficient for the new report. Physical acceptance of active camera/MoveIt
streams and Sony acquisition remains separate.
