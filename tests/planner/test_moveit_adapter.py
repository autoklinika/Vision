"""MoveIt service-boundary regressions using a synthetic two-joint model."""
from copy import deepcopy
from dataclasses import asdict, replace
import math
from types import SimpleNamespace as NS
import unittest

from vision_core.models import GateError
from vision_planner.moveit_adapter import (
    AdapterConfig, JointLimit, MoveItAdapter, camera_to_link, link_to_camera,
    scene_digest, validate_segment, validate_snapshot, _hash,
)


def stamp(sec=10, nanosec=0):
    return NS(sec=sec, nanosec=nanosec)


def header(frame='world'):
    return NS(frame_id=frame, stamp=stamp())


def pose():
    return NS(header=header(), pose=NS(position=NS(x=0., y=0., z=1.),
               orientation=NS(x=0., y=0., z=0., w=1.)))


def state(positions=(0., 0.)):
    return NS(joint_state=NS(header=header(), name=['joint1','joint2'],
              position=list(positions), velocity=[0.,0.], effort=[]),
              attached_collision_objects=[], multi_dof_joint_state=NS(
                  header=header(), joint_names=[], transforms=[], twist=[], wrench=[]),
              is_diff=False)


def scene():
    return NS(name='synthetic',robot_model_name='two_joint_model',is_diff=False,
              robot_state=state(),world=NS(collision_objects=[],octomap=NS(data=[])),
              allowed_collision_matrix=NS(entry_names=[],entry_values=[]),
              link_padding=[],link_scale=[],fixed_frame_transforms=[])


def config(**kwargs):
    data = dict(group_name='arm', ik_link_name='tip',
                joint_limits=(JointLimit('joint1',-1,1,2,3),JointLimit('joint2',-1,1,2,3)),
                link_camera_xyz_mm=(10.,0.,0.), link_camera_quaternion=(0.,0.,0.,1.),
                model_revision='synthetic-model-v1',calibration_revision='synthetic-tool-v1')
    return AdapterConfig(**(data | kwargs))


def types():
    return NS(
        scene=NS(Request=lambda:NS(components=NS(components=0))),
        ik=NS(Request=lambda:NS(ik_request=NS(group_name='',ik_link_name='',avoid_collisions=False,
                    robot_state=state(),pose_stamped=pose(),timeout=stamp(0)))),
        fk=NS(Request=lambda:NS(header=header(),fk_link_names=[],robot_state=state())),
        validity=NS(Request=lambda:NS(robot_state=state(),group_name='',constraints=NS())),
        plan=NS(Request=lambda:NS(motion_plan_request=NS(goal_constraints=[]))),
        Constraints=lambda:NS(joint_constraints=[]),
        JointConstraint=lambda:NS(joint_name='',position=0.,tolerance_above=0.,tolerance_below=0.,weight=0.),
    )


class FakeMoveIt:
    def __init__(self):
        self.scene = scene()
        self.calls = []
        self.mutate = lambda kind,response: response

    def __call__(self, kind, request, timeout):
        self.calls.append((kind,deepcopy(request),timeout))
        if kind == 'scene':
            response = NS(scene=deepcopy(self.scene))
        elif kind == 'validity':
            response = NS(valid=True,contacts=[],constraint_result=[])
        elif kind == 'ik':
            x = request.ik_request.pose_stamped.pose.position.x
            response = NS(error_code=NS(val=1),solution=state((x,0.)))
        elif kind == 'fk':
            p = pose()
            p.header.frame_id=request.header.frame_id
            p.pose.position.x = request.robot_state.joint_state.position[0]
            response = NS(error_code=NS(val=1),fk_link_names=['tip'],pose_stamped=[p])
        elif kind == 'plan':
            motion = request.motion_plan_request
            start = motion.start_state.joint_state.position
            goal = [c.position for c in motion.goal_constraints[0].joint_constraints]
            positions=[start,[(x+y)/2 for x,y in zip(start,goal)],goal]
            points=[NS(positions=list(p),velocities=[0.,0.],accelerations=[0.,0.],
                       time_from_start=stamp(i)) for i,p in enumerate(positions)]
            response=NS(motion_plan_response=NS(error_code=NS(val=1),group_name='arm',
                trajectory_start=deepcopy(motion.start_state),trajectory=NS(
                joint_trajectory=NS(joint_names=['joint1','joint2'],points=points),
                multi_dof_joint_trajectory=NS(joint_names=[],points=[]))))
        else:
            raise AssertionError('unexpected service ' + kind)
        return self.mutate(kind,response)


