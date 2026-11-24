import json
import struct
import unittest
from dataclasses import replace

import test_extensions
from vision_core import GateError, State
from vision_core.archive import digest
from vision_core.extensions import ModuleRegistry
from vision_core.workflow import STAGES
NOW = 1000
from vision_modules.thermal import (MODULE, CAPTURE, QA, ThermalProfile, ThermalFrame,
    ThermalQualityPolicy, ThermalInspectionSession, make_thermal_scenario)


class ThermalTests(unittest.TestCase):
    def make(self, scenario=None, ps=None):
        from vision_core.workflow import Workflow
        return Workflow(self.j, self.ctx, ps if ps is not None else self.ps,
                        getattr(self, 'calibrations', {'cal': 'v1'}), {}, 10, lambda: 1000,
                        scenario=scenario or self.scenario, registry=self.registry)
    ev = test_extensions.ThermalIntegrationTests.ev
    def through_s08(self):
        import cv2
        import numpy as np
        from vision_core.archive import Archive, digest
        from vision_core.photography import PhotographySession, ResultIdentity, MotionResult, CaptureResult, Original
        from vision_core.quality import QualityPolicy
        from vision_core.repeatability import complete_s05, photography_views, coverage_proof, SpatialCoverageEvidence, SpatialFootprint
        for stage in STAGES[:4]:
            self.w.start(stage, stage); self.w.complete(self.ev(stage))
        self.w.start('S05', 'S05'); complete_s05(self.w, self.plan)
        self.w.start('S06', 'S06'); self.w.complete(self.ev('S06', plan_hash=self.plan.digest))
        self.w.start('S07', 'S07')
        self.archive = Archive(self.tmp.name, self.ctx.session_id)
        self.addCleanup(self.archive.close)
        args = (self.ctx, self.ps, self.w.calibrations, {}, NOW, 10)
        photo = PhotographySession(self.w, self.archive, photography_views(self.plan, *args, extra_kinds=self.w.extra_kinds), self.plan)
        for i, view in enumerate(photo.views):
            identity = ResultIdentity(self.ctx, 'S07', view.view_id, NOW)
            photo.accept_motion(MotionResult(identity, True, (0.1, 0.2), True, NOW, 'motion'))
            image = (np.indices((32, 32)).sum(axis=0) % 2 * 180 + 30 + i * 10).astype(np.uint8)
            png = cv2.imencode('.png', image)[1].tobytes(); raw = ('raw-' + view.view_id).encode()
            photo.accept_capture(CaptureResult(identity, True, True, (Original('png', png, digest(png), view.view_id+'-png'), Original('raw', raw, digest(raw), view.view_id+'-raw')), 'capture'))
        photo.complete_capture(); self.w.start('S08', 'S08')
        ids = frozenset(v.view_id for v in photo.views)
        spatial = SpatialCoverageEvidence(self.ctx.session_id, self.plan.digest, 'scene', self.ctx.profile_revisions, NOW, ids, tuple(SpatialFootprint(v, (0, 0, 10, 20), True) for v in sorted(ids)), 'ecu_local', 'measured', True, photo.capture_bindings())
        proof, fraction = coverage_proof(self.plan, spatial, 'S08', *args, extra_kinds=self.w.extra_kinds)
        self.assertEqual(fraction, 1)
        photo.assess(QualityPolicy(10, .2, .2, 5, 250, 16, 16, (0, 0, 16, 16)), proof)
        return photo

    tearDown = test_extensions.ThermalIntegrationTests.tearDown
    def setUp(self):
        test_extensions.ThermalIntegrationTests.setUp(self)
        self.registry = ModuleRegistry(); self.registry.register(MODULE)
        self.scenario = make_thermal_scenario()
        self.ps['thermal'] = ThermalProfile('thermal', 'mock', '1', 'r1', True,
            {'thermal.frame'}, set(), {'cal': 'v1'}, 'thermal-frame', 'relative_u16_le', 'cal')
        self.w = self.make()
        from vision_core.repeatability import create_plan
        self.plan = create_plan(self.ctx, self.ps, {'cal': 'v1'}, {}, self.obs, 1000, 10,
                                min_coverage=.9, require_raw=True, extra_kinds=self.w.extra_kinds)

    def ready(self):
        self.photo = self.through_s08(); self.w.start(CAPTURE, CAPTURE)
        self.session = ThermalInspectionSession(self.w, self.archive)
        raw = b'synthetic native'; pixels = struct.pack('<4H', 10, 20, 30, 40)
        self.frame = ThermalFrame(self.ctx, CAPTURE, 1000, self.ctx.frame_id, 'thermal-frame',
            self.plan.digest, 'relative_u16_le', 2, 2, raw, pixels, digest(raw), digest(pixels),
            'source', 'synthetic sensor', True, True, 'cal')

    def policy(self): return ThermalQualityPolicy('p1', 2, 2, 0, 0, min_dynamic_range=10)
    def success(self):
        self.session.accept_frame(self.frame); self.w.start(QA, QA)
        return self.session.assess(self.policy())

    def test_relative_success(self):
        self.ready(); name = self.success(); report = json.loads(self.archive._read(name))
        self.assertEqual(report['mean'], 25); self.assertEqual(report['interpretation'], 'relative intensity')
        self.assertEqual(self.w.states[QA], State.SUCCEEDED)

    def radiometric(self):
        self.calibrations = {'cal': 'v1', 'temperature-cal': 'v2'}
        self.ps['thermal'] = replace(self.ps['thermal'], mode='radiometric_f32_kelvin_le',
            capabilities={'thermal.frame', 'thermal.radiometric'}, measurement_calibration='temperature-cal',
            calibration_dependencies=self.calibrations)
        self.w = self.make()
        from vision_core.repeatability import create_plan
        self.plan = create_plan(self.ctx, self.ps, self.calibrations, {}, self.obs, 1000, 10, min_coverage=.9, require_raw=True, extra_kinds=self.w.extra_kinds)

    def test_radiometric_success(self):
        self.radiometric()
        self.ready(); data = struct.pack('<4f', 290, 300, 310, 320)
        self.frame = replace(self.frame, mode='radiometric_f32_kelvin_le', thermal_map=data, map_sha256=digest(data), emissivity=.95, reflected_temperature_k=295)
        capture = self.session.accept_frame(self.frame); self.w.start(QA, QA)
        name = self.session.assess(ThermalQualityPolicy('p', 2, 2, 0, 0, min_kelvin=280, max_kelvin=330))
        for ref in (capture, name):
            doc = json.loads(self.archive._read(ref))
            self.assertEqual((doc['calibration_reference'], doc['calibration_revision']), ('cal', 'v1'))
            self.assertEqual((doc['measurement_calibration'], doc['measurement_calibration_revision']), ('temperature-cal', 'v2'))
        self.assertIn('adapter asserted', doc['interpretation'])

    def test_radiometric_requirements(self):
        for changes in ({'capabilities': {'thermal.frame'}}, {'measurement_calibration': ''}, {'measurement_calibration': 'cal'}, {'measurement_calibration': 'missing'}):
            with self.subTest(changes=changes):
                p = replace(self.ps['thermal'], mode='radiometric_f32_kelvin_le',
                            capabilities={'thermal.frame', 'thermal.radiometric'}, measurement_calibration='cal')
                self.ps['thermal'] = replace(p, **changes)
                self.w.profiles['thermal'] = self.ps['thermal']
                with self.assertRaises(GateError): ThermalInspectionSession(self.w, type('A', (), {'path': __import__('pathlib').Path(self.ctx.session_id)})())._profile()

    def test_radiometric_bad_emissivity(self):
        self.radiometric()
        self.ready(); data = struct.pack('<4f', 290, 300, 310, 320)
        frame = replace(self.frame, mode='radiometric_f32_kelvin_le', thermal_map=data, map_sha256=digest(data), emissivity=0, reflected_temperature_k=295)
        with self.assertRaises(GateError): self.session.accept_frame(frame)

    def test_forged_hash(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, map_sha256='0'*64))
        self.assertEqual(self.w.states['S09'], State.BLOCKED)
        self.assertFalse(list(self.archive.path.glob('thermal-*')))
        with self.assertRaises(GateError): self.w.start('S09', 'S09')

    def test_bad_pixel_count(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, width=3))

    def test_wrong_scene(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, context=replace(self.ctx, scene_revision='wrong')))

    def test_wrong_session(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, context=replace(self.ctx, session_id='wrong')))

    def test_wrong_frame(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, frame_id='wrong'))

    def test_stale_request(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, request_id='wrong', timestamp=999))

    def test_ack_only(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, transfer_complete=False))

    def test_duplicate(self):
        self.ready(); self.session.accept_frame(self.frame)
        with self.assertRaises(GateError): self.session.accept_frame(self.frame)

    def test_duplicate_qa(self):
        self.ready(); self.success()
        with self.assertRaises(GateError): self.session.assess(self.policy())
        self.assertEqual(self.w.states[QA], State.SUCCEEDED)
        self.assertEqual(len([e for e in self.j.replay(self.ctx.session_id)
                              if e.kind == 'module_verified' and e.step_id == QA]), 1)

    def test_measurement_calibration_approval(self):
        self.radiometric()
        self.w.calibrations['temperature-cal'] = 'wrong'
        with self.assertRaises(GateError):
            self.w.start('S01', 'S01')

    def test_integrity(self):
        self.ready(); self.session.accept_frame(self.frame); self.w.start(QA, QA)
        path = self.archive.path / ('thermal-map-' + self.frame.map_sha256 + '.bin')
        path.chmod(0o600); path.write_bytes(b'bad'); path.chmod(0o400)
        with self.assertRaises(GateError): self.session.assess(self.policy())
        self.assertEqual(self.w.states['S09'], State.BLOCKED)

    def test_bad_policy(self):
        self.ready(); self.session.accept_frame(self.frame); self.w.start(QA, QA)
        with self.assertRaises(GateError): self.session.assess(replace(self.policy(), min_dynamic_range=None))

    def test_plan_mismatch(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, plan_hash='0'*64))

    def test_manifest_untouched(self):
        self.ready(); self.archive.manifest({'existing': True}); before = self.archive._read('manifest-v1.json')
        self.success(); self.assertEqual(before, self.archive._read('manifest-v1.json'))

    def test_s09_requires_qa(self):
        self.ready(); self.session.accept_frame(self.frame)
        with self.assertRaises(GateError): self.w.start('S09', 'S09')

    def test_full(self):
        self.radiometric(); self.ready()
        data = struct.pack('<4f', 290, 300, 310, 320)
        self.frame = replace(self.frame, mode='radiometric_f32_kelvin_le', thermal_map=data, map_sha256=digest(data), emissivity=.95, reflected_temperature_k=295)
        self.session.accept_frame(self.frame)
        with self.assertRaises(GateError): self.w.start('S09', 'S09')
        self.w.start(QA, QA); self.session.assess(ThermalQualityPolicy('p', 2, 2, 0, 0, min_kelvin=280, max_kelvin=330))
        self.w.start('S09', 'S09'); self.w.complete(self.ev('S09'))
        self.w.start('S10', 'S10'); self.photo.archive_session()
        manifest = json.loads(self.archive._read('manifest-v1.json'))
        events = [e for e in manifest['events'] if e['kind'] == 'module_verified']
        self.assertEqual({e['step_id'] for e in events}, {CAPTURE, QA})
        docs = {}
        for event in events:
            data = event['data']; self.archive.verify(data['reference'], data['payload_sha256'])
            docs[event['step_id']] = json.loads(self.archive._read(data['reference']))
        capture, report = docs[CAPTURE], docs[QA]
        self.assertEqual(report['capture_sha256'], digest(self.archive._read(report['capture_reference'])))
        self.assertEqual(report['capture_reference'], next(e['data']['reference'] for e in events if e['step_id'] == CAPTURE))
        for kind in ('native', 'map'):
            self.archive.verify(capture[kind + '_file'], capture[kind + '_sha256'])
            self.assertEqual(report[kind + '_sha256'], capture[kind + '_sha256'])
        self.assertEqual(capture['calibration_revision'], 'v1')
        self.assertEqual((capture['measurement_calibration'], capture['measurement_calibration_revision']), ('temperature-cal', 'v2'))
        self.assertEqual(report['measurement_calibration_revision'], 'v2')
        self.w.start('S11', 'S11'); self.w.complete(self.ev('S11'))
        self.assertTrue(all(x == State.SUCCEEDED for x in self.make().states.values()))


