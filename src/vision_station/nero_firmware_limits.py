"""Read-only query of actual NERO controller joint angle/max speed limits.

A caller supplies the existing exclusive SDK owner; never instantiate a CAN
interface here. No enable, movement, reset or limit configuration operation.
SDK V121 response contains max_joint_spd, not a minimum-speed field.
"""
import math
import time
from .nero_joint_limits import JOINTS, valid_pair


def parse_reply(reply, index, started, now):
    if reply is None:return None
    try:
        m=reply.msg;stamp=reply.timestamp
        angles=(m.min_angle_limit,m.max_angle_limit)
        speed=m.max_joint_spd
        if (m.joint_index!=index or not valid_pair(angles)
                or type(speed) not in (int,float) or not math.isfinite(speed)
                or not 0<=speed<=100
                or type(stamp) not in (int,float) or not started<=stamp<=now):
            return None
        return {"joint":JOINTS[index-1],"angleRad":list(angles),
                "maxVelocityRadS":speed,"responseAt":stamp}
    except (AttributeError,TypeError,ValueError,OverflowError):return None


def query_limits(robot, check, *, clock=time.time):
    """Exactly one vendor getter call per axis; reject stale/invalid replies.

    check() is a caller-owned disabled/stationary/exclusive-owner interlock.
    Never use the result as a motion authorization or change model limits.
    """
    rows=[]
    for index in range(1,8):
        check()
        started=clock()
        reply=robot.get_joint_angle_vel_limits(index,timeout=1.,min_interval=1.)
        now=clock()
        value=parse_reply(reply,index,started,now)
        check()
        rows.append(value if value is not None else {
            "joint":JOINTS[index-1],"angleRad":None,
            "maxVelocityRadS":None,"responseAt":None})
    return rows
