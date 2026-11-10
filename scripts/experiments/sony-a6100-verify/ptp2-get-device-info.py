#!/usr/bin/env python3
"""Sony Camera Control PTP 2: read-only GetDeviceInfo (0x1001).
No session/authentication, no setter/control, no reset, no driver detach.
libusb ctypes, isolated to VENTUNO test directory, bounded response and timeout.
"""
import ctypes as C
import ctypes.util, json, os, struct, sys, time
from pathlib import Path
from datetime import datetime, timezone

VID,PID=0x054c,0x0f0d
EP_OUT,EP_IN=0x02,0x81
ROOT=Path('/srv/vision-data/tools/sony-a6100-verify/ptp2-capabilities-test')
ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)

lib=C.CDLL(ctypes.util.find_library('usb-1.0') or 'libusb-1.0.so.0')
lib.libusb_init.argtypes=[C.POINTER(C.c_void_p)]
lib.libusb_init.restype=C.c_int
lib.libusb_open_device_with_vid_pid.argtypes=[C.c_void_p,C.c_uint16,C.c_uint16]
lib.libusb_open_device_with_vid_pid.restype=C.c_void_p
lib.libusb_kernel_driver_active.argtypes=[C.c_void_p,C.c_int]
lib.libusb_kernel_driver_active.restype=C.c_int
lib.libusb_claim_interface.argtypes=[C.c_void_p,C.c_int]
lib.libusb_claim_interface.restype=C.c_int
lib.libusb_release_interface.argtypes=[C.c_void_p,C.c_int]
lib.libusb_release_interface.restype=C.c_int
lib.libusb_bulk_transfer.argtypes=[C.c_void_p,C.c_ubyte,C.POINTER(C.c_ubyte),C.c_int,C.POINTER(C.c_int),C.c_uint]
lib.libusb_bulk_transfer.restype=C.c_int
lib.libusb_close.argtypes=[C.c_void_p]
lib.libusb_exit.argtypes=[C.c_void_p]

def check_device():
    matches=[]
    for path in Path('/sys/bus/usb/devices').iterdir():
        try:
            if (path/'idVendor').read_text().strip()=='054c' and (path/'idProduct').read_text().strip()=='0f0d':
                bus=int((path/'busnum').read_text());dev=int((path/'devnum').read_text())
                assert os.access(f'/dev/bus/usb/{bus:03d}/{dev:03d}',os.R_OK|os.W_OK)
                matches.append([bus,dev])
        except (OSError,ValueError):continue
    assert len(matches)==1, f'CAMERA_COUNT={len(matches)}'
    return matches[0]

def transfer(handle,endpoint,data=None,n=16384,timeout_ms=2500):
    if data is None:
        b=(C.c_ubyte*n)();sz=n
    else:
        b=(C.c_ubyte*len(data)).from_buffer_copy(data);sz=len(data)
    actual=C.c_int()
    result=lib.libusb_bulk_transfer(handle,endpoint,b,sz,C.byref(actual),timeout_ms)
    if result:
        raise RuntimeError(f'LIBUSB_TRANSFER_ERROR endpoint=0x{endpoint:02X} code={result} actual={actual.value}')
    return bytes(b[:actual.value])

