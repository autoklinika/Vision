"""Offline synthetic ROS messages; no ROS installation or devices required."""
import copy
import hashlib
import sys
import struct
import unittest
from types import SimpleNamespace as N
from vision_runtime.ros2_messages import normalize_rgbd
from vision_runtime.ros2_bridge import SnapshotCollector, TopicBindings
from vision_runtime.ros2_observation import SensorObservationBuilder, VerifiedGeometry
from vision_runtime import MeasuredConnector

H = 'sha256:' + 'a'*64

def header(frame, sec=100): return N(frame_id=frame, stamp=N(sec=sec, nanosec=0))
def img(frame, encoding, step, data): return N(header=header(frame), width=2, height=2, encoding=encoding, step=step, is_bigendian=0, data=data)
def info(frame): return N(header=header(frame), width=2, height=2, k=[2.,0.,1.,0.,2.,1.,0.,0.,1.], d=[], r=[1.,0.,0.,0.,1.,0.,0.,0.,1.], p=[2.,0.,1.,0.,0.,2.,1.,0.,0.,0.,1.,0.], distortion_model='plumb_bob', binning_x=0, binning_y=0, roi=N(x_offset=0,y_offset=0,height=0,width=0,do_rectify=False))
def tf(target, source): return N(header=header(target), child_frame_id=source, transform=N(translation=N(x=0.,y=0.,z=0.), rotation=N(x=0.,y=0.,z=0.,w=1.)))

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.args = [img('rgb','rgb8',6,bytes(range(12))), img('depth','16UC1',4,struct.pack('<4H', 1, 2, 3, 4)), info('rgb'), info('depth'), tf('scene','rgb'), tf('rgb','depth')]
        self.kw = dict(scene_frame='scene', depth_unit='mm', now=100, max_age=1, max_skew=.1)
    def packet(self): return normalize_rgbd(*self.args, **self.kw)
    def test_valid(self):
        p=self.packet(); self.assertEqual(p.depth.stamp.frame_id,'depth'); self.assertEqual(p.rgb.stamp.reference,'sha256:'+hashlib.sha256(bytes(range(12))).hexdigest())
    def test_float_depth(self):
        self.args[1]=img('depth','32FC1',8,struct.pack('<4f', 1, 2, 3, 4)); self.kw['depth_unit']='m'; self.assertEqual(self.packet().depth.encoding,'32FC1')
    def test_bgr(self): self.args[0].encoding='bgr8'; self.packet()
    def test_calibration_hash_stable(self): self.assertEqual(self.packet().rgb_info.stamp.reference,self.packet().rgb_info.stamp.reference)
    def test_tf_hash_changes(self):
        a=self.packet().rgb_from_depth.stamp.reference; self.args[5].transform.translation.x=1.; self.assertNotEqual(a,self.packet().rgb_from_depth.stamp.reference)
    def test_wrong_unit(self): self.kw['depth_unit']='m'; self.assertRaises(ValueError,self.packet)
    def test_disparity(self): self.args[1].encoding='disparity'; self.assertRaises(ValueError,self.packet)
    def test_unitless(self): self.kw['depth_unit']=None; self.assertRaises(ValueError,self.packet)
    def test_stride(self): self.args[1].step=3; self.assertRaises(ValueError,self.packet)
    def test_length(self): self.args[1].data=bytes(7); self.assertRaises(ValueError,self.packet)
    def test_huge(self): self.args[1].step=100000000; self.assertRaises(ValueError,self.packet)
    def test_bad_encoding(self): self.args[0].encoding='mono8'; self.assertRaises(ValueError,self.packet)
    def test_bad_focal(self): self.args[2].k[0]=0; self.assertRaises(ValueError,self.packet)
    def test_nan_intrinsics(self): self.args[2].k[2]=float('nan'); self.assertRaises(ValueError,self.packet)
    def test_bad_matrix(self): self.args[2].k=[1]; self.assertRaises(ValueError,self.packet)
    def test_info_frame(self): self.args[3].header.frame_id='rgb'; self.assertRaises(ValueError,self.packet)
    def test_info_size(self): self.args[3].width=3; self.assertRaises(ValueError,self.packet)
    def test_stale(self): self.kw['now']=102; self.assertRaises(ValueError,self.packet)
    def test_skew(self): self.args[3].header.stamp.nanosec=200000000; self.assertRaises(ValueError,self.packet)
    def test_future(self): self.kw['now']=99; self.assertRaises(ValueError,self.packet)
    def test_tf_target(self): self.args[5].header.frame_id='scene'; self.assertRaises(ValueError,self.packet)
    def test_tf_source(self): self.args[5].child_frame_id='rgb'; self.assertRaises(ValueError,self.packet)
    def test_tf_quaternion(self): self.args[5].transform.rotation.w=2; self.assertRaises(ValueError,self.packet)
    def test_tf_nan(self): self.args[4].transform.translation.x=float('nan'); self.assertRaises(ValueError,self.packet)
    def test_missing_tf(self): self.args[5]=None; self.assertRaises((ValueError,AttributeError),self.packet)
    def test_no_pose(self):
        result=SensorObservationBuilder(lambda *a: True).observation(self.packet(),None,session_id='s',request_id='r',profile_revisions={'x':'r'},calibration_ids={'x':'r'},relative_calibration_id='r',scene_revision='scene',source='sensor',source_proof=H); self.assertEqual(result.status,'NOT_READY')
    def test_wrong_proof(self):
        g=VerifiedGeometry((0,0,0),(0,0,0,1),(1,1,1),.1,(MeasuredConnector('a','black',(0,0,0),.1,H),),(H,),(H,),H,'scene')
        result=SensorObservationBuilder(lambda *a: False).observation(self.packet(),g,session_id='s',request_id='r',profile_revisions={'x':'r'},calibration_ids={'x':'r'},relative_calibration_id='r',scene_revision='scene',source='sensor',source_proof=H); self.assertEqual(result.status,'NOT_READY')
    def test_collector(self):
        c=SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0),capacity=1)
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),self.args): c.inject(key,msg)
        p=c.snapshot(**self.kw,tf_lookup=lambda target,source,stamp: tf(target,source)); self.assertEqual(p.depth.stamp.frame_id,'depth')
    def test_missing_stream(self):
        c=SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0)); self.assertRaises(ValueError,c.snapshot,**self.kw,tf_lookup=lambda *x:None)
    def test_no_eager_ros(self): self.assertNotIn('rclpy',sys.modules)
    def test_topics_explicit(self): self.assertRaises(ValueError,TopicBindings,'/r','/d','/ri','/di',None)

