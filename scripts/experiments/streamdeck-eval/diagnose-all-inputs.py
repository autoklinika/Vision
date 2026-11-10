#!/usr/bin/env python3
"""Vision evaluation: parallel raw HID and evdev read-only event capture. Auto-stops."""
import os, selectors, struct, time
from collections import Counter
ident=open('/sys/class/hidraw/hidraw0/device/uevent').read()
assert 'HID_NAME=Elgato Stream Deck Plus' in ident and '00000FD9:00000084' in ident
ident2=open('/sys/class/input/event2/device/name').read().strip()
assert ident2=='Elgato Stream Deck Plus',ident2
s=selectors.DefaultSelector()
fds={}
for path in ('/dev/hidraw0','/dev/input/event2'):
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK)
    s.register(fd,selectors.EVENT_READ,path)
    fds[path]=fd
    print('DEVICE_OPEN=PASS PATH='+path,flush=True)
counts=Counter()
duration=120
start=time.monotonic()
prev=0
print('READY=YES; TEST: one button, TAP A, B, C, D, HOLD B, HOLD C, SWIPE A->D, D->A',flush=True)
try:
    while time.monotonic()-start < duration:
        now=time.monotonic()-start
        for key,_ in s.select(timeout=0.25):
            path=key.data
            try:data=os.read(key.fd,1024)
            except BlockingIOError:continue
            if not data:continue
            counts['data_'+path]+=1
            if path=='/dev/hidraw0':
                family=data[1] if len(data)>=2 else -1
                counts['hid_family_'+str(family)]+=1
                if family==2 and len(data)>=10 and data[0]==1:
                    kind=data[4]
                    x=int.from_bytes(data[6:8],'little')
                    y=int.from_bytes(data[8:10],'little')
                    zone='ABCD'[min(3,max(0,x//200))]
                    if len(data)>=14:
                        xe=int.from_bytes(data[10:12],'little')
                    else:xe=None
                    print(f'HID_TOUCH {now:.1f}s kind={kind} zone={zone} x={x} y={y} x_end={xe} raw={data[:20].hex(" ")}',flush=True)
                elif counts['hid_family_'+str(family)]<=10:
                    print(f'HID_RAW {now:.1f}s family={family} len={len(data)} raw={data[:20].hex(" ")}',flush=True)
            else:
                unit=struct.calcsize('llHHi')
                for n in range(0,len(data)-unit+1,unit):
                    sec,usec,typ,code,val=struct.unpack('llHHi',data[n:n+unit])
                    if typ==0:continue
                    counts['ev_type_'+str(typ)]+=1
                    if counts['ev_type_'+str(typ)]<=50:
                        print(f'EV {now:.1f}s type={typ} code={code} value={val}',flush=True)
        if now-prev>=15:
            print(f'ALIVE t={now:.1f}s counts={dict(counts)}',flush=True)
            prev=now
finally:
    for path,fd in fds.items():
        s.unregister(fd)
        os.close(fd)
    print('SUMMARY '+str(dict(counts)),flush=True)
    print('TEST_FINISHED_AND_FDS_CLOSED=YES',flush=True)
