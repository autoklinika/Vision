"""Read-only device projection and protected transport. Synthetic images only."""
import base64
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from vision_station.luxonis import (LuxonisMonitor, MAX_JPEG, MAX_SNAPSHOT, atomic_json,
    empty_observation, lease_active, valid_observation, validate_luxonis_report)
from vision_station.ros_luxonis import preview_image, endpoint
from vision_station.host import CoreHost
from vision_station.server import CoreServer, dispatch
from vision_station.client import RemoteStationOwner
from vision_station.protocol import PROTOCOL
from vision_api.identity import provision_account
import test_station as fixtures

NOW=100.0

def message(encoding="bgr8", big=False, stamp=99.5):
    width,height=32,24
    if encoding=="bgr8":
        line=bytes([20,90,200])*width+b"PAD!"
    elif encoding=="rgb8":
        line=bytes([200,90,20])*width+b"PAD!"
    elif encoding=="16UC1":
        line=(800).to_bytes(2,"big" if big else "little")*width+b"PAD!"
    else:
        import struct
        line=struct.pack(">f" if big else "<f",.8)*width+b"PAD!"
    return NS(header=NS(stamp=NS(sec=int(stamp),nanosec=int((stamp-int(stamp))*1e9)),frame_id="fixture_optical"),
        width=width,height=height,step=len(line),encoding=encoding,is_bigendian=int(big),data=line*height)


def observation(now=NOW):
    data=empty_observation(now,{"rgbd_lab":{"rgb.i_fps":15.0}})
    data.update(graph="ACTIVE",node={"domain":181,"name":"/oak"},
                endpoints={"rgb":"AVAILABLE","depth":"AVAILABLE"},settings={"driver.i_enable_ir":False,"rgb.i_fps":15.},
                settingsAt=now-.1)
    data["frames"]={s:preview_image(message("bgr8" if s=="rgb" else "16UC1",stamp=now-.5),s,now) for s in ("rgb","depth")}
    assert all(data["frames"].values())
    return data


