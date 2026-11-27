import copy
import math
import unittest
from test_nero_diagnostics import report
from vision_station.nero_tcp import project, validate_report, twist_intent, AXES, validate_declaration
from vision_station.server import dispatch
from vision_station.protocol import PROTOCOL
from vision_station.nero_joint_limits import Reference,JOINTS,model_bounds,sdk_bounds,intersection
from vision_station.nero_joint_limits import InstalledJointLimits
from unittest.mock import patch
from types import SimpleNamespace
import tempfile
from pathlib import Path
import sys


class TcpTests(unittest.TestCase):
    def test_real_feedback_without_actuation(self):
        n=report(drives=(0,64,0,64,0,0,0))
        d=project(n)
        self.assertTrue(validate_report(d))
        self.assertEqual(d["driveEnabled"],[False,True,False,True,False,False,False])
        self.assertFalse(any(d["capabilities"].values()))
        self.assertIsNone(d["actualTcp"])
        n["motors"]=None
        self.assertEqual(project(n)["driveEnabled"],[None]*7)
        bad=copy.deepcopy(d)
        bad["capabilities"]["jog"]=True
        self.assertFalse(validate_report(bad))

    def test_joint_preflight_outside_both_limits(self):
        n=report()
        for row in n["joints"]["rows"]:row["positionRad"]=0.
        n["joints"]["rows"][3]["positionRad"]=math.radians(126.322)
        sdk=((-2.,2.),)*3+((-1.,2.146755),)+((-1.,1.),)*3
        model=((-2.,2.),)*3+((-1.,2.14),)+((-1.,1.),)*3
        ref=Reference(sdk,model,"1.0.0","v121","a"*64)
        v=project(n,reference=ref)
        self.assertTrue(validate_report(v))
        self.assertEqual(v["jointCheck"]["state"],"OUTSIDE_LIMITS")
        self.assertEqual(v["jointCheck"]["rows"][3]["state"],"OUTSIDE_LIMITS")
        self.assertEqual(v["jointCheck"]["rows"][3]["modelRad"][1],2.14)
        self.assertEqual(v["jointCheck"]["rows"][3]["sdkRad"][1],2.146755)
        self.assertEqual(sum(r["state"]=="OUTSIDE_LIMITS" for r in v["jointCheck"]["rows"]),1)
        self.assertFalse(any(v["capabilities"].values()))
        bad=copy.deepcopy(v);bad["jointCheck"]["rows"][3]["state"]="WITHIN_LIMITS"
        self.assertFalse(validate_report(bad))
        n["joints"]["rows"][3]["positionRad"]=2.143
        self.assertEqual(project(n,reference=ref)["jointCheck"]["state"],"OUTSIDE_LIMITS")
        n["joints"]["rows"][3]["positionRad"]=2.0
        self.assertEqual(project(n,reference=ref)["jointCheck"]["state"],"WITHIN_LIMITS")
        # A different actual start state is valid without knowing PARK.
        n["joints"]["rows"][3]["positionRad"]=.6
        self.assertEqual(project(n,reference=ref)["jointCheck"]["state"],"WITHIN_LIMITS")
        unknown=project(n)
        self.assertTrue(validate_report(unknown))
        self.assertEqual(unknown["jointCheck"]["state"],"UNKNOWN")
        self.assertIsNone(unknown["jointCheck"]["reference"])
        self.assertEqual(unknown["jointCheck"]["rows"][3]["positionRad"],.6)
        self.assertIsNone(unknown["jointCheck"]["rows"][3]["modelRad"])
        n["joints"]=None
        self.assertEqual(project(n,reference=ref)["jointCheck"]["state"],"UNKNOWN")
        self.assertFalse(any(project(n)["capabilities"].values()))

    def test_installed_source_reload_no_embedded_values(self):
        def xml(upper):
            return '<robot name="nero">'+''.join(
                '<joint name="%s" type="revolute"><limit lower="-1.0" upper="%s"/></joint>'%(name,upper)
                for name in JOINTS)+'</robot>'
        cfg={"robot":"nero","firmeware_version":"v121",
             "joint_limits":{n:[-1.,1.5] for n in JOINTS}}
        fake=SimpleNamespace(ArmModel=SimpleNamespace(NERO="nero"),
                             NeroFW=type("Firmware",(),{"V121":"v121"}),
                             create_agx_arm_config=lambda **kw:cfg)
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,{"pyAgxArm":fake}), patch("vision_station.nero_joint_limits.version",return_value="test"):
            p=Path(directory)/"nero.urdf";p.write_text(xml(1.2))
            provider=InstalledJointLimits(p,"v121")
            a=provider()
            self.assertEqual(intersection(a.sdk,a.model),((-1.,1.2),)*7)
            p.write_text(xml(.8));b=provider()
            self.assertNotEqual(a.model_sha256,b.model_sha256)
            self.assertEqual(intersection(b.sdk,b.model),((-1.,.8),)*7)
            cfg["joint_limits"]["joint4"]=[-.4,.5]
            c=provider()
            self.assertEqual(intersection(c.sdk,c.model)[3],(-.4,.5))
            from vision_station.nero_manual import Profile
            profile=Profile.from_robot_model(sdk_config=cfg,model_urdf=p.read_bytes(),
                linear_max=10,angular_max=5,joint_velocity_max=(.05,)*7,tracking_error_max=.01)
            self.assertEqual(profile.joint_limits[3],(-.4,.5))
            self.assertTrue(profile.contains((.3,)*7))
            self.assertTrue(profile.contains((-.2,)*7))
            self.assertFalse(profile.contains((.7,)*7))
            p.unlink()
            with self.assertRaises(FileNotFoundError):provider()
        with self.assertRaises(ValueError):model_bounds('<robot name="nero"/>')
        with self.assertRaises(ValueError):intersection(((-2.,-1.),)*7,((0.,1.),)*7)

    def test_speed_conversion_and_frames(self):
        for frame,expected in (("BASE","base_link"),("TOOL","tcp_link")):
            d={"frame":frame,"linearMmS":25,"angularDegS":10}
            for i,axis in enumerate(AXES):
                for direction in (-1,1):
                    v=twist_intent(d,axis,direction)
                    self.assertEqual(v["frameId"],expected)
                    values=v["linear"]+v["angular"]
                    self.assertAlmostEqual(values[i],direction*(.025 if i<3 else math.radians(10)))
                    self.assertEqual(sum(x!=0 for x in values),1)

    def test_strict_inputs(self):
        d={"frame":"BASE","linearMmS":10,"angularDegS":5}
        for invalid in (0,-1,101,float("nan"),True,10.0,"10"):
            self.assertFalse(validate_declaration({**d,"linearMmS":invalid}))
        for invalid in (0,31,False):
            self.assertFalse(validate_declaration({**d,"angularDegS":invalid}))
        with self.assertRaises(ValueError):twist_intent(d,"J1",1)
        with self.assertRaises(ValueError):twist_intent(d,"X",True)
        with self.assertRaises(ValueError):twist_intent({**d,"frame":"world"},"X",1)

    def test_closed_ipc(self):
        class Host:
            def nero_tcp_report(self):return project(report())
        h=Host()
        self.assertTrue(validate_report(dispatch(h,{"schema":PROTOCOL,"operation":"nero_tcp","query":{}})))
        for operation,query in (("nero_tcp",{"enable":True}),("nero_move",{}),("nero_enable",{})):
            with self.assertRaises(ValueError):
                dispatch(h,{"schema":PROTOCOL,"operation":operation,"query":query})
