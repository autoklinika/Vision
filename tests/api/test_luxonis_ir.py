"""Closed manual IR command boundary: no real camera access in unit tests."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
from vision_api.access import ReportUnavailable
from vision_api.identity import provision_account
from vision_station.luxonis import atomic_json, empty_observation, MAX_SNAPSHOT
from vision_station.luxonis_ir import IRController, IRRejected, validate_request, validate_result
from vision_station.host import CoreHost
from vision_station.server import CoreServer, dispatch
from vision_station.protocol import PROTOCOL
from vision_station.client import RemoteStationOwner
import test_station as fixtures

def reply(instance,channel,enabled,dot=0.,flood=0.):
    values={"dot":dot,"flood":flood};values[channel]=.6 if enabled else 0.
    return {"schema":"vision.api.luxonis-ir.v1","source":"STATION","instanceId":instance,
            "channel":channel,"enabled":enabled,"capturedAt":time.time(),**values}

def observed(root, *, gate=True,domain=186):
    now=time.time()
    data=empty_observation(now)
    data.update(graph="ACTIVE",node={"domain":domain,"name":"/oak"},
      endpoints={"rgb":"AVAILABLE","depth":"AVAILABLE"},settingsAt=now,
      settings={"driver.i_enable_ir":gate,"driver.r_laser_dot_intensity":0.,"driver.r_floodlight_intensity":0.})
    atomic_json(root/"observation.json",data,MAX_SNAPSHOT)

class IRTests(unittest.TestCase):
    def test_closed_shape_and_confirmation(self):
        body={"instanceId":"a"*32,"channel":"dot","enabled":True}
        self.assertTrue(validate_request(body))
        for bad in ({**body,"channel":"rgb.i_width"},{**body,"enabled":1},{**body,"intensity":.9}):
            self.assertFalse(validate_request(bad))
        result=reply(**{"instance":body["instanceId"],"channel":"dot","enabled":True})
        self.assertTrue(validate_result(result))
        self.assertFalse(validate_result({**result,"dot":0.}))
        self.assertFalse(validate_result({**result,"flood":1.2}))

    def test_controller_calls_fixed_helper(self):
        run=Mock(return_value=NS(returncode=0,stdout=json.dumps({"dot":.6,"flood":0.,"capturedAt":time.time()})))
        c=IRController(run=run)
        self.assertTrue(validate_result(c.change("a"*32,"dot",True)))
        argv=run.call_args.args[0]
        self.assertEqual(argv[-2:],["dot","on"])
        self.assertEqual(run.call_args.kwargs["env"]["ROS_DOMAIN_ID"],"186")
        self.assertEqual(run.call_args.kwargs["timeout"],7.)
        with self.assertRaises(ValueError):c.change("a"*32,"driver.i_enable_ir",True)
        self.assertEqual(run.call_count,1)
        run.return_value=NS(returncode=2,stdout="")
        with self.assertRaises(IRRejected):c.change("a"*32,"dot",True)
        run.return_value=NS(returncode=0,stdout=json.dumps({"dot":0.,"flood":0.,"capturedAt":time.time()}))
        with self.assertRaises(ReportUnavailable):c.change("a"*32,"dot",True)

    def test_authenticated_real_ipc_and_idle_interlock(self):
        web=fixtures.StationTests();web.setUp();self.addCleanup(web.doCleanups)
        root=web.root/"monitor";root.mkdir(mode=0o700)
        controller=Mock()
        controller.change.side_effect=reply
        other={"coreConnection":"CONNECTED","state":"NO_ACTIVE_SESSION"}
        host=CoreHost(web.root/"ir-library",diagnostics=lambda:(),luxonis_directory=root,
                      luxonis_ir=controller,luxonis_ir_interlock=lambda:other)
        host._luxonis.usb=lambda:{"luxonis":"USB_DETECTED"}
        observed(root)
        socket=web.root/"ir-ipc/core.sock";server=CoreServer(socket,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01});thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        web.app.owner=RemoteStationOwner(socket)
        path="/api/v1/devices/luxonis/ir"
        body={"instanceId":host.station_report()["instanceId"],"channel":"dot","enabled":True}
        headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui"}
        def post(cookie=None,value=body,extra=headers):
            return web.request(path,method="POST",value=value,cookie=cookie,headers=extra)
        self.assertEqual(post()["status"],401)
        _,reader=web.login();self.assertEqual(post(reader)["status"],403)
        self.assertEqual(controller.change.call_count,0)
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        _,operator=web.login()
        self.assertEqual(post(operator,extra={})["status"],403)
        self.assertEqual(post(operator,{**body,"channel":"arbitrary"})["status"],400)
        self.assertEqual(post(operator,{**body,"instanceId":"b"*32})["status"],409)
        other["state"]="SESSION_ACTIVE"
        self.assertEqual(post(operator)["status"],409)
        other["state"]="NO_ACTIVE_SESSION"
        observed(root,domain=181)
        self.assertEqual(post(operator)["status"],409)
        observed(root,gate=False)
        self.assertEqual(post(operator)["status"],409)
        observed(root)
        status=web.request("/api/v1/devices/luxonis",cookie=operator)
        self.assertTrue(status["json"]["irControlAvailable"])
        self.assertEqual(controller.change.call_count,0)
        accepted=post(operator)
        self.assertEqual(accepted["status"],200)
        self.assertEqual(accepted["json"]["dot"],.6)
        controller.change.assert_called_once_with(body["instanceId"],"dot",True)
        with self.assertRaises(ValueError):
            dispatch(host,{"schema":PROTOCOL,"operation":"luxonis_ir","query":{**body,"intensity":1.}})
