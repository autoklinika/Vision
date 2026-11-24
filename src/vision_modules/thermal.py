"""Offline thermal inspection; normalization is asserted by a trusted adapter."""
from dataclasses import dataclass, asdict
import hashlib
import json
import math
import re
import struct

from vision_core.archive import Archive, digest
from vision_core.extensions import ModuleReceipt, ModuleSpec, ScenarioSpec, StageSpec
from vision_core.models import Context, Evidence, GateError, State
from vision_core.profiles import Profile, validate_profiles
from vision_core.workflow import STAGES, CHECKS

CAPTURE = 'THERMAL_CAPTURE'
QA = 'THERMAL_QA'
MODULE = ModuleSpec('thermal-inspection', '1', 'thermal', {'thermal.frame'}, True,
                    (CAPTURE, QA), (CAPTURE, QA), archive_required=True)
CAPTURE_CHECKS = frozenset({'transfer', 'integrity', 'context', 'calibration'})
QA_CHECKS = frozenset({'capture_integrity', 'quality', 'policy'})
MAX_PIXELS = 2_000_000
MAX_BYTES = 32 * 1024 * 1024
MODES = ('relative_u16_le', 'radiometric_f32_kelvin_le')


def make_thermal_scenario():
    stages = []
    for i, name in enumerate(STAGES):
        deps = [] if not i else [STAGES[i-1]]
        if name == 'S09':
            stages.extend((StageSpec(CAPTURE, ('S08',), CAPTURE_CHECKS, MODULE.module_id),
                           StageSpec(QA, (CAPTURE,), QA_CHECKS, MODULE.module_id)))
            deps.append(QA)
        stages.append(StageSpec(name, tuple(deps), CHECKS[name]))
    return ScenarioSpec('thermal-inspection', '1', tuple(stages), (MODULE.module_id,))


@dataclass(frozen=True)
class ThermalProfile(Profile):
    frame_id: str = ''
    mode: str = ''
    calibration_reference: str = ''
    measurement_calibration: str = ''


@dataclass(frozen=True)
class ThermalFrame:
    context: Context
    request_id: str
    timestamp: float
    scene_frame: str
    frame_id: str
    plan_hash: str
    mode: str
    width: int
    height: int
    native_original: bytes
    thermal_map: bytes
    native_sha256: str
    map_sha256: str
    source_id: str
    sensor_provenance: str
    shutter_ack: bool
    transfer_complete: bool
    calibration_reference: str
    emissivity: float | None = None
    reflected_temperature_k: float | None = None


@dataclass(frozen=True)
class ThermalQualityPolicy:
    revision: str
    min_width: int
    min_height: int
    max_saturation_fraction: float
    max_invalid_fraction: float
    min_dynamic_range: float | None = None
    min_kelvin: float | None = None
    max_kelvin: float | None = None


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _identifier(value):
    return isinstance(value, str) and 1 <= len(value) <= 128 and all(33 <= ord(c) <= 126 for c in value)


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


