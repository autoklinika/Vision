#!/usr/bin/env python3
"""Read-only Stream Deck Plus touch zones evaluation (temporary, no persistent changes)."""
import os, selectors, time
from collections import Counter
dev="/dev/hidraw0"
ident=open("/sys/class/hidraw/hidraw0/device/uevent",encoding="utf-8").read()
assert "HID_NAME=Elgato Stream Deck Plus" in ident and "00000FD9:00000084" in ident, "Unexpected HID"
fd=os.open(dev,os.O_RDONLY | os.O_NONBLOCK)
sel=selectors.DefaultSelector()
sel.register(fd,selectors.EVENT_READ)
duration=90
counts=Counter()
start=time.monotonic()
print("TOUCH_LISTEN=START DURATION=90s",flush=True)
print("ACTION=TAP A B C D THEN SWIPE A->D THEN D->A",flush=True)
try:
    while time.monotonic()-start < duration:
        ready=sel.select(timeout=0.5)
        for key,mask in ready:
            try:
                dat=os.read(fd,512)
            except BlockingIOError:
                continue
            if not dat or len(dat)<10 or dat[0]!=1 or dat[1]!=2:
                continue
            subtype=dat[4]
            x=int.from_bytes(dat[6:8],"little")
            y=int.from_bytes(dat[8:10],"little")
            zone="ABCD"[min(3,max(0,x//200))]
            action={1:"TAP",2:"PRESS",3:"FLICK"}.get(subtype,"OTHER"+str(subtype))
            counts["touch"]+=1
            counts[zone]+=1
            counts[action]+=1
            if subtype==3 and len(dat)>=14:
                x2=int.from_bytes(dat[10:12],"little")
                y2=int.from_bytes(dat[12:14],"little")
                zone2="ABCD"[min(3,max(0,x2//200))]
                print(f"TOUCH {action} from={zone}({x},{y}) to={zone2}({x2},{y2})",flush=True)
            else:
                print(f"TOUCH {action} zone={zone} x={x} y={y} raw={dat[:14].hex()}",flush=True)
        t=time.monotonic()-start
        if int(t)%20==0 and int((t-.5))%20!=0:
            print(f"ACTIVE elapsed={t:.1f}s counts={dict(counts)}",flush=True)
finally:
    sel.unregister(fd)
    os.close(fd)
    print("TOUCH_LISTEN=FINISHED",dict(counts),flush=True)
