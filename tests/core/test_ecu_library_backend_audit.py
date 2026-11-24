"""Independent regression tests for durable ECU Reference DRAFT backend.

All data/images are synthetic and held only in temporary directories.
"""
import copy
import json
import struct
import unittest
from unittest.mock import patch
import zlib

import test_ecu_library_backend as base


def synthetic_large_png(width=6000, height=6000):
    """Make a valid, highly compressible 36 MP PNG without allocating 108 MB."""
    def chunk(kind, data):
        return (struct.pack('>I',len(data)) + kind + data
                + struct.pack('>I',zlib.crc32(kind+data)&0xffffffff))
    ihdr=struct.pack('>IIBBBBB',width,height,8,2,0,0,0)
    encoder=zlib.compressobj(level=6)
    row=b'\x00'+b'\x00'*(width*3)
    stream=bytearray()
    for _ in range(height):
        stream.extend(encoder.compress(row))
    stream.extend(encoder.flush())
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',ihdr)
            + chunk(b'IDAT',bytes(stream)) + chunk(b'IEND',b''))


class BackendPersistenceAudit(unittest.TestCase):
    def fixture(self):
        t=base.BackendTests('runTest')
        t.setUp()
        self.addCleanup(t.doCleanups)
        return t

    def test_nonascii_canonical_size_checked_before_persisting(self):
        t=self.fixture()
        original=t.create()
        document=copy.deepcopy(original['profile'])
        # Valid UTF-8 length <512 KiB, canonical ensure_ascii=True >512 KiB.
        document['identity']['aliases']=['ą'*3000 for _ in range(43)]
        with self.assertRaises(ValueError):
            t.service.update_draft('draft', document, original['etag'])
        self.assertEqual(t.service.get_draft('draft'),original)
        self.assertEqual(len(t.service.history('draft')),1)

    def test_failure_before_current_publish_does_not_commit_history(self):
        t=self.fixture()
        initial=t.create()
        changed=copy.deepcopy(initial['profile'])
        changed['metadata']['display_name']='not-committed'
        real_write=t.service.store._write
        def fail_current(area,*args,**kwargs):
            if area=='drafts':
                raise OSError('simulated interrupted current publication')
            return real_write(area,*args,**kwargs)
        with patch.object(t.service.store,'_write',side_effect=fail_current):
            with self.assertRaises(OSError):
                t.service.update_draft('draft',changed,initial['etag'])
        self.assertEqual(t.service.get_draft('draft'), initial)
        self.assertEqual(len(t.service.history('draft')),1)

    def test_content_revert_does_not_reuse_original_generation_etag(self):
        t=self.fixture()
        initial=t.create()
        changed=copy.deepcopy(initial['profile'])
        changed['metadata']['display_name']='Changed'
        updated=t.service.update_draft('draft',changed,initial['etag'])
        reverted=t.service.update_draft('draft',initial['profile'],updated['etag'])
        self.assertNotEqual(reverted['etag'],initial['etag'])
        with self.assertRaises(FileExistsError):
            t.service.update_draft('draft',changed,initial['etag'])

    def test_compressed_image_decoded_pixel_limit(self):
        t=self.fixture()
        png=synthetic_large_png()
        self.assertLess(len(png),8*1024*1024)
        with self.assertRaises(ValueError):
            t.service.ingest_reference_image(png)
        self.assertEqual(list((t.service.store.root/'assets').iterdir()),[])

    def test_pointer_tampering_fails_closed(self):
        t=self.fixture(); t.create()
        path=t.service.store.root/'drafts/draft.json'
        pointer=json.loads(path.read_text()); pointer['key']='other'
        path.write_text(json.dumps(pointer))
        with self.assertRaises(ValueError): t.service.get_draft('draft')
        with self.assertRaises(ValueError): t.service.history('draft')

    def test_missing_snapshot_fails_closed(self):
        t=self.fixture(); t.create()
        next((t.service.store.root/'history').iterdir()).unlink()
        with self.assertRaises(FileNotFoundError): t.service.get_draft('draft')
        with self.assertRaises(FileNotFoundError): t.service.history('draft')

    def test_snapshot_tampering_fails_closed(self):
        t=self.fixture(); t.create()
        path=next((t.service.store.root/'history').iterdir())
        snapshot=json.loads(path.read_text()); snapshot['profile']['metadata']['display_name']='tampered'
        path.write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError): t.service.get_draft('draft')

    def test_etag_survives_second_instance(self):
        t=self.fixture(); original=t.create()
        other=base.ECULibraryService(t.service.store.root)
        self.assertEqual(other.get_draft('draft'), original)
        self.assertEqual(other.history('draft')[0]['etag'], original['etag'])

    def test_chain_order_and_missing_ancestor(self):
        t=self.fixture(); first=t.create()
        document=copy.deepcopy(first['profile']); document['metadata']['display_name']='second'
        second=t.service.update_draft('draft',document,first['etag'])
        history=t.service.history('draft')
        self.assertEqual([h['etag'] for h in history], [first['etag'],second['etag']])
        (t.service.store.root/'history'/('draft--'+history[0]['snapshot_id']+'.json')).unlink()
        with self.assertRaises(FileNotFoundError): t.service.history('draft')

    def test_interrupted_create_leaves_no_visible_draft(self):
        t=self.fixture(); real=t.service.store._write
        def fail(area,*args,**kwargs):
            if area=='drafts': raise OSError('interrupted')
            return real(area,*args,**kwargs)
        with patch.object(t.service.store,'_write',side_effect=fail):
            with self.assertRaises(OSError): t.create()
        self.assertEqual(t.service.store.keys(),[])
        with self.assertRaises(FileNotFoundError): t.service.history('draft')
        created=t.create()
        self.assertEqual(len(t.service.history('draft')),1)
        self.assertEqual(t.service.get_draft('draft'),created)

    def test_oversized_canonical_create_writes_nothing(self):
        t=self.fixture()
        with self.assertRaises(ValueError):
            t.service.create_draft(*t.args[:5], 'ą'*100000)
        self.assertEqual(list((t.service.store.root/'drafts').iterdir()),[])
        self.assertEqual(list((t.service.store.root/'history').iterdir()),[])

    def test_valid_png_and_jpeg_dimensions(self):
        t=self.fixture()
        import cv2
        import numpy as np
        for extension, mime in (('.png','image/png'),('.jpg','image/jpeg')):
            ok, encoded=cv2.imencode(extension,np.zeros((24,60,3),dtype=np.uint8))
            self.assertTrue(ok)
            self.assertEqual(t.service.ingest_reference_image(encoded.tobytes())['mime'],mime)

    def test_large_valid_sony_dimensions_allowed(self):
        t=self.fixture()
        png=synthetic_large_png(6000,4000)
        self.assertEqual(t.service.ingest_reference_image(png)['mime'],'image/png')