def transaction(handle,op,tid,params=()):
    assert op==0x1001 and not params, 'Only GetDeviceInfo is permitted in this stage'
    req=struct.pack('<IHHI',12+4*len(params),1,op,tid)
    written=transfer(handle,EP_OUT,req,timeout_ms=2500)
    assert len(written)==len(req), 'SHORT_WRITE'
    received=bytearray()
    datasets=[]
    response=None
    deadline=time.monotonic()+9
    while time.monotonic()<deadline and response is None:
        pkt=transfer(handle,EP_IN,n=16384,timeout_ms=2500)
        received+=pkt
        assert len(received)<131072,'OVERLONG_DEVICE_DATA'
        while len(received)>=12:
            length,kind,code,tx=struct.unpack_from('<IHHI',received,0)
            assert 12<=length<=65536,f'PTP_CONTAINER_LENGTH_INVALID {length}'
            if len(received)<length:break
            payload=bytes(received[12:length])
            del received[:length]
            assert tx==tid,f'WRONG_TRANSACTION_ID={tx}'
            if kind==2:
                assert code==op,'MISMATCH_DATA_CODE'
                datasets.append(payload)
            elif kind==3:
                response={'code':code,'code_hex':f'0x{code:04X}','params_hex':[f'0x{x:08X}' for x in struct.unpack('<'+'I'*(len(payload)//4),payload)]}
                break
            else:
                raise RuntimeError(f'UNEXPECTED_CONTAINER kind={kind} code={code:04X}')
    assert response is not None,'PTP_NO_RESPONSE'
    return response,b''.join(datasets)

def parse_info(payload):
    off=0
    def num(fmt):
        nonlocal off
        length=struct.calcsize(fmt)
        if off+length>len(payload):raise ValueError('TRUNCATED_DATA')
        val=struct.unpack_from(fmt,payload,off)[0];off+=length;return val
    def ptp_string():
        nonlocal off
        c=num('<B')
        n=c*2
        if off+n>len(payload):raise ValueError('TRUNCATED_STRING')
        raw=payload[off:off+n];off+=n
        return raw.decode('utf-16-le',errors='replace').rstrip('\x00')
    def array16():
        nonlocal off
        n=num('<I')
        if n>10000 or off+2*n>len(payload):raise ValueError('INVALID_ARRAY_COUNT')
        vals=list(struct.unpack_from('<'+'H'*n,payload,off)) if n else []
        off+=2*n
        return [f'0x{x:04X}' for x in vals]
    standard=num('<H');vendor=num('<I');extversion=num('<H');desc=ptp_string()
    func=num('<H')
    result={
      'standard_version_hex':f'0x{standard:04X}',
      'vendor_extension_id_hex':f'0x{vendor:08X}',
      'vendor_extension_version_hex':f'0x{extversion:04X}',
      'vendor_extension_description':desc,
      'functional_mode':func,
      'operations_supported':array16(),
      'events_supported':array16(),
      'device_properties_supported':array16(),
      'capture_formats':array16(),
      'image_formats':array16(),
      'manufacturer':ptp_string(),
      'model':ptp_string(),
      'device_version':ptp_string(),
      'serial_number_present':bool(ptp_string()),
      'parsed_bytes':off,
      'raw_length':len(payload),
    }
    return result

def main():
    info={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'test':'PTP_GetDeviceInfo_0x1001','read_only':True,'camera_bus_dev':check_device()}
    print('PREFLIGHT_CAMERA_SINGLE=PASS',flush=True)
    ctx=C.c_void_p()
    rc=lib.libusb_init(C.byref(ctx))
    if rc:raise RuntimeError(f'LIBUSB_INIT={rc}')
    handle=None
    claimed=False
    try:
        handle=lib.libusb_open_device_with_vid_pid(ctx,VID,PID)
        if not handle:raise RuntimeError('DEVICE_OPEN_FAIL')
        driver=lib.libusb_kernel_driver_active(handle,0)
        if driver==1:raise RuntimeError('KERNEL_DRIVER_ACTIVE_NO_DETACH')
        print('USB_KERNEL_DRIVER_DETACH=NOT_PERFORMED',flush=True)
        rc=lib.libusb_claim_interface(handle,0)
        if rc:raise RuntimeError(f'LIBUSB_CLAIM_FAILED code={rc}')
        claimed=True
        print('PTP_GET_DEVICE_INFO_REQUEST=0x1001',flush=True)
        response,payload=transaction(handle,0x1001,0)
        info['response']=response
        info['payload_bytes']=len(payload)
        print('PTP_RESPONSE='+response['code_hex'],flush=True)
        if response['code_hex']=='0x2001':
            parsed=parse_info(payload)
            info['device_info']=parsed
            print('CAMERA='+parsed['manufacturer']+' '+parsed['model'],flush=True)
            print('VENDOR_EXT='+parsed['vendor_extension_description'],flush=True)
            print('OPERATIONS_COUNT='+str(len(parsed['operations_supported'])),flush=True)
            print('EXT_OP_0x9202_ADVERTISED='+str('0x9202' in parsed['operations_supported']).upper(),flush=True)
            print('SONY_PTP_0x96FD_ADVERTISED='+str('0x96FD' in parsed['operations_supported']).upper(),flush=True)
            print('SONY_PTP_0x96FE_ADVERTISED='+str('0x96FE' in parsed['operations_supported']).upper(),flush=True)
            print('OPERATIONS='+' '.join(parsed['operations_supported']),flush=True)
        else:
            print('PTP_GET_DEVICE_INFO_FAILED_RESPONSE='+response['code_hex'],flush=True)
    finally:
        if claimed:lib.libusb_release_interface(handle,0)
        if handle:lib.libusb_close(handle)
        lib.libusb_exit(ctx)
        print('USB_INTERFACE_RELEASED=YES',flush=True)
    (ROOT/'get-device-info.json').write_text(json.dumps(info,indent=2,ensure_ascii=False)+'\n')
    print('RESULT='+str(ROOT/'get-device-info.json'),flush=True)
if __name__=='__main__':main()
