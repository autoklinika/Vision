import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from vision_modules.ecu_library_backend import ECULibraryService


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ECULibraryService(Path(self.temp.name) / 'private')
        self.args = ('ETC3', 'provisional_3connector', 'v1', 'draft', 'r1', 'ÉCU')

    def create(self): return self.service.create_draft(*self.args)
    def test_catalog(self):
        item = self.service.list_catalog()[0]
        self.assertEqual([x['color'] for x in item['connectors']], ['black', 'black', 'gray'])
        self.assertIsNone(item['envelope']); self.assertFalse(item['field_notes_verified'])
        self.assertEqual({x['reported_height_mm'] for x in item['field_notes']}, {65, 69})
        self.assertTrue(all(x['provenance']['datum'] is None for x in item['field_notes']))
    def test_multiple_catalog_records(self):
        source = Path(__file__).resolve().parents[2] / 'config/ecu_profiles/etc3_poc_v1.json'
        record = json.loads(source.read_text())
        record.update(family='OTHER', variant='variant', profile_id='other')
        directory = Path(self.temp.name) / 'catalog'; directory.mkdir()
        (directory / 'other.json').write_text(json.dumps(record))
        service = ECULibraryService(Path(self.temp.name) / 'second', directory)
        self.assertEqual(len(service.list_catalog()), 2)
        self.assertEqual(service.catalog_detail('OTHER', 'variant', 'v1')['record']['family'], 'OTHER')
        service.create_draft('OTHER', 'variant', 'v1', 'other_draft', 'r1', 'Other')
    def test_catalog_symlink(self):
        directory = Path(self.temp.name) / 'catalog'; directory.mkdir()
        (directory / 'bad.json').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): ECULibraryService(Path(self.temp.name) / 'second', directory)
    def test_catalog_oversize(self):
        directory = Path(self.temp.name) / 'catalog'; directory.mkdir()
        (directory / 'bad.json').write_bytes(b' ' * (512 * 1024 + 1))
        with self.assertRaises(ValueError): ECULibraryService(Path(self.temp.name) / 'second', directory)
    def test_catalog_exact(self):
        with self.assertRaises(FileNotFoundError): self.service.catalog_detail('ETC3', 'provisional_3connector', 'missing')
    def test_catalog_search(self): self.assertEqual(len(self.service.list_catalog('etc3')), 1)
    def test_catalog_search_missing(self): self.assertEqual(self.service.list_catalog('zzzzz'), [])
    def test_create_and_get(self):
        d = self.create(); self.assertEqual(d, self.service.get_draft('draft'))
    def test_nonascii(self): self.assertEqual(self.create()['profile']['metadata']['display_name'], 'ÉCU')
    def test_listing(self):
        self.create(); self.assertEqual(len(self.service.list_profiles('écu', 'DRAFT')), 1)
    def test_status_filter(self):
        self.create(); self.assertEqual(self.service.list_profiles(status='APPROVED'), [])
    def test_unknown_ecu(self):
        with self.assertRaises(FileNotFoundError): self.service.create_draft('unknown', *self.args[1:])
    def test_duplicate_id(self):
        self.create()
        with self.assertRaises(FileExistsError): self.create()
    def test_duplicate_revision(self):
        self.create()
        with self.assertRaises(FileExistsError): self.service.create_draft(*self.args[:3], 'other', 'r1', 'X')
    def test_update(self):
        d = self.create(); d['profile']['metadata']['display_name'] = 'Updated'
        updated = self.service.update_draft('draft', d['profile'], d['etag'])
        self.assertNotEqual(updated['etag'], d['etag'])
    def test_conflict(self):
        d = self.create(); d['profile']['metadata']['display_name'] = 'Updated'
        self.service.update_draft('draft', d['profile'], d['etag'])
        with self.assertRaises(FileExistsError): self.service.update_draft('draft', d['profile'], d['etag'])
    def test_missing_etag(self):
        d = self.create()
        with self.assertRaises(FileExistsError): self.service.update_draft('draft', d['profile'], None)
    def test_history_immutable(self):
        d = self.create(); d['profile']['metadata']['display_name'] = 'New'
        self.service.update_draft('draft', d['profile'], d['etag'])
        h = self.service.history('draft'); self.assertEqual(len(h), 2)
        self.assertEqual(h[0]['profile']['metadata']['display_name'], 'ÉCU')
        h[0]['profile']['metadata']['display_name'] = 'tamper'
        self.assertEqual(self.service.history('draft')[0]['profile']['metadata']['display_name'], 'ÉCU')
    def test_clone(self):
        self.create(); c = self.service.clone_draft('draft', 'clone', 'r2')
        self.assertEqual(c['profile']['metadata']['profile_revision'], 'r2')
    def test_clone_same_revision(self):
        self.create()
        with self.assertRaises(ValueError): self.service.clone_draft('draft', 'clone', 'r1')
    def test_clone_duplicate_revision(self):
        self.create(); self.service.clone_draft('draft', 'clone', 'r2')
        with self.assertRaises(FileExistsError): self.service.clone_draft('draft', 'another', 'r2')
    def test_change_family(self): self.assert_change_rejected('family_id', 'other')
    def test_change_variant(self): self.assert_change_rejected('variant_id', 'other')
    def test_change_revision(self): self.assert_change_rejected('profile_revision', 'r2')
    def test_change_key(self): self.assert_change_rejected('profile_id', 'other')
    def test_approval(self): self.assert_change_rejected('approval_scopes', [{'state_id': 'a', 'recipe_id': 'b', 'scope': 'verify_identity'}])
    def test_digest(self): self.assert_change_rejected('content_sha256', 'a' * 64)
    def test_status(self): self.assert_change_rejected('status', 'APPROVED')
    def assert_change_rejected(self, field, value):
        d = self.create(); d['profile']['metadata'][field] = value
        with self.assertRaises(ValueError): self.service.update_draft('draft', d['profile'], d['etag'])
    def test_duplicate_json_key(self):
        self.assertEqual(self.service.validate_profile('{"a":1,"a":2}', 'x', 'x', 'verify_identity')['status'], 'PARSE_ERROR')
    def test_nan(self):
        self.assertEqual(self.service.validate_profile('{"x":NaN}', 'x', 'x', 'verify_identity')['status'], 'PARSE_ERROR')
    def test_oversize(self):
        self.assertEqual(self.service.validate_profile(' ' * (512 * 1024 + 1), 'x', 'x', 'verify_identity')['status'], 'PARSE_ERROR')
    def test_readiness(self):
        result = self.service.validate_profile(self.create()['profile'], 'x', 'x', 'verify_identity')
        self.assertEqual(result['status'], 'NOT_READY'); self.assertTrue(result['blockers'])
    def test_invalid_scope(self):
        self.assertEqual(self.service.validate_profile(self.create()['profile'], 'x', 'x', 'bad')['status'], 'INPUT_ERROR')
    def test_schema(self):
        schema = self.service.section_schema(); self.assertEqual(len(schema['sections']), 15)
        self.assertTrue(next(s for s in schema['sections'] if s['name'] == 'connectors_landmarks')['field_templates']['connectors'])
        self.assertIn('verify_identity', schema['enums']['scope'])
    def test_private_modes(self):
        self.create(); root = self.service.store.root
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((root / 'drafts/draft.json').stat().st_mode & 0o777, 0o600)
    def test_unsafe_id(self):
        with self.assertRaises(ValueError): self.service.get_draft('../draft')
    def test_root_symlink(self):
        link = Path(self.temp.name) / 'link'; link.symlink_to(self.service.store.root, target_is_directory=True)
        with self.assertRaises(ValueError): ECULibraryService(link)
    def test_draft_symlink(self):
        (self.service.store.root / 'drafts/draft.json').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): self.service.get_draft('draft')
    def test_fake_image(self):
        with self.assertRaises(ValueError): self.service.ingest_reference_image(b'\x89PNG\r\n\x1a\ninvalid')
    def test_image(self):
        import cv2
        import numpy as np
        ok, encoded = cv2.imencode('.png', np.zeros((3, 3, 3), dtype=np.uint8)); self.assertTrue(ok)
        data = encoded.tobytes(); meta = self.service.ingest_reference_image(data)
        self.assertEqual(meta['sha'], hashlib.sha256(data).hexdigest()); self.assertFalse(meta['verified'])
        self.assertEqual(self.service.read_reference_image(meta['sha']), (data, 'image/png'))
    def test_image_hash_tampering(self):
        import cv2
        import numpy as np
        _, encoded = cv2.imencode('.jpg', np.zeros((3, 3, 3), dtype=np.uint8))
        meta = self.service.ingest_reference_image(encoded.tobytes())
        (self.service.store.root / 'assets' / meta['sha']).write_bytes(b'tamper')
        with self.assertRaises(ValueError): self.service.read_reference_image(meta['sha'])
    def test_invalid_hash(self):
        with self.assertRaises(ValueError): self.service.read_reference_image('../etc')
    def test_image_oversize(self):
        with self.assertRaises(ValueError): self.service.ingest_reference_image(b'x' * (8 * 1024 * 1024 + 1))
    def test_templates_unchanged(self):
        repo = Path(__file__).resolve().parents[2]
        paths = [repo / 'docs/templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json', repo / 'config/ecu_profiles/etc3_poc_v1.json']
        before = [p.read_bytes() for p in paths]
        self.create(); self.service.clone_draft('draft', 'clone', 'r2')
        self.assertEqual(before, [p.read_bytes() for p in paths])
    def test_conflict_across_instances(self):
        original = self.create()
        other = ECULibraryService(self.service.store.root)
        changed = copy.deepcopy(original['profile']); changed['metadata']['display_name'] = 'changed'
        other.update_draft('draft', changed, original['etag'])
        with self.assertRaises(FileExistsError): self.service.update_draft('draft', original['profile'], original['etag'])
    def test_repo_root_forbidden(self):
        with self.assertRaises(ValueError): ECULibraryService(Path(__file__).resolve().parents[2] / 'private')


if __name__ == '__main__': unittest.main()
