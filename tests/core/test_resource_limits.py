import os
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from vision_core.archive import Archive
from vision_core.models import GateError
from vision_core.quality import QualityPolicy, evaluate
from vision_core.repeatability import _areas, _rect, coverage_proof


class ResourceLimits(unittest.TestCase):
    def setUp(self):
        self.policy = QualityPolicy(0, 1, 1, 0, 255, 1, 1, max_encoded_bytes=1024 * 1024, max_pixels=10000)

    def test_real_images_and_byte_limit(self):
        image = np.zeros((20, 30, 3), dtype=np.uint8)
        for extension in ('.png', '.jpg'):
            ok, encoded = cv2.imencode(extension, image)
            self.assertTrue(ok)
            self.assertEqual(evaluate(encoded.tobytes(), self.policy)['width'], 30)
            with patch('cv2.imdecode') as decode:
                with self.assertRaises(ValueError):
                    evaluate(encoded.tobytes(), QualityPolicy(0, 1, 1, 0, 255, 1, 1, max_encoded_bytes=1))
                decode.assert_not_called()

    def test_bomb_and_malformed_headers_never_decode(self):
        png = b'\x89PNG\r\n\x1a\n' + b'\0\0\0\rIHDR' + (100000).to_bytes(4, 'big') * 2 + bytes(9)
        jpeg = bytes.fromhex('ffd8 ffc0 000b 08 ffff ffff 01 011100')
        for data in (png, jpeg, b'\xff\xd8\xff\xc0\x00', b'unknown'):
            with self.subTest(data=data), patch('cv2.imdecode') as decode:
                with self.assertRaises(ValueError):
                    evaluate(data, self.policy)
                decode.assert_not_called()
        self.assertGreaterEqual(QualityPolicy(0, 1, 1, 0, 255, 1, 1).max_pixels, 24_000_000)

    def test_archive_limits_before_write_and_read(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Archive(root, 'session', max_bytes=4, max_manifest_bytes=2)
            try:
                with self.assertRaises(ValueError):
                    archive.write('large.raw', b'12345')
                with self.assertRaises(ValueError):
                    archive.manifest({'x': 1})
                self.assertEqual(os.listdir(archive.path), [])
                archive.write('ok.raw', b'1234')
                with open(archive.path / 'external.raw', 'wb') as f:
                    f.write(b'12345')
                os.chmod(archive.path / 'external.raw', 0o400)
                with self.assertRaises(ValueError):
                    archive._read('external.raw')
            finally:
                archive.close()

    def test_coverage_geometry_and_grid_limits(self):
        for rect in ((0, 0, 0, 1), (0, 0, -1, 1), (0, 0, float('nan'), 1), (1e10, 0, 1, 1), (1, 1, 1e-100, 1)):
            with self.subTest(rect=rect), self.assertRaises(GateError):
                _rect(rect)
        regions = [_rect((-2, -2, 4, 4)), _rect((0, 0, 2, 2))]
        footprints = [_rect((-2, -2, 2, 4)), _rect((-2, -2, 1, 1))]
        total, covered = _areas(regions, footprints)
        self.assertEqual((total, covered), (16, 8))
        rectangles = [_rect((i * 2, i * 2, 1, 1)) for i in range(100)]
        with self.assertRaises(GateError):
            _areas(rectangles, [_rect((i * 2 + .5, i * 2 + .5, 1, 1)) for i in range(100)])

    def test_invalid_footprint_collection_rejected_early(self):
        from types import SimpleNamespace
        for footprints in (None, 'bad', [None] * 129):
            with self.assertRaises(GateError):
                coverage_proof(None, SimpleNamespace(footprints=footprints), '', None, None, None, None, 0, 1)


if __name__ == '__main__':
    unittest.main()
