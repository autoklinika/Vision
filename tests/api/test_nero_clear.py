"""Clear acceptance uses only mock SDK feedback; never opens real CAN."""
import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest

from test_nero_diagnostics import report
from vision_station.nero_clear import (ClearEngine,Evidence,read_sdk_evidence,result,validate_result)
from vision_station.nero_local_approval import Approval
from vision_station.nero_history import FaultHistory,validate_history,validate_attempts
from vision_station.nero_clear_coordinator import eligible
from vision_station.host import CoreHost
from vision_station.nero import MAX_BYTES
from vision_station.luxonis import atomic_json

ID="b"*32

class Mock:
    def __init__(self,drives=(4,0,0,0,0,0,0),mask=0,after=None,stale=False,repeat=False):
        self.now=100.;self.calls=[];self.drives=drives;self.mask=mask;self.after=after
        self.stale=stale;self.repeat=repeat;self.locked=True;self.approval=True
    def sleep(self,dt):self.now+=dt
    def evidence(self):
        t=self.now-.01
        if self.calls and (self.stale or self.repeat):t=99.99 if self.stale else 100.01
        return Evidence(t,6,self.mask,tuple(self.drives),(t,)*7)
    def send(self,scope):
        self.calls.append(scope)
        if self.after is not None:self.drives,self.mask=self.after
    def engine(self,commissioned=True):
        return ClearEngine(read=self.evidence,clear=self.send,interlock=lambda:self.locked,
                           consume_approval=lambda op,scope:self.approval,commissioned=commissioned,
                           clock=lambda:self.now,mono=lambda:self.now,sleep=self.sleep)

class EngineTests(unittest.TestCase):
    def check(self,v,status):
        self.assertTrue(validate_result(v),v);self.assertEqual(v["result"],status)
    def test_clear_single_and_scope(self):
        m=Mock(drives=(4,0,32,0,0,0,0),after=((0,0,32,0,0,0,0),0))
        engine=m.engine();v=engine.execute(ID,1,110.)
        self.check(v,"CLEARED");self.assertEqual(m.calls,[1])
        self.assertEqual(v["axisResults"],["CLEARED"]+["NOT_SELECTED"]*6)
        self.assertGreater(min(v["after"]["driveStamps"]),v["sentAfter"])
        self.check(engine.execute(ID,1,110.),"REJECTED")
        self.assertEqual(m.calls,[1])
    def test_partial_and_all(self):
        m=Mock(drives=(4,0,32,0,0,0,0),after=((0,0,32,0,0,0,0),0))
        v=m.engine().execute(ID,255,110.)
        self.check(v,"PARTIAL");self.assertEqual(m.calls,[255])
        self.assertEqual(v["axisResults"][:3],["CLEARED","NO_ACTIVE_FAULTS","STILL_ACTIVE"])
    def test_persistent_and_new_fault(self):
        for new in ((4,0,0,0,0,0,0),(32,0,0,0,0,0,0)):
            m=Mock(after=(new,0))
            self.check(m.engine().execute(ID,1,110.),"STILL_ACTIVE" if new[0]==4 else "PARTIAL")
    def test_stale_and_republished_timestamp(self):
        for kwargs in ({"stale":True},{"repeat":True}):
            m=Mock(after=((0,)*7,0),**kwargs)
            self.check(m.engine().execute(ID,1,110.),"UNVERIFIED")
            self.assertEqual(m.calls,[1])
    def test_two_fresh_identical_samples_required(self):
        m=Mock(after=((0,)*7,0))
        engine=m.engine()
        def read():
            e=m.evidence()
            if m.calls and m.now>100.06:return None
            return e
        engine.read=read
        self.check(engine.execute(ID,1,110.),"UNVERIFIED")
    def test_admission_and_no_fault_no_send(self):
        cases=[(Mock(drives=(0,)*7),True,"NO_ACTIVE_FAULTS"),
               (Mock(drives=(0x44,0,0,0,0,0,0)),True,"REJECTED"),
               (Mock(),False,"REJECTED")]
        a=Mock();a.approval=False;cases.append((a,True,"REJECTED"))
        b=Mock();b.locked=False;cases.append((b,True,"REJECTED"))
        for m,enabled,status in cases:
            self.check(m.engine(enabled).execute(ID,255,110.),status);self.assertEqual(m.calls,[])
    def test_hold_interrupt_and_exception(self):
        m=Mock(after=((0,)*7,0));engine=m.engine()
        def interrupt(scope):m.send(scope);m.locked=False
        engine.clear=interrupt
        self.check(engine.execute(ID,1,110.),"UNVERIFIED")
        m=Mock();engine=m.engine()
        def fail(scope):m.calls.append(scope);raise RuntimeError()
        engine.clear=fail;self.check(engine.execute(ID,1,110.),"FAILED")
        self.assertEqual(m.calls,[1])
    def test_forged_success(self):
        m=Mock(after=((0,)*7,0));v=m.engine().execute(ID,1,110.)
        bad=copy.deepcopy(v);bad["after"]["driveStamps"][0]=bad["sentAfter"]
        self.assertFalse(validate_result(bad))
        bad=copy.deepcopy(v);bad["axisResults"][0]="STILL_ACTIVE"
        self.assertFalse(validate_result(bad))
    def test_read_sdk_uses_actual_timestamps(self):
        robot=SimpleNamespace(is_ok=lambda:True,
            get_arm_status=lambda:SimpleNamespace(timestamp=99.9,msg=SimpleNamespace(arm_status=6,err_code=0)),
            get_driver_states=lambda i:SimpleNamespace(timestamp=99.9+i/1000,msg=SimpleNamespace(foc_status_code=4 if i==2 else 0)))
        e=read_sdk_evidence(robot,clock=lambda:100.)
        self.assertEqual(e.drive_status[1],4)
        self.assertNotEqual(e.drive_stamps[0],e.drive_stamps[1])
        self.assertIsNone(read_sdk_evidence(robot,clock=lambda:101.))
    def test_eligibility_requires_full_coverage_disabled_and_can(self):
        self.assertTrue(eligible(report()))
        self.assertFalse(eligible(report(drives=(64,0,0,0,0,0,0))))
        v=report();v["can"]=None;self.assertFalse(eligible(v))
        v=report();v["motors"]["rows"][0].update(level=3,enabled=None,rawStatus=None,faults=None,voltageV=None,driverTempC=None,motorTempC=None,currentA=None)
        self.assertFalse(eligible(v))

