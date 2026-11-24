# Vision Runtime ROS2 Luxonis adapter V1

Status: read-only, offline verified; partial physical ROS2 camera stream and adapter acceptance completed 2026-11-24; no production deployment and no physical S03/S04 ECU acceptance. See [Live Luxonis acceptance](../audits/VISION_RUNTIME_LUXONIS_LIVE_READONLY_ACCEPTANCE_2026-11-24.md). ETC3 remains DRAFT. This adapter does not launch a driver, change illumination, control motion, select an ECU, or supply object detection. Missing independent pose or feature landmarks produces NOT_READY. The coordinator still requires the operator's declared type and its independent trust verifier.

`ros2_messages.normalize_rgbd` accepts sensor_msgs-compatible messages, explicit metric depth units (`16UC1` in mm or `32FC1` in m), current time and freshness/skew limits. RGB and depth CameraInfo must match their own images. At least one depth pixel must be positive (millimeters for 16UC1, finite meters for 32FC1); zero and invalid pixels may coexist with usable samples. Row padding is excluded from this check, and byte order is honored. Spatial coverage is the pose estimator’s responsibility. The two TF messages must map RGB optical to scene and depth optical to RGB optical respectively. Frame identifiers are never rewritten. Image bytes remain in the bounded packet, not the Core Journal. Image references hash the exact transmitted bytes including row padding. Calibration and transform references hash deterministic compact JSON representations of the normalized calibration fields and frame/transform values; timestamps are retained separately. An external verifier must authenticate those references, source, calibration revisions, geometry, uncertainties, and device state. Hashes alone do not establish trust.

`SnapshotCollector` accepts explicitly configured `TopicBindings` including ROS domain; `inject` supports offline use. `snapshot` takes a caller-supplied TF lookup `(target, source, stamp)` and selects the newest synchronized set from timestamp-ordered bounded queues, with latest arrival breaking timestamp ties, and rejects stale or unsynchronized sets. It looks up TF at the selected image timestamps. Ingress checks image dimensions, stride, byte length and encoding before retention; each image is limited to 64 MiB, total retained image bytes to 128 MiB, and each stream to at most 32 messages. CameraInfo fields are bounded. Middleware allocations before the callback are outside this budget. The optional `from_node` subscribes on an existing node with sensor QoS and checks the configured domain against `ROS_DOMAIN_ID`, treating an unset variable as domain 0. The caller sets the domain before creating the node, supplies a tf2 buffer/lookup, manages spin, lifecycle and resource cleanup. There is no automatic node creation or background executor. Configure actual topic names explicitly; historical VGP topics included `/oak/rgb/image_raw`, `/oak/stereo/image_raw`, `/oak/rgb/camera_info`, and `/oak/stereo/camera_info`, but their presence and depth units must be verified in the active graph. A stereo image may be disparity or non-metric and must not be passed as metric depth.

TF timestamps, including static transforms, must meet the same freshness and skew limits; old static TF stamps fail these limits unless explicitly fresh; deployments must provide appropriately timestamped verified transform evidence, without fabricating timestamps. The adapter does not interpolate, register pixels, transform feature geometry, or infer calibration. External scene-frame geometry must already be independently measured and verified; distinct optical frames require a pinned relative calibration and a trusted configured transform pair. Real deployment requires confirming driver topics, image semantics and calibration, clock domain, TF direction and provenance, resource limits, and independent source verifier before use. No physical validation is claimed.

ROS conventions: [Jazzy Image](https://docs.ros.org/en/jazzy/p/sensor_msgs/msg/Image.html), [Jazzy CameraInfo](https://docs.ros.org/en/jazzy/p/sensor_msgs/msg/CameraInfo.html), [Jazzy TransformStamped](https://docs.ros.org/en/jazzy/p/geometry_msgs/msg/TransformStamped.html), [tf2 concepts](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Tf2.html).

Ingress retains owned, deeply immutable copies of image bytes, headers, timestamps and CameraInfo metadata after checking the image size and retained-byte budget. The caller may reuse or mutate its messages after injection. Snapshot searches candidates in deterministic newest-first order and validates each synchronized quartet, including both transforms, before returning it; invalid candidates can fall back to older messages. The search examines at most 4096 quartets and fails closed if none is valid within that limit, even if a valid quartet exists beyond it. Subscription callbacks are opt-in through `from_node`; offline injection does not create subscriptions.


## Live ROS 2 Jazzy compatibility

During the read-only test, CameraInfo K/R/P arrived as NumPy arrays containing numpy.float64 values. The collector now accepts finite real-number scalars including NumPy, while rejecting booleans, NaN/Inf and strings. Regression tests cover the observed Jazzy data types.

The owned adapter stamp is not a generated ROS builtin_interfaces.msg.Time object. For a caller-managed tf2 buffer, convert it explicitly using rclpy.time.Time(seconds=stamp.sec, nanoseconds=stamp.nanosec), then call buffer.lookup_transform(target, source, query_time). The test probe originally used Time.from_msg on an owned stamp, which is invalid.

The live camera's RGB and aligned Depth frames were both oak_rgb_camera_optical_frame. Its camera-local TF was available from oak_parent_frame, but there was no verified active world-to-camera transform. PointCloud2 was received independently with RELIABLE QoS; it is not included in the Runtime RGBDFramePacket and does not establish ECU pose.

## Verifier payload contract

`SensorObservationBuilder` calls `verifier(kind, payload) -> bool` and requires
the result to be exactly `True`. For `kind == "binding"`, `payload` is the complete
`MeasurementBinding`. Its digest is checked before and after authentication and
again after constructing the observation receipt. Profile and calibration maps
are copied before constructing the binding, so the receipt uses the same snapshot
that was authenticated. Mutation of geometry or binding fields during verification
produces `NOT_READY`.

For `kind == "readiness"`, `payload` is now the complete typed `ReadinessReceipt`,
including session, request, both revision maps, timestamp, source, proof, quality,
capabilities and device-state reference. This intentionally replaces the former
four-item tuple before V1 is merged; integrations must authenticate the full
receipt. The builder checks its digest across the callback. The coordinator then
checks readiness freshness and the configured context again after authentication.
Callbacks authenticate evidence; they must not modify their input.
