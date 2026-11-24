"""Offline, immutable input contracts; receipts do not authenticate themselves."""
from dataclasses import dataclass
from types import MappingProxyType
import math
from vision_modules.ecu_profiles.models import identifier, frame_identifier, text, vector


def _stamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid timestamp')
    return value


def _mapping(value):
    if not hasattr(value, 'items') or not 0 < len(value) <= 128:
        raise ValueError('invalid mapping')
    result = dict(value)
    for key, item in result.items():
        identifier(key); identifier(item)
    return MappingProxyType(result)


@dataclass(frozen=True)
class SensorStamp:
    frame_id: str
    timestamp: float
    reference: str

    def __post_init__(self):
        frame_identifier(self.frame_id); _stamp(self.timestamp); text(self.reference)


@dataclass(frozen=True)
class MeasuredConnector:
    connector_id: str
    color: str
    position_mm: tuple[float, float, float]
    uncertainty_mm: float
    reference: str

    def __post_init__(self):
        identifier(self.connector_id)
        if self.color not in ('black', 'gray', 'other'): raise ValueError('invalid color')
        object.__setattr__(self, 'position_mm', vector(self.position_mm, 3))
        if type(self.uncertainty_mm) not in (int, float) or not math.isfinite(self.uncertainty_mm) or not 0 < self.uncertainty_mm <= 1000000: raise ValueError('invalid uncertainty')
        text(self.reference)


@dataclass(frozen=True)
class ReadinessReceipt:
    session_id: str
    request_id: str
    profile_revisions: object
    calibration_ids: object
    timestamp: float
    source: str
    reference: str
    quality: bool
    capabilities: frozenset[str]
    device_state_reference: str

    def __post_init__(self):
        identifier(self.session_id); identifier(self.request_id); identifier(self.source)
        object.__setattr__(self, 'profile_revisions', _mapping(self.profile_revisions))
        object.__setattr__(self, 'calibration_ids', _mapping(self.calibration_ids))
        _stamp(self.timestamp); text(self.reference)
        if type(self.quality) is not bool: raise ValueError('invalid quality')
        object.__setattr__(self, 'capabilities', frozenset(self.capabilities))
        for capability in self.capabilities: identifier(capability)
        text(self.device_state_reference)


@dataclass(frozen=True)
class ObservationReceipt:
    session_id: str
    request_id: str
    profile_revisions: object
    calibration_ids: object
    scene_revision: str
    frame_id: str
    rgb: SensorStamp
    depth: SensorStamp
    camera_info: SensorStamp
    tf: SensorStamp
    tf_source_frame: str
    depth_encoding: str
    position_mm: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]
    envelope_mm: tuple[float, float, float]
    envelope_uncertainty_mm: float
    connectors: tuple[MeasuredConnector, ...]
    pcb_references: tuple[str, ...]
    obstacle_references: tuple[str, ...]
    source: str
    reference: str
    quality: bool
    depth_camera_info: SensorStamp | None = None
    depth_to_rgb_tf: SensorStamp | None = None
    depth_to_rgb_source_frame: str | None = None
    relative_calibration_id: str | None = None
    geometry_reference: str | None = None
    source_proof: str | None = None
    binding_reference: str | None = None

    def __post_init__(self):
        for item in (self.session_id, self.request_id, self.scene_revision, self.source): identifier(item)
        frame_identifier(self.frame_id); frame_identifier(self.tf_source_frame)
        object.__setattr__(self, 'profile_revisions', _mapping(self.profile_revisions))
        object.__setattr__(self, 'calibration_ids', _mapping(self.calibration_ids))
        for stamp in (self.rgb, self.depth, self.camera_info, self.tf):
            if not isinstance(stamp, SensorStamp): raise ValueError('typed sensor stamp required')
        if any(x is not None for x in (self.depth_camera_info, self.depth_to_rgb_tf, self.depth_to_rgb_source_frame, self.relative_calibration_id)):
            if not isinstance(self.depth_camera_info, SensorStamp) or not isinstance(self.depth_to_rgb_tf, SensorStamp): raise ValueError('relative calibration stamps required')
            frame_identifier(self.depth_to_rgb_source_frame); identifier(self.relative_calibration_id)
        for ref in (self.geometry_reference, self.source_proof, self.binding_reference):
            if ref is not None: text(ref)
        if self.depth_encoding not in ('16UC1', '32FC1'): raise ValueError('unsupported depth')
        object.__setattr__(self, 'position_mm', vector(self.position_mm, 3))
        q = vector(self.quaternion_xyzw, 4)
        if abs(math.hypot(*q) - 1) > 1e-5: raise ValueError('invalid quaternion')
        object.__setattr__(self, 'quaternion_xyzw', q)
        object.__setattr__(self, 'envelope_mm', vector(self.envelope_mm, 3, True))
        if type(self.envelope_uncertainty_mm) not in (int, float) or not math.isfinite(self.envelope_uncertainty_mm) or not 0 < self.envelope_uncertainty_mm <= 1000000: raise ValueError('invalid envelope uncertainty')
        if not isinstance(self.connectors, (tuple, list)) or not 0 < len(self.connectors) <= 128 or any(not isinstance(c, MeasuredConnector) for c in self.connectors): raise ValueError('invalid connectors')
        object.__setattr__(self, 'connectors', tuple(self.connectors))
        if len({c.connector_id for c in self.connectors}) != len(self.connectors): raise ValueError('duplicate connector')
        for name in ('pcb_references', 'obstacle_references'):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or not 0 < len(values) <= 128: raise ValueError('references required')
            for value in values: text(value)
            if len(set(values)) != len(values): raise ValueError('duplicate reference')
            object.__setattr__(self, name, tuple(values))
        text(self.reference)
        if type(self.quality) is not bool: raise ValueError('invalid quality')
