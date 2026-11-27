import unittest
from types import SimpleNamespace as NS
from vision_station.nero_firmware_limits import parse_reply,query_limits

class FirmwareLimitsTests(unittest.TestCase):
    def packet(self,i,stamp=100.2,lo=-1.,hi=2.,velocity=1.5):
        return NS(timestamp=stamp,msg=NS(joint_index=i,min_angle_limit=lo,max_angle_limit=hi,max_joint_spd=velocity))

    def test_reply_validation(self):
        self.assertEqual(parse_reply(self.packet(4),4,100.,101.)["angleRad"],[-1.,2.])
        for p in (None,self.packet(5),self.packet(4,stamp=99.),
                  self.packet(4,stamp=102.),self.packet(4,lo=2.1),
                  self.packet(4,velocity=float("nan")),self.packet(4,velocity=-1.)):
            self.assertIsNone(parse_reply(p,4,100.,101.))

    def test_queries_only_once_per_axis(self):
        calls=[];checks=[];times=iter([100.,101.]*7)
        def get(i,**kw):
            calls.append((i,kw))
            return None if i==6 else self.packet(i)
        v=query_limits(NS(get_joint_angle_vel_limits=get),lambda:checks.append(True),clock=lambda:next(times))
        self.assertEqual([i for i,k in calls],list(range(1,8)))
        self.assertEqual(len(checks),14)
        self.assertIsNone(v[5]["angleRad"])
        self.assertEqual(v[6]["maxVelocityRadS"],1.5)

    def test_interlock_stops_queries(self):
        calls=[]
        def reject():raise RuntimeError("not disabled")
        with self.assertRaises(RuntimeError):
            query_limits(NS(get_joint_angle_vel_limits=lambda *a,**k:calls.append(a)),reject)
        self.assertEqual(calls,[])
