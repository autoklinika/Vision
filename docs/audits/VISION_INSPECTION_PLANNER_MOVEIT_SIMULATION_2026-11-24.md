# Inspection Planner V1 — isolated MoveIt simulation, 2026-11-24

## Outcome

**PASS: two sequential camera targets planned by the installed NERO MoveIt stack.**
The adapter also rejected an unreachable target and a scene containing a blocking
collision object. This is a synthetic software integration result. It is not a
physical ETC3 inspection, station calibration, robot movement or metrology result.

The test used a fresh, localhost-only ROS domain **187**. A separate vendor
`move_group.launch.py` instance ran with `arm_type:=nero`, `effector_type:=none`,
`follow:=false`, and **`allow_trajectory_execution:=false`**. The script read the
execution parameter and required it to be false before creating any fixtures.
Only the test's synthetic JointState publisher and MoveIt server were started.
No hardware driver, controller, camera, shutter or execution client was started.

## Tested exchange

The NERO model and limits came from that isolated server's URDF, SRDF and planning
parameters. A deterministic, collision-free synthetic seed was published with
source timestamps and zero measured velocities. The test added a synthetic floor
and a small camera collision body attached to `tcp_link`; only `tcp_link` and
`link7` were touch links. Two nearby camera targets were derived from the model's
FK in its declared planning frame, `world`, with a **synthetic** tool transform.

For each target the adapter used collision-aware `GetPositionIK`, FK verification,
`GetStateValidity`, `GetMotionPlan` and bounded checks of the returned trajectory.
The second segment started at the first segment's planned endpoint. The published
measured seed remained unchanged: **maximum joint drift 0 rad**. No trajectory
was executed. Scene content hashes remained equal across the successful plans.

| Result | View 1 | View 2 |
|---|---:|---:|
| Timed trajectory points | 5 | 5 |
| Additional sampled states checked for collisions | 5 | 5 |
| Planned trajectory duration | 0.327602250 s | 0.328208702 s |
| Adapter round-trip time | 0.167070 s | 0.176795 s |
| FK camera position residual within the model | 0.032078 mm | 0.004851 mm |
| FK camera orientation residual within the model | 0.000073330 rad | 0.000115195 rad |
| Age of measured joint source at final snapshot receipt | 0.019619 s | 0.028388 s |

The unreachable target returned `MoveIt IK failed`. A subsequently inserted
synthetic blocking box returned `MoveIt state collision or constraint failure`.
These failures did not produce a successful segment or any Core stage transition.

## Integration findings resolved

### PlanningScene is not a timestamped measured-state source

The installed `GetPlanningScene` response provided joint positions but a zero
JointState timestamp and an empty velocity array, despite the active 20 Hz
synthetic source. Treating service receipt time as measurement time would hide
stale feedback. The adapter initially rejected this response, then gained an
explicit, read-only `AdapterConfig.joint_state_topic` subscription.

The adapter now compares the source positions with the PlanningScene positions,
preserves the source timestamp and actual velocity array, and records a separate
`received_at`. It retains one bounded owned copy. Missing, stale or inconsistent
source data remains an error. The test topic was `/control/joint_states` solely
inside domain 187; it is not a default production feedback topic.

### Jazzy time parameterization has a nonzero first-point velocity

The installed time-optimal parameterization returned a maximum first-point
velocity of **0.0005000000000000001 rad/s** while the measured seed and requested
start state had zero velocity. Both final-point maxima were below `1.1e-17 rad/s`.
The original `1e-6 rad/s` check correctly rejected the trajectory.

