"""Vision Inspection Planner V1: calibrated S05 and plan-only S06.

Importing this package does not initialize ROS, load a robot driver, acquire
images, or send hardware commands. ROS dependencies are optional and imported
only by MoveItAdapter.from_node().
"""
from .preparation import (
    CameraCalibration, PlanningPolicy, PreparedInspection, PredictedFootprint,
    ViewBinding, ViewCoverage, prepare_plan, verify_prepared,
)
from .moveit_adapter import (
    AdapterConfig, JointLimit, MoveItAdapter, SceneSnapshot, SegmentResult,
    TrajectoryPoint, camera_to_link, link_to_camera, validate_segment,
)
from .coordinator import (
    InspectionPlanner, MotionPlan, MotionSetup, SceneBinding, SceneLease,
    PreparationBinding,
)

__all__ = [
    'AdapterConfig', 'CameraCalibration', 'InspectionPlanner', 'JointLimit',
    'MotionPlan', 'MotionSetup', 'MoveItAdapter', 'PlanningPolicy',
    'PredictedFootprint', 'PreparationBinding', 'PreparedInspection',
    'SceneBinding', 'SceneLease', 'SceneSnapshot', 'SegmentResult',
    'TrajectoryPoint', 'ViewBinding', 'ViewCoverage', 'camera_to_link',
    'link_to_camera', 'prepare_plan', 'validate_segment', 'verify_prepared',
]
