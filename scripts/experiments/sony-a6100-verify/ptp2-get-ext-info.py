#!/usr/bin/env python3
"""Sony PTP2 SDIO_GetExtDeviceInfo 0x9202 capability probe.
Only PTP Open/CloseSession, SDIO_Connect (authentication phases), and 0x9202.
No property setters (0x9205), no actuator controls (0x9207), no USB reset.
Use exact documented Sony handshake. Bounded retries, small timeouts.
"""
import ctypes as C, importlib.util, struct, sys, json, os, hashlib, time
from pathlib import Path
from datetime import datetime,timezone

BASE=Path('/srv/vision-data/tools/sony-a6100-verify')
OUT=BASE/'ptp2-capabilities-test'
spec=importlib.util.spec_from_file_location("ptp_usb_info",str(BASE/'ptp2-get-device-info.py'))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ALLOWED={
 0x1002:'OpenSession',
 0x9201:'SDIO_Connect',
 0x9202:'SDIO_GetExtDeviceInfo',
 0x1003:'CloseSession',
}
RESPONSES={0x2001:'OK',0x2002:'General_Error',0x2003:'Session_Not_Open',
           0x2005:'Operation_Not_Supported',0x2019:'Device_Busy',0xA101:'Sony_Authentication_Failed'}

def transact(handle,op,tid,params):
    if op not in ALLOWED:raise RuntimeError('NON_READONLY_OPCODE_DENIED')
    if op in (0x1002,0x1003):
        if op==0x1002 and tuple(params)!=(1,):raise RuntimeError('INVALID_OPEN_PARAMS')
        if op==0x1003 and params:raise RuntimeError('INVALID_CLOSE_PARAMS')
    elif op==0x9201:
        if len(params)!=3 or params[0] not in (1,2,3) or params[1:] !=(0,0):
            raise RuntimeError('INVALID_AUTH_PARAMETERS')
    elif op==0x9202 and tuple(params)!=(0xC8,):
        raise RuntimeError('INVALID_PROTOCOL_VERSION')
    req=struct.pack('<IHHI',12+4*len(params),1,op,tid)+b''.join(struct.pack('<I',x) for x in params)
    n=mod.transfer(handle,mod.EP_OUT,req,timeout_ms=2400)
    if len(n)!=len(req):raise RuntimeError('PTP_REQUEST_SHORT_WRITE')
    buf=bytearray()
    datasets=[]
    response=None
    deadline=time.monotonic()+8.5
    while time.monotonic()<deadline and response is None:
        block=mod.transfer(handle,mod.EP_IN,n=16384,timeout_ms=2400)
        if not block:continue
        buf+=block
        if len(buf)>66000:raise RuntimeError('PTP_RX_EXCESS')
        while len(buf)>=12:
            length,kind,code,t=struct.unpack_from('<IHHI',buf)
            if not 12<=length<=65536:raise RuntimeError(f'PTP_CONTAINER_LENGTH={length}')
            if len(buf)<length:break
            payload=bytes(buf[12:length])
            del buf[:length]
            if t!=tid:raise RuntimeError(f'UNEXPECTED_TID={t} instead of={tid}')
            if kind==2:
                if code!=op:raise RuntimeError('UNEXPECTED_DATA_OPERATION')
                datasets.append(payload)
            elif kind==3:
                response={'status':f'0x{code:04X}','meaning':RESPONSES.get(code,'Other'),
                          'parameters':[f'0x{x:08X}' for x in struct.unpack('<'+'I'*(len(payload)//4),payload)]}
                break
            else:raise RuntimeError(f'INVALID_PTP_CONTAINER_KIND={kind}')
    if response is None:raise RuntimeError('TIMEOUT_NO_PTP_RESPONSE')
    data=b''.join(datasets)
    print(f'PTP_TRANSACTION={ALLOWED[op]}(0x{op:04X}) response={response["status"]} data_bytes={len(data)}',flush=True)
    return response,data

def parse_sdi_dataset(data):
    if len(data)<10:raise ValueError(f'SDI_DATA_TOO_SHORT={len(data)}')
    extver,=struct.unpack_from('<H',data,0)
    offset=2
    def codes():
        nonlocal offset
        if offset+4>len(data):raise ValueError('SDI_NO_ARRAY_HEADER')
        count,=struct.unpack_from('<I',data,offset)
        offset+=4
        if count>3000 or offset+2*count>len(data):raise ValueError('SDI_INVALID_ARRAY_LENGTH')
        values=[f'0x{n:04X}' for n in struct.unpack_from('<'+'H'*count,data,offset)] if count else []
        offset+=2*count
        return values
    props=codes()
    controls=codes()
    return {
      'extension_version_hex':f'0x{extver:04X}',
      'extension_version_expected':'0x00C8',
      'version_matches': extver==0x00C8,
      'properties':props,
      'controls':controls,
      'num_properties':len(props),
      'num_controls':len(controls),
      'unused_bytes':len(data)-offset,
    }

def main():
    info={'test':'sony_ptp2_extended_caps_read_only','timestamp_utc':datetime.now(timezone.utc).isoformat(),
          'sony_device_bus_dev':mod.check_device(),
          'operation_allowlist':{f'0x{k:04X}':v for k,v in ALLOWED.items()},
          'ptp_transactions':[],'status':'STARTED'}
    advertised=json.loads((OUT/'get-device-info.json').read_text())['device_info']['operations_supported']
    assert all(v in advertised for v in ('0x1002','0x1003','0x9201','0x9202')), 'OPERATION_NOT_ADVERTISED'
    ctx=C.c_void_p()
    rc=mod.lib.libusb_init(C.byref(ctx))
    if rc:raise RuntimeError(f'LIBUSB_INIT={rc}')
    handle=None
    claimed=False
    session_open=False
    tid=0
    try:
        handle=mod.lib.libusb_open_device_with_vid_pid(ctx,mod.VID,mod.PID)
        if not handle:raise RuntimeError('DEVICE_OPEN_FAILED')
        driver=mod.lib.libusb_kernel_driver_active(handle,0)
        if driver==1:raise RuntimeError('KERNEL_DRIVER_PRESENT_ABORT_NO_DETACH')
        rc=mod.lib.libusb_claim_interface(handle,0)
        if rc:raise RuntimeError(f'CLAIM_INTERFACE_ERROR={rc}')
        claimed=True
        print('CAMERA_IDENTIFICATION_AND_LIBUSB_INTERFACE=PASS; NO_DETACH_OR_RESET',flush=True)
        resp,data=transact(handle,0x1002,0,(1,))
        info['ptp_transactions'].append({'operation':'0x1002','phase':'open','response':resp})
        if resp['status']!='0x2001':raise RuntimeError('PTP_SESSION_NOT_OPEN')
        session_open=True
        tid=1
        for phase in (1,2):
            resp,data=transact(handle,0x9201,tid,(phase,0,0))
            info['ptp_transactions'].append({'operation':'0x9201','phase':phase,'response':resp,'data_size':len(data)})
            tid+=1
            if resp['status']!='0x2001':raise RuntimeError(f'SDIO_CONNECT_{phase}_FAILED')
        max_attempts=3
        for attempt in range(1,max_attempts+1):
            resp,data=transact(handle,0x9202,tid,(0xC8,))
            info['ptp_transactions'].append({'operation':'0x9202','attempt':attempt,'response':resp,'data_size':len(data)})
            tid+=1
            if resp['status']!='0x2001':raise RuntimeError('SDIO_GET_EXT_DEVICE_INFO_FAILED')
            if data:
                parsed=parse_sdi_dataset(data)
                info['sdi_capabilities']=parsed
                digest=hashlib.sha256(data).hexdigest()
                (OUT/'get-ext-device-info.bin').write_bytes(data)
                info['sdi_payload_sha256']=digest
                print('SDI_PROTOCOL_VERSION='+parsed['extension_version_hex'],flush=True)
                print('EXTENDED_PROPERTIES_COUNT='+str(parsed['num_properties']),flush=True)
                print('EXTENDED_CONTROLS_COUNT='+str(parsed['num_controls']),flush=True)
                print('EXTENDED_PROPERTIES='+' '.join(parsed['properties']),flush=True)
                print('EXTENDED_CONTROLS='+' '.join(parsed['controls']),flush=True)
                print('SDI_EXT_DATA_SHA256='+digest,flush=True)
                break
            print('SDIO_DATA_EMPTY_RETRY='+str(attempt),flush=True)
            if attempt==max_attempts:raise RuntimeError('SDIO_GET_EXT_INFO_EMPTY_BOUNDED_ABORT')
            time.sleep(.25)
        # Complete ephemeral documented handshake, then close PTP session.
        resp,dt=transact(handle,0x9201,tid,(3,0,0))
        info['ptp_transactions'].append({'operation':'0x9201','phase':3,'response':resp,'data_size':len(dt)})
        tid+=1
        if resp['status']!='0x2001':raise RuntimeError('SDIO_CONNECT_PHASE3_FAILED')
        info['status']='PASS'
    except Exception as exc:
        info['status']='ERROR'
        info['error']=repr(exc)
        print('PTP_CAPABILITY_PROBE_ERROR='+repr(exc),flush=True)
    finally:
        if session_open:
            try:
                resp,dt=transact(handle,0x1003,tid,())
                info['ptp_transactions'].append({'operation':'0x1003','phase':'close','response':resp})
                print('PTP_SESSION_CLOSED='+str(resp['status']=='0x2001'),flush=True)
            except Exception as exc:
                info['close_error']=repr(exc)
                print('PTP_SESSION_CLOSE_FAILED='+repr(exc),flush=True)
        if claimed:
            rc=mod.lib.libusb_release_interface(handle,0)
            print('LIBUSB_INTERFACE_RELEASE_RC='+str(rc),flush=True)
        if handle:mod.lib.libusb_close(handle)
        mod.lib.libusb_exit(ctx)
        info['completed_utc']=datetime.now(timezone.utc).isoformat()
        (OUT/'get-ext-device-info.json').write_text(json.dumps(info,indent=2,ensure_ascii=False)+'\n')
        print('USB_HANDLE_CLOSED=YES',flush=True)
    print('STATUS='+info['status'],flush=True)
    print('EVIDENCE='+str(OUT/'get-ext-device-info.json'),flush=True)
    if info['status']!='PASS':sys.exit(2)
if __name__=='__main__':main()