The adapter now has a hashed, explicit `start_velocity_tolerance_rad_s` setting,
defaulting to **`1e-6`** and bounded at **`0.001`**. This synthetic smoke explicitly
used `0.001`; it did not modify or zero the returned trajectory. Final-point
velocity remains limited to `1e-6`. This setting is a numerical acceptance policy
for the synthetic test, not an approval of physical motion or photography while
moving. A related upstream Jazzy behavior is tracked in
[MoveIt issue #3014](https://github.com/moveit/moveit2/issues/3014).

## Versions and evidence

| Package | Installed version |
|---|---|
| `ros-jazzy-moveit-core` | `2.12.4-1noble.20261106.060446` |
| `ros-jazzy-moveit-ros-move-group` | `2.12.4-1noble.20261106.103016` |
| `ros-jazzy-moveit-msgs` | `2.6.0-1noble.20261105.191325` |
| `ros-jazzy-rclpy` | `7.1.13-1noble.20261105.191212` |

The actual pipeline logged OMPL `geometric::RRTConnect`, time-optimal
parameterization and `ValidateSolution`. Interface fields were checked against
the installed Jazzy `moveit_msgs` definitions. Their upstream source is
[moveit/moveit_msgs](https://github.com/moveit/moveit_msgs/tree/ros2).

Private test evidence is retained under the station staging directory
`vision-inspection-planner-v1-20261124-smoke`; no live camera images or real ECU
geometry are in this PR.

- Result JSON SHA-256: `ff4d02367ecc739dcfb19c028d4bbf06a168b41ca5d5ac38623dbc57bfa9b6f0`.
- Configuration digest: `fa46c84a7af74e3aa6235809805fcf3a7351d90379dbacec4c6c1f50e2ac9094`.
- Successful scene hash: `7717dcff168adcd25419b35ac83bf90da3a0436eabe210a442c1a3cdabb14b6c`.
- View 1 digest: `80099fa8d55b66b8487810234223cede968a24faa4ed7f4f2809b0bb303302d4`.
- View 2 digest: `c5dfc812b89fbc1f27bc40c2e801cbaea1cacc2db3c7bed192bf5d3da2be7b3f`.

The final source additionally bounds oversized joint-name arrays before copying
or iterating them. That resource guard was added after the successful live smoke;
its specific regression and the explicit velocity-policy regression passed with
the other adapter tests (**29 tests**). No planning policy or successful-trajectory
data was changed by the final resource guard.

The owned test launch and MoveIt process were stopped, and their process group was
confirmed empty. Existing station robot, MoveIt and Luxonis processes remained
present. No existing station process or baseline was changed by this test.

## Reproduction and limits

Source ROS 2 Jazzy and the official NERO vendor workspace, then start a **fresh**
isolated localhost-only MoveIt server with execution disabled:

```bash
export ROS_DOMAIN_ID=187
export ROS_LOCALHOST_ONLY=1
ros2 launch agx_arm_moveit move_group.launch.py \
  arm_type:=nero effector_type:=none follow:=false \
  allow_trajectory_execution:=false
```

In the same isolated environment, with this repository's `src` prepended to
`PYTHONPATH`, run:

```bash
python3 tools/lab/inspection_planner/moveit_smoke.py \
  --domain-id 187 --output /tmp/vision-planner-synthetic-result.json
```

The script intentionally creates synthetic scene fixtures. Stop the owned test
server afterward; use a fresh server for another run. Domains 0, 185 and 186 are
explicitly rejected by this lab script. This is an operator-selected simulation
test, not an automatic station startup path.

Two short synthetic paths do not establish whole-workspace reachability, measured
ECU coverage, absolute camera-to-table accuracy or controller behavior between
trajectory points. Linear samples supplement MoveIt's path checks; they do not
constitute a continuous-collision proof for a future controller interpolation.
See the upstream [time parameterization documentation](https://moveit.picknik.ai/main/api/html/classTimeOptimalTrajectoryGeneration.html).

Scene pre/post hashes detect changed content but do not authenticate a scene owner
or exclude transient concurrent changes. The coordinator still requires its
separate trusted scene lease and full Runtime observation binding. The measured
ETC3 profile, absolute station transform and physical S03–S04 acceptance remain
separate prerequisites for a real inspection.
