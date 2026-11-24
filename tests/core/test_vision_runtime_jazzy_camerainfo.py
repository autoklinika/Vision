"""Regression: real ROS 2 Jazzy CameraInfo K/R/P are numpy.float64 arrays."""
import unittest
import numpy as np

import test_vision_runtime_ros2 as fixture
from vision_runtime.ros2_bridge import SnapshotCollector, TopicBindings


class JazzyCameraInfoCompatibility(unittest.TestCase):
    def fixture(self):
        case=fixture.AdapterTests('test_valid')
        case.setUp()
        return case

    def setUp(self):
        self.c=SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0),capacity=2)

    def test_numpy_float64_camera_info_acceptance(self):
        case=self.fixture()
        for msg in (case.args[2],case.args[3]):
            msg.k=np.array(msg.k,dtype=np.float64)
            msg.r=np.array(msg.r,dtype=np.float64)
            msg.p=np.array(msg.p,dtype=np.float64)
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),case.args):
            self.c.inject(key,msg)
        packet=self.c.snapshot(**case.kw,tf_lookup=lambda target,source,stamp: fixture.tf(target,source))
        self.assertEqual(packet.rgb_info.k[0],2.0)
        self.assertEqual(packet.depth_info.k[0],2.0)

    def test_nonfinite_numpy_calibration_rejected(self):
        case=self.fixture()
        case.args[2].k=np.array(case.args[2].k,dtype=np.float64)
        case.args[2].k[0]=np.inf
        with self.assertRaises(ValueError): self.c.inject('rgb_info',case.args[2])

    def test_bool_numpy_calibration_rejected(self):
        case=self.fixture()
        case.args[2].k=[True]+list(case.args[2].k)[1:]
        with self.assertRaises(ValueError): self.c.inject('rgb_info',case.args[2])

    def test_string_calibration_rejected(self):
        case=self.fixture()
        case.args[2].k=['2.0']+list(case.args[2].k)[1:]
        with self.assertRaises(ValueError): self.c.inject('rgb_info',case.args[2])


if __name__ == '__main__':
    unittest.main()
