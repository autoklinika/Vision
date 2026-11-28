"""Owner factory and shared profile tests; no physical ROS or SDK."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

from vision_station.nero import NODE
from vision_station.nero_manual import JOINTS, Profile, Feedback
from vision_station.nero_manual_station import Candidate, STATUS
from vision_station.nero_manual_pipeline import Routes
from vision_station.nero_manual_composition import (
    OwnerWiring, existing_owner_factory, review_profile, verify_tcp,
    servo_parameters, planning_parameters, contract_for_loaded_model, prepare_owner_start,
)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        root=ET.Element("robot",name="fixture")
        for n in ("base_link",*[f"link{i}" for i in range(1,8)],"flange_link","tcp_link"):
            ET.SubElement(root,"link",name=n)
        for i,name in enumerate(JOINTS,1):
            j=ET.SubElement(root,"joint",name=name,type="revolute")
            ET.SubElement(j,"parent",link="base_link" if i==1 else f"link{i-1}")
            ET.SubElement(j,"child",link=f"link{i}")
            ET.SubElement(j,"origin",xyz="0 0 0",rpy="0 0 0")
            ET.SubElement(j,"axis",xyz="0 0 1")
            ET.SubElement(j,"limit",lower="-1",upper="1",velocity="5",effort="100")
        tcp=ET.SubElement(root,"joint",name="tcp_joint",type="fixed")
        ET.SubElement(tcp,"parent",link="flange_link")
        ET.SubElement(tcp,"child",link="tcp_link")
        ET.SubElement(tcp,"origin",xyz="0 0 .012",rpy="0 0 0")
        self.urdf=ET.tostring(root,encoding="unicode")
        self.srdf='<robot name="fixture"><group name="arm"><chain base_link="base_link" tip_link="tcp_link"/></group></robot>'
        self.limits={"jointPositionRad":[[-.8,.9]]*7,"controllerMaxVelocityRadS":[3.14]*7}
        self.candidate=Candidate({"status":STATUS,"physicalExecutionAllowed":False,"limits":self.limits},
                                 self.urdf,self.srdf,b"fixture",(0.,)*7)
        self.profile=review_profile(self.candidate)
        self.base={"robot_description_planning":{"default_velocity_scaling_factor":.1,
                   "default_acceleration_scaling_factor":.1,"joint_limits":{
                    n:{"has_velocity_limits":True,"max_velocity":5.,
                       "has_acceleration_limits":True,"max_acceleration":5.}
                    for n in (*JOINTS,"gripper")}}}

    def params(self,routes):
        return {**planning_parameters(self.base,self.urdf,self.profile),
                "robot_description":self.urdf,"robot_description_semantic":self.srdf,
                "moveit_servo":servo_parameters(routes,self.profile),"use_sim_time":False}

    def contract(self,routes):
        return contract_for_loaded_model(routes,self.profile,self.params(routes),"a"*64)

    def test_precision_profile_is_explicit_and_never_approved(self):
        p=self.profile
        self.assertEqual((p.linear_max,p.angular_max),(5,2))
        self.assertEqual(p.joint_velocity_max,(.02,)*7)
        self.assertEqual(p.tracking_error_max,.005)
        self.assertFalse(self.candidate.manifest["physicalExecutionAllowed"])
        self.assertEqual(verify_tcp(self.urdf,self.srdf),(0.,0.,.012))
        bad=replace(self.candidate,manifest={**self.candidate.manifest,"physicalExecutionAllowed":True})
        with self.assertRaises(ValueError):review_profile(bad)

    def test_planning_caps_and_existing_collision_thresholds(self):
        p=self.params(Routes.fixture())
        rows=p["robot_description_planning"]["joint_limits"]
        self.assertEqual(set(rows),set(JOINTS))
        self.assertTrue(all(r["max_velocity"]==.02 and r["max_acceleration"]==5. for r in rows.values()))
        self.assertEqual(self.base["robot_description_planning"]["joint_limits"]["joint1"]["max_velocity"],5.)
        servo=p["moveit_servo"]
        self.assertTrue(servo["check_collisions"])
        self.assertEqual(servo["self_collision_proximity_threshold"],.01)
        self.assertEqual(servo["scene_collision_proximity_threshold"],.02)
        self.assertEqual(servo["scale"]["linear"],.005)
        self.assertEqual(servo["joint_topic"],Routes.fixture().feedback_topic)

    def test_changed_servo_or_velocity_limits_rejected(self):
        routes=Routes.physical()
        p=self.params(routes)
        p["moveit_servo"]["check_collisions"]=False
        with self.assertRaises(ValueError):
            contract_for_loaded_model(routes,self.profile,p,"a"*64)
        p=self.params(routes)
        p["robot_description_planning"]["joint_limits"]["joint1"]["max_velocity"]=.1
        with self.assertRaises(ValueError):
            contract_for_loaded_model(routes,self.profile,p,"a"*64)

    def test_review_fixture_contract_cannot_bind_hardware_owner(self):
        with self.assertRaises(ValueError):OwnerWiring(self.profile,self.contract(Routes.fixture()))
        with self.assertRaises(ValueError):
            existing_owner_factory(self.candidate,approval_directory="/nonexistent",
                                   socket_path="/nonexistent/m.sock",relay_binary="/nonexistent/relay",
                                   twist_mode_confirmed=lambda:False)

    def test_wiring_rejects_mismatched_speed(self):
        with self.assertRaises(ValueError):
            OwnerWiring(replace(self.profile,linear_max=10),self.contract(Routes.physical()))
        with self.assertRaises(ValueError):
            OwnerWiring(replace(self.profile,tracking_error_max=.01),self.contract(Routes.physical()))

    def start_wiring(self):
        root=ET.fromstring(self.urdf)
        ctrl=ET.SubElement(root,"ros2_control",name="FakeSystem",type="system")
        ET.SubElement(ET.SubElement(ctrl,"hardware"),"plugin").text="mock_components/GenericSystem"
        for name in JOINTS:
            joint=ET.SubElement(ctrl,"joint",name=name)
            ET.SubElement(joint,"command_interface",name="position")
            interface=ET.SubElement(joint,"state_interface",name="position")
            ET.SubElement(interface,"param",name="initial_value").text="0.0"
            ET.SubElement(joint,"state_interface",name="velocity")
        self.urdf=ET.tostring(root,encoding="unicode")
        return OwnerWiring(self.profile,self.contract(Routes.physical()))

    def feedback(self,q,t):
        return Feedback(tuple(q),(0.,)*7,t,t,6,0,1,(0,)*7,(t,)*7,(t,)*7)

    def test_prepare_current_position_changes_only_virtual_initial_values(self):
        wiring=self.start_wiring()
        original=dict(wiring.contract.parameters)
        for q in ((.1,.2,-.1,.3,.4,-.2,.5),(-.5,-.4,.3,.2,-.1,.4,.6)):
            prepared,seed=prepare_owner_start(wiring,self.feedback(q,99.94),
                                              self.feedback(q,99.97),now=100.)
            self.assertEqual(seed.q,q)
            self.assertEqual(prepared.profile,wiring.profile)
            self.assertEqual(prepared.contract.routes,wiring.contract.routes)
            self.assertEqual(prepared.contract.scene_digest,wiring.contract.scene_digest)
            params=dict(prepared.contract.parameters)
            model=ET.fromstring(params.pop("robot_description"))
            expected=ET.fromstring(original["robot_description"])
            self.assertEqual(params,{k:v for k,v in original.items() if k!="robot_description"})
            self.assertEqual([float(j.findtext("state_interface/param")) for j in model.findall("ros2_control/joint")],list(q))
            for root in (model,expected):
                for v in root.findall("ros2_control/joint/state_interface/param"):
                    v.text="0.0"
            self.assertEqual(ET.tostring(model),ET.tostring(expected))
        self.assertEqual(dict(wiring.contract.parameters),original)

    def test_prepare_owner_start_cannot_promote_review_or_stale_feedback(self):
        wiring=self.start_wiring()
        f=self.feedback((.1,)*7,99.94)
        g=self.feedback((.1,)*7,99.97)
        for bad in (self.candidate,None):
            with self.assertRaises(ValueError):prepare_owner_start(bad,f,g,now=100.)
        with self.assertRaises(ValueError):prepare_owner_start(wiring,f,g,now=100.2)
        with self.assertRaises(ValueError):prepare_owner_start(wiring,g,g,now=100.)
        with self.assertRaises(ValueError):prepare_owner_start(wiring,f,replace(g,control_mode=3),now=100.)

    def test_wiring_uses_same_owner_and_existing_runtime_once(self):
        wiring=OwnerWiring(self.profile,self.contract(Routes.physical()))
        class Owner:
            def get_fully_qualified_name(self):return NODE
            def hold(self):return False
        owner=Owner()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);approval=root/"approval";socket=root/"ipc"
            approval.mkdir(mode=0o700);socket.mkdir(mode=0o700)
            mode=Mock(return_value=False)
            with patch("vision_station.ros_nero_manual_pipeline.RosPipelineMonitor") as monitor, \
                 patch("vision_station.ros_nero_manual.ManualRuntime") as runtime:
                factory=existing_owner_factory(wiring,approval_directory=approval,
                        socket_path=socket/"m.sock",relay_binary=root/"relay",twist_mode_confirmed=mode)
                monitor.assert_not_called();runtime.assert_not_called()
                with self.assertRaises(ValueError):factory(owner,Owner().hold)
                monitor.assert_not_called()
                self.assertIs(factory(owner,owner.hold),runtime.return_value)
                monitor.assert_called_once_with(owner,wiring.contract,twist_mode_confirmed=mode)
                runtime.assert_called_once()
                self.assertIs(runtime.call_args.args[0],owner)
                self.assertEqual(runtime.call_args.kwargs["profile"],self.profile)
                self.assertIs(runtime.call_args.kwargs["pipeline_authority"],monitor.return_value)
                self.assertEqual(runtime.call_args.kwargs["native_hold"],owner.hold)
                with self.assertRaises(ValueError):factory(owner,owner.hold)
                self.assertEqual(runtime.call_count,1)

    def test_factory_failure_closes_monitor(self):
        wiring=OwnerWiring(self.profile,self.contract(Routes.physical()))
        class Owner:
            def get_fully_qualified_name(self):return NODE
            def hold(self):return False
        owner=Owner()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);approval=root/"approval";socket=root/"ipc"
            approval.mkdir(mode=0o700);socket.mkdir(mode=0o700)
            with patch("vision_station.ros_nero_manual_pipeline.RosPipelineMonitor") as monitor, \
                 patch("vision_station.ros_nero_manual.ManualRuntime",side_effect=RuntimeError("test")):
                factory=existing_owner_factory(wiring,approval_directory=approval,
                        socket_path=socket/"m.sock",relay_binary=root/"relay",
                        twist_mode_confirmed=lambda:False)
                with self.assertRaises(RuntimeError):factory(owner,owner.hold)
                monitor.return_value.close.assert_called_once()


if __name__=="__main__":
    unittest.main()
