"""API-03 reads use an already-owned, committed library without side effects."""
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from vision_modules.ecu_library_backend import ECULibraryService
from vision_modules.ecu_library_backend.read_model import LibraryReadModel, SECTION_ROWS
from vision_modules.ecu_library_backend.storage import DraftReadUnavailable, _snapshot_hash
from vision_modules.ecu_profiles.models import Connector


def files(root):
    return {str(p.relative_to(root)): (p.stat().st_mode, p.stat().st_mtime_ns,
                hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_file()}


class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ECULibraryService(Path(self.temp.name) / 'private')

    def create(self, key='draft', revision='r1', name='Example ECU'):
        return self.service.create_draft('ETC3', 'provisional_3connector', 'v1',
                                         key, revision, name)


class CommittedLibraryReadTests(LibraryFixture):
    def test_empty_store_read_never_creates_lock_or_files(self):
        before = files(self.service.store.root)
        self.assertFalse((self.service.store.root / '.lock').exists())
        for _ in range(2):
            self.assertEqual(self.service.store.read_snapshot(), ())
        self.assertEqual(files(self.service.store.root), before)
        self.assertFalse((self.service.store.root / '.lock').exists())

    def test_committed_read_is_immutable_and_does_not_use_mutators(self):
        draft = self.create()
        before = files(self.service.store.root)
        with (patch.object(self.service.store, 'transaction', side_effect=AssertionError('write transaction')),
             patch.object(self.service.store, '_write', side_effect=AssertionError('write')),
             patch.object(self.service, 'ingest_reference_image', side_effect=AssertionError('asset'))):
            view = self.service.store.read_snapshot()
        self.assertEqual(files(self.service.store.root), before)
        self.assertEqual(view[0].etag, draft['etag'])
        self.assertEqual(view[0].history[-1].etag, view[0].etag)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            view[0].key = 'changed'
        with self.assertRaises(TypeError):
            view[0].profile.data['metadata']['display_name'] = 'changed'

    def test_old_snapshot_and_revision_history_remain_correlated(self):
        original = self.create()
        old = self.service.store.read_snapshot()
        modified = copy.deepcopy(original['profile'])
        modified['metadata']['display_name'] = 'Changed'
        second = self.service.update_draft('draft', modified, original['etag'])
        changed = self.service.store.read_snapshot()[0]
        self.assertEqual(changed.etag, second['etag'])
        self.assertEqual(len(changed.history), 2)
        self.assertEqual(changed.history[0].etag, original['etag'])
        self.assertEqual(changed.history[-1].etag, second['etag'])
        self.assertEqual(old[0].profile.data['metadata']['display_name'], 'Example ECU')
        reverted = self.service.update_draft('draft', original['profile'], second['etag'])
        self.assertNotEqual(reverted['etag'], original['etag'])
        self.assertEqual(self.service.store.read_snapshot()[0].etag, reverted['etag'])

    def test_missing_lock_with_committed_draft_fails_without_repair(self):
        self.create()
        (self.service.store.root / '.lock').unlink()
        before = files(self.service.store.root)
        with self.assertRaises(DraftReadUnavailable) as error:
            self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_INCONSISTENT')
        self.assertEqual(files(self.service.store.root), before)

    def test_different_owner_write_lock_has_bounded_read_wait(self):
        self.create()
        other = ECULibraryService(self.service.store.root)
        held = threading.Event()
        release = threading.Event()

        def writer():
            with other.store.transaction():
                held.set()
                release.wait(2)

        thread = threading.Thread(target=writer)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(release.set)
        self.assertTrue(held.wait(1))
        with patch('vision_modules.ecu_library_backend.storage.READ_LOCK_TIMEOUT', 0.02):
            with self.assertRaises(DraftReadUnavailable) as error:
                self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_BUSY')
        release.set()
        thread.join(1)
        self.assertEqual(len(self.service.store.read_snapshot()), 1)

    def test_reentrant_owner_mutation_cannot_expose_partial_state(self):
        self.create()
        with self.service.store.transaction():
            with self.assertRaises(DraftReadUnavailable) as error:
                self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_BUSY')

    def test_aggregate_byte_budget_fails_whole_read_without_writes(self):
        self.create()
        before = files(self.service.store.root)
        with patch('vision_modules.ecu_library_backend.storage.MAX_READ_BYTES', 100):
            with self.assertRaises(DraftReadUnavailable) as error:
                self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_LIMIT_EXCEEDED')
        self.assertEqual(files(self.service.store.root), before)

    def test_profile_count_limit_checked_before_profile_reads(self):
        self.create()
        self.create('second', 'r2')
        with (patch('vision_modules.ecu_library_backend.storage.MAX_READ_PROFILES', 1),
             patch.object(self.service.store, '_chain', side_effect=AssertionError('must not read history'))):
            with self.assertRaises(DraftReadUnavailable) as error:
                self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_LIMIT_EXCEEDED')

    def test_missing_history_is_unavailable_and_does_not_repair(self):
        self.create()
        next((self.service.store.root / 'history').glob('*.json')).unlink()
        before = files(self.service.store.root)
        with self.assertRaises(DraftReadUnavailable) as error:
            self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_UNAVAILABLE')
        self.assertNotIn(str(self.service.store.root), str(error.exception))
        self.assertEqual(files(self.service.store.root), before)

    def test_symlinked_lock_is_not_opened(self):
        self.create()
        lock = self.service.store.root / '.lock'
        lock.unlink()
        outside = Path(self.temp.name) / 'outside'
        outside.write_bytes(b'private content')
        lock.symlink_to(outside)
        with self.assertRaises(DraftReadUnavailable) as error:
            self.service.store.read_snapshot()
        self.assertEqual(error.exception.reason, 'LIBRARY_UNAVAILABLE')
        self.assertEqual(outside.read_bytes(), b'private content')

    def test_recomputed_history_hash_does_not_admit_changed_identity_or_approval(self):
        original = self.create()
        changed = copy.deepcopy(original['profile'])
        changed['metadata']['display_name'] = 'Second'
        self.service.update_draft('draft', changed, original['etag'])
        first_id = self.service.store.read_snapshot()[0].history[0].snapshot_id
        path = self.service.store.root / 'history' / ('draft--' + first_id + '.json')
        raw = path.read_bytes()
        for key, value in (('family_id', 'another'), ('status', 'APPROVED')):
            with self.subTest(key=key):
                wrapper = json.loads(raw)
                wrapper['profile']['metadata'][key] = value
                canonical = json.dumps(wrapper['profile'], sort_keys=True,
                    separators=(',', ':'), ensure_ascii=True).encode('ascii')
                wrapper['sha256'] = hashlib.sha256(canonical).hexdigest()
                del wrapper['snapshot_sha256']
                wrapper['snapshot_sha256'] = _snapshot_hash(wrapper)
                path.write_text(json.dumps(wrapper))
                before = files(self.service.store.root)
                with self.assertRaises(DraftReadUnavailable) as error:
                    self.service.store.read_snapshot()
                self.assertEqual(error.exception.reason, 'LIBRARY_INCONSISTENT')
                self.assertEqual(files(self.service.store.root), before)
        path.write_bytes(raw)


class ClosedLibraryProjectionTests(LibraryFixture):
    def model(self):
        return LibraryReadModel(self.service)

    def populated(self):
        draft = self.create()
        document = copy.deepcopy(draft['profile'])
        document['physical_states'] = [{'state_id': 'closed', 'display_name': 'Closed',
            'geometry_id': None, 'required_recipe_ids': ['inspect'],
            'verified': True, 'source_id': 'synthetic_source'}]
        document['inspection_workflows']['recipes'] = [{'recipe_id': 'inspect',
            'state_id': 'closed', 'scenario_ref': 'inspection', 'required_view_ids': [],
            'required_modules': [], 'required_capabilities': [], 'quality_policy_refs': [],
            'required_asset_ids': ['synthetic_image'], 'approval_scope': 'verify_identity'}]
        document['provenance_release']['measurement_sources'] = [{
            'source_id': 'synthetic_source', 'date': '2026-01-01', 'status': 'VERIFIED',
            'instrument': '/private/synthetic-instrument', 'datum': 'test-only',
            'uncertainty_mm': 0.1, 'reference': 'private-source-secret'}]
        document['reference_assets']['asset_manifest_revision'] = 'synthetic_manifest'
        document['reference_assets']['assets'] = [{'asset_id': 'synthetic_image',
            'kind': 'photo', 'relative_path': 'private/reference-secret.png',
            'sha256': 'a' * 64, 'bytes': 100, 'mime': 'image/png',
            'physical_state_id': 'closed', 'source_id': 'synthetic_source',
            'verified': True, 'privacy_class': 'private'}]
        document['provenance_release']['asset_hashes'] = [
            {'asset_id': 'synthetic_image', 'sha256': 'a' * 64}]
        return self.service.update_draft('draft', document, draft['etag'])

    def test_injected_existing_backend_and_empty_snapshot_do_not_initialize(self):
        before = files(self.service.store.root)
        with patch('vision_modules.ecu_library_backend.service.DraftStore',
                   side_effect=AssertionError('must not initialize')):
            snapshot = self.model().capture()
        self.assertEqual(len(snapshot.catalog), 1)
        self.assertEqual(snapshot.profiles, ())
        self.assertEqual(files(self.service.store.root), before)
        self.assertFalse((self.service.store.root / '.lock').exists())
        with self.assertRaises(ValueError):
            LibraryReadModel(self.service.store.root)

    def test_catalog_is_an_unready_declaration_with_unverified_field_notes(self):
        item = self.model().capture().catalog[0]
        self.assertEqual(item.summary.profile_id, 'etc3_poc')
        self.assertEqual(item.summary.reason_code, 'CATALOG_ONLY')
        self.assertEqual(item.summary.readiness, 'NOT_READY')
        self.assertEqual([row.color for row in item.connectors], ['black', 'black', 'gray'])
        self.assertFalse(item.envelope_present)
        self.assertEqual(item.field_note_count, 2)
        self.assertFalse(item.field_notes_verified)
        self.assertNotIn('reported_height_mm', json.dumps(dataclasses.asdict(item)))

    def test_populated_draft_has_exact_fifteen_structural_sections_and_no_runtime_claim(self):
        draft = self.populated()
        before = files(self.service.store.root)
        with (patch.object(self.service, 'validate_profile', side_effect=AssertionError('readiness')),
              patch.object(self.service, 'read_reference_image', side_effect=AssertionError('asset read')),
              patch('vision_modules.ecu_reference.assets.AssetStore.verify_asset',
                    side_effect=AssertionError('asset verification'))):
            snapshot = self.model().capture()
        detail = snapshot.profiles[0]
        self.assertEqual(detail.summary.etag, draft['etag'])
        self.assertEqual(detail.summary.status, 'DRAFT')
        self.assertEqual(detail.summary.readiness, 'NOT_READY')
        self.assertEqual(detail.summary.reason_code, 'UNSIGNED_DRAFT')
        self.assertEqual(tuple(section.name for section in detail.sections), tuple(name for name, _ in SECTION_ROWS))
        self.assertEqual(len(detail.sections), 15)
        self.assertEqual({section.status for section in detail.sections}, {'NOT_EVALUATED'})
        counts = {section.name: section.row_count for section in detail.sections}
        self.assertEqual(counts['reference_assets'], 1)
        self.assertEqual(counts['provenance_release'], 2)
        self.assertIsNone(counts['metadata'])
        self.assertIsNone(counts['identity'])
        self.assertTrue(detail.physical_states[0].declared_verified)
        self.assertEqual(detail.workflows[0].scope, 'verify_identity')
        self.assertEqual(detail.workflows[0].state_id, detail.physical_states[0].state_id)
        serialized = json.dumps(dataclasses.asdict(snapshot))
        for private in ('reference-secret', 'private-source-secret', 'synthetic-instrument',
                        'relative_path', 'sha256', 'instrument', 'content_sha256'):
            self.assertNotIn(private, serialized)
        self.assertEqual(files(self.service.store.root), before)

    def test_view_is_stable_without_mutation_and_changes_after_content_revert(self):
        original = self.create()
        one = self.model().capture()
        two = self.model().capture()
        self.assertEqual(one.view_id, two.view_id)
        self.assertRegex(one.view_id, r'^[a-f0-9]{64}$')
        changed = copy.deepcopy(original['profile'])
        # A non-exported field still changes the committed generation and view.
        changed['identity']['aliases'] = ['private-alias']
        updated = self.service.update_draft('draft', changed, original['etag'])
        three = self.model().capture()
        self.assertNotEqual(one.view_id, three.view_id)
        self.service.update_draft('draft', original['profile'], updated['etag'])
        four = self.model().capture()
        self.assertNotEqual(one.view_id, four.view_id)
        self.assertEqual(len(four.profiles[0].history), 3)
        self.assertEqual(len(one.profiles[0].history), 1)

    def test_invalid_or_path_like_display_names_fail_whole_view(self):
        draft = self.create()
        for label in ('X' * 161, '/private/secret', 'C:\\private\\secret', 'hidden\u202ename'):
            with self.subTest(label=label):
                changed = copy.deepcopy(draft['profile'])
                changed['metadata']['display_name'] = label
                draft = self.service.update_draft('draft', changed, draft['etag'])
                with self.assertRaises(DraftReadUnavailable) as error:
                    self.model().capture()
                self.assertEqual(error.exception.reason, 'LIBRARY_INCONSISTENT')

    def test_catalog_count_limit_checked_before_record_materialization(self):
        with (patch('vision_modules.ecu_library_backend.read_model.MAX_CATALOG_RECORDS', 0),
              patch.object(self.service.catalog, 'list_records',
                           side_effect=AssertionError('must not materialize'))):
            with self.assertRaises(DraftReadUnavailable) as error:
                self.model().capture()
        self.assertEqual(error.exception.reason, 'LIBRARY_LIMIT_EXCEEDED')

    def test_catalog_connector_limit_fails_whole_view(self):
        record = self.service.catalog.list_records()[0]
        self.service.catalog.register(dataclasses.replace(record,
            revision='v2', connectors=tuple(Connector('connector_' + str(i), 'black', None, False)
                                            for i in range(65))))
        with self.assertRaises(DraftReadUnavailable) as error:
            self.model().capture()
        self.assertEqual(error.exception.reason, 'LIBRARY_LIMIT_EXCEEDED')

    def test_state_and_workflow_limits_fail_whole_view(self):
        self.populated()
        for constant in ('MAX_STATE_ROWS', 'MAX_WORKFLOW_ROWS'):
            with self.subTest(constant=constant), patch(
                    'vision_modules.ecu_library_backend.read_model.' + constant, 0):
                with self.assertRaises(DraftReadUnavailable) as error:
                    self.model().capture()
                self.assertEqual(error.exception.reason, 'LIBRARY_LIMIT_EXCEEDED')

    def test_changed_catalog_during_capture_rejects_mixed_snapshot(self):
        record = self.service.catalog.list_records()[0]
        real_capture = self.service.store.read_snapshot

        def append_and_read():
            self.service.catalog.register(dataclasses.replace(record, revision='v2'))
            return real_capture()

        with patch.object(self.service.store, 'read_snapshot', side_effect=append_and_read):
            with self.assertRaises(DraftReadUnavailable) as error:
                self.model().capture()
        self.assertEqual(error.exception.reason, 'LIBRARY_BUSY')


if __name__ == '__main__':
    unittest.main()
