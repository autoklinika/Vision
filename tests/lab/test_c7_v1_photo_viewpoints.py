"""C7 V1 LAB-only tests. No ROS, network or robot access."""
import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/lab/c7_v1_photo_viewpoints.py"
SPEC = importlib.util.spec_from_file_location("vision_c7_v1_photo", MODULE)
PHOTO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PHOTO)


class C7V1ViewpointsTest(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "config/lab/c7_v1_sony_tool_planonly.json").read_text())
        self.scene = json.loads((ROOT / "examples/lab/etc3_synthetic_scene.json").read_text())

    def test_safety_first_zoom_policy_does_not_authorize_motion(self):
        p = self.profile["design_priorities"]
        self.assertFalse(p["photographic_positioning_accuracy_1mm_required"])
        self.assertTrue(p["optical_zoom_allowed_for_framing"])
        self.assertFalse(p["zoom_substitutes_collision_check"])
        self.assertFalse(p["zoom_substitutes_focus_check"])
        self.assertTrue(p["prefer_clear_standoff_over_close_up"])
        self.assertIsNone(p["required_clearance_margin_mm"])
        self.assertTrue(p["clearance_margin_must_exceed_combined_geometry_uncertainty"])
        self.assertTrue(p["full_trajectory_obstacle_checks_required"])
        self.assertTrue(p["conservative_tool_model_required"])
        self.assertEqual(p["accepted_laboratory_stop_mode"], "supervised_software_HOLD")
        self.assertFalse(self.profile["execution_policy"]["allow_trajectory_execution"])
        self.assertFalse(self.profile["execution_policy"]["send_robot_commands"])

    def test_five_views_two_azimuths_and_fail_closed(self):
        output = PHOTO.generate(self.profile, self.scene)
        self.assertEqual(output["status"], "OFFLINE_VIEWPOINT_CANDIDATES_ONLY")
        self.assertEqual(output["candidate_count"], 10)
        self.assertEqual(output["views_requested"], 5)
        self.assertEqual(output["scene_evidence_kind"], "synthetic_fixture")
        self.assertFalse(output["physical_execution_allowed"])
        self.assertFalse(output["IK_solved"])
        self.assertFalse(output["MoveIt_planning_executed"])
        self.assertFalse(output["active_TF_published"])
        self.assertTrue(output["table_to_base_tf_not_approved"])
        self.assertTrue(output["real_optical_center_not_calibrated"])
        for c in output["candidates"]:
            self.assertFalse(c["execution_allowed"])
            self.assertFalse(c["trajectory_generated"])
            self.assertFalse(c["collision_checked"])
            self.assertFalse(c["inverse_kinematics_checked"])
            self.assertEqual(c["link7_IK_candidate"]["header_frame_id"], "base_link")
            self.assertEqual(c["link7_IK_candidate"]["link_name"], "link7")
            self.assertEqual(c["sony_optical_direction_table_unit"], [0, 0, -1])
            self.assertEqual(c["camera_lens_front_center_table_xyz_mm"][2], 275)
            q = c["link7_IK_candidate"]["quaternion_xyzw"]
            self.assertAlmostEqual(sum(v*v for v in q), 1.0, places=8)

    def test_center_and_four_quadrants_on_synthetic_board(self):
        output = PHOTO.generate(self.profile, self.scene)
        view = {}
        for candidate in output["candidates"]:
            view.setdefault(candidate["view_id"], []).append(candidate)
        self.assertEqual(set(view), {"center", "front_left", "front_right", "back_right", "back_left"})
        expected = {
            "center": [750.0, 410.0],
            "front_left": [716.4, 387.6],
            "front_right": [783.6, 387.6],
            "back_right": [783.6, 432.4],
            "back_left": [716.4, 432.4]
        }
        for name, points in view.items():
            self.assertEqual(len(points), 2)
            self.assertEqual([v["mount_signed_azimuth_assumption_deg"] for v in points], [90, -90])
            for a, b in zip(points[0]["target_pcb_table_xy_mm"], expected[name]):
                self.assertAlmostEqual(a, b, places=5)
            self.assertEqual(points[0]["camera_lens_front_center_table_xyz_mm"],
                             points[1]["camera_lens_front_center_table_xyz_mm"])
            self.assertNotEqual(points[0]["link7_IK_candidate"]["quaternion_xyzw"],
                                points[1]["link7_IK_candidate"]["quaternion_xyzw"])

    def test_board_yaw_90_rotates_view_pattern_not_camera_optical_z(self):
        altered = copy.deepcopy(self.scene)
        altered["pcb"]["yaw_table_deg"] = 90
        out = PHOTO.generate(self.profile, altered)
        a = next(x for x in out["candidates"] if x["view_id"] == "front_left")
        self.assertAlmostEqual(a["target_pcb_table_xy_mm"][0], 772.4, places=5)
        self.assertAlmostEqual(a["target_pcb_table_xy_mm"][1], 376.4, places=5)
        self.assertEqual(a["sony_optical_direction_table_unit"], [0, 0, -1])

    def test_production_authorization_is_rejected(self):
        for key in ("allow_trajectory_execution", "send_robot_commands", "publish_static_tf",
                    "activate_production_profile", "use_for_collision_safety"):
            bad = copy.deepcopy(self.profile)
            bad["execution_policy"][key] = True
            with self.subTest(key=key), self.assertRaises(PHOTO.InputError):
                PHOTO.generate(bad, self.scene)

    def test_missing_or_bad_transform_rejected(self):
        bad = copy.deepcopy(self.profile)
        bad["candidate_T_table_base_link"][0][0] = 2
        with self.assertRaises(PHOTO.InputError):
            PHOTO.generate(bad, self.scene)
        bad = copy.deepcopy(self.profile)
        bad["candidate_T_table_base_link_approved"] = True
        with self.assertRaises(PHOTO.InputError):
            PHOTO.generate(bad, self.scene)

    def test_unknown_yaw_and_axial_offsets_not_silently_approved(self):
        for name, change in (
            ("azimuth", {"signed_azimuth_options_deg": [90]}),
            ("axial", {"flange_to_socket_axial_offset_mm": 10}),
            ("socket_plusZ", {"socket_plusZ_relative_flange_plusZ": -1}),
            ("physical", {"axial_offset_physically_verified": True})
        ):
            bad = copy.deepcopy(self.profile)
            bad["tool_hypothesis"].update(change)
            with self.subTest(name=name), self.assertRaises(PHOTO.InputError):
                PHOTO.generate(bad, self.scene)

    def test_invalid_physical_coordinates_rejected(self):
        inputs = [
            ("out_of_table", ("pcb", "center_table_xy_mm"), [1600, 200]),
            ("wrong_height", ("pcb", "top_z_mm"), -1),
            ("negative_size", ("pcb", "size_xy_mm"), [-120, 80]),
            ("zero_distance", ("camera", "lens_front_working_distance_mm"), 0),
            ("nan_distance", ("camera", "lens_front_working_distance_mm"), float("nan")),
            ("bad_fraction", ("camera", "quadrant_fraction"), 0.5)
        ]
        for name, keys, val in inputs:
            s = copy.deepcopy(self.scene)
            s[keys[0]][keys[1]] = val
            with self.subTest(name=name), self.assertRaises(PHOTO.InputError):
                PHOTO.generate(self.profile, s)

    def test_scene_evidence_must_be_declared(self):
        bad = copy.deepcopy(self.scene)
        bad["evidence_kind"] = "assumed_to_be_measured"
        with self.assertRaises(PHOTO.InputError):
            PHOTO.generate(self.profile, bad)

    def test_execution_instruction_in_scene_is_rejected(self):
        for key in ("execute", "execution", "allow_trajectory_execution", "move_robot", "publish_tf"):
            bad = copy.deepcopy(self.scene)
            bad[key] = True
            with self.subTest(key=key), self.assertRaises(PHOTO.InputError):
                PHOTO.generate(self.profile, bad)

    def test_deterministic_json_hashes(self):
        a = PHOTO.generate(self.profile, self.scene)
        b = PHOTO.generate(self.profile, self.scene)
        self.assertEqual(a, b)
        self.assertEqual(len(a["source_profile_sha256"]), 64)
        self.assertEqual(len(a["source_scene_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
