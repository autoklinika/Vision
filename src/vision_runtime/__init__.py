"""Stage A input contracts. No sensor acquisition or hardware activation."""
from .contracts import ReadinessReceipt, ObservationReceipt, SensorStamp, MeasuredConnector

__all__ = ['ReadinessReceipt', 'ObservationReceipt', 'SensorStamp', 'MeasuredConnector']
from .coordinator import VisionRuntimeCoordinator, RuntimeResult
__all__ += ['VisionRuntimeCoordinator', 'RuntimeResult']
