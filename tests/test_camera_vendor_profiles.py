"""Small, hardware-free tests of official StereoDepth profile adoption."""
from pathlib import Path
import sys
import unittest

OAK = Path(__file__).resolve().parents[1] / "scripts/camera/oak"
sys.path.insert(0, str(OAK))
from camera_vendor_profiles import apply_stereo_preset, preset_for_profile


class _Recorder:
    def __init__(self):
        self.calls = []
    def setDefaultProfilePreset(self, v): self.calls.append(("preset", v))
    def setDepthAlign(self, v): self.calls.append(("align", v))
    def setRectification(self, v): self.calls.append(("rectify", v))
    def setLeftRightCheck(self, v): self.calls.append(("lr", v))


class VendorStereoProfileTests(unittest.TestCase):
    def test_preset_order_and_frame_invariants_on_actual_sdk_enums(self):
        import depthai as dai  # import only; NEVER create Pipeline while USB owned
        for app, name in (
            ("balanced", "FAST_ACCURACY"),
            ("detail", "FAST_ACCURACY"),
            ("near", "HIGH_DETAIL"),
            ("robotics", "ROBOTICS"),
        ):
            with self.subTest(app=app):
                stub = _Recorder()
                self.assertEqual(apply_stereo_preset(stub, dai, app), name)
                self.assertEqual(stub.calls, [
                    ("preset", getattr(dai.node.StereoDepth.PresetMode, name)),
                    ("align", dai.StereoDepthConfig.AlgorithmControl.DepthAlign.RECTIFIED_LEFT),
                    ("rectify", True),
                    ("lr", True),
                ])
                self.assertEqual(len(stub.calls), 4)

    def test_unknown_profile_fails_closed_before_touching_stereo(self):
        import depthai as dai
        stub = _Recorder()
        with self.assertRaises(ValueError):
            apply_stereo_preset(stub, dai, "experimental_ir_unsupported")
        self.assertEqual(stub.calls, [])
        self.assertEqual(preset_for_profile("near"), "HIGH_DETAIL")

    def test_decimated_depth_metadata_stays_in_its_own_frame(self):
        import depthai as dai
        from camera_optics import describe_output_transform
        left_k = [[400., 0., 317.], [0., 400., 189.], [0., 0., 1.]]
        tr = dai.ImgTransformation(640, 400, left_k)
        class Frame:
            def getTransformation(self): return tr
        data = describe_output_transform(Frame(), 640, 400, "stereo_depth")
        self.assertEqual(data["resolution"], [640, 400])
        self.assertEqual(data["K"], left_k)
        self.assertEqual(data["frame_of_reference"], "stereo_left_rectified_optical")
        with self.assertRaises(ValueError):
            describe_output_transform(Frame(), 1280, 800, "stereo_depth")


if __name__ == "__main__":
    unittest.main()
