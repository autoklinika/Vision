# Vision C8 — ROS 2 NERO single-segment FollowJointTrajectory (lab)

**Status, 2026-11-20:** the first implementation and tests are complete in a separate overlay; **no physical trajectory execution has occurred**. The real robot remains in `NORMAL` with 7/7 drives enabled and the original `vision-nero-guarded-lab.service` operator HOLD receiver restored. CAN TX remained **6** during the entire software development and test sequence.

## Why separate from the full ETC3 photo route

C7 MoveIt has found candidate trajectories on the estimated ETC3 scene using a **5 mm software obstacle buffer**, but the exact physical table, base and Sony tool transformations have not yet been independently accepted. A supported lab check must not execute the complete multi-joint Pilz plan blindly. The C8 implementation is therefore intentionally a constrained **single-step first-motion bridge**, not a general-purpose trajectory executor.

## Implementation

- `ws/src/agx_arm_ctrl/agx_arm_ctrl/vision_nero_single_segment_node.py` subclasses the existing guarded AgileX ROS 2 node and retains its single SDK SocketCAN owner and `/nero_guarded/controlled_stop_hold` service.
- `/nero_guarded/follow_joint_trajectory_lab` is a standard `control_msgs/action/FollowJointTrajectory` action, but the first phase accepts **exactly two joint-state points**, **only J2**, **0.2–2.0 degrees**, starting within 0.15° of live telemetry. All other joints must remain fixed to 0.025°.
- Live feedback freshness: <= 150 ms for joints and controller status, <= 200 ms for motor telemetry; firmware `NORMAL`, `CAN_CTRL`, error mask 0, seven motors enabled.
- Vendor URDF joint limits retained with 1° endpoint margin, speed capped at **3%**.
- Uses only vendor `move_j()`, NEVER `move_js()` (undamped fast-response mode); monitors actual joint state and goal convergence. This is *vendor point-to-point motion*, not timed playback of arbitrary Pilz waypoint arrays.
- `CancelGoal` or the existing operator ROS HOLD latches stop and retargets the measured `current_q` via the physically tested `move_j(current_q)` procedure. No automatic disable or damped E-STOP.
- Defaults `physical_single_segment_enabled=false`; enabling requires operator authorization, valid short-lived one-shot file, local ROS domain 181, operator HOLD enabled and exact goal token. A durable `.used` marker blocks replay after restart. Mock activation is restricted to a fake Arm instance and isolated ROS domain 178.
- The original guard remains the normal, enabled unit. The new `vision-nero-single-segment-lab.service` is installed **but disabled for boot**. It was briefly run in read-only mode on real NERO (firmware NORMAL, HOLD service exposed, action visible but not armed); then stopped and original HOLD restored.

## Evidence

- Pure policy tests: **11/11 PASS**.
- ROS 2 ActionServer with an injected fully fake AgileX SDK, ROS domain 178:
  - `SUCCEEDED`: reached test J2 goal, only one `move_j` invocation.
  - `CANCELED`: one actual mocked HOLD invocation and action returned `STATUS_CANCELED` after cancel request.
  - Second attempt rejected after a one-shot goal.
  - Both mock runs showed **real CAN TX 6 -> 6**.
- Live actual pose snapshot: J1 90.321°, J2 56.847°, J3 -0.797°, J4 106.276°, J5 0.239°, J6 -0.881°, J7 23.329° before software-only work.
- Isolated MoveIt domain 203 planned an explicit J2 +1.0° segment in the real ETC3 surrogate scene and checked 21 samples in each of four combinations (+90/-90 Sony mounting hypotheses, detailed/conservative tool). **4/4 PASS; CAN 6 -> 6.** This does *not* establish continuous swept-volume collision clearance.
- Live read-only service test: `physical_single_segment_enabled=false`, NERO firmware NORMAL, motors enabled 7/7, HOLD available; action registered, not armed.
- Original guard restored, normal `vision-nero-guarded-lab.service` active, new experimental unit disabled, motors left enabled and stationary.

## Outstanding

Physical action authorization and the first on-hardware `FollowJointTrajectory` goal were **not performed**. The requested path remains blocked until its execution gate is explicitly established. Keep the arm supported and operator present. No autonomous multicontact, multi-segment or full ETC3 trajectory is allowed by this implementation. Do not manually edit the authorization mode to bypass a failed gate.

The original robot HOLD is an accepted **operator-supervised laboratory procedure** for this project, not a certified protective stop.

## Files

- `logs/fake_action_success_final_20261120.log`
- `logs/fake_action_cancel_final_20261120.log`
- `validation/nero_live_j2_plus1deg_moveit_20261120.json`
- `config/one_shot_mode.env`
- `bin/start_limited_guarded.sh`
- The separate unit definition: `/home/arduino/.config/systemd/user/vision-nero-single-segment-lab.service` (not enabled).

Full raw reports remain on the VENTUNO Q private NVMe.