class PreviewTests(unittest.TestCase):
    def test_stride_color_and_depth_encoding(self):
        import cv2
        import numpy as np
        def decode(v):
            return cv2.imdecode(np.frombuffer(base64.b64decode(v["jpeg"]),np.uint8),cv2.IMREAD_COLOR)
        a=decode(preview_image(message("bgr8"),"rgb",NOW))
        b=decode(preview_image(message("rgb8"),"rgb",NOW))
        self.assertTrue(np.array_equal(a,b))
        self.assertLess(abs(int(a[0,0,2])-200),4)
        depth=[decode(preview_image(message(enc,big),"depth",NOW)) for enc in ("16UC1","32FC1") for big in (False,True)]
        for item in depth:
            self.assertTrue(np.array_equal(depth[0],item))
        z=message("16UC1");z.data=bytes(z.step*z.height)
        self.assertEqual(int(decode(preview_image(z,"depth",NOW)).max()),0)
        self.assertIsNone(preview_image(message(stamp=90),"rgb",NOW))
        bad=message();bad.data=b"short"
        self.assertIsNone(preview_image(bad,"rgb",NOW))

    def test_report_privacy_freshness_and_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            value=observation()
            self.assertTrue(valid_observation(value))
            atomic_json(root/"observation.json",value,MAX_SNAPSHOT)
            clock=[NOW]
            m=LuxonisMonitor(root,clock=lambda:clock[0],usb=lambda:{"luxonis":"USB_DETECTED"})
            r=m.report("a"*32)
            self.assertTrue(validate_luxonis_report(r))
            self.assertEqual(r["frames"],{"rgb":None,"depth":None})
            self.assertFalse((root/"viewer.json").exists())
            r=m.report("a"*32,preview=True)
            self.assertTrue(validate_luxonis_report(r))
            self.assertTrue(all(r["frames"].values()))
            self.assertTrue(lease_active(root,NOW))
            blocked=m.report("a"*32,preview=True,idle=False)
            self.assertFalse(blocked["previewAllowed"])
            self.assertEqual(blocked["frames"],{"rgb":None,"depth":None})
            clock[0]+=3
            r=m.report("a"*32)
            self.assertEqual(r["graph"],"ACTIVE")
            self.assertIsNone(m.report("a"*32,preview=True)["frames"]["rgb"])
            clock[0]+=5
            r=m.report("a"*32)
            self.assertEqual(r["observer"],"UNAVAILABLE")
            self.assertEqual(r["settings"],{})
            self.assertEqual(r["graph"],"UNKNOWN")
            self.assertFalse(lease_active(root,clock[0]))
            # Shared-permission/symlink snapshots cannot expose frames.
            atomic_json(root/"observation.json",observation(clock[0]),MAX_SNAPSHOT)
            (root/"observation.json").chmod(0o644)
            self.assertEqual(m.report("a"*32,preview=True)["observer"],"UNAVAILABLE")
            (root/"observation.json").unlink()
            (root/"other").write_text("{}");(root/"observation.json").symlink_to(root/"other")
            self.assertEqual(m.report("a"*32,preview=True)["observer"],"UNAVAILABLE")

    def test_schema_and_source_rejections(self):
        r=observation()
        r["settings"]["serial"]="private"
        self.assertFalse(valid_observation(r))
        r=observation();r["node"]["domain"]=99
        self.assertFalse(valid_observation(r))
        r=observation();r["frames"]["rgb"]["jpeg"]=base64.b64encode(bytes(MAX_JPEG+1)).decode()
        self.assertFalse(valid_observation(r))
        r=observation();r["graph"]="NO_NODE"
        self.assertFalse(valid_observation(r))
        node=NS(get_publishers_info_by_topic=lambda _: [NS(node_namespace="/",node_name="oak",topic_type="sensor_msgs/msg/Image",endpoint_gid=[1,2])])
        self.assertEqual(endpoint(node,"/oak/rgb/image_raw","/oak"),("AVAILABLE",(1,2)))
        self.assertEqual(endpoint(node,"/oak/rgb/image_raw","/oak800"),("AMBIGUOUS",None))

    def test_actual_http_ipc_role_boundary(self):
        web=fixtures.StationTests()
        web.setUp();self.addCleanup(web.doCleanups)
        directory=web.root/"monitor";directory.mkdir(mode=0o700)
        host=CoreHost(web.root/"test-library",diagnostics=lambda:(),luxonis_directory=directory)
        host._luxonis.usb=lambda:{"luxonis":"USB_DETECTED"}
        atomic_json(directory/"observation.json",observation(time.time()),MAX_SNAPSHOT)
        socket=web.root/"luxonis-ipc/core.sock"
        server=CoreServer(socket,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        web.app.owner=RemoteStationOwner(socket)
        status="/api/v1/devices/luxonis";preview=status+"/preview"
        self.assertEqual(web.request(status)["status"],401)
        self.assertEqual(web.request(preview)["status"],401)
        _,reader=web.login()
        r=web.request(status,cookie=reader)
        self.assertEqual(r["status"],200)
        self.assertEqual(r["json"]["hardwareConnection"],"USB_DETECTED")
        self.assertTrue(all(f is None for f in r["json"]["frames"].values()))
        self.assertEqual(web.request(preview,cookie=reader)["status"],403)
        self.assertFalse((directory/"viewer.json").exists())
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        _,operator=web.login()
        atomic_json(directory/"observation.json",observation(time.time()),MAX_SNAPSHOT)
        r=web.request(preview,cookie=operator)
        self.assertEqual(r["status"],200)
        self.assertTrue(all(r["json"]["frames"].values()))
        self.assertEqual(r["headers"]["Cache-Control"],"no-store")
        self.assertTrue(lease_active(directory,time.time()))
        self.assertEqual(web.request(status+"?path=other",cookie=operator)["status"],404)
        self.assertEqual(web.request(status,method="POST",cookie=operator,value={})["status"],405)
        with self.assertRaises(ValueError):
            dispatch(host,{"schema":PROTOCOL,"operation":"luxonis_preview","query":{"topic":"/arbitrary"}})
        self.assertEqual(host.station_report()["state"],"NO_ACTIVE_SESSION")
