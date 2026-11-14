# Vision / Luxonis OAK-D Pro AF — on-device AI bring-up (2026-11-10)

## Scope
Real hardware test on VENTUNO Q (Ubuntu 24.04.4 LTS ARM64) with installed DepthAI 3.12.0, isolated NVMe venv.
Camera product: OAK-D-PRO-AF, RVC2 / Myriad X. No NERO actuation, no IR switching, no factory EEPROM changes.
No photographs saved or uploaded in the AI tests. All changes are local staging.

## Model
Luxonis Model Zoo `yolov6-nano`, explicitly compiled for `RVC2`.
- Resolved archive: YOLOv6_Nano-R2_COCO_512x384.rvc2.tar.xz
- Model package type: SUPERBLOB; contains a usable RVC2 blob.
- Download bytes: 8054568.
- SHA256 archive: 926124b2f926d644e8ce6fd1ea8f90c30ebfe569bdb17105055718299a426a00
- Cache on NVMe, not on eMMC; host did not run NN inference.
- Node: `dai.node.DetectionNetwork`, using on-device NeuralNetwork and DetectionParser.
- Model has 80 COCO classes and is demonstrative, not PCB-/ECU-trained.

## Test A — object inference, camera only
Script: `test_rvc2_ai.py`
- Platform `RVC2`, USB `UsbSpeed.SUPER`.
- 20.04 seconds, 427 NN output packets, effective 21.31 inference results/s.
- Detection outputs received and parsed on the host; 409 of those packets contained a `tv` label (409 detections summed over frames), maximum confidence 0.758.
- This proves model execution and parsed output, not accuracy of the class assignment. No labeled ground-truth validation has been performed.
- Result `AI_ON_RVC2_PASS`; exit 0.

## Test B — combined on-device NN + stereo depth
Script: `test_rvc2_ai_stereo.py`
- 15.04 seconds, 223 paired NN and depth outputs; 14.83 paired results/s.
- Depth frame 1280x800 (unit mm).
- Average valid-depth fraction 0.20 over sampled full frames (valid 1..4999 mm).
- 203 detections aggregated over the paired outputs.
- Result `PASS`; exit 0.

## Interpretation and constraints
- The inference *runs on OAK-RVC2 VPU*, not the VENTUNO host CPU. Python on host receives output packets and does telemetry/aggregation.
- These FPS are end-to-end application measurements, not isolated silicon peak compute. Different camera and stereo settings affect them.
- Camera is temporarily pointed at a non-calibrated indoor scene, not the final rigid overhead mount. Real PCB/ECU accuracy and detection capability are NOT yet demonstrated.
- YOLOv6 Nano COCO contains general classes; specialized PCB/ECU object recognition will need labeled data and a model exported for RVC2.
- No stability soak test, latency distribution, on-die temperatures or power-headroom benchmark has been performed.
- No automatic robot actions should use these detections until calibration, safety interlocks and acceptance checks are completed.

## Next recommended steps
1. Controlled 5/30/60 min latency, inference FPS and temperature audit with resource logging.
2. Compare 1 and 2 inference threads, model variants, input sizes and the stereo pipeline to choose operating point.
3. Capture non-sensitive calibration targets with known dimensions and distances, benchmark 2D and 3D quality.
4. Build replay-based tests and an adapter API in Vision Core, separate from any NERO actuation.
5. Keep all public GitHub evidence privacy-sanitized and leave main untouched until explicit approval.

## Official documentation
- https://docs.luxonis.com/software-v3/depthai/examples/detection_network/detection_network
- https://docs.luxonis.com/software-v3/depthai/examples/rvc2/nn_archive/nn_archive_superblob
