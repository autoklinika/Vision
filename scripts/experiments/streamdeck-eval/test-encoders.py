#!/usr/bin/env python3
"""Vision: non-invasive verification of all 4 rotary encoders and push buttons.
Read-only; no images written, no device settings altered; 180 s auto-stop.
"""
import os, selectors, time, json
from datetime import datetime, timezone

ROOT="/srv/vision-data/tools/streamdeck-eval"
DEV="/dev/hidraw0"
ident=open("/sys/class/hidraw/hidraw0/device/uevent",encoding="utf-8").read()
assert "HID_NAME=Elgato Stream Deck Plus" in ident and "00000FD9:00000084" in ident
DURATION=300
fd=os.open(DEV,os.O_RDONLY | os.O_NONBLOCK)
sel=selectors.DefaultSelector()
sel.register(fd, selectors.EVENT_READ)
per=[{"CW":0,"CCW":0,"PRESS":0,"RELEASE":0,"raw_rotation":0} for _ in range(4)]
state=[False]*4
out={"device":"0fd9:0084","test":"rotary-input-v1","start_utc":datetime.now(timezone.utc).isoformat(),"events":[]}
start=time.monotonic()
print("ROTARY_TEST=READY DURATION_SECONDS=300",flush=True)
print("ACTIONS: encoder 1 -> CW CCW press/release, repeat 2 3 4",flush=True)
try:
    while (time.monotonic()-start) < DURATION:
        for key,_ in sel.select(timeout=0.35):
            try: report=os.read(fd,512)
            except BlockingIOError: continue
            if len(report)<9 or tuple(report[:2])!=(1,3) or report[2]!=5:
                continue
            kind=report[4]
            if kind not in (0,1):continue
            data=report[5:9]
            t=round(time.monotonic()-start,2)
            if kind==1:
                for i,v in enumerate(data):
                    delta=int.from_bytes(bytes((v,)),byteorder="little",signed=True)
                    if delta==0:continue
                    direction="CW" if delta>0 else "CCW"
                    per[i][direction]+=abs(delta)
                    per[i]["raw_rotation"]+=1
                    event={"t":t,"encoder":i+1,"action":direction,"ticks":delta}
                    out["events"].append(event)
                    print(f"ENCODER={i+1} ROTATE={direction} TICKS={delta} t={t}s",flush=True)
            else:
                for i,v in enumerate(data):
                    pressed=bool(v)
                    if pressed==state[i]:continue
                    state[i]=pressed
                    action="PRESS" if pressed else "RELEASE"
                    per[i][action]+=1
                    event={"t":t,"encoder":i+1,"action":action}
                    out["events"].append(event)
                    print(f"ENCODER={i+1} BUTTON={action} t={t}s",flush=True)
    out["end_utc"]=datetime.now(timezone.utc).isoformat()
    out["totals"]=per
    out["status"]=["PASS" if all(row[k]>0 for k in ("CW","CCW","PRESS","RELEASE")) else "INCOMPLETE" for row in per]
    print("RESULTS "+json.dumps({"per_encoder":per,"status":out["status"]},ensure_ascii=False),flush=True)
finally:
    sel.unregister(fd)
    os.close(fd)
    print("HID_CLOSED=YES",flush=True)
    with open(ROOT+"/encoder-test-results.json","w",encoding="utf-8") as f:
        json.dump(out,f,indent=2,ensure_ascii=False)
        f.write(chr(10))
    print("RESULTS_FILE="+ROOT+"/encoder-test-results.json",flush=True)
