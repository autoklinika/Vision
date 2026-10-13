import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/audit"))
import sony_ptp_sd_compare as check


def jpeg(metadata=b"meta", entropy=b"pixels"):
    return (b"\xff\xd8\xff\xe1" + (len(metadata) + 2).to_bytes(2, "big") + metadata
            + b"\xff\xda\x00\x02" + entropy + b"\xff\xd9")


class IntegrityTests(unittest.TestCase):
    def test_exact_file(self):
        data = jpeg()
        self.assertEqual(check.compare_jpeg_bytes(data, data)["classification"], "EXACT")

    def test_zero_padding_preserves_encoded_image_and_metadata(self):
        data = jpeg()
        r = check.compare_jpeg_bytes(data, data + bytes(9226))
        self.assertFalse(r["whole_file_equal"])
        self.assertTrue(r["encoded_through_eoi_equal"])
        self.assertEqual(r["sd_tail_bytes"], 9226)
        self.assertEqual(r["classification"], "ENCODED_IDENTICAL_ZERO_PADDING_ONLY")

    def test_nonzero_trailing_data_is_not_accepted_as_padding(self):
        data = jpeg()
        self.assertEqual(check.compare_jpeg_bytes(data, data + b"\x01")["classification"], "DIFFERENT")

    def test_metadata_difference_fails_even_if_pixels_unchanged(self):
        self.assertEqual(check.compare_jpeg_bytes(jpeg(b"AAAA"), jpeg(b"BBBB"))["classification"], "DIFFERENT")

    def test_entropy_difference_fails(self):
        self.assertEqual(check.compare_jpeg_bytes(jpeg(entropy=b"A"), jpeg(entropy=b"B"))["classification"], "DIFFERENT")

    def test_eoi_in_app_metadata_does_not_terminate_image(self):
        data = jpeg(b"\xff\xd9metadata")
        self.assertEqual(check.jpeg_end(data + bytes(10)), len(data))

    def test_stuffed_ff_and_restart_markers_are_entropy(self):
        data = jpeg(entropy=b"a\xff\x00b\xff\xd3c")
        self.assertEqual(check.jpeg_end(data), len(data))

    def test_fake_eoi_in_nonzero_tail_does_not_hide_original_end(self):
        data = jpeg()
        result = check.compare_jpeg_bytes(data, data + b"x\xff\xd9")
        self.assertEqual(result["sd_eoi_end_bytes"], len(data))
        self.assertEqual(result["classification"], "DIFFERENT")

    def test_missing_eoi_or_truncated_segment_fails(self):
        for data in (jpeg()[:-2], b"\xff\xd8\xff\xe1\x00\x20bad", b"bad"):
            with self.subTest(data=data), self.assertRaises(check.af.GateError):
                check.jpeg_end(data)


if __name__ == "__main__":
    unittest.main()