class PersistenceTests(unittest.TestCase):
    def test_one_use_expired_and_scope(self):
        with tempfile.TemporaryDirectory() as d:
            now=[100.];a=Approval(d,clock=lambda:now[0])
            a.grant(ID,1);self.assertFalse(a.consume(ID,2));self.assertFalse(a.consume(ID,1))
            a.grant(ID,1);self.assertTrue(a.consume(ID,1));self.assertFalse(a.consume(ID,1))
            a.grant(ID,1);now[0]+=61;self.assertFalse(a.consume(ID,1))
    def test_attempt_links_and_crash_no_replay(self):
        with tempfile.TemporaryDirectory() as d:
            h=FaultHistory(d);h.observe(report(drives=(4,0,0,0,0,0,0)))
            self.assertIsNone(h.begin_clear(ID,1,"operator",100.))
            self.assertEqual(h.begin_clear(ID,1,"operator",100.)["result"],"UNVERIFIED")
            h.close();h=FaultHistory(d)
            self.assertEqual(h.begin_clear(ID,1,"operator",101.)["result"],"UNVERIFIED")
            page=h.page(ID,"J1","ACTIVE");self.assertTrue(validate_history(page))
            self.assertEqual(page["events"][0]["lastClear"]["reason"],"INTERRUPTED")
            self.assertTrue(validate_attempts(h.attempts(ID)))
            h.close()
    def test_core_dispatch_uses_mock_only_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);obs=root/"obs";hist=root/"hist";obs.mkdir(mode=0o700);hist.mkdir(mode=0o700)
            v=report(time.time(),drives=(4,0,0,0,0,0,0));ob={k:v[k] for k in ("schema","capturedAt","graph","node","joints","arm","motors","parameters","can")};ob["schema"]="vision.nero-observation.v1"
            atomic_json(obs/"observation.json",ob,MAX_BYTES)
            calls=[]
            def change(op,scope):
                calls.append((op,scope))
                m=Mock(after=((0,)*7,0))
                return m.engine().execute(op,scope,110.)
            host=CoreHost(root/"library",diagnostics=lambda:(),nero_directory=obs,nero_history_directory=hist,
                         nero_clear_transport=SimpleNamespace(change=change),
                         nero_clear_interlock=lambda:{"coreConnection":"CONNECTED","state":"NO_ACTIVE_SESSION"})
            try:
                host._nero.usb=lambda:{"nero":"USB_CAN_DETECTED"}
                deadline=time.monotonic()+2
                while not host._nero_history.available and time.monotonic()<deadline:time.sleep(.02)
                intent={"instanceId":host.station_report()["instanceId"],"operationId":ID,"scope":1,"operator":"operator"}
                r=host.clear_nero(**intent);self.assertEqual(r["operation"]["result"],"CLEARED")
                self.assertEqual(host.clear_nero(**intent),r)
                self.assertEqual(calls,[(ID,1)])
            finally:host.close_nero_history()
