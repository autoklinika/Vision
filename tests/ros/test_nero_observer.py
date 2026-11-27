"""Explicit synthetic NERO ROS integration, never joins real domain 181.

Only fixture feedback publishers and a read-only parameter server exist.
"""
import os
import time
import unittest

from vision_station.nero import JOINTS, FLAGS, PARAMS, NODE, valid_observation
from vision_station.ros_nero import Observer


class NeroObserverTest(unittest.TestCase):
    def test_read_only_feedback_and_lost_source(self):
        self.assertEqual(os.environ.get("ROS_LOCALHOST_ONLY"),"1")
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import QoSProfile
        from sensor_msgs.msg import JointState
        from diagnostic_msgs.msg import DiagnosticArray,DiagnosticStatus,KeyValue
        import json
        context=Context()
        rclpy.init(args=[],context=context,domain_id=219,signal_handler_options=SignalHandlerOptions.NO)
        executor=SingleThreadedExecutor(context=context)
        observer_node=rclpy.create_node("nero_fixture_observer",context=context,enable_rosout=False,start_parameter_services=False)
        executor.add_node(observer_node)
        o=Observer(observer_node,can=lambda:None)
        driver=None
        try:
            until=time.monotonic()+1.5
            while time.monotonic()<until:executor.spin_once(timeout_sec=.05)
            self.assertEqual(observer_node.get_node_names_and_namespaces(),[("nero_fixture_observer","/")])
            driver=rclpy.create_node("agx_arm_ctrl_single_node",namespace="/nero_guarded",context=context,enable_rosout=False)
            executor.add_node(driver)
            for key in PARAMS:driver.declare_parameter(key,key=="physical_hold_enabled")
            qos=QoSProfile(depth=1)
            pj=driver.create_publisher(JointState,"feedback/joint_states",qos)
            pa=driver.create_publisher(DiagnosticArray,"feedback/arm_status",qos)
            pm=driver.create_publisher(DiagnosticArray,"feedback/motor_status",qos)
            def status(name,hardware,lvl,fields):
                return DiagnosticStatus(name=name,hardware_id=hardware,level=bytes([lvl]),
                                        values=[KeyValue(key=k,value=v) for k,v in fields.items()])
            def publish():
                j=JointState(name=list(JOINTS),position=[.1]*7,velocity=[0.]*7,effort=[0.]*7)
                j.header.stamp=driver.get_clock().now().to_msg()
                pj.publish(j)
                a=DiagnosticArray(status=[status("arm","can0:arm",2,{
                    "ctrl_mode":"1","arm_status":"6","mode_feedback":"1",
                    "teach_status":"0","motion_status":"0","trajectory_num":"0","err_status":"0",
                    "joint_angle_limit":json.dumps([False]*7),
                    "communication_status_joint":json.dumps([False]*7)})])
                a.header.stamp=driver.get_clock().now().to_msg();pa.publish(a)
                m=DiagnosticArray(status=[status(n,f"can0:{i}",0,{
                    "enabled":"false",**dict.fromkeys(FLAGS,"false"),"status_raw":"0",
                    "bus_voltage_v":"24.1","driver_temp_deg":"30","motor_temp_deg":"25","bus_current":"0.0"})
                    for i,n in enumerate(JOINTS,1)])
                m.header.stamp=driver.get_clock().now().to_msg();pm.publish(m)
            end=time.monotonic()+10
            while time.monotonic()<end:
                publish();executor.spin_once(timeout_sec=.02)
                v=o.step()
                if all(v[k] is not None for k in ("joints","arm","motors","parameters")):break
                time.sleep(.02)
            self.assertTrue(valid_observation(v));self.assertEqual(v["graph"],"ACTIVE")
            self.assertEqual(v["arm"]["armStatus"],6)
            self.assertEqual(v["joints"]["rows"][6]["positionRad"],.1)
            self.assertFalse(v["motors"]["rows"][0]["enabled"])
            self.assertEqual(v["parameters"]["values"],dict(zip(PARAMS,(False,False,True))))
            readers=dict(o.subs)
            end=time.monotonic()+.8
            while time.monotonic()<end:
                publish();executor.spin_once(timeout_sec=.02)
                self.assertEqual(o.step()["graph"],"ACTIVE")
                self.assertEqual(o.subs,readers)
            executor.remove_node(driver);driver.destroy_node();driver=None
            end=time.monotonic()+4
            while time.monotonic()<end:
                executor.spin_once(timeout_sec=.05)
                v=o.step()
                if v["graph"]=="NO_NODE":break
            self.assertEqual(v["graph"],"NO_NODE")
            self.assertTrue(all(v[k] is None for k in ("joints","arm","motors","parameters")))
            self.assertFalse(o.subs)
        finally:
            o.reset()
            if driver is not None:executor.remove_node(driver);driver.destroy_node()
            executor.remove_node(observer_node);observer_node.destroy_node()
            executor.shutdown();context.try_shutdown()


if __name__=="__main__":
    unittest.main()
