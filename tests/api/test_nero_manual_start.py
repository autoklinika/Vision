"""Startup evidence and virtual-only initialization; no hardware."""
from dataclasses import replace
import unittest
import xml.etree.ElementTree as ET

from vision_station.nero_manual import Feedback, JOINTS, Profile
from vision_station.nero_manual_start import (
    ControllerStart, initial_virtual_model, live_seed, seed_virtual_model,
)


class CurrentPositionTests(unittest.TestCase):
    def setUp(self):
        self.now=100.
        self.profile=Profile(5,2,((-1.,1.),)*7,(.02,)*7,.005)
        root=ET.Element("robot",name="fixture")
        control=ET.SubElement(root,"ros2_control",name="FakeSystem",type="system")
        ET.SubElement(ET.SubElement(control,"hardware"),"plugin").text="mock_components/GenericSystem"
        for name in JOINTS:
            joint=ET.SubElement(root,"joint",name=name,type="revolute")
            ET.SubElement(joint,"limit",lower="-1",upper="1",velocity="5",effort="100")
            j=ET.SubElement(control,"joint",name=name)
            ET.SubElement(j,"command_interface",name="position")
            p=ET.SubElement(j,"state_interface",name="position")
            ET.SubElement(p,"param",name="initial_value").text="0.0"
            ET.SubElement(j,"state_interface",name="velocity")
        self.urdf=ET.tostring(root,encoding="unicode")
        self.q=(.1,.2,-.1,.3,.4,-.2,.5)

    def sample(self,q=None,t=99.97):
        return Feedback(self.q if q is None else tuple(q),(0.,)*7,t,t,6,0,1,(0,)*7,(t,)*7,(t,)*7)

    def test_arbitrary_actual_seed_not_home(self):
        for q in (self.q,(-.5,-.4,.3,.2,-.1,.4,.6)):
            first=self.sample(q,t=99.94);second=self.sample(q)
            model,seed=initial_virtual_model(self.urdf,first,second,profile=self.profile,now=self.now)
            self.assertEqual(seed.q,q)
            self.assertTrue(seed.valid(self.now,self.profile))
            root=ET.fromstring(model)
            self.assertEqual([float(j.findtext("state_interface/param")) for j in root.findall("ros2_control/joint")],list(q))
            old=ET.fromstring(self.urdf)
            for x in (old,root):
                x.remove(x.find("ros2_control"))
            self.assertEqual(ET.tostring(root),ET.tostring(old))

    def test_repeated_or_expired_feedback_is_rejected(self):
        f=self.sample()
        with self.assertRaises(ValueError):live_seed(f,f,profile=self.profile,now=self.now)
        with self.assertRaises(ValueError):live_seed(self.sample(t=99.8),f,profile=self.profile,now=self.now)
        with self.assertRaises(ValueError):live_seed(self.sample(t=99.94),f,profile=self.profile,now=100.2)

    def test_movement_fault_or_invalid_mode_rejected(self):
        f=self.sample(t=99.94);g=self.sample()
        for bad in (replace(g,q=(.9,)*7),replace(g,velocity=(.2,)*7),
                    replace(g,arm_mask=1),replace(g,control_mode=3),
                    replace(g,q=(2.,)*7),replace(g,drive_status=(64,0,0,0,0,0,0))):
            with self.assertRaises(ValueError):live_seed(f,bad,profile=self.profile,now=self.now)

    def test_only_virtual_interpolator(self):
        with self.assertRaises(ValueError):seed_virtual_model(self.urdf.replace("mock_components/GenericSystem","fixture/physical"),self.q,self.profile)
        with self.assertRaises(ValueError):seed_virtual_model(self.urdf,(2.,)*7,self.profile)

    def test_controller_state_and_reference_must_both_match(self):
        f=self.sample()
        c=ControllerStart(99.98,b"a",self.q,self.q,(0.,)*7,(0.,)*7)
        self.assertTrue(c.matches(f,now=self.now,expected_gid=b"a"))
        for bad in (replace(c,reference=(0.,)*7),replace(c,q=(0.,)*7),
                    replace(c,stamp=99.8),replace(c,stamp=100.1),
                    replace(c,gid=b"b"),replace(c,reference_velocity=(.02,)*7),
                    replace(c,velocity=(.02,)*7)):
            self.assertFalse(bad.matches(f,now=self.now,expected_gid=b"a"))

if __name__=="__main__":
    unittest.main()
