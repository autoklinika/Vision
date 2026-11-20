"""C7 V1 MoveIt joint-limit numeric boundary regression, OFFLINE only."""
import importlib.util, math, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/"scripts/lab/c7_v1_joint_limits.py"
spec=importlib.util.spec_from_file_location("c7_v1_joint_limits",str(P))
lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
URDF=Path("/srv/vision-data/experiments/vision-nero-moveit-20261117/ws/src/agx_arm_description/agx_arm_urdf/nero/urdf/nero_description.urdf")
NAMES=[f"joint{i}" for i in range(1,8)]

class JointBounds(unittest.TestCase):
    def setUp(self):
        self.limits=lib.load_urdf_joint_limits(URDF,NAMES)

    def test_exact_minus_ninety_is_fractionally_outside_vendor_urdf(self):
        low,hi=self.limits["joint7"]
        self.assertGreater(low,-math.pi/2)
        self.assertLess(low+math.pi/2,1e-6)
        q=[0]*7;q[6]=-math.pi/2
        result=lib.inset_at_limit(q,NAMES,self.limits)
        self.assertTrue(result["changed"])
        self.assertEqual(len(result["adjustments"]),1)
        self.assertEqual(result["adjustments"][0]["joint"],"joint7")
        self.assertGreater(result["corrected_q"][6],low)
        self.assertLess(result["max_abs_delta_deg"],0.02)
        self.assertTrue(result["offline_only"])

    def test_positive_boundary_has_the_same_numeric_inset(self):
        _,upper=self.limits["joint7"]
        q=[0]*7;q[6]=math.pi/2
        result=lib.inset_at_limit(q,NAMES,self.limits)
        self.assertLess(result["corrected_q"][6],upper)
        self.assertGreater(result["corrected_q"][6],0)
        self.assertLess(result["max_abs_delta_deg"],0.02)

    def test_angles_well_inside_limits_are_not_affected(self):
        q=[math.radians(x) for x in [10,5,-20,40,10,0,12]]
        out=lib.inset_at_limit(q,NAMES,self.limits)
        self.assertEqual(out["corrected_q"],q)
        self.assertFalse(out["changed"])

    def test_significantly_outside_joint_limits_must_fail(self):
        for name,value in [("joint7",-95),("joint7",95),("joint4",150)]:
            q=[0.]*7;q[NAMES.index(name)]=math.radians(value)
            with self.subTest(joint=name,value=value),self.assertRaises(lib.JointLimitError):
                lib.inset_at_limit(q,NAMES,self.limits)

    def test_non_finite_and_wrong_joint_count_are_rejected(self):
        with self.assertRaises(lib.JointLimitError):
            lib.inset_at_limit([0.]*6,NAMES,self.limits)
        with self.assertRaises(lib.JointLimitError):
            lib.inset_at_limit([0.]*6+[float('nan')],NAMES,self.limits)

    def test_outcome_cannot_authorize_robot_motion(self):
        x=lib.inset_at_limit([0.]*6+[-math.pi/2],NAMES,self.limits)
        self.assertTrue(x["offline_only"])
        self.assertTrue(x["preserves_vendor_joint_limits"])
        self.assertNotIn("execution_allowed",x)

if __name__=="__main__":unittest.main()
