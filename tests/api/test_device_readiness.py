"""Offline diagnostic evidence tests; no ROS service calls or hardware access."""
from pathlib import Path
from types import SimpleNamespace as NS
import json
import math
import tempfile
import unittest
from unittest.mock import patch

from vision_station.readiness import (
    JOINTS, Observation, arm, motors, joints, nero_observation, rgbd_observation,
    planning_observation, device_observation, read_snapshot, write_snapshot,
)
from vision_station.ros_readiness import image_stamp, unique_publisher
from vision_station.inspection import DEVICES, DeviceStatus, validate_inspection_report
from vision_station.host import CoreHost

NOW = 100.0
STAMP = 99.5
HEADER = NS(stamp=NS(sec=99,nanosec=500_000_000), frame_id="camera")
POSITIONS = tuple(float(i)/10 for i in range(7))


def diagnostic(fields, *, name="arm", hardware_id="can0:arm", level=b"\x00"):
    return NS(name=name, hardware_id=hardware_id, level=level,
              values=[NS(key=k,value=v) for k,v in fields.items()])


def arm_message(code="0", error="0", level=b"\x00", header=HEADER):
    return NS(header=header,status=[diagnostic({
        "arm_status":code,"err_status":error,
        "joint_angle_limit":json.dumps([False]*7),
        "communication_status_joint":json.dumps([False]*7),
    },level=level)])


def motor_message(enabled="true", level=b"\x00"):
    return NS(header=HEADER,status=[diagnostic({"enabled":enabled},name=n,
        hardware_id=f"can0:{i}",level=level) for i,n in enumerate(JOINTS,1)])


def joint_message():
    return NS(header=HEADER,name=list(JOINTS),position=POSITIONS)


