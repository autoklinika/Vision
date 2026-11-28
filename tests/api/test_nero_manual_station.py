"""Offline station bundle contracts; synthetic data, no hardware or ROS."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from vision_station.nero_joint_limits import JOINTS, model_bounds
from vision_station.nero_manual_station import load, prepare, sha, STATUS


def write_json(path,value):
    path.write_text(json.dumps(value),encoding="utf-8")


class StationCandidateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.source=self.root/"source"
        self.source.mkdir()
        self.mesh=self.root/"meshes"
        self.mesh.mkdir()
        self.output=self.root/"candidate"
        robot=ET.Element("robot",name="agx_arm")
        for n in ("base_link",*[f"link{i}" for i in range(1,8)],"flange_link"):
            link=ET.SubElement(robot,"link",name=n)
            shape=ET.SubElement(ET.SubElement(link,"collision"),"geometry")
            path=self.mesh/(n+".stl")
            path.write_bytes(("fixture mesh "+n).encode())
            ET.SubElement(shape,"mesh",filename="package://agx_arm_description/"+path.name)
        ET.SubElement(robot,"link",name="tcp_link")
        for i,name in enumerate(JOINTS,1):
            j=ET.SubElement(robot,"joint",name=name,type="revolute")
            ET.SubElement(j,"parent",link="base_link" if i==1 else f"link{i-1}")
            ET.SubElement(j,"child",link=f"link{i}")
            ET.SubElement(j,"origin",xyz="0 0 0",rpy="0 0 0")
            ET.SubElement(j,"axis",xyz="0 0 1")
            ET.SubElement(j,"limit",lower="-1.0",upper="1.0",velocity="2.0",effort="100")
        for name,child in (("tcp_joint","tcp_link"),("flange_joint","flange_link")):
            j=ET.SubElement(robot,"joint",name=name,type="fixed")
            ET.SubElement(j,"parent",link="link7")
            ET.SubElement(j,"child",link=child)
            ET.SubElement(j,"origin",xyz="0 0 0",rpy="0 0 0")
        ctrl=ET.SubElement(robot,"ros2_control",name="FakeSystem",type="system")
        ET.SubElement(ET.SubElement(ctrl,"hardware"),"plugin").text="mock_components/GenericSystem"
        for name in JOINTS:
            j=ET.SubElement(ctrl,"joint",name=name)
            ET.SubElement(j,"command_interface",name="position")
            ET.SubElement(j,"state_interface",name="position")
            ET.SubElement(j,"state_interface",name="velocity")
        self.urdf=ET.tostring(robot)
        self.srdf=b'<robot name="agx_arm"><group name="arm"><chain base_link="base_link" tip_link="tcp_link"/></group></robot>'
        self.scene=b"opaque synthetic fixture CDR"
        (self.source/"model.urdf").write_bytes(self.urdf)
        (self.source/"model.srdf").write_bytes(self.srdf)
        (self.source/"scene.cdr").write_bytes(self.scene)
        self.assembly={"physicalExecutionAllowed":False,"armKinematicsUnchanged":True,
            "adapterAddedOffsetMm":0,"toolTouchLinks":["flange_link"],
            "faceOffsetInFlangeFrameMm":12.0,
            "factoryFlangeMeshSha256":sha((self.mesh/"flange_link.stl").read_bytes()),
            "robotDescriptionSha256":sha(self.urdf),
            "semanticDescriptionSha256":sha(self.srdf),"sceneSha256":sha(self.scene)}
        write_json(self.source/"assembly.json",self.assembly)
        self.fw=self.root/"firmware.json"
        self.firmware={"schema":"vision.nero.firmware-limit-observation.v1","startedAt":100.,
            "capturedAt":101.,"source":{"sdkVersion":"1.0.0","firmwareProfile":"v121","modelSha256":"a"*64},
            "controllerRows":[{"joint":n,"angleRad":[-.8,.9],"maxVelocityRadS":2.,"responseAt":100.5}
                for n in JOINTS],"sdkRad":[[-.9,.95]]*7,"modelRad":[[-1.,1.]]*7}
        write_json(self.fw,self.firmware)
        self.pose=self.root/"pose.json"
        self.historical={"status":"OPERATOR_REPORTED_OEM_LINE_MOTION_COMPLETE",
            "physicalMotionCommandedByAssistant":False,"errorCode":0,"motorsEnabled":[True]*7,
            "motorVelocityRadS":[0.]*7,"canJointDeg":[5.]*7,"utc":"2026-01-01T10:00:00+00:00"}
        write_json(self.pose,self.historical)

    def prepare(self):
        return prepare(self.source,self.fw,self.pose,self.output,mesh_root=self.mesh)

    def reload(self):
        return load(self.output,mesh_root=self.mesh)

    def test_only_tcp_changes_and_limits_intersect(self):
        c=self.prepare()
        self.assertEqual(c.manifest["status"],STATUS)
        self.assertFalse(c.manifest["physicalExecutionAllowed"])
        self.assertFalse(c.manifest["tcp"]["operatorApproved"])
        self.assertFalse(c.manifest["limits"]["manualSpeedProfileApproved"])
        self.assertEqual(c.manifest["limits"]["jointPositionRad"],[[-.8,.9]]*7)
        a,b=ET.fromstring(self.urdf),ET.fromstring(c.urdf)
        j=b.find('joint[@name="tcp_joint"]')
        self.assertEqual(j.find("parent").get("link"),"flange_link")
        self.assertEqual(j.find("origin").get("xyz"),"0 0 0.012")
        for root in (a,b):
            root.remove(root.find('joint[@name="tcp_joint"]'))
        self.assertEqual(ET.tostring(a),ET.tostring(b))
        self.assertEqual(model_bounds(c.urdf),model_bounds(self.urdf))
        self.assertEqual(c.scene,self.scene)
        self.assertEqual(c.manifest,self.reload().manifest)

    def test_manifest_cannot_promote_candidate(self):
        self.prepare()
        p=self.output/"manifest.json"
        m=json.loads(p.read_text());m["physicalExecutionAllowed"]=True
        write_json(p,m)
        with self.assertRaises(ValueError):self.reload()

    def test_changed_scene_rejected(self):
        self.prepare()
        (self.output/"scene.cdr").write_bytes(b"changed")
        with self.assertRaises(ValueError):self.reload()

    def test_changed_mesh_rejected(self):
        self.prepare()
        (self.mesh/"link2.stl").write_bytes(b"changed")
        with self.assertRaises(ValueError):self.reload()

    def test_changed_model_rejected_even_with_rewritten_hash(self):
        self.prepare()
        p=self.output/"model.urdf";p.write_bytes(p.read_bytes()+b" ")
        f=self.output/"manifest.json";m=json.loads(f.read_text());m["sha256"]["model.urdf"]=sha(p.read_bytes())
        write_json(f,m)
        with self.assertRaises(ValueError):self.reload()

    def test_existing_candidate_is_not_overwritten(self):
        self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()

    def test_out_of_bounds_historical_pose_rejected(self):
        self.historical["canJointDeg"]=[90.]*7
        write_json(self.pose,self.historical)
        with self.assertRaises(ValueError):self.prepare()

    def test_invalid_firmware_sample_rejected(self):
        self.firmware["controllerRows"][2]["responseAt"]=99.
        write_json(self.fw,self.firmware)
        with self.assertRaises(ValueError):self.prepare()

    def test_non_generic_interpolator_rejected(self):
        xml=self.urdf.replace(b"mock_components/GenericSystem",b"fixture/UnexpectedPlugin")
        (self.source/"model.urdf").write_bytes(xml)
        self.assembly["robotDescriptionSha256"]=sha(xml)
        write_json(self.source/"assembly.json",self.assembly)
        with self.assertRaises(ValueError):self.prepare()

    def test_symlink_must_match_declared_package_source(self):
        path=self.mesh/"link1.stl"
        other=self.root/"other"
        other.mkdir()
        copy_path=other/path.name
        copy_path.write_bytes(path.read_bytes());path.unlink();path.symlink_to(copy_path)
        with self.assertRaises(ValueError):self.prepare()
        c=prepare(self.source,self.fw,self.pose,self.output,
                  mesh_root=self.mesh,mesh_source_root=other)
        self.assertEqual(c.manifest["status"],STATUS)


if __name__=="__main__":
    unittest.main()
