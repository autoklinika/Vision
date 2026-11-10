#!/usr/bin/env python3
"""Read-only Sony PTP2 property descriptor check, focusing on 0xD214 GetSet.
Allowed commands: temporary PTP session, documented auth phases, GET 0x9209.
Prohibits setter 0x9205 and actuator 0x9207.
"""
import ctypes as C, importlib.util, json, struct, sys, time, hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path('/srv/vision-data/tools/sony-a6100-verify')
OUT=ROOT/'ptp2-capabilities-test'
spec=importlib.util.spec_from_file_location('ptp2_ext',str(ROOT/'ptp2-get-ext-info.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
e.ALLOWED[0x9209]='SDIO_GetAllExtDevicePropInfo'
session_open=False
claimed=False
tid=0
ctx=C.c_void_p()
handle=None
report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'test':'Sony PTP2 read-only GetAllExtDevicePropInfo 0x9209','status':'STARTED','allowed_opcodes':sorted(f'0x{x:04X}' for x in e.ALLOWED)}
try:
    p=json.loads((OUT/'get-device-info.json').read_text())
    assert '0x9209' in p['device_info']['operations_supported'],'OP_NOT_ADVERTISED'
    assert e.mod.check_device()==p['camera_bus_dev'],'CAMERA_PORT_CHANGED'
    rc=e.mod.lib.libusb_init(C.byref(ctx))
    if rc:raise RuntimeError(f'LIBUSB_INIT={rc}')
    handle=e.mod.lib.libusb_open_device_with_vid_pid(ctx,e.mod.VID,e.mod.PID)
    if not handle:raise RuntimeError('SONY_OPEN_FAILED')
    if e.mod.lib.libusb_kernel_driver_active(handle,0)==1:raise RuntimeError('DRIVER_BUSY_NO_DETACH')
    rc=e.mod.lib.libusb_claim_interface(handle,0)
    if rc:raise RuntimeError(f'CLAIM_ERROR={rc}')
    claimed=True
    resp,data=e.transact(handle,0x1002,0,(1,))
    if resp['status']!='0x2001':raise RuntimeError('OPEN_SESSION_ERROR')
    session_open=True;tid=1
    for phase in (1,2):
        resp,data=e.transact(handle,0x9201,tid,(phase,0,0))
        if resp['status']!='0x2001':raise RuntimeError(f'CONNECT_PHASE_{phase}_ERROR')
        tid+=1
    resp,data=e.transact(handle,0x9202,tid,(0xC8,))
    if resp['status']!='0x2001' or not data:raise RuntimeError('EXT_INFO_NOT_READY')
    tid+=1
    resp,dt=e.transact(handle,0x9201,tid,(3,0,0))
    if resp['status']!='0x2001':raise RuntimeError('CONNECT_PHASE_3_ERROR')
    tid+=1
    resp,body=e.transact(handle,0x9209,tid,())
    if resp['status']!='0x2001' or not body:raise RuntimeError('GET_ALL_PROPS_ERROR')
    tid+=1
    (OUT/'get-all-ext-properties.bin').write_bytes(body)
    count,=struct.unpack_from('<Q',body,0)
    print(f'PTP_PROPERTY_DESCRIPTOR_COUNT={count} DATA_BYTES={len(body)}',flush=True)
    assert 1<=count<=2000,'IMPLAUSIBLE_ELEMENT_COUNT'
    # Fingerprint precise field sequence in official Sony PTP2 0xD214 descriptor,
    # according to Camera Control PTP 2 Reference PDF p.60:
    # PropertyCode U16, Datatype U16, GetSet U8, Enabled U8, Default U32,
    # Current U32, FormFlag U8, Range Min U32 Max U32 Step U32.
    marker=struct.pack('<HH',0xD214,0x0006)
    matches=[]
    for offset in range(8,len(body)-25):
        if body[offset:offset+4]!=marker:continue
        props=struct.unpack_from('<HHBBIIBIII',body,offset)
        code,dtype,getset,enabled,default,current,form,minval,maxval,step=props
        candidate={
          'offset':offset,'property_code_hex':f'0x{code:04X}',
          'data_type_hex':f'0x{dtype:04X}', 'getset':getset,
          'is_enabled':enabled,'default_value':default,'current_value':current,
          'form_flag':form,'range_min':minval,'range_max':maxval,'range_step':step,
        }
        if form==1 and minval==0 and maxval==0xffffffff and step==1:
            matches.append(candidate)
    report['sdi_num_elements']=count
    report['raw_bytes']=len(body)
    report['raw_sha256']=hashlib.sha256(body).hexdigest()
    report['d214_candidates']=matches
    if len(matches)==1:
        item=matches[0]
        print('D214_DESCRIPTOR_CONFIRMED='+json.dumps(item,sort_keys=True),flush=True)
        print('D214_GET_ONLY='+str(item['getset']==0).upper(),flush=True)
        report['status']='PASS'
    else:
        print('D214_DESCRIPTOR_NOT_UNIQUELY_LOCATED='+str(len(matches)),flush=True)
        report['status']='PARTIAL'
except Exception as ex:
    report['status']='ERROR'
    report['error']=repr(ex)
    print('PTP_PROPERTY_AUDIT_ERROR='+repr(ex),flush=True)
finally:
    if session_open:
        try:
            resp,dt=e.transact(handle,0x1003,tid,())
            report['session_close_status']=resp['status']
            print('PTP_SESSION_CLOSED='+str(resp['status']=='0x2001'),flush=True)
        except Exception as ex:
            report['session_close_error']=repr(ex)
            print('PTP_SESSION_CLOSE_ERROR='+repr(ex),flush=True)
    if claimed:e.mod.lib.libusb_release_interface(handle,0)
    if handle:e.mod.lib.libusb_close(handle)
    if ctx:e.mod.lib.libusb_exit(ctx)
    report['finished_utc']=datetime.now(timezone.utc).isoformat()
    (OUT/'get-all-ext-properties.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('USB_RELEASED=YES',flush=True)
    print('STATUS='+report['status'],flush=True)
if report['status']=='ERROR':sys.exit(2)
