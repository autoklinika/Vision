#!/usr/bin/env python3
"""Read-only 45 s diagnostic of Stream Deck Plus reports; no configuration changes."""
import os, selectors, struct, time
from collections import Counter
from datetime import datetime

HID='/dev/hidraw0'
EV='/dev/input/event2'
DURATION=45
sel=selectors.DefaultSelector()
fds=[]
for path in (HID, EV):
    try:
        fd=os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        sel.register(fd, selectors.EVENT_READ, path)
        fds.append(fd)
        print(f'OPEN {path}=PASS', flush=True)
    except OSError as exc:
        print(f'OPEN {path}=FAIL ({exc})', flush=True)
print('CAPTURE_ACTIVE_SECONDS=45; press a key, turn a dial, press a dial, touch the strip', flush=True)
counts=Counter()
seen=set()
start=time.monotonic()
try:
    while time.monotonic()-start<DURATION:
        for key, _ in sel.select(timeout=0.5):
            path=key.data
            try: data=os.read(key.fd,4096)
            except BlockingIOError: continue
            if not data: continue
            if path==HID:
                counts['hid_reports']+=1
                sample=data[:18].hex(' ')
                if sample not in seen:
                    seen.add(sample)
                    print(f'HID {time.monotonic()-start:.1f}s size={len(data)} bytes={sample}', flush=True)
            else:
                unit=struct.calcsize('llHHi')
                for n in range(0,len(data)-unit+1,unit):
                    sec,usec,etype,code,value=struct.unpack('llHHi',data[n:n+unit])
                    counts['ev_events']+=1
                    if etype not in (0,):
                        print(f'EV {time.monotonic()-start:.1f}s type={etype} code={code} value={value}',flush=True)
finally:
    for fd in fds: sel.unregister(fd); os.close(fd)
    print(f'CAPTURE_FINISHED counts={dict(counts)} distinct_report_prefixes={len(seen)}', flush=True)
