"""Explicit local synthetic ROS test, never joins the station's domains.

Run using system Python with ROS Jazzy sourced. Only fixture messages are
published, in an unused local domain. No installed driver or camera is opened.
"""
import os
from pathlib import Path
import tempfile
import time
import unittest

from vision_station.luxonis import atomic_json
from vision_station.ros_luxonis import Observer, configured_profile


class SyntheticObserverTest(unittest.TestCase):
    def test_whitelisted_saved_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"profile.yaml"
            p.write_text('/oak:\n  ros__parameters:\n    rgb:\n      i_fps: 15.0\n      serial: secret\n    driver:\n      i_enable_ir: false\n      r_floodlight_intensity: 0.1\n      i_pipeline_auto_calibration_mode: OFF\n')
            self.assertEqual(configured_profile(p,"/oak"),{"rgb.i_fps":15.0,"driver.i_enable_ir":False,"driver.r_floodlight_intensity":.1})
            self.assertIsNone(configured_profile(p,"/oak800"))


    def test_read_parameters_rgb_depth_and_expire_viewer(self):
        self.assertEqual(os.environ.get("ROS_LOCALHOST_ONLY"),"1")
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.signals import SignalHandlerOptions
        from sensor_msgs.msg import Image
        from rclpy.qos import qos_profile_sensor_data
        domain=219
        context=Context()
        rclpy.init(args=[],context=context,domain_id=domain,signal_handler_options=SignalHandlerOptions.NO)
        probe=rclpy.create_node("vision_fixture_probe",context=context,enable_rosout=False,start_parameter_services=False)
        executor=SingleThreadedExecutor(context=context)
        executor.add_node(probe)
        try:
            end=time.monotonic()+1.5
            while time.monotonic()<end:executor.spin_once(timeout_sec=.05)
            if any(n!="vision_fixture_probe" for n,_ns in probe.get_node_names_and_namespaces()):
                self.fail("fixture domain already occupied")
            driver=rclpy.create_node("oak",context=context,enable_rosout=False)
            executor.add_node(driver)
            driver.declare_parameter("rgb.i_fps",15.0)
            driver.declare_parameter("rgb.r_set_man_focus",False)
            driver.declare_parameter("driver.i_enable_ir",False)
            pub={s:driver.create_publisher(Image,"/oak/"+("rgb" if s=="rgb" else "stereo")+"/image_raw",qos_profile_sensor_data)
                 for s in ("rgb","depth")}
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                o=Observer(root,{},domains=[domain])
                try:
                    end=time.monotonic()+12
                    result=None
                    while time.monotonic()<end:
                        executor.spin_once(timeout_sec=.02)
                        atomic_json(root/"viewer.json",{"requestedAt":time.time()},256)
                        for stream,p in pub.items():
                            msg=Image()
                            msg.header.stamp=driver.get_clock().now().to_msg()
                            msg.header.frame_id="synthetic_optical"
                            msg.width=32;msg.height=24
                            msg.encoding="bgr8" if stream=="rgb" else "16UC1"
                            msg.step=32*(3 if stream=="rgb" else 2)
                            msg.data=bytes([30,90,180])*768 if stream=="rgb" else bytes([0x20,0x03])*768
                            p.publish(msg)
                        result=o.step(bindings=((domain,"/oak"),))
                        if all(result["frames"].values()) and result["settings"].get("rgb.i_fps")==15.0:break
                        time.sleep(.04)
                    self.assertEqual(result["graph"],"ACTIVE")
                    self.assertEqual(result["settings"].get("rgb.i_fps"),15.0)
                    self.assertTrue(all(result["frames"].values()),result["endpoints"])
                    self.assertEqual(result["frames"]["depth"]["encoding"],"16UC1")
                    (root/"viewer.json").unlink()
                    stopped=o.step(bindings=((domain,"/oak"),))
                    self.assertEqual(stopped["frames"],{"rgb":None,"depth":None})
                    self.assertFalse(o.subs)
                finally:o.close()
            executor.remove_node(driver);driver.destroy_node()
        finally:
            executor.remove_node(probe);executor.shutdown();probe.destroy_node();context.try_shutdown()


if __name__=="__main__":
    unittest.main()