class MoveItAdapterTests(unittest.TestCase):
    def setUp(self):
        self.rpc=FakeMoveIt()
        self.config=config()
        self.adapter=MoveItAdapter(self.config,self.rpc,types(),clock=lambda:10.,monotonic=lambda:1.)

    def plan(self):
        expected=self.adapter.snapshot().scene_hash
        return self.adapter.plan_segment('view_001','world',(100.,0.,1000.),(0.,0.,0.,1.),(0.,0.),expected)

    def mutate_plan(self, callback):
        def mutate(kind,response):
            if kind == 'plan': callback(response.motion_plan_response)
            return response
        self.rpc.mutate=mutate

    def test_camera_tool_rotation_roundtrip(self):
        q=(0.,0.,math.sin(.3),math.cos(.3))
        toolq=(math.sin(.2),0.,0.,math.cos(.2))
        p=(300.,-400.,800.)
        link=camera_to_link(p,q,(20.,30.,40.),toolq)
        camera=link_to_camera(*link,(20.,30.,40.),toolq)
        for expected,actual in zip(p+q,camera[0]+camera[1]): self.assertAlmostEqual(expected,actual)
        self.assertNotEqual(link[0],p)

    def test_real_service_request_contract_and_plan_only(self):
        result=self.plan()
        validate_segment(result,self.config)
        self.assertEqual(result.end_joints,(.09,0.))
        self.assertEqual(result.config_hash,self.config.digest)
        self.assertEqual(result.checked_state_count,3)
        kinds={kind for kind,_,_ in self.rpc.calls}
        self.assertEqual(kinds,{'scene','ik','fk','validity','plan'})
        ik=next(req.ik_request for kind,req,_ in self.rpc.calls if kind=='ik')
        self.assertTrue(ik.avoid_collisions)
        self.assertAlmostEqual(ik.pose_stamped.pose.position.x,.09)
        self.assertEqual(ik.pose_stamped.pose.position.z,1.)
        self.assertEqual(ik.ik_link_name,'tip')
        plan=next(req.motion_plan_request for kind,req,_ in self.rpc.calls if kind=='plan')
        self.assertEqual(plan.max_velocity_scaling_factor,.1)
        self.assertEqual(plan.max_acceleration_scaling_factor,.1)
        self.assertFalse(hasattr(self.adapter,'execute'))

    def test_scene_hash_covers_geometry_acm_tool_and_other_joints(self):
        original=scene()
        digest=scene_digest(original,('joint1','joint2'))
        variants=[]
        a=deepcopy(original); a.world.collision_objects.append(NS(id='obstacle',xyz=[1.,0.,0.])); variants.append(a)
        a=deepcopy(original); a.allowed_collision_matrix.entry_names.append('tip'); variants.append(a)
        a=deepcopy(original); a.robot_state.attached_collision_objects.append(NS(link_name='tip',id='camera')); variants.append(a)
        a=deepcopy(original); a.link_padding.append(NS(link_name='tip',padding=.001)); variants.append(a)
        a=deepcopy(original); a.fixed_frame_transforms.append(NS(header=header(),child_frame_id='fixture',translation=[1.,0.,0.])); variants.append(a)
        a=deepcopy(original); a.robot_state.joint_state.name.append('unplanned'); a.robot_state.joint_state.position.append(.2); variants.append(a)
        for changed in variants:
            with self.subTest(changed=changed): self.assertNotEqual(digest,scene_digest(changed,('joint1','joint2')))
        a=deepcopy(original); a.robot_state.joint_state.position=[.3,.2]; a.robot_state.joint_state.header.stamp=stamp(12)
        self.assertEqual(digest,scene_digest(a,('joint1','joint2')))

    def test_scene_is_full_not_diff(self):
        self.rpc.scene.is_diff=True
        with self.assertRaises(GateError): self.adapter.snapshot()

    def test_stale_or_future_source_stamp_rejected(self):
        for sec in (7,11):
            self.rpc.scene.robot_state.joint_state.header.stamp=stamp(sec)
            with self.subTest(sec=sec),self.assertRaises(GateError): self.adapter.snapshot()

    def test_missing_velocities_are_not_fabricated(self):
        self.rpc.scene.robot_state.joint_state.velocity=[]
        self.assertEqual(self.adapter.snapshot().joint_velocities,())

    def test_jazzy_scene_zero_stamp_requires_actual_source(self):
        self.rpc.scene.robot_state.joint_state.header.stamp=stamp(0)
        self.rpc.scene.robot_state.joint_state.velocity=[]
        with self.assertRaises(GateError): self.adapter.snapshot()
        measured=state().joint_state
        cfg=replace(self.config,joint_state_topic='/measured_joint_states')
        adapter=MoveItAdapter(cfg,self.rpc,types(),clock=lambda:10.,monotonic=lambda:1.,
                             joint_state_source=lambda:measured)
        snapshot=adapter.snapshot()
        self.assertEqual(snapshot.timestamp,10.)
        self.assertEqual(snapshot.joint_velocities,(0.,0.))
        self.assertEqual(snapshot.received_at,10.)
        measured.header.stamp=stamp(7)
        with self.assertRaises(GateError): adapter.snapshot()

    def test_explicit_source_must_agree_with_planning_scene(self):
        measured=state((.2,0.)).joint_state
        cfg=replace(self.config,joint_state_topic='/measured_joint_states')
        adapter=MoveItAdapter(cfg,self.rpc,types(),clock=lambda:10.,monotonic=lambda:1.,
                             joint_state_source=lambda:measured)
        with self.assertRaises(GateError): adapter.snapshot()
        adapter._joint_state_source=lambda:None
        with self.assertRaises(GateError): adapter.snapshot()

    def test_source_can_be_newer_than_request_start(self):
        clock_values=iter([10.,10.1,10.2,10.3])
        self.adapter._clock=lambda:next(clock_values)
        self.rpc.scene.robot_state.joint_state.header.stamp=stamp(10,50000000)
        digest=scene_digest(self.rpc.scene,self.config.joint_names)
        segment=self.adapter.plan_segment('view_001','world',(100.,0.,1000.),(0.,0.,0.,1.),(0.,0.),digest)
        self.assertGreater(segment.scene_before.timestamp,segment.started_at)
        validate_segment(segment,self.config)

    def test_joint_bounds_do_not_rely_on_state_validity_service(self):
        self.rpc.scene.robot_state.joint_state.position=[1.01,0.]
        with self.assertRaises(GateError): self.adapter.snapshot()
        self.assertNotIn('validity',[kind for kind,_,_ in self.rpc.calls])

    def test_failed_ik_cannot_reach_planning(self):
        def mutate(kind,response):
            if kind=='ik': response.error_code.val=-31
            return response
        self.rpc.mutate=mutate
        with self.assertRaises(GateError): self.plan()
        self.assertNotIn('plan',[kind for kind,_,_ in self.rpc.calls])

    def test_successful_ik_with_wrong_camera_fk_is_rejected(self):
        def mutate(kind,response):
            if kind=='fk': response.pose_stamped[0].pose.position.x+=.02
            return response
        self.rpc.mutate=mutate
        with self.assertRaises(GateError): self.plan()

    def test_collision_at_interior_sample_is_rejected(self):
        base=self.rpc
        def rpc(kind,request,timeout):
            result=base(kind,request,timeout)
            if kind=='validity' and .04 < request.robot_state.joint_state.position[0] < .05: result.valid=False
            return result
        self.adapter._rpc=rpc
        with self.assertRaises(GateError): self.plan()

    def test_success_with_contact_is_rejected(self):
        def mutate(kind,response):
            if kind=='validity': response.contacts.append(NS(body_name='table'))
            return response
        self.rpc.mutate=mutate
        with self.assertRaises(GateError): self.plan()

    def test_scene_change_mid_plan_invalidates_result(self):
        def mutate(kind,response):
            if kind=='plan': self.rpc.scene.world.collision_objects.append(NS(id='new_obstacle'))
            return response
        self.rpc.mutate=mutate
        with self.assertRaises(GateError): self.plan()

    def test_actual_robot_drift_invalidates_result(self):
        def mutate(kind,response):
            if kind=='plan': self.rpc.scene.robot_state.joint_state.position[0]=.01
            return response
        self.rpc.mutate=mutate
        with self.assertRaises(GateError): self.plan()

    def test_wrong_scene_hash_prevents_ik(self):
        with self.assertRaises(GateError):
            self.adapter.plan_segment('view_001','world',(100.,0.,1000.),(0.,0.,0.,1.),(0.,0.),'0'*64)
        self.assertNotIn('ik',[kind for kind,_,_ in self.rpc.calls])

    def test_planner_cannot_fix_a_different_start_silently(self):
        self.mutate_plan(lambda result:setattr(result.trajectory_start.joint_state,'position',[.03,0.]))
        with self.assertRaises(GateError): self.plan()

    def test_trajectory_joint_order_mismatch_rejected(self):
        self.mutate_plan(lambda result:setattr(result.trajectory.joint_trajectory,'joint_names',['joint2','joint1']))
        with self.assertRaises(GateError): self.plan()

    def test_partial_or_untimed_trajectory_rejected(self):
        for field,value in [('velocities',[]),('accelerations',[]),('positions',[float('nan'),0.]),('time_from_start',stamp(0))]:
            with self.subTest(field=field):
                self.mutate_plan(lambda result:setattr(result.trajectory.joint_trajectory.points[1],field,value))
                with self.assertRaises(GateError): self.plan()

    def test_scaled_derivative_limits_rejected(self):
        for field,value in [('velocities',[.21,0.]),('accelerations',[.31,0.])]:
            with self.subTest(field=field):
                self.mutate_plan(lambda result:setattr(result.trajectory.joint_trajectory.points[1],field,value))
                with self.assertRaises(GateError): self.plan()

    def test_jazzy_start_velocity_requires_explicit_policy_goal_still_stops(self):
        self.mutate_plan(lambda result:setattr(result.trajectory.joint_trajectory.points[0],'velocities',[.0005,0.]))
        with self.assertRaises(GateError): self.plan()
        self.adapter.config=replace(self.config,start_velocity_tolerance_rad_s=.001)
        result=self.plan()
        self.assertEqual(result.points[0].velocities[0],.0005)
        validate_segment(result,self.adapter.config)
        self.mutate_plan(lambda result:setattr(result.trajectory.joint_trajectory.points[-1],'velocities',[.0005,0.]))
        with self.assertRaises(GateError): self.plan()

    def test_excessive_scene_names_rejected_before_iteration_or_copy(self):
        class Excessive:
            def __len__(self): return 1000000
            def __iter__(self): raise AssertionError('must reject before iteration')
        self.rpc.scene.robot_state.joint_state.name=Excessive()
        self.rpc.scene.robot_state.joint_state.position=Excessive()
        with self.assertRaises(GateError): scene_digest(self.rpc.scene,self.config.joint_names)
        with self.assertRaises(GateError): self.adapter._joints(self.rpc.scene.robot_state.joint_state)

    def test_planner_endpoint_must_match_ik(self):
        self.mutate_plan(lambda result:setattr(result.trajectory.joint_trajectory.points[-1],'positions',[.095,0.]))
        with self.assertRaises(GateError): self.plan()

    def test_sample_limit_checked_before_state_validation_loop(self):
        self.adapter.config=replace(self.config,max_samples=2)
        with self.assertRaises(GateError): self.plan()
        count=sum(kind=='validity' for kind,_,_ in self.rpc.calls)
        self.assertEqual(count,2) # seed and IK only

    def test_false_digest_and_resigned_false_derivative_rejected(self):
        result=self.plan()
        with self.assertRaises(GateError): validate_segment(replace(result,checked_state_count=1),self.config)
        points=list(result.points)
        points[1]=replace(points[1],velocities=(.5,0.))
        changed=replace(result,points=tuple(points),digest='')
        data=asdict(changed); data.pop('digest')
        changed=replace(changed,digest=_hash(data))
        with self.assertRaises(GateError): validate_segment(changed,self.config)

    def test_forged_snapshot_bounds_rejected(self):
        snapshot=self.adapter.snapshot()
        with self.assertRaises(GateError): validate_snapshot(replace(snapshot,joint_positions=(4.,0.)),self.config)

    def test_total_deadline_rejects_late_response(self):
        tick=[1.]
        base=self.rpc
        def rpc(kind,request,timeout):
            result=base(kind,request,timeout)
            tick[0]+=6.
            return result
        self.adapter._monotonic=lambda:tick[0]
        self.adapter._rpc=rpc
        with self.assertRaises(GateError): self.adapter.snapshot()

    def test_invalid_policy_rejected(self):
        for kwargs in ({'velocity_scale':0},{'velocity_scale':True},{'max_points':True},
                       {'link_camera_quaternion':(0,0,0,2)}, {'sample_step_rad':.2},
                       {'service_names':(('execute','/execute_trajectory'),)}):
            with self.subTest(kwargs=kwargs),self.assertRaises(GateError): config(**kwargs)


if __name__=='__main__':
    unittest.main()
