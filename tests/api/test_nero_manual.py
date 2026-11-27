import unittest
from vision_station.nero_manual import ManualEngine,Profile,Feedback,NANO

ID="a"*32
OP="b"*32
class Clock:
    now=100.
    def wall(self):return self.now
    def step(self,dt):self.now+=dt
class Ports:
    def __init__(self,c):
        self.c=c;self.drives=False;self.approval=False;self.ready=True
        self.enables=0;self.positions=[];self.holds=0;self.twists=[];self.q=(0.,)*7;self.ref=None
        self.stale=False;self.bad=False
    def read_feedback(self):
        t=self.c.now-(.3 if self.stale else .005)
        return Feedback(self.q,(0.,)*7,t,t,0 if self.drives else 6,1 if self.bad else 0,1,
                        (64 if self.drives else 0,)*7,(t,)*7,(t,)*7)
    def pipeline_ready(self):return self.ready
    def approve(self,v):
        ok=self.approval;self.approval=False;return ok
    def enable(self):self.enables+=1
    def twist(self,v):self.twists.append(v)
    def reference(self):r=self.ref;self.ref=None;return r
    def position(self,q):self.positions.append(q);self.q=q
    def hold(self):self.holds+=1;return True
class ManualTests(unittest.TestCase):
    def setUp(self):
        self.c=Clock();self.p=Ports(self.c)
        self.e=ManualEngine(Profile(10,5,((-1.,1.),)*7,(.05,)*7,.01),self.p,wall=self.c.wall,mono=self.c.wall)
    def cmd(self,action,seq=0,**kw):
        return self.e.command({"instanceId":ID,"operationId":OP,"action":action,"sequence":seq,"sentAt":self.c.now,
            "declaration":None,"axis":None,"direction":None,**kw})
    def tick(self,dt=.02):self.c.step(dt);self.e.tick()
    def enabled(self):
        self.p.approval=True;self.assertTrue(self.cmd("ENABLE")["accepted"])
        self.assertEqual(self.e.state,"ENABLING")
        self.p.drives=True;self.tick();self.tick();self.assertEqual(self.e.state,"READY")
    def jog(self,seq=1):
        return self.cmd("JOG",seq,declaration={"frame":"BASE","linearMmS":5,"angularDegS":2},axis="X",direction=1)
    def ref(self,q=.0002):
        self.p.ref={"stampNs":int(self.c.now*NANO),"windowEndNs":int((self.c.now+.1)*NANO),
                    "status":0,"positions":[q]*7,"velocities":[.01]*7}
    def test_enable_explicit_and_observed(self):
        self.assertFalse(self.cmd("ENABLE")["accepted"]);self.assertEqual(self.p.enables,0)
        self.enabled();self.assertEqual(self.p.enables,1);self.assertEqual(self.p.positions,[])
        self.assertFalse(self.cmd("ENABLE")["accepted"])
    def test_enable_timeout_no_retry(self):
        self.p.approval=True;self.cmd("ENABLE");self.tick(3)
        self.assertEqual(self.e.state,"HOLD");self.assertEqual(self.p.enables,1);self.assertEqual(self.p.holds,1)
    def test_jtc_reference_and_lease(self):
        self.enabled();self.assertTrue(self.jog()["accepted"]);self.c.step(.02);self.ref();self.e.tick()
        self.assertEqual(len(self.p.positions),1);self.assertEqual(self.p.twists[-1]["linear"],[.005,0.,0.])
        self.tick(.31);self.assertEqual(self.e.state,"HOLD");self.assertEqual(self.p.holds,1)
        self.assertFalse(self.jog(2)["accepted"]);self.assertEqual(len(self.p.positions),1)
    def test_external_hold(self):
        self.enabled();self.jog();self.e.external_hold();self.ref();self.tick()
        self.assertEqual(self.p.positions,[]);self.assertFalse(self.jog(2)["accepted"])
    def test_release(self):
        self.enabled();self.jog();self.c.step(.02);self.ref();self.e.tick();self.cmd("RELEASE",2)
        for _ in range(12):
            self.c.step(.02);self.ref(self.p.q[0]);self.p.ref["velocities"]=[0.]*7;self.e.tick()
        self.assertEqual(self.e.state,"READY");self.assertEqual(self.p.holds,0)
    def test_reference_limits(self):
        self.enabled();self.jog();self.c.step(.02);self.ref(.4);self.e.tick()
        self.assertEqual(self.p.positions,[]);self.assertEqual(self.e.state,"HOLD")
    def test_feedback_lost(self):
        self.enabled();self.jog();self.p.stale=True;self.tick()
        self.assertEqual(self.p.positions,[]);self.assertEqual(self.e.state,"HOLD")
    def test_bad_speed(self):
        self.enabled();self.assertFalse(self.cmd("JOG",1,declaration={"frame":"BASE","linearMmS":100,"angularDegS":5},axis="X",direction=1)["accepted"])
        self.assertEqual(self.p.positions,[])

