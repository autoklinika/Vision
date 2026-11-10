#!/usr/bin/env python3
"""Read-only 60s touch test for precise TAP and PRESS events on B and C."""
import os,selectors,time
from collections import Counter
p='/dev/hidraw0'
ident=open('/sys/class/hidraw/hidraw0/device/uevent').read()
assert 'HID_NAME=Elgato Stream Deck Plus' in ident and '00000FD9:00000084' in ident
fd=os.open(p,os.O_RDONLY|os.O_NONBLOCK)
s=selectors.DefaultSelector();s.register(fd,selectors.EVENT_READ)
counts=Counter()
start=time.monotonic()
print('SECONDARY_TEST_READY=YES DURATION=60s',flush=True)
print('DO: quick TAP B, quick TAP C, 2-second HOLD B, 2-second HOLD C',flush=True)
try:
 while time.monotonic()-start<60:
  for k,mask in s.select(timeout=.4):
   try:r=os.read(fd,512)
   except BlockingIOError:continue
   if len(r)<10 or r[0]!=1 or r[1]!=2:continue
   subtype=r[4];x=int.from_bytes(r[6:8],'little');y=int.from_bytes(r[8:10],'little')
   zone='ABCD'[min(3,x//200)]; gesture={1:'TAP',2:'PRESS',3:'FLICK'}.get(subtype,'OTHER')
   counts[zone+'_'+gesture]+=1
   if subtype==3 and len(r)>=14:
    x2=int.from_bytes(r[10:12],'little')
    print(f'GESTURE={gesture} START_ZONE={zone} X={x} END_ZONE={"ABCD"[min(3,x2//200)]} X2={x2}',flush=True)
   else:print(f'GESTURE={gesture} ZONE={zone} X={x} Y={y}',flush=True)
 print(f'RESULT={dict(counts)}',flush=True)
finally:
 s.unregister(fd);os.close(fd);print('HID_RELEASED=YES',flush=True)
