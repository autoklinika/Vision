"""General module archive proof: independent per-test and per-case fixtures."""
import json
import unittest
from dataclasses import replace
from unittest.mock import patch
from vision_core import GateError, State
from vision_core.archive import digest
import test_final_audit


class ModuleArchiveHardening(unittest.TestCase):
    def trial(self):
        trial = test_final_audit.ThermalPublicationAudit('runTest')
        trial.setUp()
        self.addCleanup(trial.tearDown)
        return trial

    def test_direct_s10_completion_requires_proofs(self):
        t = self.trial()
        t.take_good_thermal()
        with self.assertRaises(GateError):
            t.fixture.w.complete(t.fixture.ev('S10'))
        self.assertNotEqual(t.fixture.w.states['S10'], State.SUCCEEDED)

    def test_valid_archive_records_both_module_proofs(self):
        t = self.trial()
        t.take_good_thermal()
        t.photo.archive_session()
        self.assertEqual(t.fixture.w.states['S10'], State.SUCCEEDED)
        manifest = json.loads(t.fixture.archive._read('manifest-v1.json'))
        proofs = [e for e in manifest['events'] if e['kind'] == 'module_archive_verified']
        self.assertEqual({e['data']['stage_id'] for e in proofs}, {'THERMAL_CAPTURE','THERMAL_QA'})
        for proof in proofs:
            t.fixture.archive.verify(proof['data']['reference'], proof['data']['payload_sha256'])
        self.assertTrue(any(e['kind']=='module_verified' for e in manifest['events']))

    def test_missing_qa_json(self):
        t = self.trial()
        t.take_good_thermal()
        event = next(e for e in t.fixture.j.replay(t.fixture.ctx.session_id)
                     if e.kind == 'module_verified' and e.step_id == 'THERMAL_QA')
        (t.fixture.archive.path / event.data['reference']).unlink()
        with self.assertRaises(GateError): t.photo.archive_session()
        self.assertFalse((t.fixture.archive.path / 'manifest-v1.json').exists())

    def test_changed_qa_json(self):
        t = self.trial()
        t.take_good_thermal()
        event = next(e for e in t.fixture.j.replay(t.fixture.ctx.session_id)
                     if e.kind == 'module_verified' and e.step_id == 'THERMAL_QA')
        path = t.fixture.archive.path / event.data['reference']
        path.chmod(0o600)
        path.write_bytes(b'{}')
        path.chmod(0o400)
        with self.assertRaises(GateError): t.photo.archive_session()
        self.assertFalse((t.fixture.archive.path / 'manifest-v1.json').exists())

    def test_missing_or_wrong_receipt(self):
        for mutation in ('missing','wrong_request','wrong_reference'):
            with self.subTest(mutation=mutation):
                t = self.trial()
                t.take_good_thermal()
                journal = t.fixture.j
                original = journal.replay
                def replay(session):
                    result = []
                    for event in original(session):
                        if event.kind == 'module_verified' and event.step_id == 'THERMAL_QA':
                            if mutation == 'missing':
                                continue
                            event = replace(event,
                                request_id='wrong') if mutation == 'wrong_request' else replace(
                                event, data={**event.data,'reference':'missing.json'})
                        result.append(event)
                    return result
                with patch.object(journal,'replay',side_effect=replay):
                    with self.assertRaises(GateError): t.photo.archive_session()
                self.assertFalse((t.fixture.archive.path / 'manifest-v1.json').exists())

    def test_forged_or_missing_entry_list(self):
        for entries in (None, [], [{'name':'missing.bin','sha256':'0'*64}]):
            with self.subTest(entries=entries):
                t=self.trial()
                t.take_good_thermal()
                journal=t.fixture.j
                original=journal.replay
                payload=json.dumps({'archive_entries':entries}).encode()
                name='forged-'+digest(payload)+'.json'
                t.fixture.archive.write(name,payload)
                def replay(session):
                    return [replace(e,data={**e.data,'reference':name,'payload_sha256':digest(payload)})
                            if e.kind == 'module_verified' and e.step_id == 'THERMAL_QA' else e
                            for e in original(session)]
                with patch.object(journal,'replay',side_effect=replay):
                    with self.assertRaises(GateError):t.photo.archive_session()
                self.assertFalse((t.fixture.archive.path / 'manifest-v1.json').exists())

    def test_unexpected_manifest_exception_fails_s10_closed(self):
        t = self.trial()
        t.take_good_thermal()
        with patch.object(t.fixture.archive, 'manifest', side_effect=RuntimeError('synthetic manifest I/O failure')):
            with self.assertRaises(GateError):
                t.photo.archive_session()
        self.assertNotIn(t.fixture.w.states['S10'], (State.RUNNING, State.SUCCEEDED))
        with self.assertRaises(GateError):
            t.fixture.w.complete(t.fixture.ev('S10'))
        self.assertFalse((t.fixture.archive.path / 'manifest-v1.json').exists())

    def test_module_proofs_without_manifest_publication_never_complete_s10(self):
        t = self.trial()
        t.take_good_thermal()
        w = t.fixture.w
        receipts = [e for e in w.journal.replay(w.context.session_id)
                    if e.kind == 'module_verified' and e.step_id in ('THERMAL_CAPTURE','THERMAL_QA')]
        self.assertEqual(len(receipts), 2)
        for receipt in receipts:
            w._record('S10', 'module_archive_verified',
                {'stage_id': receipt.step_id,'reference':receipt.data['reference'],
                 'payload_sha256':receipt.data['payload_sha256']})
        with self.assertRaises(GateError):
            w.complete(t.fixture.ev('S10'))
        self.assertNotEqual(w.states['S10'], State.SUCCEEDED)
        self.assertFalse((t.fixture.archive.path / 'manifest-v1.json').exists())
