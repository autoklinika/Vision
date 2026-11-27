"""Strict candidate conversion; no physical driver or ROS imports."""
import unittest
from types import SimpleNamespace as NS
from vision_station.nero_servo_bridge import (JOINTS,NANO,CandidateRejected,
    LockedBridge,decode_candidate)

NOW=100*NANO
def stamp(ns):return NS(sec=ns//NANO,nanosec=ns%NANO)
def trajectory(*,start=NOW-50_000_000,offsets=(0,40_000_000,80_000_000),names=JOINTS):
    return NS(header=NS(stamp=stamp(start),frame_id=""),joint_names=names,
              points=[NS(time_from_start=stamp(t),positions=list(range(7)),
                         velocities=[0.]*7,accelerations=[],effort=[]) for t in offsets])

class Arbiter:
    def __init__(self):self.calls=[];self.reason="CAN_TX_DISABLED_PENDING_HARDWARE_ACCEPTANCE"
    def classify_setpoint(self,names,positions,**kwargs):
        self.calls.append((names,positions,kwargs))
        return NS(accepted=True,reason=self.reason)  # even malicious/ permissive mock stays locked

class BridgeTests(unittest.TestCase):
    def test_order_and_absolute_time(self):
        c=decode_candidate(trajectory(names=tuple(reversed(JOINTS))),NOW)
        self.assertEqual(c.points[0].positions,tuple(reversed(range(7))))
        self.assertEqual(c.first_future(NOW).at_ns,NOW+30_000_000)
        self.assertEqual(c.points[0].at_ns,NOW-50_000_000)
        self.assertEqual(c.end_ns,NOW+30_000_000)

    def test_invalid_windows(self):
        for msg,reason in ((trajectory(names=JOINTS[:-1]),"JOINT_NAMES"),
                           (trajectory(names=(*JOINTS[:6],JOINTS[0])),"JOINT_NAMES"),
                           (trajectory(start=NOW-500_000_000),"STALE"),
                           (trajectory(start=NOW+100_000_000),"FUTURE"),
                           (trajectory(offsets=(0,20_000_000)),"EXPIRED"),
                           (trajectory(offsets=(0,20_000_000,20_000_000)),"TIME_ORDER"),
                           (trajectory(offsets=(0,600_000_000)),"HORIZON"),
                           (trajectory(offsets=()),"FORMAT")):
            with self.subTest(reason=reason),self.assertRaisesRegex(CandidateRejected,reason):
                decode_candidate(msg,NOW)
        msg=trajectory();msg.points[0].positions[0]=float("nan")
        with self.assertRaisesRegex(CandidateRejected,"NONFINITE"):decode_candidate(msg,NOW)

    def test_guard_is_authoritative_but_never_acts(self):
        a=Arbiter()
        b=LockedBridge(a,lambda:{"arm_status":"NORMAL","firmware_error_mask":0,"feedback_stamp":99.99})
        v=b.assess(trajectory(),NOW,(1,2))
        self.assertTrue(v.accepted_format);self.assertFalse(v.can_execute)
        self.assertEqual(v.guard_reason,a.reason)
        self.assertEqual(a.calls[0][0],JOINTS)
        self.assertEqual(a.calls[0][2]["now"],100.)
        self.assertEqual(b.assess(trajectory(),NOW,(1,2)).reason,"REPLAY")
        self.assertEqual(b.assess(trajectory(start=NOW),NOW,(3,4)).reason,"SOURCE_CHANGED")
        self.assertEqual(len(a.calls),1)
        a.reason="STOP_ALREADY_LATCHED"
        v=b.assess(trajectory(start=NOW),NOW,(1,2))
        self.assertEqual(v.guard_reason,a.reason);self.assertFalse(v.can_execute)

    def test_unavailable_guard(self):
        b=LockedBridge(Arbiter(),lambda:None)
        v=b.assess(trajectory(),NOW,(1,))
        self.assertEqual(v.reason,"GUARD_UNAVAILABLE");self.assertFalse(v.can_execute)