class ManualBoundaryTests(unittest.TestCase):
    def test_complete_private_and_local_http_path(self):
        import threading
        import test_station as fixture
        from vision_station.host import CoreHost
        from vision_station.server import CoreServer
        from vision_station.client import RemoteStationOwner
        from vision_station.nero_manual_transport import ManualTransport,ManualOwnerServer
        from vision_api.station import StationApplication
        from vision_api.identity import provision_account
        from vision_station.inspection import InspectionRejected

        web=fixture.StationTests();web.setUp();self.addCleanup(web.doCleanups)
        c=Clock();p=Ports(c)
        engine=ManualEngine(Profile(10,5,((-1.,1.),)*7,(.05,)*7,.01),p,wall=c.wall,mono=c.wall)
        private=web.root/"owner";private.mkdir(mode=0o700)
        server=ManualOwnerServer(private/"manual.sock",engine);self.addCleanup(server.close)
        host=CoreHost(web.root/"manual-library",diagnostics=lambda:(),
                      nero_manual_transport=ManualTransport(private/"manual.sock"))
        core=CoreServer(web.root/"ipc/core.sock",host)
        thread=threading.Thread(target=core.serve_forever,kwargs={"poll_interval":.01});thread.start()
        self.addCleanup(lambda:(core.shutdown(),thread.join(3),core.server_close()))
        proxy=RemoteStationOwner(web.root/"ipc/core.sock")
        web.app.owner=proxy
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        _,cookie=web.login()
        route="/api/v1/devices/nero/manual"
        headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui","REMOTE_ADDR":"127.0.0.1"}
        instance=proxy.station_report()["instanceId"]
        req={"instanceId":instance,"operationId":OP,"action":"ENABLE","sequence":0,"sentAt":c.now,
             "declaration":None,"axis":None,"direction":None}
        self.assertIsNone(web.request(route,cookie=cookie,headers=headers)["json"]["status"])
        self.assertEqual(web.request(route+"/command",method="POST",cookie=cookie,value=req,headers=headers)["status"],403)
        self.assertEqual(p.enables,0)
        web.app=StationApplication(identity=web.identity,owner=proxy,dist_root=web.dist,
                                   origins=["http://127.0.0.1:18490"],manual_local=True)
        self.assertEqual(web.request(route)["status"],401)
        self.assertIsNone(web.request(route,cookie=cookie,headers={**headers,"REMOTE_ADDR":"192.0.2.1"})["json"]["status"])
        self.assertEqual(web.request(route+"/command",method="POST",cookie=cookie,value=req,
                                    headers={**headers,"REMOTE_ADDR":"192.0.2.1"})["status"],403)
        self.assertTrue(web.request(route,cookie=cookie,headers=headers)["json"]["status"]["enableAvailable"])
        denied=web.request(route+"/command",method="POST",cookie=cookie,value=req,headers=headers)["json"]["result"]
        self.assertEqual(denied["reason"],"NO_LOCAL_CONFIRMATION");self.assertEqual(p.enables,0)
        p.approval=True
        accepted=web.request(route+"/command",method="POST",cookie=cookie,value=req,headers=headers)["json"]["result"]
        self.assertTrue(accepted["accepted"]);self.assertEqual(accepted["state"],"ENABLING");self.assertEqual(p.enables,1)
        p.drives=True;c.step(.02);engine.tick();c.step(.02);engine.tick()
        self.assertEqual(web.request(route,cookie=cookie,headers=headers)["json"]["status"]["state"],"READY")
        jog={**req,"action":"JOG","sequence":1,"sentAt":c.now,
             "declaration":{"frame":"BASE","linearMmS":5,"angularDegS":2},"axis":"X","direction":1}
        self.assertFalse(proxy.nero_manual_command(operator="other",**jog)["result"]["accepted"])
        self.assertTrue(web.request(route+"/command",method="POST",cookie=cookie,value=jog,headers=headers)["json"]["result"]["accepted"])
        c.step(.02);p.ref={"stampNs":int(c.now*NANO),"windowEndNs":int((c.now+.1)*NANO),"status":0,
                          "positions":[.0002]*7,"velocities":[.01]*7};engine.tick()
        self.assertEqual(len(p.positions),1)
        hold={**req,"action":"HOLD","sequence":2,"sentAt":c.now}
        self.assertTrue(web.request(route+"/command",method="POST",cookie=cookie,value=hold,headers=headers)["json"]["result"]["accepted"])
        self.assertEqual(p.holds,1);self.assertEqual(engine.state,"HOLD")
        with self.assertRaises(InspectionRejected):host.start_inspection()

    def test_native_ports_delegate_only_existing_owner(self):
        from types import SimpleNamespace as NS
        from vision_station.ros_nero_manual import NativePorts
        c=Clock();p=Ports(c)
        from unittest.mock import patch
        native=NativePorts.__new__(NativePorts)
        calls=[]
        native.owner=NS(agx_arm=NS(enable=lambda **kw:calls.append(("enable",kw))),
                        _control_arm_joints=lambda q:calls.append(("position",q)))
        native.pipeline_ready=lambda:True;native.read_feedback=p.read_feedback
        with patch("vision_station.ros_nero_manual.time.time",c.wall):
            native.enable()
            self.assertEqual(calls,[("enable",{"timeout":0.})])
            with self.assertRaises(RuntimeError):native.position((0.,)*7)
            p.drives=True
            native.position((.01,)*7)
        self.assertEqual(calls[-1],("position",{f"joint{i}":.01 for i in range(1,8)}))
