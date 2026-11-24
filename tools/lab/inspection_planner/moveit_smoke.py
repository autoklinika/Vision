#!/usr/bin/env python3
"""Opt-in synthetic NERO MoveIt smoke; requires an isolated server with execution off.

The script publishes *synthetic* joint states and replaces synthetic collision
objects only in its explicitly selected test domain. It does not start drivers,
controllers, motion actions, cameras or Core workflow transitions.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--domain-id',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.domain_id in (0,185,186) or not 1 <= args.domain_id <= 232 or os.environ.get('ROS_DOMAIN_ID') != str(args.domain_id):
        raise SystemExit('Use an explicit isolated test ROS domain, not a station domain')
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1':
        raise SystemExit('Synthetic smoke requires ROS_LOCALHOST_ONLY=1')

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rcl_interfaces.srv import GetParameters
    from sensor_msgs.msg import JointState
    from moveit_msgs.srv import GetStateValidity,GetPositionFK,ApplyPlanningScene
    from moveit_msgs.msg import RobotState,CollisionObject,AttachedCollisionObject
    from geometry_msgs.msg import Pose
    from shape_msgs.msg import SolidPrimitive
    from vision_core.models import GateError
    from vision_planner.moveit_adapter import MoveItAdapter,AdapterConfig,JointLimit,link_to_camera,validate_segment

    rclpy.init()
    node=rclpy.create_node('vision_planner_synthetic_smoke')
    executor=MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    thread=threading.Thread(target=executor.spin,daemon=True)
    thread.start()
    clients=[]
    adapter=None

    def wait(future,timeout):
        event=threading.Event()
        future.add_done_callback(lambda _:event.set())
        event.wait(timeout)

    def rpc(type_,name,request,timeout=5.):
        client=node.create_client(type_,name)
        clients.append(client)
        if not client.wait_for_service(timeout_sec=timeout): raise RuntimeError('service unavailable '+name)
        future=client.call_async(request)
        wait(future,timeout)
        if not future.done() or future.exception(): raise RuntimeError('service failed '+name)
        return future.result()

    try:
        names=['allow_trajectory_execution','robot_description','robot_description_semantic']
        for index in range(1,8):
            for field in ('max_velocity','max_acceleration'):
                names.append(f'robot_description_planning.joint_limits.joint{index}.{field}')
        request=GetParameters.Request();request.names=names
        parameters=rpc(GetParameters,'/move_group/get_parameters',request).values
        if parameters[0].type != 1 or parameters[0].bool_value is not False:
            raise RuntimeError('MoveIt trajectory execution must be disabled')
        urdf,srdf=parameters[1].string_value,parameters[2].string_value
        model=ET.fromstring(urdf)
        virtual_joint=ET.fromstring(srdf).find('virtual_joint')
        roots={link.attrib['name'] for link in model.findall('link')}-{joint.find('child').attrib['link'] for joint in model.findall('joint')}
        frame=virtual_joint.attrib['parent_frame'] if virtual_joint is not None else sorted(roots)[0]
        limits=[]
        for index in range(1,8):
            joint=model.find(f"joint[@name='joint{index}']")
            bound=joint.find('limit')
            limits.append(JointLimit(f'joint{index}',float(bound.attrib['lower']),float(bound.attrib['upper']),
                    min(float(bound.attrib['velocity']),parameters[3+2*(index-1)].double_value),
                    parameters[4+2*(index-1)].double_value))
        config=AdapterConfig('arm','tcp_link',tuple(limits),(0.,0.,60.),(1.,0.,0.,0.),
                             'sha256:'+hashlib.sha256((urdf+srdf).encode()).hexdigest(),
                             'synthetic-tool-v1',planning_time_s=2.,service_timeout_s=6.,segment_timeout_s=120.,
                             joint_state_topic='/control/joint_states',start_velocity_tolerance_rad_s=.001)
        print('MODEL_LOADED',config.digest,'PLANNING_FRAME',frame,flush=True)

        def robot_state(positions):
            message=RobotState()
            message.joint_state.header.stamp=node.get_clock().now().to_msg()
            message.joint_state.name=list(config.joint_names)
            message.joint_state.position=list(map(float,positions))
            message.joint_state.velocity=[0.]*7
            return message

        # Finite deterministic synthetic candidates; no real feedback is read.
        candidates=[(0.,-.4,0.,.8,0.,-.4,0.),(0.,.4,0.,-.8,0.,.4,0.),
                    (0.,0.,0.,0.,0.,0.,0.),(.2,-.6,.1,.8,.1,-.3,.1)]
        seed=None
        for candidate in candidates:
            if any(not lim.lower <= v <= lim.upper for v,lim in zip(candidate,limits)): continue
            request=GetStateValidity.Request();request.group_name='arm';request.robot_state=robot_state(candidate)
            result=rpc(GetStateValidity,'/check_state_validity',request)
            if result.valid and not result.contacts:
                seed=candidate;break
        if seed is None: raise RuntimeError('No collision-free synthetic seed')
        publisher=node.create_publisher(JointState,'/control/joint_states',10)
        def publish(): publisher.publish(robot_state(seed).joint_state)
        timer=node.create_timer(.05,publish)
        publish()
        # Wait for the source state to be represented in the planning scene.
        adapter=MoveItAdapter.from_node(node,config,wait)
        raw_rpc=adapter._rpc
        def report_rpc(kind,request,timeout):
            result=raw_rpc(kind,request,timeout)
            if kind=='plan':
                points=result.motion_plan_response.trajectory.joint_trajectory.points
                if points:
                    print('RAW_TERMINAL_VELOCITIES',list(points[0].velocities),list(points[-1].velocities),flush=True)
            return result
        adapter._rpc=report_rpc
        deadline=time.monotonic()+5
        last_error='source positions differ'
        while True:
            try:
                initial=adapter.snapshot()
                if max(abs(x-y) for x,y in zip(initial.joint_positions,seed)) <= config.joint_tolerance: break
            except GateError as exc:
                last_error=str(exc)
            if time.monotonic()>=deadline: raise RuntimeError('Synthetic source not observed: '+last_error)
            threading.Event().wait(.05)

        # Synthetic fixtures are applied solely to this isolated test server.
        def box(id_,frame,dimensions,xyz):
            obj=CollisionObject();obj.id=id_;obj.header.frame_id=frame;obj.operation=CollisionObject.ADD
            primitive=SolidPrimitive();primitive.type=SolidPrimitive.BOX;primitive.dimensions=list(dimensions)
            p=Pose();p.position.x,p.position.y,p.position.z=xyz;p.orientation.w=1.
            obj.primitives=[primitive];obj.primitive_poses=[p]
            return obj
        request=ApplyPlanningScene.Request();request.scene.is_diff=True;request.scene.robot_state.is_diff=True
        request.scene.world.collision_objects=[box('synthetic_floor',frame,(2.,2.,.1),(0.,0.,-.2))]
        attached=AttachedCollisionObject();attached.link_name='tcp_link';attached.touch_links=['tcp_link','link7']
        attached.object=box('synthetic_camera','tcp_link',(.04,.04,.05),(0.,0.,.06))
        request.scene.robot_state.attached_collision_objects=[attached]
        if not rpc(ApplyPlanningScene,'/apply_planning_scene',request).success: raise RuntimeError('Synthetic scene apply failed')
        initial=adapter.snapshot()
        print('SYNTHETIC_SCENE',initial.scene_hash,'SOURCE_AGE',initial.received_at-initial.timestamp,flush=True)
        segments=[]
        start=seed
        for index,delta in enumerate((.025,.05),1):
            goal=list(seed);goal[0]+=delta
            request=GetPositionFK.Request();request.header.frame_id=frame;request.fk_link_names=['tcp_link'];request.robot_state=robot_state(goal)
            result=rpc(GetPositionFK,'/compute_fk',request)
            if result.error_code.val != 1: raise RuntimeError('Synthetic target FK failed: '+str(result.error_code.val))
            p=result.pose_stamped[0].pose.position;q=result.pose_stamped[0].pose.orientation
            camera=link_to_camera((p.x*1000,p.y*1000,p.z*1000),(q.x,q.y,q.z,q.w),config.link_camera_xyz_mm,config.link_camera_quaternion)
            segment=adapter.plan_segment(f'view_{index:03d}',frame,*camera,start,initial.scene_hash)
            validate_segment(segment,config)
            segments.append(segment);start=segment.end_joints
            print('SEGMENT_PASS',index,len(segment.points),segment.checked_state_count,segment.digest,flush=True)
        final=adapter.snapshot()
        if final.scene_hash != initial.scene_hash or final.joint_positions != initial.joint_positions:
            raise RuntimeError('Synthetic scene or published measured seed changed')
        # Demonstrate that an unreachable target produces failure, not evidence.
        try:
            adapter.plan_segment('unreachable',frame,(100000.,100000.,100000.),(0.,0.,0.,1.),seed,initial.scene_hash)
        except GateError as exc:
            unreachable=str(exc)
        else:
            raise RuntimeError('Unreachable target unexpectedly accepted')
        blocked=ApplyPlanningScene.Request();blocked.scene.is_diff=True;blocked.scene.robot_state.is_diff=True
        blocked.scene.world.collision_objects=[box('synthetic_blocker',frame,(4.,4.,4.),(0.,0.,0.))]
        if not rpc(ApplyPlanningScene,'/apply_planning_scene',blocked).success: raise RuntimeError('Synthetic blocker apply failed')
        blocked_snapshot=adapter.snapshot()
        try:
            adapter.plan_segment('blocked',frame,*camera,seed,blocked_snapshot.scene_hash)
        except GateError as exc:
            collision=str(exc)
            if 'collision' not in collision: raise RuntimeError('Blocked scenario failed for unrelated reason') from exc
        else:
            raise RuntimeError('Blocked scene unexpectedly accepted')
        output={'schema_version':'1','classification':'SYNTHETIC_MOVEIT_SMOKE_NOT_PHYSICAL_ACCEPTANCE',
                'ros_domain_id':args.domain_id,'allow_trajectory_execution':False,
                'hardware_drivers_started':False,'controllers_started':False,'motion_execution_requests':0,
                'configuration':asdict(config),'initial_snapshot':asdict(initial),'final_snapshot':asdict(final),
                'segments':[asdict(x) for x in segments],'unreachable_rejection':unreachable,
                'collision_rejection':collision,'blocked_scene_hash':blocked_snapshot.scene_hash}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
        print('SMOKE_PASS',args.output,flush=True)
        node.destroy_timer(timer)
    finally:
        if adapter is not None: adapter.close()
        for client in clients: node.destroy_client(client)
        executor.shutdown(timeout_sec=3.)
        thread.join(timeout=3.)
        node.destroy_node();rclpy.shutdown()


if __name__=='__main__':
    main()