def _capture_failure(changes):
    def test(self):
        self.ready()
        with self.assertRaises(GateError): self.session.accept_frame(replace(self.frame, **changes))
        self.assertEqual(self.w.states[CAPTURE], State.FAILED)
        with self.assertRaises(GateError): self.w.start('S09', 'S09')
        self.assertFalse(any(e.step_id == 'S09' and e.kind == 'started' for e in self.j.replay(self.ctx.session_id)))
    return test

for _name, _changes in {
    'wrong_calibration': {'calibration_reference': 'wrong'},
    'invalid_source': {'source_id': '  '},
    'invalid_native_sha': {'native_sha256': '0' * 64},
}.items():
    setattr(ThermalTests, 'test_' + _name, _capture_failure(_changes))


def _quality_failure(values, policy, radiometric=False):
    def test(self):
        if radiometric: self.radiometric()
        self.ready()
        data = struct.pack('<' + str(len(values)) + ('f' if radiometric else 'H'), *values)
        changes = {'width': len(values), 'height': 1, 'thermal_map': data, 'map_sha256': digest(data)}
        if radiometric: changes.update(mode='radiometric_f32_kelvin_le', emissivity=.95, reflected_temperature_k=295)
        self.session.accept_frame(replace(self.frame, **changes)); self.w.start(QA, QA)
        with self.assertRaises(GateError): self.session.assess(policy)
        self.assertEqual(self.w.states[QA], State.FAILED)
        with self.assertRaises(GateError): self.w.start('S09', 'S09')
    return test

