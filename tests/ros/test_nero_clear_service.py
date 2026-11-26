"""Typed ROS 2 service test in isolated domain 219. No SDK/CAN imports."""
import os
import threading
import time
import unittest

from vision_station.nero_clear import ClearEngine,Evidence,validate_result,SERVICE
from vision_station.ros_nero_clear import binding,call
from vision_station.ros_nero_guarded_diagnostics import to_message

class ClearServiceTest(unittest.TestCase):
    def test_actual_typed_service_and_duplicate_provider(self):
        self.assertEqual(os.environ.get("ROS_LOCALHOST_ONLY"),"1")
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.signals import SignalHandlerOptions
        from vision_nero_diagnostics_interfaces.srv import ClearJointErrors
        ctx=Context()
        rclpy.init(args=[],context=ctx,domain_id=219,signal_handler_options=SignalHandlerOptions.NO)
        driver=rclpy.create_node("agx_arm_ctrl_single_node",namespace="/nero_guarded",context=ctx)
        client=rclpy.create_node("nero_clear_fixture_client",context=ctx)
        executor=SingleThreadedExecutor(context=ctx);executor.add_node(client)
        owner=SingleThreadedExecutor(context=ctx);owner.add_node(driver)
        calls=[]
        def read():
            stamp=time.time()-.001
            return Evidence(stamp,6,0,(0 if calls else 4,0,0,0,0,0,0),(stamp,)*7)
        engine=ClearEngine(read=read,clear=lambda scope:calls.append(scope),interlock=lambda:True,
                           consume_approval=lambda op,scope:True,commissioned=True)
        def callback(req,response):
            v=engine.execute(req.operation_id,req.scope,req.not_after)
            response.operation_id=v["operationId"];response.scope=v["scope"];response.result=v["result"];response.reason=v["reason"]
            response.command_invoked=v["commandInvoked"];response.sent_after=v["sentAfter"] or 0.
            response.axis_results=v["axisResults"]
            response.before=to_message(v["before"],response.before)
            response.after=to_message(v["after"],response.after)
            return response
        driver.create_service(ClearJointErrors,"diagnostics/clear_joint_errors",callback)
        stop=threading.Event()
        def spin():
            while not stop.is_set():owner.spin_once(timeout_sec=.03)
        thread=threading.Thread(target=spin);thread.start()
        duplicate=None
        try:
            deadline=time.monotonic()+3
            while not binding(client) and time.monotonic()<deadline:executor.spin_once(timeout_sec=.05)
            self.assertTrue(binding(client))
            v=call(client,executor,"c"*32,1,time.time()+7,time.monotonic()+6)
            self.assertTrue(validate_result(v));self.assertEqual(v["result"],"CLEARED");self.assertEqual(calls,[1])
            duplicate=rclpy.create_node("untrusted_duplicate",context=ctx)
            duplicate.create_service(ClearJointErrors,SERVICE,callback)
            end=time.monotonic()+3
            while binding(client) and time.monotonic()<end:executor.spin_once(timeout_sec=.05)
            self.assertFalse(binding(client))
            v=call(client,executor,"d"*32,1,time.time()+7,time.monotonic()+4.3)
            self.assertEqual(v["result"],"REJECTED");self.assertEqual(calls,[1])
        finally:
            stop.set();thread.join(3);executor.shutdown();owner.shutdown()
            if duplicate is not None:duplicate.destroy_node()
            client.destroy_node();driver.destroy_node();rclpy.shutdown(context=ctx)

if __name__=="__main__":unittest.main()
