"""Collector regression tests using synthetic messages only."""
import copy
import sys
import types
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

from test_vision_runtime_ros2 import AdapterTests, tf
from vision_runtime.ros2_bridge import SnapshotCollector, TopicBindings


class CollectorC3Tests(unittest.TestCase):
    def setUp(self):
        fixture = AdapterTests('test_valid')
        fixture.setUp()
        self.messages = fixture.args[:4]
        self.collector = SnapshotCollector(TopicBindings('/r', '/d', '/ri', '/di', 0))
        for name, message in zip(('rgb', 'depth', 'rgb_info', 'depth_info'), self.messages):
            self.collector.inject(name, message)

    def snapshot(self, lookup=None):
        return self.collector.snapshot(scene_frame='scene', depth_unit='mm', now=100,
                                       max_age=1, max_skew=.1,
                                       tf_lookup=lookup or (lambda target, source, stamp: tf(target, source)))

    def test_mismatched_tf_fails_closed(self):
        with self.assertRaises(ValueError):
            self.snapshot(lambda target, source, stamp: tf('wrong', source))

    def test_no_matching_calibration_fails_closed(self):
        self.collector._buffers['rgb_info'].clear()
        message = copy.deepcopy(self.messages[2]); message.header.frame_id = 'other'
        self.collector.inject('rgb_info', message)
        with self.assertRaises(ValueError): self.snapshot()

    def test_all_invalid_depth_fails_closed(self):
        c = SnapshotCollector(self.collector.bindings, capacity=1)
        for name, message in zip(('rgb', 'depth', 'rgb_info', 'depth_info'), self.messages):
            message = copy.deepcopy(message)
            if name == 'depth': message.data = bytes(len(message.data))
            c.inject(name, message)
        self.collector = c
        with self.assertRaises(ValueError): self.snapshot()

    def test_mutable_bytearray_is_copied(self):
        message = copy.deepcopy(self.messages[0]); message.data = bytearray(message.data)
        self.collector.inject('rgb', message); message.data[0] = 255
        self.assertEqual(self.snapshot().rgb.data[0], 0)

    def test_nested_snapshots_are_frozen(self):
        stored = self.collector._buffers['rgb'][-1][0]
        with self.assertRaises(FrozenInstanceError): stored.header.stamp.sec = 0
        with self.assertRaises(FrozenInstanceError): stored.header.frame_id = 'other'

    def test_camera_info_nested_fields_are_owned(self):
        message = copy.deepcopy(self.messages[2]); self.collector.inject('rgb_info', message)
        message.r[0] = 99; message.p[0] = 99; message.roi.x_offset = 7
        result = self.snapshot().rgb_info
        self.assertEqual((result.r[0], result.p[0], result.roi[0]), (1, 2, 0))

    def test_invalid_new_calibration_falls_back(self):
        message = copy.deepcopy(self.messages[2]); message.k[0] = 0
        self.collector.inject('rgb_info', message)
        self.assertEqual(self.snapshot().rgb_info.k[0], 2)

    def test_unset_domain_defaults_to_zero(self):
        modules = {name: types.ModuleType(name) for name in ('rclpy', 'tf2_ros', 'sensor_msgs', 'sensor_msgs.msg')}
        modules['sensor_msgs.msg'].Image = type('Image', (), {})
        modules['sensor_msgs.msg'].CameraInfo = type('CameraInfo', (), {})
        node = SimpleNamespace(create_subscription=lambda *args: args)
        with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
            self.assertEqual(len(SnapshotCollector.from_node(node, self.collector.bindings, qos=1)._subscriptions), 4)
            with self.assertRaises(ValueError):
                SnapshotCollector.from_node(node, TopicBindings('/r', '/d', '/ri', '/di', 1), qos=1)
