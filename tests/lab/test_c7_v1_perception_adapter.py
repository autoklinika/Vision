"""Strict C7 Perception input integration tests, no hardware or ROS imports."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ADAPTER=load(ROOT/"scripts/lab/c7_v1_perception_adapter.py","vision_c7_v1_adapter")
GENERATOR=load(ROOT/"scripts/lab/c7_v1_photo_viewpoints.py","vision_c7_v1_generator")


class TestPerceptionToPhotoScene(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((ROOT/"examples/lab/etc3_synthetic_perception_pcb_table.json").read_text())
        self.profile=json.loads((ROOT/"config/lab/c7_v1_sony_tool_planonly.json").read_text())

    def test_synthetic_perception_to_ten_views(self):
        result=ADAPTER.import_observation(self.fixture)
        self.assertEqual(result["status"],"UNAPPROVED_PCB_SCENE_READY_FOR_OFFLINE_VIEWPOINTS")
        scene=result["scene"]
        self.assertEqual(scene["evidence_kind"],"synthetic_fixture")
        self.assertEqual(scene["scenario_id"],"C7_ETC3_POC_SYNTHETIC_GEOMETRY_001")
        out=GENERATOR.generate(self.profile,scene)
        self.assertEqual(out["candidate_count"],10)
        self.assertFalse(out["physical_execution_allowed"])
        self.assertFalse(out["IK_solved"])

    def test_camera_only_original_contract_fails_closed(self):
        sample={
          "schema_version":"perception.scene_observation.v1",
          "source_bundle_id":"real-ecu-xyz",
          "table_frame":{"status":"UNAVAILABLE"},
          "robot_base_frame":{"status":"UNAVAILABLE"},
          "frame_of_reference":"stereo_left_rectified_optical",
          "safety_function":False,
          "objects":[{"object_id":"unknown_1","class":"unknown_object",
                      "position_camera_m":[0.01,0.02,0.79]}],
          "validity":"EXPLORATORY_UNVERIFIED_PROJECTION"
        }
        result=ADAPTER.import_observation(sample)
        self.assertEqual(result["status"],"BLOCKED_CAMERA_FRAME_ONLY")
        self.assertIsNone(result["PCB_table_scene"])
        self.assertFalse(result["MoveIt_targets_generated"])
        self.assertIn("TABLE_FRAME_UNAVAILABLE",result["reason_codes"])

    def test_historical_real_etc3_camera_geometry_is_not_pcb(self):
        summary={
          "status":"REPLAY_COMPLETE_NOT_METROLOGICALLY_VALIDATED",
          "frames_total":25,"frames_geometry_detected":25,
          "camera_frame":"stereo_left_rectified_optical",
          "table_frame":"UNAVAILABLE","robot_base_frame":"UNAVAILABLE",
          "metrology_verified":False,
          "stats":{
            "core_footprint_length_mm":{"median":274.19},
            "core_footprint_width_mm":{"median":224.13},
            "height_visible_envelope_p99_mm":{"median":51.32}
          }
        }
        result=ADAPTER.import_legacy_etc3({"summary":summary},source_path="private")
        self.assertEqual(result["status"],"BLOCKED_HISTORICAL_ETC3_VISIBLE_PCB_UNSEGMENTED_CAMERA_ONLY")
        self.assertIn("OPEN_PCB_VISIBLE_IN_RGB_BUT_NOT_SEGMENTED_IN_DEPTH",result["reason_codes"])
        self.assertIsNone(result["PCB_table_scene"])
        self.assertFalse(result["physical_execution_allowed"])

    def test_missing_coordinate_reference_rejected(self):
        bad=copy.deepcopy(self.fixture)
        bad["frame_of_reference"]="stereo_left_rectified_optical"
        with self.assertRaises(ADAPTER.BlockedInput):
            ADAPTER.import_observation(bad)

    def test_body_label_cannot_be_used_as_pcb(self):
        for key,val in (("object_class","ECU_HOUSING"),("pcb_surface","CASE_LID")):
            bad=copy.deepcopy(self.fixture)
            bad[key]=val
            with self.subTest(key=key),self.assertRaises(ADAPTER.BlockedInput):
                ADAPTER.import_observation(bad)

    def test_bad_calibration_claims_and_missing_provenance(self):
        for key,val in (("calibration_approved",True),
                        ("source_artifact_sha256","short"),
                        ("source_bundle_id",""),
                        ("safety_function",True)):
            bad=copy.deepcopy(self.fixture);bad[key]=val
            with self.subTest(key=key),self.assertRaises(ADAPTER.BlockedInput):
                ADAPTER.import_observation(bad)

    def test_fixture_cannot_masquerade_as_real(self):
        bad=copy.deepcopy(self.fixture);bad["source_kind"]="vision_perception_candidate"
        with self.assertRaises(ADAPTER.BlockedInput):
            ADAPTER.import_observation(bad)
        bad=copy.deepcopy(self.fixture);bad["fixture_only"]=False
        with self.assertRaises(ADAPTER.BlockedInput):
            ADAPTER.import_observation(bad)

    def test_nan_dimension_or_nonpositive_pcb_extent_rejected(self):
        for field,val in (("size_xy_mm",[-2,80]),("size_xy_mm",[120,float("nan")]),
                          ("center_table_xy_mm",[float("inf"),410])):
            bad=copy.deepcopy(self.fixture);bad["pcb"][field]=val
            with self.subTest(field=field,val=str(val)),self.assertRaises(ADAPTER.BlockedInput):
                ADAPTER.import_observation(bad)

    def test_physical_execution_field_is_never_output(self):
        raw=copy.deepcopy(self.fixture)
        raw["execution_allowed"]=True
        result=ADAPTER.import_observation(raw)
        self.assertFalse(result["execution_allowed"])
        self.assertNotIn("execution_allowed",result["scene"])
        generator=GENERATOR.generate(self.profile,result["scene"])
        self.assertFalse(generator["physical_execution_allowed"])


if __name__=="__main__":unittest.main()
