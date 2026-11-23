import os
import json
from unittest.mock import patch
import tempfile
import unittest
from dataclasses import replace

import cv2
import numpy as np
import test_workflow as foundation
NOW = foundation.NOW
from vision_core import GateError, State
from vision_core.archive import Archive, digest
from vision_core.photography import (PhotographySession, View, ResultIdentity, MotionResult,
                                     CaptureResult, Original, CoverageProof)
from vision_core.quality import QualityPolicy, evaluate


class PhotographyTests(unittest.TestCase):
    make = foundation.WorkflowTests.make
    evidence = foundation.WorkflowTests.evidence
    advance = foundation.WorkflowTests.advance
    def setUp(self):
        foundation.WorkflowTests.setUp(self)
        self.advance(6)
        self.engine.start('S07', 'req-S07')
        self.archive = Archive(self.tmp.name, 'session')
        self.views = (View('one', (1, 2, 3), True), View('two', (2, 3, 4)))
        self.photo = PhotographySession(self.engine, self.archive, self.views)
        self.policy = QualityPolicy(10, .2, .2, 5, 250, 16, 16, (0, 0, 16, 16))

    def tearDown(self):
        self.archive.close()
        foundation.WorkflowTests.tearDown(self)

    def identity(self, view='one'):
        return ResultIdentity(self.ctx, 'req-S07', view, NOW)

    def motion(self, view='one'):
        return MotionResult(self.identity(view), True, (0.1, 0.2), True, NOW, 'independent-state')

    def capture(self, view='one', raw=True):
        image = np.indices((32, 32)).sum(axis=0) % 2 * 180 + (30 if view == 'one' else 40)
        ok, encoded = cv2.imencode('.png', image.astype(np.uint8))
        self.assertTrue(ok)
        data = encoded.tobytes()
        originals = [Original('png', data, digest(data), view + '-image')]
        if raw:
            data = ('synthetic raw ' + view).encode()
            originals.append(Original('raw', data, digest(data), view + '-raw'))
        return CaptureResult(self.identity(view), True, True, tuple(originals), 'transfer-proof')

    def take(self):
        for view in ('one', 'two'):
            self.photo.accept_motion(self.motion(view))
            self.photo.accept_capture(self.capture(view, view == 'one'))
        self.photo.complete_capture()

    def test_full_pipeline_separate_park(self):
        self.photo.accept_motion(self.motion())
        self.photo.accept_capture(self.capture())
        self.assertEqual(self.engine.states['S07'], State.RUNNING)
        self.photo.accept_motion(self.motion('two'))
        self.photo.accept_capture(self.capture('two', False))
        self.photo.complete_capture()
        self.engine.start('S08', 'req-S08')
        proof = CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'spatial-proof')
        self.photo.assess(self.policy, proof)
        self.assertEqual(self.engine.states['S09'], State.PENDING)
        with self.assertRaises(GateError): self.engine.start('S10', 'req-S10')
        self.engine.start('S09', 'req-S09')
        self.engine.complete(self.evidence('S09'))
        self.engine.start('S10', 'req-S10')
        self.photo.archive_session()
        self.assertEqual(self.engine.states['S10'], State.SUCCEEDED)

    def fresh(self):
        fixture = PhotographyTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def test_invalid_motion_and_capture(self):
        identities = [lambda f: replace(f.identity(), request_id='wrong'),
                      lambda f: replace(f.identity(), view_id='wrong'),
                      lambda f: replace(f.identity(), context=replace(f.ctx, session_id='other')),
                      lambda f: replace(f.identity(), context=replace(f.ctx, profile_revisions={**f.ctx.profile_revisions, 'capture': 'wrong'})),
                      lambda f: replace(f.identity(), context=replace(f.ctx, scene_revision='wrong')),
                      lambda f: replace(f.identity(), context=replace(f.ctx, frame_id='wrong')),
                      lambda f: replace(f.identity(), timestamp=NOW-11),
                      lambda f: None]
        variants = [lambda f: replace(f.motion(), identity=identity(f)) for identity in identities]
        variants += [lambda f: replace(f.motion(), terminal_success=False),
                     lambda f: replace(f.motion(), goal_verified=False),
                     lambda f: replace(f.motion(), measured_state=())]
        for variant in variants:
            with self.subTest(variant=variant):
                f = self.fresh()
                with self.assertRaises(GateError): f.photo.accept_motion(variant(f))
                self.assertEqual(f.engine.states['S08'], State.BLOCKED)
                self.assertEqual(list(f.archive.path.iterdir()), [])
        for identity in identities:
            with self.subTest(capture_identity=identity):
                f = self.fresh()
                f.photo.accept_motion(f.motion())
                with self.assertRaises(GateError): f.photo.accept_capture(replace(f.capture(), identity=identity(f)))
                self.assertEqual(f.engine.states['S08'], State.BLOCKED)
                self.assertEqual(list(f.archive.path.iterdir()), [])

    def test_capture_before_actual_state(self):
        self.engine.clock = lambda: NOW + 2
        self.photo.accept_motion(replace(self.motion(), state_timestamp=NOW + 1))
        with self.assertRaises(GateError): self.photo.accept_capture(self.capture())
        self.assertEqual(self.engine.states['S08'], State.BLOCKED)
        self.assertEqual(list(self.archive.path.iterdir()), [])

    def test_stopped_or_invalidated_s07_rejects_results(self):
        for state in (State.CANCELLED, State.TIMED_OUT, State.FAILED, State.BLOCKED):
            for action in ('motion', 'capture'):
                with self.subTest(state=state, action=action):
                    f = self.fresh()
                    if action == 'capture': f.photo.accept_motion(f.motion())
                    if state == State.BLOCKED: f.engine.invalidate('synthetic invalidation')
                    else: f.engine.stop('S07', state, 'synthetic stop')
                    with self.assertRaises(GateError):
                        getattr(f.photo, 'accept_' + action)(getattr(f, action)())
                    self.assertEqual(list(f.archive.path.iterdir()), [])
                    self.assertEqual(f.engine.states['S08'], State.BLOCKED)
                    self.assertEqual(f.engine.states['S09'], State.BLOCKED)

    def test_scene_change_after_motion_and_restart(self):
        self.photo.accept_motion(self.motion())
        self.engine.update_context(replace(self.ctx, scene_revision='changed'))
        with self.assertRaises(GateError): self.photo.accept_capture(self.capture())
        self.assertEqual(list(self.archive.path.iterdir()), [])
        self.assertEqual(self.engine.states['S09'], State.BLOCKED)
        f = self.fresh()
        f.photo.accept_motion(f.motion())
        before = sum(e.kind == 'dispatch' for e in f.journal.replay('session'))
        replay = f.make()
        self.assertEqual(replay.states['S07'], State.BLOCKED)
        self.assertEqual(replay.states['S09'], State.BLOCKED)
        with self.assertRaises(GateError): PhotographySession(replay, f.archive, f.views)
        with self.assertRaises(GateError): replay.start('S07', 'again')
        with self.assertRaises(GateError): replay.start('S09', 'park')
        self.assertEqual(before, sum(e.kind == 'dispatch' for e in f.journal.replay('session')))
        self.assertEqual(list(f.archive.path.iterdir()), [])

    def test_view_orientation_record_and_legacy_constructor(self):
        legacy = View('legacy', (1, 2, 3), False)
        self.assertIsNone(legacy.orientation_xyzw)
        oriented = replace(self.views[0], orientation_xyzw=(0, 0, 0, 1))
        self.photo = PhotographySession(self.engine, self.archive, (oriented, self.views[1]))
        self.photo.accept_motion(self.motion())
        self.photo.accept_capture(self.capture())
        self.assertEqual(self.photo.records[0]['orientation_xyzw'], (0, 0, 0, 1))

    def test_invalid_view_orientation_rejected(self):
        with self.assertRaises(GateError):
            PhotographySession(self.engine, self.archive, (replace(self.views[0], orientation_xyzw=(0, 0, 0, 2)),))

    def test_ack_only_blocks(self):
        self.photo.accept_motion(self.motion())
        with self.assertRaises(GateError): self.photo.accept_capture(replace(self.capture(), transfer_complete=False))
        self.assertEqual(self.engine.states['S08'], State.BLOCKED)

    def test_missing_raw_blocks(self):
        self.photo.accept_motion(self.motion())
        with self.assertRaises(GateError): self.photo.accept_capture(self.capture(raw=False))

    def test_coverage_required(self):
        self.take()
        self.engine.start('S08', 'req-S08')
        with self.assertRaises(GateError):
            self.photo.assess(self.policy, CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, False, 'x'))
        self.assertEqual(self.engine.states['S09'], State.BLOCKED)

    def test_mutation_detected(self):
        self.take()
        os.chmod(self.archive.path / 'one.png', 0o600)
        (self.archive.path / 'one.png').write_bytes(b'mutated')
        self.engine.start('S08', 'req-S08')
        with self.assertRaises(GateError):
            self.photo.assess(self.policy, CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof'))

    def test_archive_no_overwrite_and_symlink(self):
        self.archive.write('file.jpg', b'first')
        with self.assertRaises(FileExistsError): self.archive.write('file.jpg', b'second')
        with self.assertRaises(ValueError): self.archive.write('../bad', b'x')
        os.symlink('file.jpg', self.archive.path / 'link')
        with self.assertRaises(OSError): self.archive.verify('link', digest(b'first'))
        self.archive.verify('file.jpg', digest(b'first'))

    def test_capture_original_validation(self):
        for variant in ('hash', 'source', 'no_image', 'partial', 'ack', 'duplicate'):
            with self.subTest(variant=variant):
                f = self.fresh()
                f.photo.accept_motion(f.motion())
                capture = f.capture()
                image, raw = capture.originals
                if variant == 'hash': capture = replace(capture, originals=(replace(image, sha256='bad'), raw))
                if variant == 'source': capture = replace(capture, originals=(image, replace(raw, source_id=image.source_id)))
                if variant == 'no_image': capture = replace(capture, originals=(raw,))
                if variant == 'partial': capture = replace(capture, transfer_complete=False)
                if variant == 'ack': capture = replace(capture, shutter_ack=False)
                if variant == 'duplicate': capture = replace(capture, originals=(image, image, raw))
                with self.assertRaises(GateError): f.photo.accept_capture(capture)
                self.assertEqual(f.engine.states['S08'], State.BLOCKED)
                self.assertEqual(list(f.archive.path.iterdir()), [])

    def test_coverage_identity_variants(self):
        for variant in ('session', 'profile', 'scene', 'frame', 'request', 'views', 'stale', 'unverified'):
            with self.subTest(variant=variant):
                f = self.fresh(); f.take(); f.engine.start('S08', 'req-S08')
                proof = CoverageProof(f.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof')
                if variant == 'session': proof = replace(proof, context=replace(f.ctx, session_id='other'))
                if variant == 'profile': proof = replace(proof, context=replace(f.ctx, profile_revisions={**f.ctx.profile_revisions, 'capture': 'wrong'}))
                if variant == 'scene': proof = replace(proof, context=replace(f.ctx, scene_revision='other'))
                if variant == 'frame': proof = replace(proof, context=replace(f.ctx, frame_id='other'))
                if variant == 'request': proof = replace(proof, request_id='wrong')
                if variant == 'views': proof = replace(proof, view_ids=frozenset({'one', 'extra'}))
                if variant == 'stale': proof = replace(proof, timestamp=NOW-11)
                if variant == 'unverified': proof = replace(proof, verified=False)
                with self.assertRaises(GateError): f.photo.assess(f.policy, proof)
                self.assertEqual(f.engine.states['S09'], State.BLOCKED)

    def test_real_formats_and_corrupt_magic(self):
        image = (np.indices((32, 32)).sum(axis=0) % 2 * 180 + 30).astype(np.uint8)
        for extension in ('.png', '.jpg'):
            data = cv2.imencode(extension, image)[1].tobytes()
            self.assertGreater(evaluate(data, self.policy)['focus'], 10)
        for data in (b'\xff\xd8\xffbad', b'\x89PNG\r\n\x1a\nbad'):
            with self.assertRaises(ValueError): evaluate(data, self.policy)
            f = self.fresh(); f.photo.accept_motion(f.motion())
            kind = 'jpeg' if data.startswith(b'\xff') else 'png'
            cap = f.capture(); raw = cap.originals[1]
            f.photo.accept_capture(replace(cap, originals=(Original(kind, data, digest(data), 'corrupt'), raw)))
            f.photo.accept_motion(f.motion('two')); f.photo.accept_capture(f.capture('two', False)); f.photo.complete_capture()
            f.engine.start('S08', 'req-S08')
            with self.assertRaises(GateError): f.photo.assess(f.policy, CoverageProof(f.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof'))
            self.assertEqual(f.engine.states['S09'], State.BLOCKED)

    def test_manifest_snapshot_and_integrity(self):
        captures = [self.capture(), self.capture('two', False)]
        for view, capture in zip(('one', 'two'), captures):
            self.photo.accept_motion(self.motion(view)); self.photo.accept_capture(capture)
        self.photo.complete_capture(); self.engine.start('S08', 'req-S08')
        self.photo.assess(self.policy, CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof'))
        self.engine.start('S09', 'req-S09'); self.engine.complete(self.evidence('S09')); self.engine.start('S10', 'req-S10')
        self.photo.archive_session()
        manifest = json.loads(self.archive._read('manifest-v1.json'))
        self.assertEqual(manifest['status'], 'prepared')
        for record, capture in zip(manifest['views'], captures):
            for entry, original in zip(record['files'], capture.originals):
                self.assertEqual(entry['sha256'], digest(original.data))
                self.assertEqual(self.archive._read(entry['name']), original.data)
        self.assertFalse(any(e['kind'] == 'archive_verified' for e in manifest['events']))
        events = self.journal.replay('session')
        self.assertTrue(any(e.kind == 'archive_verified' for e in events))
        self.assertTrue(any(e.step_id == 'S10' and e.kind == 'transition' and e.data['to'] == 'SUCCEEDED' for e in events))

    def test_archive_failure_before_manifest(self):
        self.take(); self.engine.start('S08', 'req-S08')
        self.photo.assess(self.policy, CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof'))
        self.engine.start('S09', 'req-S09'); self.engine.complete(self.evidence('S09')); self.engine.start('S10', 'req-S10')
        os.chmod(self.archive.path / 'one.raw', 0o600)
        (self.archive.path / 'one.raw').write_bytes(b'corrupt')
        os.chmod(self.archive.path / 'one.raw', 0o400)
        with self.assertRaises(GateError): self.photo.archive_session()
        self.assertEqual(self.engine.states['S10'], State.FAILED)
        self.assertFalse((self.archive.path / 'manifest-v1.json').exists())

    def test_existing_manifest_blocks_s10(self):
        self.take(); self.engine.start('S08', 'req-S08')
        self.photo.assess(self.policy, CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof'))
        self.engine.start('S09', 'req-S09'); self.engine.complete(self.evidence('S09')); self.engine.start('S10', 'req-S10')
        self.archive.write('manifest-v1.json', b'existing')
        with self.assertRaises(GateError): self.photo.archive_session()
        self.assertEqual(self.engine.states['S10'], State.FAILED)
        self.assertEqual(self.archive._read('manifest-v1.json'), b'existing')

    def test_jpeg_capture_preserves_original(self):
        image = (np.indices((32, 32)).sum(axis=0) % 2 * 180 + 30).astype(np.uint8)
        data = cv2.imencode('.jpg', image)[1].tobytes()
        capture = self.capture()
        capture = replace(capture, originals=(Original('jpeg', data, digest(data), 'jpeg-source'), capture.originals[1]))
        self.photo.accept_motion(self.motion()); self.photo.accept_capture(capture)
        self.assertEqual(self.archive._read('one.jpg'), data)
        self.photo.accept_motion(self.motion('two')); self.photo.accept_capture(self.capture('two', False)); self.photo.complete_capture()
        self.engine.start('S08', 'req-S08')
        self.photo.assess(self.policy, CoverageProof(self.ctx, 'req-S08', frozenset({'one', 'two'}), NOW, True, 'proof'))
        self.assertEqual(digest(self.archive._read('one.jpg')), digest(data))

    def test_blur_fails_focus_policy(self):
        image = cv2.imencode('.png', np.full((32, 32), 128, dtype=np.uint8))[1].tobytes()
        with self.assertRaises(ValueError): evaluate(image, self.policy)

    def test_archive_publication_and_readers(self):
        with patch('vision_core.archive.os.link', wraps=os.link) as link:
            self.archive.write('original.png', b'bytes')
            link.assert_called_once()
        self.assertEqual((self.archive.path / 'original.png').stat().st_mode & 0o777, 0o400)
        for name in ('../escape', 'a/other', '..'):
            with self.assertRaises(ValueError): self.archive._read(name)
        os.symlink('original.png', self.archive.path / 'symlink')
        with self.assertRaises(OSError): self.archive._read('symlink')
        with self.assertRaises(FileExistsError): self.archive.write('original.png', b'new')
        self.assertEqual(self.archive._read('original.png'), b'bytes')

    def test_raw_capability_and_alternative_profiles(self):
        f = self.fresh()
        f.engine.profiles['capture'] = replace(f.engine.profiles['capture'], capabilities=frozenset({'basic'}))
        with self.assertRaises(GateError): PhotographySession(f.engine, f.archive, f.views)
        self.assertEqual(f.engine.states['S08'], State.BLOCKED)
        f = self.fresh()
        f.engine.profiles['capture'] = replace(f.engine.profiles['capture'], identifier='changed')
        with self.assertRaises(GateError): f.take()
        for i in range(2):
            f = PhotographyTests('runTest')
            foundation.WorkflowTests.setUp(f)
            f.profiles['capture'] = replace(f.profiles['capture'], identifier='mock' + str(i))
            f.engine = f.make()
            f.advance(6)
            f.engine.start('S07', 'req-S07')
            f.archive = Archive(f.tmp.name, 'session')
            f.views = (View('one', (1, 2, 3), True), View('two', (2, 3, 4)))
            f.photo = PhotographySession(f.engine, f.archive, f.views)
            self.addCleanup(f.tearDown)
            f.take()
            self.assertEqual(f.engine.states['S07'], State.SUCCEEDED)

    def test_late_and_repeated_capture_rejected(self):
        self.photo.accept_motion(self.motion()); self.photo.accept_capture(self.capture())
        with self.assertRaises(GateError): self.photo.accept_capture(self.capture())
        self.assertEqual(self.engine.states['S08'], State.BLOCKED)
        f = self.fresh(); f.take()
        with self.assertRaises(GateError): f.photo.accept_motion(f.motion())
        with self.assertRaises(GateError): f.photo.accept_capture(f.capture())

    def test_quality_failures(self):
        for data in (b'\xff\xd8\xffbad', cv2.imencode('.png', np.zeros((32, 32), dtype=np.uint8))[1].tobytes(),
                     cv2.imencode('.png', np.full((32, 32), 255, dtype=np.uint8))[1].tobytes()):
            with self.assertRaises(ValueError): evaluate(data, self.policy)