class ReadinessTests(unittest.TestCase):
    def test_nero_normal_and_current_fault(self):
        j = joints(joint_message(),NOW)
        a = arm(arm_message(),NOW)
        m = motors(motor_message(),NOW)
        self.assertEqual(nero_observation(j,a,m,NOW).state,"READY")
        self.assertEqual(nero_observation(j,arm(arm_message("6",level=b"\x02"),NOW),None,NOW).reason,
                         "ARM_BRAKE_NOT_RELEASED")
        self.assertEqual(nero_observation(j,arm(arm_message(error="1"),NOW),m,NOW).reason,"ARM_FAULT")
        self.assertEqual(nero_observation(j,a,motors(motor_message("false"),NOW),NOW).reason,"MOTORS_NOT_ENABLED")
        self.assertEqual(nero_observation(j,a,None,NOW).reason,"MOTOR_STATUS_UNVERIFIED")

    def test_stale_future_invalid_and_partial_evidence(self):
        self.assertIsNone(joints(joint_message(),102.0))
        self.assertIsNone(joints(joint_message(),99.0))
        self.assertIsNone(joints(NS(header=HEADER,name=JOINTS,position=[math.nan]*7),NOW))
        self.assertIsNone(joints(NS(header=HEADER,name=JOINTS[:-1],position=POSITIONS[:-1]),NOW))
        self.assertIsNone(arm(arm_message(level=b"\x03"),NOW))
        self.assertIsNone(motors(motor_message(level=b"\x03"),NOW))
        self.assertEqual(nero_observation(None,None,None,NOW).state,"UNKNOWN")
        self.assertEqual(nero_observation((STAMP,POSITIONS),(STAMP,"ARM_FAULT"),None,103).state,"UNKNOWN")

    def test_rgbd_and_planning_require_fresh_consistent_inputs(self):
        self.assertEqual(rgbd_observation(99.5,99.8,NOW).state,"READY")
        self.assertEqual(rgbd_observation(99.0,99.8,NOW).state,"UNKNOWN")
        self.assertEqual(rgbd_observation(99.5,None,NOW).state,"UNKNOWN")
        j = (STAMP,POSITIONS)
        self.assertEqual(planning_observation(j,j,STAMP,NOW).state,"READY")
        self.assertEqual(planning_observation(j,None,STAMP,NOW).reason,"SCENE_UNVERIFIED")
        self.assertEqual(planning_observation(j,j,97,NOW).reason,"ROBOT_TF_UNVERIFIED")
        self.assertEqual(planning_observation(j,(STAMP,(0,)*7),STAMP,NOW).state,"UNKNOWN")

    def test_image_metadata_and_depth_pixels(self):
        rgb=NS(header=HEADER,width=2,height=1,step=6,encoding="bgr8",is_bigendian=0,data=bytes(6))
        depth=NS(header=HEADER,width=2,height=1,step=4,encoding="16UC1",is_bigendian=0,data=b"\x00\x00\x10\x00")
        self.assertEqual(image_stamp(rgb,NOW),STAMP)
        self.assertEqual(image_stamp(depth,NOW,depth=True),STAMP)
        depth.data=bytes(4)
        self.assertIsNone(image_stamp(depth,NOW,depth=True))
        rgb.data=bytes(5)
        self.assertIsNone(image_stamp(rgb,NOW))

    def test_expected_unique_ros_publisher(self):
        good=NS(node_namespace="/nero_guarded",node_name="agx_arm_ctrl_single_node",endpoint_gid=[1,2,3])
        node=NS(get_publishers_info_by_topic=lambda _: [good])
        self.assertEqual(unique_publisher(node,"/test","/nero_guarded/agx_arm_ctrl_single_node"),(1,2,3))
        self.assertIsNone(unique_publisher(node,"/test","/other"))
        node.get_publishers_info_by_topic=lambda _: [good,good]
        self.assertIsNone(unique_publisher(node,"/test","/nero_guarded/agx_arm_ctrl_single_node"))

    def test_source_file_freshness_ownership_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"observations.json"
            observations={
                "nero":Observation("ARM_BRAKE_NOT_RELEASED",STAMP),
                "oak":Observation("RGBD_STREAMS_OK",STAMP),
                "oak800":Observation("RGBD_UNVERIFIED",STAMP),
                "moveit":Observation("SCENE_UNVERIFIED",STAMP),
            }
            write_snapshot(path,observations,NOW)
            self.assertEqual(read_snapshot(path,NOW),observations)
            self.assertEqual(read_snapshot(path,106),{})
            self.assertEqual(read_snapshot(path,99),{})
            path.chmod(0o644)
            self.assertEqual(read_snapshot(path,NOW),{})
            path.chmod(0o600)
            link=path.with_name("link")
            link.symlink_to(path)
            self.assertEqual(read_snapshot(link,NOW),{})
            observations["nero"]=Observation("RGBD_STREAMS_OK",STAMP)
            write_snapshot(path,observations,NOW)
            self.assertNotIn("nero",read_snapshot(path,NOW))

    def test_service_state_and_scene_binding(self):
        evidence={"nero":Observation("ARM_BRAKE_NOT_RELEASED",STAMP),
                  "oak":Observation("RGBD_STREAMS_OK",STAMP)}
        self.assertEqual(device_observation("nero","ACTIVE","USB_CAN_DETECTED",evidence,(),NOW).state,"NOT_READY")
        self.assertEqual(device_observation("nero","INACTIVE","USB_CAN_DETECTED",evidence,(),NOW).reason,"SERVICE_INACTIVE")
        self.assertEqual(device_observation("nero","ACTIVE","USB_CAN_NOT_DETECTED",evidence,(),NOW).reason,"USB_MISSING")
        self.assertEqual(device_observation("luxonis","ACTIVE","USB_DETECTED",evidence,("oak",),NOW).state,"READY")
        self.assertEqual(device_observation("luxonis","ACTIVE","USB_DETECTED",evidence,("oak800",),NOW).state,"UNKNOWN")
        self.assertEqual(device_observation("luxonis","ACTIVE","USB_DETECTED",evidence,("oak","oak800"),NOW).reason,"AMBIGUOUS_SCENE")
        self.assertEqual(device_observation("sony","UNKNOWN","USB_DETECTED",evidence,(),NOW).state,"UNKNOWN")
        self.assertEqual(device_observation("nero","ACTIVE","USB_CAN_DETECTED",evidence,(),106).state,"UNKNOWN")

    def test_diagnostic_report_does_not_authorize_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("vision_station.inspection.time.time",return_value=NOW):
                host=CoreHost(Path(directory)/"library",diagnostics=lambda:tuple(
                    DeviceStatus(d,"ACTIVE","NOT_READY" if d=="nero" else "UNKNOWN",NOW,"UNKNOWN",
                        "ARM_BRAKE_NOT_RELEASED" if d=="nero" else "OBSERVER_UNAVAILABLE") for d in DEVICES))
                report=host.inspection_report()
            self.assertTrue(validate_inspection_report(report))
            self.assertFalse(report["startAllowed"])
            self.assertEqual(report["devices"][1]["readinessReason"],"ARM_BRAKE_NOT_RELEASED")
            report["devices"][0]["readinessReason"]="ARM_FAULT"
            self.assertFalse(validate_inspection_report(report))


if __name__ == "__main__":
    unittest.main()
