"""Optional candidate receiver inside the existing guarded ROS owner.

This is a non-actuating integration. It reads the current SDK cache and uses
the existing arbiter; it never sends anything to the SDK. There is no launch
entrypoint and no second CAN owner. Bind only as part of owner commissioning.
"""
from .nero_servo_bridge import LockedBridge

TOPIC="/vision_servo/candidate_trajectory"
SERVO_NODE="/vision_servo/servo_node"
TYPE="trajectory_msgs/msg/JointTrajectory"


def publisher_identity(node,topic=TOPIC,source=SERVO_NODE):
    """Bind one uniquely identified Servo publisher, not a generic topic."""
    try:
        names=[ns.rstrip("/")+"/"+name for name,ns in node.get_node_names_and_namespaces()]
        endpoints=node.get_publishers_info_by_topic(topic)
        # ServoNode creates internal nodes with the same name. The actual
        # output endpoint must be unique, and its GID must match the sample.
        if source not in names or len(endpoints)!=1:return None
        ep=endpoints[0]
        if ep.node_namespace.rstrip("/")+"/"+ep.node_name!=source or ep.topic_type!=TYPE:return None
        return tuple(ep.endpoint_gid)
    except Exception:return None


def owner_feedback(owner):
    """Read only the SDK caches that the guarded callback already consumes."""
    arm_status,errors=owner._get_status_string()
    f=owner.agx_arm.get_joint_angles()
    return {"arm_status":arm_status,"firmware_error_mask":errors,
            "feedback_stamp":float(f.timestamp) if f is not None else None}


class CandidateReceiver:
    def __init__(self,owner,*,topic=TOPIC,source=SERVO_NODE,on_verdict=None):
        from trajectory_msgs.msg import JointTrajectory
        from rclpy.qos import QoSProfile
        self.owner=owner;self.topic=topic;self.source=source
        self.bridge=LockedBridge(owner.vision_arbiter,lambda:owner_feedback(owner))
        self.on_verdict=on_verdict
        self.last_verdict=None
        self.last_provenance="UNAVAILABLE"
        self.received=0
        self.valid_windows=0
        self.sub=owner.create_subscription(JointTrajectory,topic,self._receive,QoSProfile(depth=1))

    def _receive(self,msg,info):
        actual=publisher_identity(self.owner,self.topic,self.source)
        gid=info.get("publisher_gid")
        # Jazzy rclpy MessageInfo may omit publisher_gid. Graph-only
        # attribution is sufficient only for this non-actuating monitor.
        # Do not silently upgrade it to per-sample attribution.
        self.last_provenance="UNAVAILABLE"
        pinned=None
        if actual is not None:
            if gid is None:
                pinned=actual
                self.last_provenance="GRAPH_ONLY"
            elif tuple(gid)==actual:
                pinned=actual
                self.last_provenance="SAMPLE_GID_MATCH"
        self.last_verdict=self.bridge.assess(msg,self.owner.get_clock().now().nanoseconds,pinned)
        self.received+=1
        self.valid_windows+=int(self.last_verdict.accepted_format)
        if self.on_verdict is not None:self.on_verdict(self.last_verdict)