_relative_policy = ThermalQualityPolicy('p', 1, 1, .49, .49, min_dynamic_range=1)
_kelvin_policy = ThermalQualityPolicy('p', 1, 1, .49, .49, min_kelvin=280, max_kelvin=330)
for _name, _values, _policy, _radiometric in [
    ('flat_map', [20, 20], _relative_policy, False),
    ('saturated_map', [0, 65535], _relative_policy, False),
    ('mostly_nan', [float('nan')] * 99 + [300], _kelvin_policy, True),
    ('nonpositive_kelvin', [0, -1, 300], _kelvin_policy, True),
    ('nan_kelvin', [float('nan'), float('nan'), 300], _kelvin_policy, True),
    ('invalid_fraction_policy', [10, 20], replace(_relative_policy, max_invalid_fraction=.5), False),
    ('saturation_fraction_policy', [10, 20], replace(_relative_policy, max_saturation_fraction=.5), False),
    ('zero_dynamic_policy', [10, 20], replace(_relative_policy, min_dynamic_range=0), False),
    ('negative_dynamic_policy', [10, 20], replace(_relative_policy, min_dynamic_range=-1), False),
]:
    setattr(ThermalTests, 'test_' + _name, _quality_failure(_values, _policy, _radiometric))


def _metadata_test(field, value):
    def test(self):
        self.radiometric(); self.ready()
        data = struct.pack('<4f', 290, 300, 310, 320)
        frame = replace(self.frame, mode='radiometric_f32_kelvin_le', thermal_map=data,
                        map_sha256=digest(data), emissivity=.95, reflected_temperature_k=295)
        with self.assertRaises(GateError): self.session.accept_frame(replace(frame, **{field: value}))
        with self.assertRaises(GateError): self.w.start('S09', 'S09')
    return test
for _name, _field, _value in [('emissivity_nan', 'emissivity', float('nan')), ('emissivity_high', 'emissivity', 1.1),
                               ('reflection_zero', 'reflected_temperature_k', 0), ('reflection_nan', 'reflected_temperature_k', float('nan'))]:
    setattr(ThermalTests, 'test_' + _name, _metadata_test(_field, _value))