class ThermalInspectionSession:
    def __init__(self, workflow, archive: Archive):
        self.workflow, self.archive = workflow, archive
        if archive.path.name != workflow.context.session_id:
            raise GateError('archive session mismatch')
        if workflow.modules.get(MODULE.module_id) != MODULE:
            raise GateError('thermal module not selected')

    def _fail(self, stage, exc):
        if self.workflow.states.get(stage) == State.RUNNING:
            self.workflow.stop(stage, State.FAILED, 'thermal validation failed: ' + str(exc))
        raise GateError(str(exc)) from exc

    def _profile(self):
        w = self.workflow
        p = w.profiles.get('thermal')
        if (not isinstance(p, ThermalProfile) or p.kind != 'thermal' or not p.approved
                or p.mode not in MODES or not _identifier(p.frame_id) or not _identifier(p.calibration_reference)
                or (p.measurement_calibration != '' and not _identifier(p.measurement_calibration))
                or p.calibration_reference not in p.calibration_dependencies
                or 'thermal.frame' not in p.capabilities
                or validate_profiles(w.profiles, w.calibrations, w.requirements, extra_kinds=w.extra_kinds)
                or w._context_errors(w.context)):
            raise GateError('invalid thermal profile or calibration')
        if p.mode == MODES[1] and ('thermal.radiometric' not in p.capabilities
                or not p.measurement_calibration or p.measurement_calibration == p.calibration_reference
                or p.measurement_calibration not in p.calibration_dependencies):
            raise GateError('radiometric capability and measurement calibration required')
        return p

    def _receipt(self, stage, timestamp, payload, reference, checks):
        w = self.workflow
        r = ModuleReceipt(w.context.session_id, stage, w.requests[stage], MODULE.module_id,
                          MODULE.version, w.profiles['thermal'].revision, w.context, timestamp,
                          digest(payload), reference, True)
        w.verify_module_receipt(r, payload)
        w.complete(Evidence(w.context.session_id, stage, w.requests[stage], w.context, timestamp,
                            True, True, checks, reference))

    def accept_frame(self, frame: ThermalFrame):
        w = self.workflow
        try:
            if w.states.get(CAPTURE) != State.RUNNING:
                raise GateError('capture stage not running')
            p = self._profile()
            if not isinstance(frame, ThermalFrame): raise GateError('typed frame required')
            now = w.clock()
            if (frame.context != w.context or frame.context != w.snapshots[CAPTURE]
                or frame.request_id != w.requests[CAPTURE] or not _identifier(frame.scene_frame)
                or not _identifier(frame.frame_id) or frame.scene_frame != w.context.frame_id
                or frame.frame_id != p.frame_id or frame.mode != p.mode
                or not _sha(frame.plan_hash) or frame.plan_hash != w.accepted_plan_hash
                or not _number(frame.timestamp) or not _number(now)
                or not 0 <= now - frame.timestamp <= w.max_age
                or frame.timestamp < w.dispatch_times[CAPTURE]
                or frame.timestamp < w.context.observation_timestamp
                or frame.calibration_reference != p.calibration_reference
                or frame.shutter_ack is not True or frame.transfer_complete is not True
                or not isinstance(frame.source_id, str) or not frame.source_id.strip()
                or not isinstance(frame.sensor_provenance, str) or not frame.sensor_provenance.strip()):
                raise GateError('frame identity, timing, calibration or transfer mismatch')
            if (type(frame.width) is not int or type(frame.height) is not int or frame.width < 1 or frame.height < 1
                or frame.width * frame.height > MAX_PIXELS or not isinstance(frame.native_original, bytes)
                or not 0 < len(frame.native_original) <= MAX_BYTES or not isinstance(frame.thermal_map, bytes)
                or len(frame.thermal_map) != frame.width * frame.height * (2 if p.mode == MODES[0] else 4)
                or len(frame.thermal_map) > MAX_BYTES or not _sha(frame.native_sha256) or not _sha(frame.map_sha256)
                or digest(frame.native_original) != frame.native_sha256 or digest(frame.thermal_map) != frame.map_sha256):
                raise GateError('invalid frame size or digest')
            if p.mode == MODES[1]:
                if (not _number(frame.emissivity) or not 0 < frame.emissivity <= 1
                    or not _number(frame.reflected_temperature_k) or not 0 < frame.reflected_temperature_k <= 5000):
                    raise GateError('invalid radiometric metadata')
            elif frame.emissivity is not None or frame.reflected_temperature_k is not None:
                raise GateError('relative frame cannot declare radiometric metadata')
            history = w.journal.replay(w.context.session_id)
            if any(e.kind == 'module_verified' and e.step_id == CAPTURE for e in history):
                raise GateError('duplicate capture')
            native = 'thermal-native-' + frame.native_sha256 + '.bin'
            mapping = 'thermal-map-' + frame.map_sha256 + '.bin'
            document = {'schema': 'thermal-capture-v1', 'context': frame.context.to_dict(),
                        'request_id': frame.request_id, 'timestamp': frame.timestamp, 'scene_frame': frame.scene_frame,
                        'frame_id': frame.frame_id, 'plan_hash': frame.plan_hash, 'mode': frame.mode,
                        'width': frame.width, 'height': frame.height, 'native_file': native,
                        'native_sha256': frame.native_sha256, 'map_file': mapping, 'map_sha256': frame.map_sha256,
                        'source_id': frame.source_id, 'sensor_provenance': frame.sensor_provenance,
                        'calibration_reference': frame.calibration_reference,
                        'calibration_revision': p.calibration_dependencies[p.calibration_reference],
                        'measurement_calibration': p.measurement_calibration,
                        'measurement_calibration_revision': p.calibration_dependencies.get(p.measurement_calibration),
                        'emissivity': frame.emissivity, 'reflected_temperature_k': frame.reflected_temperature_k,
                        'shutter_ack': True, 'transfer_complete': True,
                        'archive_entries': [{'name': native, 'sha256': frame.native_sha256},
                                            {'name': mapping, 'sha256': frame.map_sha256}]}
            payload = _json(document)
            self.archive.write(native, frame.native_original); self.archive.write(mapping, frame.thermal_map)
            self.archive.verify(native, frame.native_sha256); self.archive.verify(mapping, frame.map_sha256)
            ref = 'thermal-capture-' + digest(payload) + '.json'
            self.archive.write(ref, payload); self.archive.verify(ref, digest(payload))
            self._receipt(CAPTURE, frame.timestamp, payload, ref, CAPTURE_CHECKS)
            return ref
        except Exception as exc:
            self._fail(CAPTURE, exc)

    def assess(self, policy: ThermalQualityPolicy):
        w = self.workflow
        try:
            if w.states.get(QA) != State.RUNNING or w.states.get(CAPTURE) != State.SUCCEEDED:
                raise GateError('successful capture and running QA required')
            p = self._profile()
            if (not isinstance(policy, ThermalQualityPolicy) or not isinstance(policy.revision, str) or not policy.revision.strip()
                or type(policy.min_width) is not int or type(policy.min_height) is not int
                or not 1 <= policy.min_width <= MAX_PIXELS or not 1 <= policy.min_height <= MAX_PIXELS
                or not _number(policy.max_saturation_fraction) or not 0 <= policy.max_saturation_fraction < 0.5
                or not _number(policy.max_invalid_fraction) or not 0 <= policy.max_invalid_fraction < 0.5):
                raise GateError('invalid quality policy')
            if p.mode == MODES[0]:
                if not _number(policy.min_dynamic_range) or not 0 < policy.min_dynamic_range <= 65535 or policy.min_kelvin is not None or policy.max_kelvin is not None:
                    raise GateError('relative policy requires dynamic range')
            elif (policy.min_dynamic_range is not None or not _number(policy.min_kelvin) or not _number(policy.max_kelvin)
                  or not 0 < policy.min_kelvin < policy.max_kelvin <= 5000):
                raise GateError('radiometric policy requires Kelvin bounds')
            events = [e for e in w.journal.replay(w.context.session_id) if e.kind == 'module_verified' and e.step_id == CAPTURE]
            if len(events) != 1: raise GateError('capture receipt missing')
            ref = events[0].data['reference']; capture_sha = events[0].data['payload_sha256']
            self.archive.verify(ref, capture_sha)
            capture = json.loads(self.archive._read(ref))
            self.archive.verify(capture['native_file'], capture['native_sha256'])
            self.archive.verify(capture['map_file'], capture['map_sha256'])
            data = self.archive._read(capture['map_file'])
            if capture['width'] < policy.min_width or capture['height'] < policy.min_height:
                raise GateError('thermal map too small')
            values = [x[0] for x in struct.iter_unpack('<H' if p.mode == MODES[0] else '<f', data)]
            valid = [v for v in values if _number(v) and (p.mode == MODES[0] or 0 < v <= 5000)]
            invalid = 1 - len(valid) / len(values)
            if not valid or invalid > policy.max_invalid_fraction: raise GateError('invalid pixels')
            if p.mode == MODES[0]:
                saturation = sum(v in (0, 65535) for v in valid) / len(values)
                unsaturated = [v for v in valid if 0 < v < 65535]
                if len(unsaturated) < 2 or max(unsaturated) - min(unsaturated) < policy.min_dynamic_range: raise GateError('insufficient dynamic range')
            else:
                saturation = sum(v < policy.min_kelvin or v > policy.max_kelvin for v in valid) / len(values)
            if saturation > policy.max_saturation_fraction: raise GateError('saturation or range exceeded')
            now = w.clock()
            report = {'schema': 'thermal-qa-v1', 'capture_reference': ref, 'capture_sha256': capture_sha,
                      'native_sha256': capture['native_sha256'], 'map_sha256': capture['map_sha256'],
                      'source_id': capture['source_id'], 'sensor_provenance': capture['sensor_provenance'],
                      'calibration_reference': capture['calibration_reference'], 'calibration_revision': capture['calibration_revision'],
                      'measurement_calibration': capture['measurement_calibration'],
                      'measurement_calibration_revision': capture['measurement_calibration_revision'], 'emissivity': capture['emissivity'],
                      'reflected_temperature_k': capture['reflected_temperature_k'], 'mode': p.mode,
                      'policy': asdict(policy), 'min': min(valid), 'max': max(valid), 'mean': sum(valid)/len(valid),
                      'invalid_fraction': invalid, 'saturation_fraction': saturation,
                      'interpretation': 'relative intensity' if p.mode == MODES[0] else 'adapter asserted Kelvin; physical accuracy unproven',
                      'archive_entries': [{'name': ref, 'sha256': capture_sha},
                                          {'name': capture['native_file'], 'sha256': capture['native_sha256']},
                                          {'name': capture['map_file'], 'sha256': capture['map_sha256']}] }
            payload = _json(report); name = 'thermal-qa-' + digest(payload) + '.json'
            self.archive.write(name, payload); self.archive.verify(name, digest(payload))
            self._receipt(QA, now, payload, name, QA_CHECKS)
            return name
        except Exception as exc:
            self._fail(QA, exc)
