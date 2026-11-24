"""Build receipts only from independently authenticated measurements and proof."""
from dataclasses import dataclass, fields, is_dataclass
import re
import json
import hashlib
from .contracts import ObservationReceipt, ReadinessReceipt
from .ros2_messages import RGBDFramePacket, _canonical, _ref


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value): raise ValueError('SHA-256 reference required')


@dataclass(frozen=True)
class VerifiedGeometry:
    position_mm: tuple
    quaternion_xyzw: tuple
    envelope_mm: tuple
    envelope_uncertainty_mm: float
    connectors: tuple
    pcb_references: tuple
    obstacle_references: tuple
    reference: str
    frame_id: str


@dataclass(frozen=True)
class MeasurementBinding:
    packet: RGBDFramePacket
    geometry: VerifiedGeometry
    session_id: str
    request_id: str
    profile_revisions: tuple
    calibration_ids: tuple
    source: str
    source_proof: str
    scene_revision: str
    relative_calibration_id: str


def binding_reference(binding):
    """Hash every binding field, including image bytes, for retained evidence lookup."""
    def encode(value):
        if isinstance(value, bytes): return {'bytes_sha256': hashlib.sha256(value).hexdigest()}
        if is_dataclass(value): return {f.name: encode(getattr(value, f.name)) for f in fields(value)}
        if isinstance(value, (tuple, list)): return [encode(v) for v in value]
        if hasattr(value, 'items'): return {k: encode(v) for k, v in value.items()}
        return value
    return _ref(json.dumps(encode(binding), sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


@dataclass(frozen=True)
class BuildResult:
    status: str
    receipt: object = None
    reasons: tuple = ()


class SensorObservationBuilder:
    def __init__(self, verifier):
        if not callable(verifier): raise ValueError('independent verifier required')
        self.verifier = verifier

    def observation(self, packet, geometry, *, session_id, request_id, profile_revisions, calibration_ids, relative_calibration_id, scene_revision, source, source_proof):
        try:
            if not isinstance(packet, RGBDFramePacket) or not isinstance(geometry, VerifiedGeometry): raise ValueError('verified pose and feature landmarks required')
            _hash(source_proof); _hash(geometry.reference)
            for ref in (*geometry.pcb_references, *geometry.obstacle_references, *(c.reference for c in geometry.connectors)): _hash(ref)
            if not geometry.connectors or not geometry.pcb_references or not geometry.obstacle_references: raise ValueError('feature landmarks required')
            if geometry.frame_id != packet.scene_from_rgb.stamp.frame_id: raise ValueError('geometry scene frame mismatch')
            if relative_calibration_id not in calibration_ids.values(): raise ValueError('relative calibration revision not pinned')
            binding = MeasurementBinding(packet, geometry, session_id, request_id, tuple(sorted(profile_revisions.items())), tuple(sorted(calibration_ids.items())), source, source_proof, scene_revision, relative_calibration_id)
            if self.verifier('binding', binding) is not True: raise ValueError('independent binding verification failed')
            refs = [packet.rgb.stamp.reference, packet.depth.stamp.reference, packet.rgb_info.stamp.reference, packet.depth_info.stamp.reference, packet.scene_from_rgb.stamp.reference, packet.rgb_from_depth.stamp.reference, geometry.reference, source_proof]
            for ref in refs: _hash(ref)
            binding_ref = binding_reference(binding)
            receipt = ObservationReceipt(session_id, request_id, profile_revisions, calibration_ids, scene_revision, geometry.frame_id, packet.rgb.stamp, packet.depth.stamp, packet.rgb_info.stamp, packet.scene_from_rgb.stamp, packet.scene_from_rgb.source_frame, packet.depth.encoding, geometry.position_mm, geometry.quaternion_xyzw, geometry.envelope_mm, geometry.envelope_uncertainty_mm, geometry.connectors, geometry.pcb_references, geometry.obstacle_references, source, _ref(_canonical(refs)), True, packet.depth_info.stamp, packet.rgb_from_depth.stamp, packet.rgb_from_depth.source_frame, relative_calibration_id, geometry.reference, source_proof, binding_ref)
            return BuildResult('READY', receipt)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            return BuildResult('NOT_READY', reasons=(str(exc),))

    def readiness(self, *, session_id, request_id, profile_revisions, calibration_ids, timestamp, source, source_proof, device_state_reference, capabilities):
        try:
            _hash(source_proof); _hash(device_state_reference)
            if self.verifier('readiness', (source, source_proof, device_state_reference, capabilities)) is not True: raise ValueError('independent verification failed')
            if not {'rgb','depth','camera_info','tf'} <= set(capabilities): raise ValueError('missing capabilities')
            return BuildResult('READY', ReadinessReceipt(session_id, request_id, profile_revisions, calibration_ids, timestamp, source, source_proof, True, frozenset(capabilities), device_state_reference))
        except (ValueError, TypeError) as exc:
            return BuildResult('NOT_READY', reasons=(str(exc),))