if __name__=='__main__':
    unittest.main()

class HistoryIntegrityRegressions(unittest.TestCase):
    def fixture(self):
        t=base.BackendTests('runTest')
        t.setUp()
        self.addCleanup(t.doCleanups)
        return t

    def two_generations(self,t):
        first=t.create()
        doc=copy.deepcopy(first['profile'])
        doc['metadata']['display_name']='Second generation'
        second=t.service.update_draft('draft',doc,first['etag'])
        return first,second

    def test_missing_history_ancestor_blocks_read_and_update(self):
        t=self.fixture()
        first, second = self.two_generations(t)
        snapshots=t.service.history('draft')
        oldest=snapshots[0]['snapshot_id']
        (t.service.store.root/'history'/('draft--'+oldest+'.json')).unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            t.service.get_draft('draft')
        with self.assertRaises((ValueError, FileNotFoundError)):
            t.service.update_draft('draft',second['profile'],second['etag'])

    def test_tampered_previous_link_blocks_read_and_history(self):
        t=self.fixture()
        first, second=self.two_generations(t)
        latest=t.service.history('draft')[-1]['snapshot_id']
        path=t.service.store.root/'history'/('draft--'+latest+'.json')
        obj=json.loads(path.read_text())
        self.assertIsNotNone(obj['previous'])
        obj['previous']=None
        path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            t.service.get_draft('draft')
        with self.assertRaises(ValueError):
            t.service.history('draft')

    def test_tampered_generation_and_hash_rejected_without_writes(self):
        for field, value in (('generation', '0'*32), ('sha256', '0'*64),
                             ('snapshot_sha256', 'invalid')):
            with self.subTest(field=field):
                t=self.fixture(); first, second=self.two_generations(t)
                root=t.service.store.root
                latest=t.service.history('draft')[-1]['snapshot_id']
                path=root/'history'/('draft--'+latest+'.json')
                obj=json.loads(path.read_text()); obj[field]=value
                path.write_text(json.dumps(obj))
                before={p.name:p.read_bytes() for p in (root/'history').iterdir()}
                pointer=(root/'drafts/draft.json').read_bytes()
                other=base.ECULibraryService(root)
                for operation in (lambda: other.get_draft('draft'),
                                  lambda: other.history('draft'),
                                  lambda: other.update_draft('draft',second['profile'],second['etag'])):
                    with self.assertRaises(ValueError): operation()
                self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'history').iterdir()})
                self.assertEqual(pointer,(root/'drafts/draft.json').read_bytes())

    def test_cycle_with_recomputed_hash_is_rejected(self):
        from vision_modules.ecu_library_backend.storage import _snapshot_hash
        t=self.fixture(); first, second=self.two_generations(t)
        root=t.service.store.root
        latest=t.service.history('draft')[-1]['snapshot_id']
        path=root/'history'/('draft--'+latest+'.json')
        obj=json.loads(path.read_text()); obj['previous']=latest
        obj.pop('snapshot_sha256'); obj['snapshot_sha256']=_snapshot_hash(obj)
        path.write_text(json.dumps(obj))
        before={p.name:p.read_bytes() for p in (root/'history').iterdir()}
        other=base.ECULibraryService(root)
        with self.assertRaises(ValueError): other.get_draft('draft')
        with self.assertRaises(ValueError): other.history('draft')
        with self.assertRaises(ValueError): other.update_draft('draft',second['profile'],second['etag'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'history').iterdir()})

    def test_restart_update_and_malformed_pointer_preserves_history(self):
        t=self.fixture(); first=t.create()
        other=base.ECULibraryService(t.service.store.root)
        doc=copy.deepcopy(first['profile']); doc['metadata']['display_name']='After restart'
        second=other.update_draft('draft',doc,first['etag'])
        again=base.ECULibraryService(t.service.store.root)
        self.assertEqual(again.get_draft('draft'),second)
        self.assertEqual([h['etag'] for h in again.history('draft')],[first['etag'],second['etag']])
        root=t.service.store.root
        before={p.name:p.read_bytes() for p in (root/'history').iterdir()}
        (root/'drafts/draft.json').write_text('{')
        with self.assertRaises(ValueError): again.get_draft('draft')
        with self.assertRaises(ValueError): again.history('draft')
        with self.assertRaises(ValueError): again.update_draft('draft',doc,second['etag'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'history').iterdir()})

    def test_chain_bound_blocks_read_and_update(self):
        t=self.fixture(); first, second=self.two_generations(t)
        root=t.service.store.root
        before={p.name:p.read_bytes() for p in (root/'history').iterdir()}
        with patch('vision_modules.ecu_library_backend.storage.MAX_HISTORY_REVISIONS', 1):
            with self.assertRaises(ValueError): t.service.get_draft('draft')
            with self.assertRaises(ValueError): t.service.history('draft')
            with self.assertRaises(ValueError): t.service.update_draft('draft',second['profile'],second['etag'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'history').iterdir()})
