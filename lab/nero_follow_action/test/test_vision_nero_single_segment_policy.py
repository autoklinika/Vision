"""Fail-closed policy tests for first live NERO ROS2 FollowJointTrajectory step."""
import math,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agx_arm_ctrl.vision_nero_single_segment_policy import (
    JOINTS,RejectGoal,validate_step,check_feedback,converged)
deg=math.radians

class StepPolicy(unittest.TestCase):
 def setUp(self):
  self.current=[deg(x) for x in [90.321,56.848,-.8,106.271,.237,-.88,23.33]]
  self.end=self.current[:];self.end[1]+=deg(1.25)
  self.points=[(self.current,0.0),(self.end,10.0)]
 def valid(self,points=None,names=None):
  return validate_step(names or JOINTS,points or self.points,self.current)

 def test_exact_joint2_step_accepted(self):
  result=self.valid()
  self.assertEqual(result.joint,'joint2')
  self.assertAlmostEqual(result.delta_deg,1.25,places=5)
  self.assertEqual(result.permitted_speed_percent,3)
 def test_rejects_more_than_two_degrees(self):
  x=self.end[:];x[1]=self.current[1]+deg(2.5)
  with self.assertRaisesRegex(RejectGoal,'DISPLACEMENT'):
   self.valid([(self.current,0),(x,10)])
 def test_unrelated_joint_motion_refused(self):
  x=self.end[:];x[0]+=deg(1)
  with self.assertRaisesRegex(RejectGoal,'ONE_APPROVED'):
   self.valid([(self.current,0),(x,10)])
 def test_j7_or_j1_only_refused(self):
  for ix in (0,6):
   x=self.current[:];x[ix]+=deg(1)
   with self.subTest(joint=ix),self.assertRaisesRegex(RejectGoal,'ONE_APPROVED'):
    self.valid([(self.current,0),(x,10)])
 def test_wrong_start_rejected(self):
  bad=self.current[:];bad[1]+=deg(.5)
  with self.assertRaisesRegex(RejectGoal,'START_NOT_LIVE'):
   self.valid([(bad,0),(self.end,10)])
 def test_outside_urdf_denied(self):
  x=self.end[:];x[6]=deg(89.99)
  with self.assertRaisesRegex(RejectGoal,'VENDOR_JOINT_LIMIT'):
   self.valid([(self.current,0),(x,10)])
 def test_names_and_time_contract(self):
  badnames=list(reversed(JOINTS))
  with self.assertRaisesRegex(RejectGoal,'JOINT_NAMES'):
   self.valid(names=badnames)
  with self.assertRaisesRegex(RejectGoal,'TIMING'):
   self.valid(points=[(self.current,0),(self.end,2)])
  with self.assertRaisesRegex(RejectGoal,'TWO_WAYPOINTS'):
   self.valid(points=[(self.end,10)])
 def test_speed_policy(self):
  with self.assertRaisesRegex(RejectGoal,'SPEED'):
   validate_step(JOINTS,self.points,self.current,speed_percent=10)
 def test_stale_status_disabled_and_nonfinite_rejected(self):
  args={'q':self.current,'velocity':[0]*7,'status':'NORMAL','error_mask':0,
       'ctrl_mode':'CAN_CTRL','motors_enabled':[True]*7,'timestamp_age_s':.02}
  self.assertTrue(check_feedback(**args))
  for key,v in [('timestamp_age_s',.2),('status','JOINT_BRAKE_NOT_RELEASED'),
                ('error_mask',1),('motors_enabled',[False]*7),
                ('velocity',[float('nan')]*7)]:
   b={**args,key:v}
   with self.subTest(key=key),self.assertRaises(RejectGoal):
    check_feedback(**b)
 def test_fail_closed_joint_drift(self):
  a=self.current[:];a[0]+=deg(.5)
  with self.assertRaisesRegex(RejectGoal,'UNCOMMANDED_NON_J2'):
   check_feedback(a,[0]*7,'NORMAL',0,'CAN_CTRL',[True]*7,
       timestamp_age_s=.02,expected_start=self.current)
 def test_convergence(self):
  self.assertTrue(converged(self.end,[0]*7,self.end))
  self.assertFalse(converged(self.current,[0]*7,self.end))

if __name__=='__main__':unittest.main()
