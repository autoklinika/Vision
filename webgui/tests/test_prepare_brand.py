"""Standard-library tests; synthetic pixels only, no private original needed."""
import base64
import importlib.util
import json
import hashlib
import struct
import zlib
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_brand', ROOT / 'scripts' / 'prepare-brand.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
GIF = base64.b64decode(json.loads((ROOT / 'tests/fixtures/brand.json').read_text())['intro'])


class PreparationTests(unittest.TestCase):
    def test_only_loop_application_is_removed(self):
        loop = b'\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00'
        comment = b'\x21\xfe\x0bNETSCAPE2.0\x00'
        other_app = b'\x21\xff\x0bOTHERAPP1.0\x03\x01\x00\x00\x00'
        source = GIF[:-1] + comment + other_app + loop + GIF[-1:]
        self.assertEqual(prepare.strip_loop(source), GIF[:-1] + comment + other_app + GIF[-1:])
        self.assertEqual(prepare.strip_loop(GIF), GIF)

    def test_truncation_rejected(self):
        with self.assertRaises((ValueError, IndexError)):
            prepare.strip_loop(GIF[:-2])

    def test_canonical_png_reproducible(self):
        pixels = bytes(range(24))
        first = prepare.canonical_png(4, 2, pixels)
        self.assertEqual(first, prepare.canonical_png(4, 2, pixels))
        length = struct.unpack('>I', first[33:37])[0]
        self.assertEqual(zlib.decompress(first[41:41 + length]), b'\0' + pixels[:12] + b'\0' + pixels[12:])
        self.assertEqual(hashlib.sha256(first).hexdigest(), 'b6584210aa7efee3c267338bbc6087a5bde5dfe04de37ec1809e620606f1bccb')

    def test_derivatives_reject_substitution(self):
        with self.assertRaisesRegex(ValueError, 'trusted reference'):
            prepare.verify_derivatives(GIF, prepare.canonical_png(1, 1, b'\0\0\0'))

    def test_wrong_original_invalidates_previous_preparation(self):
        (ROOT / 'test-results').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'test-results') as temporary:
            prepare.DEST = Path(temporary) / 'local-brand'
            prepare.DEST.mkdir()
            (prepare.DEST / 'manifest.json').write_text('stale')
            source = Path(temporary) / 'fixture.gif'
            source.write_bytes(GIF)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                prepare.prepare(source)
            self.assertEqual(list(prepare.DEST.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
