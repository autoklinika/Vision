"""RGB-D offline tests: synthetic frames only; never initializes USB or robot."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

MOD = Path(__file__).resolve().parents[1] / "scripts/camera/oak"
sys.path.insert(0, str(MOD))
from camera_sync import (FramePacket, RgbdSynchronizer, bundle_metadata,
                         encode_replay_npz, decode_replay_npz)


JPEG = b"\xff\xd8" + b"synthetic-data" + b"\xff\xd9"


def packet(stream, seq, device_ms, host_ms, payload=None):
    if payload is None:
        payload = JPEG if stream == "rgb" else np.full((4, 6), 1100, dtype=np.uint16)
    return FramePacket(
        stream=stream, sequence=seq, device_ns=int(device_ms * 1e6),
        host_received_ns=int(host_ms * 1e6),
        width=6, height=4, payload=payload,
    )


class CameraSynchronizerTests(unittest.TestCase):
    def test_pair_uses_device_clock_not_host_arrival(self):
        s = RgbdSynchronizer()
        self.assertIsNone(s.ingest(packet("rgb", 101, 1000, 2000), 2000_000_000))
        pair = s.ingest(packet("depth", 7, 1011, 2070), 2070_000_000)
        self.assertIsNotNone(pair)
        self.assertEqual(pair.pairing_delta_ms, 11)
        self.assertEqual((pair.rgb.sequence, pair.depth.sequence), (101, 7))
        self.assertEqual(s.diagnostics(2070_000_000)["state"], "SYNCED")
        m = bundle_metadata(pair, now_ns=2070_000_000)
        self.assertEqual(m["schema_version"], "camera.frame_bundle.v1")
        self.assertEqual(m["depth"]["coordinate_frame"], "stereo_left_rectified_optical")
        self.assertEqual(m["rgb"]["coordinate_frame"], "rgb_optical")
        self.assertEqual(m["transform_status"]["robot_base"], "UNAVAILABLE")
        self.assertEqual(m["age_basis"], "host_receive_proxy_not_sensor_exposure")
        self.assertEqual(m["host_arrival_spread_ms"], 70)

    def test_cross_tolerance_discards_old_head(self):
        s = RgbdSynchronizer(max_delta_ms=15)
        s.ingest(packet("rgb", 1, 1000, 2000), 2000_000_000)
        s.ingest(packet("depth", 1, 1040, 2030), 2030_000_000)
        self.assertEqual(s.matched, 0)
        self.assertEqual(s.dropped["rgb"], 1)
        pair = s.ingest(packet("rgb", 2, 1041, 2040), 2040_000_000)
        self.assertIsNotNone(pair)
        self.assertEqual(pair.pair_sequence, 1)

    def test_depth_first_pair(self):
        s = RgbdSynchronizer()
        s.ingest(packet("depth", 55, 1000, 2000), 2000_000_000)
        self.assertIsNotNone(s.ingest(packet("rgb", 2, 1003, 2020), 2020_000_000))

    def test_sequence_gaps_duplicates_and_out_of_order(self):
        s = RgbdSynchronizer()
        s.ingest(packet("rgb", 2, 1000, 2000), 2000_000_000)
        s.ingest(packet("rgb", 5, 1033, 2033), 2033_000_000)
        s.ingest(packet("rgb", 5, 1066, 2066), 2066_000_000)
        s.ingest(packet("rgb", 6, 1030, 2070), 2070_000_000)
        self.assertEqual(s.lost_sequence["rgb"], 2)
        self.assertEqual(s.rejected["rgb"], 2)
        self.assertEqual(s.received["rgb"], 2)

    def test_bounded_queue_and_timeout(self):
        s = RgbdSynchronizer(capacity=2, max_pending_ms=100)
        for i in range(3):
            s.ingest(packet("rgb", i, 1000 + i * 33, 2000 + i * 25),
                     (2000 + i * 25) * 1000000)
        self.assertEqual(len(s.pending["rgb"]), 2)
        self.assertEqual(s.dropped["rgb"], 1)
        s.ingest(packet("depth", 1, 2000, 2300), 2300_000_000)
        self.assertEqual(len(s.pending["rgb"]), 0)
        self.assertGreaterEqual(s.dropped["rgb"], 3)

    def test_staleness_and_session_reset(self):
        s = RgbdSynchronizer(max_age_ms=100)
        s.ingest(packet("rgb", 1, 1000, 2000), 2000_000_000)
        s.ingest(packet("depth", 1, 1001, 2010), 2010_000_000)
        self.assertIsNotNone(s.current(2050_000_000))
        self.assertIsNone(s.current(2120_000_000))
        self.assertEqual(s.diagnostics(2120_000_000)["state"], "NOT_READY")
        old_session = s.session_id
        s.reset()
        self.assertNotEqual(s.session_id, old_session)
        self.assertIsNone(s.latest)

    def test_invalid_timestamps_and_parameters(self):
        s = RgbdSynchronizer()
        self.assertIsNone(s.ingest(packet("rgb", 0, 0, 1000), 1000_000_000))
        self.assertEqual(s.rejected["rgb"], 1)
        with self.assertRaises(ValueError):
            RgbdSynchronizer(capacity=0)

    def test_replay_lossless_without_camera(self):
        s = RgbdSynchronizer()
        raw = np.arange(24, dtype=np.uint16).reshape((4, 6))
        raw[0, 0] = 0
        s.ingest(packet("rgb", 1, 1000, 2000), 2000_000_000)
        pair = s.ingest(packet("depth", 3, 1002, 2020, raw), 2020_000_000)
        meta = bundle_metadata(pair, {"state": "READ_ONLY", "revision": "test"},
                               now_ns=2020_000_000)
        archive = encode_replay_npz(pair, meta)
        restored_meta, jpeg, depth = decode_replay_npz(archive)
        self.assertEqual(restored_meta["bundle_id"], meta["bundle_id"])
        self.assertEqual(jpeg, JPEG)
        np.testing.assert_array_equal(depth, raw)
        self.assertEqual(int(depth[0, 0]), 0)

    def test_replay_rejects_invalid_recording(self):
        with self.assertRaises(Exception):
            decode_replay_npz(b"not-npz")


if __name__ == "__main__":
    unittest.main()
