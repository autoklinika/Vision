"""Diagnostic NERO ROS owner plus explicit standalone CAN connection."""
import os
from threading import RLock
import rclpy
from rclpy.executors import ExternalShutdownException
from agx_arm_ctrl.vision_nero_guarded_node import VisionNeroGuardedNode
from .nero_can_connection import CanConnectionOwner,CanConnectionServer

SOCKET="/run/user/1000/vision-nero-can-owner/connect.sock"

class IndependentCanOwner(VisionNeroGuardedNode):
    def __init__(self):
        self._can_tx_lock=RLock()
        self._connection_server=None
        super().__init__()
        self._connection_server=CanConnectionServer(SOCKET,CanConnectionOwner(self,self._can_tx_lock))

    def _controlled_stop_hold_callback(self,request,response):
        with self._can_tx_lock:
            return super()._controlled_stop_hold_callback(request,response)

    def _guarded_trajectory_callback(self,msg):
        with self._can_tx_lock:
            return super()._guarded_trajectory_callback(msg)

    def destroy_node(self):
        if self._connection_server is not None:self._connection_server.close()
        with self._can_tx_lock:
            return super().destroy_node()

def main():
    os.umask(0o077)
    rclpy.init()
    node=None
    try:
        node=IndependentCanOwner()
        rclpy.spin(node)
    except (KeyboardInterrupt,ExternalShutdownException):pass
    finally:
        if node is not None:node.destroy_node()
        rclpy.try_shutdown()

if __name__=="__main__":main()
