"""Independent RED-before-fix cases for ROS2 collector synchronization and ownership.

All inputs are synthetic ROS-message-shaped objects, no middleware or devices.
"""
import copy
import unittest
from unittest.mock import patch

from test_vision_runtime_ros2 import AdapterTests, header, tf
from vision_runtime.ros2_bridge import SnapshotCollector, TopicBindings


class CollectorFinalAudit(unittest.TestCase):
    def fixture(self):
        t=AdapterTests('test_valid')
        t.setUp()
        return t

    def collector(self, t):
        c=SnapshotCollector(TopicBindings('/rgb','/depth','/rgb_info','/depth_info',0),capacity=4)
        for name,msg in zip(('rgb','depth','rgb_info','depth_info'), t.args):
            c.inject(name,copy.deepcopy(msg))
        return c

    def snapshot(self,c):
        return c.snapshot(
            scene_frame='scene',depth_unit='mm',now=100,max_age=2,max_skew=.1,
            tf_lookup=lambda target,source,stamp: tf(target,source))

    def test_new_rgb_wrong_frame_does_not_discard_valid_older_rgb(self):
        t=self.fixture()
        c=self.collector(t)
        changed=copy.deepcopy(t.args[0])
        changed.header=header('different_rgb',100)
        c.inject('rgb',changed)
        result=self.snapshot(c)
        self.assertEqual(result.rgb.stamp.frame_id,'rgb')
        self.assertEqual(result.rgb.data,bytes(range(12)))

    def test_invalid_newest_depth_falls_back_to_old_valid_depth(self):
        t=self.fixture()
        c=self.collector(t)
        bad=copy.deepcopy(t.args[1])
        bad.data=bytes(len(bad.data))
        c.inject('depth',bad)
        result=self.snapshot(c)
        self.assertEqual(result.depth.data,bytes(t.args[1].data))

    def test_buffer_owns_image_bytes_and_metadata_after_ingress(self):
        t=self.fixture()
        c=self.collector(t)
        original=bytes(t.args[0].data)
        incoming=copy.deepcopy(t.args[0])
        c.inject('rgb',incoming)
        incoming.data=b'\xff'*1024
        incoming.header.frame_id='not_rgb'
        incoming.header.stamp.sec=200
        # Validate ingress ownership directly: old (still queued) mutable objects
        # must not be stored by reference.
        queued=c._buffers['rgb'][-1][0]
        self.assertEqual(queued.data,original)
        self.assertEqual(queued.header.frame_id,'rgb')
        result=self.snapshot(c)
        self.assertEqual(result.rgb.data,original)
        self.assertEqual(result.rgb.stamp.frame_id,'rgb')

    def test_retained_budget_cannot_be_bypassed_by_post_ingress_mutation(self):
        t=self.fixture()
        c=SnapshotCollector(TopicBindings('/rgb','/depth','/rgb_info','/depth_info',0),capacity=2)
        incoming=copy.deepcopy(t.args[0])
        with patch('vision_runtime.ros2_bridge.MAX_RETAINED_BYTES', 24):
            c.inject('rgb',incoming)
            incoming.data=b'x'*4096
            c.inject('rgb', copy.deepcopy(t.args[0]))
            # Both retained images were 12 bytes on ingress; ownership must
            # preserve that bound after the external message was mutated.
            self.assertLessEqual(c._retained_bytes,24)
            self.assertTrue(all(len(getattr(msg,'data',b''))<=12
                                for msg, *_ in c._buffers['rgb']))

    def test_camera_info_owned_after_ingress(self):
        t=self.fixture()
        c=SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0),capacity=1)
        original=copy.deepcopy(t.args[2])
        c.inject('rgb_info',original)
        original.k[0]=0.0
        stored=c._buffers['rgb_info'][-1][0]
        self.assertEqual(stored.k[0],2.0)
        self.assertEqual(stored.header.frame_id,'rgb')


if __name__=='__main__':
    unittest.main()
