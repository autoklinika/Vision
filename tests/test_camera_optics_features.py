"""Offline optical/IR/AF/ROI checks: NO USB opening or real LED commands."""
import sys
import unittest
from pathlib import Path

import cv2
import depthai as dai
import numpy as np

OAK = Path(__file__).resolve().parents[1] / "scripts/camera/oak"
sys.path.insert(0, str(OAK))
from camera_optics import (
    OpticalMetadataError, describe_output_transform,
    roi_from_normalized, crop_diagnostic_jpeg, intrinsics_for_crop,
)
from camera_features import (
    EXPERIMENTAL_PROFILES, get_profile, validate_ir_levels,
    apply_ir_test_levels, reset_ir_test_levels, af_sensor_roi_from_transform,
    make_focus_control,
)


class FakeImgFrame:
    def __init__(self, transform):
        self.transform = transform

    def getTransformation(self):
        return self.transform


class MockIr:
    def __init__(self, fail_flood=False):
        self.calls = []
        self.fail_flood = fail_flood

    def setIrLaserDotProjectorIntensity(self, intensity):
        self.calls.append(("dot", intensity))

    def setIrFloodLightIntensity(self, intensity):
        self.calls.append(("flood", intensity))
        if self.fail_flood:
            raise RuntimeError("IR simulated failure")


class OpticalTests(unittest.TestCase):
    def setUp(self):
        self.k = [[500., 0, 320.], [0, 500., 240.], [0, 0, 1.]]
        self.t = dai.ImgTransformation(640, 480, self.k)

    def test_real_depthai_3_transformation_api_no_usb(self):
        result = describe_output_transform(FakeImgFrame(self.t), 640, 480,
                                           "stereo_depth")
        self.assertEqual(result["frame_of_reference"],
                         "stereo_left_rectified_optical")
        self.assertEqual(result["resolution"], [640, 480])
        self.assertEqual(result["K"], self.k)
        self.assertEqual(result["validity"],
                         "FRAME_METADATA_REPORTED_NOT_METROLOGICALLY_VERIFIED")

    def test_wrong_size_and_bad_k_fail_closed(self):
        with self.assertRaises(OpticalMetadataError):
            describe_output_transform(FakeImgFrame(self.t), 1280, 800, "stereo_depth")
        with self.assertRaises(OpticalMetadataError):
            describe_output_transform(FakeImgFrame(self.t), 640, 480, "something")

    def test_normalized_crop_and_geometry(self):
        self.assertEqual(roi_from_normalized(.25, .25, .5, .5, 640, 480),
                         (160, 120, 320, 240))
        self.assertEqual(intrinsics_for_crop(self.k, (160, 120, 320, 240)),
                         [[500., 0, 160.], [0, 500., 120.], [0, 0, 1.]])
        for args in ((0,0,1.1,1),(0,0,-.3,.2),(.999,.999,.0001,.0001)):
            with self.assertRaises(ValueError):
                roi_from_normalized(*args, 640, 480)

    def test_digital_zoom_jpeg_lossless_geometry(self):
        rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(rgb, (160,120), (479,359), (255,255,255), thickness=-1)
        ok, encoded = cv2.imencode(".jpg", rgb)
        self.assertTrue(ok)
        output, meta = crop_diagnostic_jpeg(encoded.tobytes(),
                                             (.25, .25, .5, .5))
        restored = cv2.imdecode(np.frombuffer(output,dtype=np.uint8),
                                cv2.IMREAD_COLOR)
        self.assertEqual(restored.shape, (240,320,3))
        self.assertEqual(meta["roi_pixels"], [160,120,320,240])
        self.assertEqual(meta["depth_registration"], "NOT_ALIGNED")
        self.assertEqual(meta["zoom_type"], "digital_crop")

    def test_crop_source_transform_scales_roi(self):
        t = dai.ImgTransformation(1280, 800, 1280, 800)
        t.addScale(.5, .5)
        self.assertEqual(af_sensor_roi_from_transform(t, (.25,.25,.5,.5)),
                         (320,200,640,400))


class FeatureTests(unittest.TestCase):
    def test_profiles_are_opt_in(self):
        self.assertEqual(set(EXPERIMENTAL_PROFILES),
                         {"survey", "depth_precision", "detail", "low_light"})
        self.assertTrue(all(not p.hardware_validated for p in
                            EXPERIMENTAL_PROFILES.values()))
        self.assertEqual(get_profile("depth_precision").ir_dot, .15)
        with self.assertRaises(ValueError):
            get_profile("production-unverified")

    def test_ir_range_rejects_unsafe_values(self):
        for pair in ((.4,0),(0,1),(-.01,0),(float("nan"),0)):
            with self.assertRaises(ValueError):
                validate_ir_levels(*pair)

    def test_ir_mock_send_and_reset(self):
        device = MockIr()
        out = apply_ir_test_levels(device,.2,.1)
        self.assertEqual(out["status"],
                         "COMMAND_SENT_NOT_PHOTOMETRICALLY_VERIFIED")
        self.assertEqual(reset_ir_test_levels(device),[])
        self.assertEqual(device.calls, [("dot",.2),("flood",.1),
                                        ("dot",0.0),("flood",0.0)])

    def test_ir_second_command_failure_resets_dot(self):
        device = MockIr(fail_flood=True)
        with self.assertRaises(RuntimeError):
            apply_ir_test_levels(device,.2,.1)
        self.assertEqual(device.calls[-1], ("dot",0.0))

    def test_af_message_builds_using_installed_depthai(self):
        control = make_focus_control(dai, "auto", sensor_roi=(10,20,60,70))
        self.assertIsInstance(control, dai.CameraControl)
        self.assertIsInstance(make_focus_control(dai, "continuous_video"),
                              dai.CameraControl)
        with self.assertRaises(ValueError):
            make_focus_control(dai, "flight")

if __name__ == "__main__":
    unittest.main()
