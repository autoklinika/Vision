"""Immutable bindings supplied by a trusted inspection-planner coordinator.

These bindings authenticate no source by themselves. The coordinator validates
the calibrated preparation and MoveIt result before supplying them to Core.
"""
from dataclasses import dataclass
import math

from .models import Context, GateError


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _sha256(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _common(context, request_id, inspection_plan_hash, preparation_hash, timestamp):
    if (not isinstance(context, Context) or not _text(context.session_id)
            or not _text(context.scene_revision) or not _text(context.frame_id)
            or not context.profile_revisions
            or any(not _text(k) or not _text(v) for k, v in context.profile_revisions.items())
            or not _finite(context.observation_timestamp)
            or context.observation_timestamp < 0 or not _text(request_id)
            or not _sha256(inspection_plan_hash) or not _sha256(preparation_hash)
            or not _finite(timestamp)
            or timestamp < context.observation_timestamp):
        raise GateError('invalid preparation or planning proof')


@dataclass(frozen=True)
class PreparationProof:
    context: Context
    request_id: str
    inspection_plan_hash: str
    preparation_hash: str
    timestamp: float
    reference: str

    def __post_init__(self):
        _common(self.context, self.request_id, self.inspection_plan_hash,
                self.preparation_hash, self.timestamp)
        if self.reference != 'inspection-preparation:sha256:' + self.preparation_hash:
            raise GateError('preparation reference mismatch')


@dataclass(frozen=True)
class PlanningProof:
    context: Context
    request_id: str
    inspection_plan_hash: str
    preparation_hash: str
    motion_hash: str
    timestamp: float
    reference: str

    def __post_init__(self):
        _common(self.context, self.request_id, self.inspection_plan_hash,
                self.preparation_hash, self.timestamp)
        if (not _sha256(self.motion_hash)
                or self.reference != 'motion-plan:sha256:' + self.motion_hash):
            raise GateError('motion reference mismatch')