class CoordinatorIntegrationTests(unittest.TestCase):
    def test_distinct_frames_require_calibration(self):
        from test_vision_runtime_v1 import RuntimeTests
        from vision_runtime.validation import validate_observation
        from vision_runtime import SensorStamp
        fixture=RuntimeTests('test_full'); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        obs=fixture.obs(depth=SensorStamp('depth',100,H))
        kw=dict(now=100,max_age=10,max_skew=.1,sensor_frame='camera',scene_frame='station',known_transforms={('camera','station'),('depth','camera')},capabilities=fixture.caps)
        with self.assertRaises(ValueError): validate_observation(obs,fixture.ctx,fixture.cal,**kw)
        from dataclasses import replace
        obs=replace(obs,depth_camera_info=SensorStamp('depth',100,H),depth_to_rgb_tf=SensorStamp('camera',100,H),depth_to_rgb_source_frame='depth',relative_calibration_id=next(iter(fixture.cal.values())))
        validate_observation(obs,fixture.ctx,fixture.cal,**kw)
        fixture.coordinator=fixture.make(known_transforms=kw['known_transforms'])
        fixture.s03(obs)
        self.assertEqual(fixture.coordinator.verify_selected_ecu(fixture.req('S04')).status,'SUCCEEDED')

class CorrectiveTests(unittest.TestCase):
    setUp = AdapterTests.setUp
    packet = AdapterTests.packet
    def collector(self, capacity=4):
        return SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0), capacity=capacity)
    def test_depth_big_endian(self):
        self.args[1].is_bigendian=1
        self.args[1].data=struct.pack('>4H',0,0,1,0)
        self.packet()
    def test_depth_padding_ignored(self):
        self.args[1].step=6
        self.args[1].data=b'\0'*4+b'\xff\xff'+b'\0'*4+b'\xff\xff'
        with self.assertRaises(ValueError): self.packet()
    def test_depth_padding_positive(self):
        self.args[1].step=6
        self.args[1].data=b'\0\0\x01\0xx'+b'\0'*6
        self.packet()
    def test_depth_no_finite_float(self):
        self.args[1]=img('depth','32FC1',8,struct.pack('<4f',float('nan'),float('inf'),-1,0))
        self.kw['depth_unit']='m'
        with self.assertRaises(ValueError): self.packet()
    def test_depth_mixed_float(self):
        self.args[1]=img('depth','32FC1',8,struct.pack('<4f',float('nan'),float('inf'),-1,0.1))
        self.kw['depth_unit']='m'
        self.packet()
    def test_depth_short_bytes(self):
        self.args[1].data=b'\1'
        with self.assertRaises(ValueError): self.packet()
    def test_ingress_missing_timestamp(self):
        del self.args[0].header.stamp
        with self.assertRaises(ValueError): self.collector().inject('rgb',self.args[0])
    def test_ingress_wrong_message(self):
        with self.assertRaises(ValueError): self.collector().inject('rgb',self.args[2])
    def test_ingress_capacity(self):
        c=self.collector(2)
        for _ in range(3): c.inject('rgb',self.args[0])
        self.assertEqual(len(c._buffers['rgb']),2)
        self.assertEqual(c._retained_bytes,24)
    def test_ingress_budget(self):
        from unittest.mock import patch
        c=self.collector()
        with patch('vision_runtime.ros2_bridge.MAX_RETAINED_BYTES', 12):
            c.inject('rgb',self.args[0])
            with self.assertRaises(ValueError): c.inject('depth',self.args[1])
        self.assertEqual(c._retained_bytes,12)
    def test_out_of_order(self):
        c=self.collector()
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),self.args):
            newer=copy.deepcopy(msg); newer.header.stamp.sec=101
            c.inject(key,newer); c.inject(key,msg)
        kw=dict(self.kw,now=101)
        def lookup(target,source,stamp):
            result=tf(target,source); result.header.stamp.sec=stamp.sec; return result
        self.assertEqual(c.snapshot(**kw,tf_lookup=lookup).rgb.stamp.timestamp,101)
    def test_stale_quartet(self):
        c=self.collector()
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),self.args): c.inject(key,msg)
        with self.assertRaises(ValueError): c.snapshot(**dict(self.kw,now=102),tf_lookup=lambda *x:None)
    def test_equal_timestamp_latest_arrival(self):
        c=self.collector()
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),self.args): c.inject(key,msg)
        latest=copy.deepcopy(self.args[0]); latest.data=bytes(reversed(range(12))); c.inject('rgb',latest)
        self.assertEqual(c.snapshot(**self.kw,tf_lookup=lambda target,source,stamp:tf(target,source)).rgb.data,latest.data)
    def test_mixed_stream_skew(self):
        c=self.collector()
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),self.args):
            m=copy.deepcopy(msg)
            if key == 'depth': m.header.stamp.sec=101
            c.inject(key,m)
        with self.assertRaises(ValueError): c.snapshot(**dict(self.kw,now=101,max_age=2),tf_lookup=lambda *x:None)

    def test_default_domain_zero_and_lazy_imports(self):
        from unittest.mock import patch
        import types
        modules = {'rclpy': types.ModuleType('rclpy'), 'tf2_ros': types.ModuleType('tf2_ros'), 'sensor_msgs': types.ModuleType('sensor_msgs'), 'sensor_msgs.msg': types.ModuleType('sensor_msgs.msg')}
        modules['sensor_msgs.msg'].Image = type('Image', (), {})
        modules['sensor_msgs.msg'].CameraInfo = type('CameraInfo', (), {})
        node = N(create_subscription=lambda *args: args)
        with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
            collector = SnapshotCollector.from_node(node, TopicBindings('/r','/d','/ri','/di',0), qos=1)
            self.assertEqual(len(collector._subscriptions), 4)
            with self.assertRaises(ValueError): SnapshotCollector.from_node(node, TopicBindings('/r','/d','/ri','/di',1), qos=1)
