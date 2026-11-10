#!/usr/bin/env python3
"""Temporary LCD/touch hardware verification for Elgato Stream Deck Plus 0fd9:0084.
Requires an explicit user test session; no firmware, udev, systemd or app settings.
Restore boot logo in finally; one /dev/hidraw handle owned by this process.
"""
import os, io, time, struct, fcntl, selectors
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

BASE="/srv/vision-data/tools/streamdeck-eval"
NODE="/dev/hidraw0"
TEST_DURATION=95
DATA_CHUNK=1016
BUTTON_COLORS=[
    ("1","RED",(195,37,54)),
    ("2","ORANGE",(220,107,12)),
    ("3","YELLOW",(201,171,19)),
    ("4","GREEN",(20,145,75)),
    ("5","CYAN",(19,144,159)),
    ("6","BLUE",(33,78,186)),
    ("7","VIOLET",(122,65,175)),
    ("8","PINK",(187,49,139)),
]
ZONES=[
    ("A",(0,111,185)),
    ("B",(8,146,127)),
    ("C",(170,96,28)),
    ("D",(150,39,100)),
]
fontpath="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
fontlarge=ImageFont.truetype(fontpath,65)
fontsmall=ImageFont.truetype(fontpath,15)
fontbar=ImageFont.truetype(fontpath,38)
fontinfo=ImageFont.truetype(fontpath,13)
def text_center(draw, xy, text, font, fill):
    bbox=draw.textbbox((0,0),text,font=font)
    w=bbox[2]-bbox[0];h=bbox[3]-bbox[1]
    draw.text((xy[0]-w/2,xy[1]-h/2-bbox[1]),text,font=font,fill=fill)

def jpeg(im):
    b=io.BytesIO()
    im.save(b,format="JPEG",quality=90,subsampling=0,optimize=False)
    return b.getvalue()

def button_image(n,label,color):
    im=Image.new("RGB",(120,120),color)
    dr=ImageDraw.Draw(im)
    dr.rounded_rectangle((4,4,115,115),radius=13,outline=(255,255,255),width=3)
    text_center(dr,(60,56),n,fontlarge,(255,255,255))
    text_center(dr,(60,100),label,fontsmall,(255,255,255))
    return jpeg(im)

def strip_image(selected=None,count=0):
    im=Image.new("RGB",(800,100),(10,10,12))
    dr=ImageDraw.Draw(im)
    for idx,(label,color) in enumerate(ZONES):
        x=idx*200
        dr.rectangle((x+2,2,x+197,97),fill=color)
        border=(255,255,255) if idx==selected else (75,75,75)
        dr.rectangle((x+4,4,x+195,95),outline=border,width=5 if idx==selected else 2)
        text_center(dr,(x+100,47),label,fontbar,(255,255,255))
        text_center(dr,(x+100,79),("DOTYK OK" if idx==selected else "DOTKNIJ"),fontinfo,(255,255,255))
    return jpeg(im)

def feature(fd, cmd):
    buf=bytearray(32)
    buf[0]=3;buf[1]=cmd
    ioctl=(3<<30)|(32<<16)|(ord("H")<<8)|0x06
    return fcntl.ioctl(fd,ioctl,buf,True)

def upload(fd,cmd,idx,payload):
    parts=(len(payload)+DATA_CHUNK-1)//DATA_CHUNK
    for part in range(parts):
        chunk=payload[part*DATA_CHUNK:(part+1)*DATA_CHUNK]
        done=1 if part==parts-1 else 0
        packet=bytes((2,cmd,idx,done))+struct.pack("<HH",len(chunk),part)+chunk
        packet=packet.ljust(1024,b"\x00")
        for attempt in range(12):
            try:
                size=os.write(fd,packet)
                break
            except BlockingIOError:
                time.sleep(0.025)
        else:
            raise RuntimeError("Device remains busy on WRITE")
        if size!=1024:
            raise RuntimeError(f"Partial USB HID WRITE: {size}/1024")
    return parts

def touch_zone(x):
    return max(0,min(3,x//200))

def main():
    with open("/sys/class/hidraw/hidraw0/device/uevent",encoding="utf-8") as f:
        identity=f.read()
    if "HID_NAME=Elgato Stream Deck Plus" not in identity or "00000FD9:00000084" not in identity:
        raise RuntimeError("Device identity mismatch: aborting")
    if not os.access(NODE,os.R_OK|os.W_OK):
        raise PermissionError("No HID read/write access")
    fd=os.open(NODE,os.O_RDWR|os.O_NONBLOCK)
    sel=selectors.DefaultSelector()
    counters=Counter()
    started=time.monotonic()
    print("STREAM_DECK_PLUS_ID=0fd9:0084 CONFIRMED",flush=True)
    try:
        # Direct, RAM-only image output using official Stream Deck Plus HID image commands.
        for idx,(number,label,color) in enumerate(BUTTON_COLORS):
            chunks=upload(fd,0x07,idx,button_image(number,label,color))
            print(f"BUTTON_LCD_{number}=UPLOAD_OK JPEG_CHUNKS={chunks}",flush=True)
        chunks=upload(fd,0x0B,0,strip_image())
        print(f"TOUCH_STRIP_IMAGE=UPLOAD_OK JPEG_CHUNKS={chunks}",flush=True)
        print(f"DISPLAY_READY=YES; test for {TEST_DURATION}s; tap A B C D and swipe across touch strip",flush=True)
        sel.register(fd,selectors.EVENT_READ)
        last_heartbeat=started
        while time.monotonic()-started < TEST_DURATION:
            for key,_ in sel.select(timeout=0.20):
                try:
                    report=os.read(fd,512)
                except BlockingIOError:
                    continue
                if len(report)<4 or report[0]!=1:
                    continue
                cmd=report[1]
                size=int.from_bytes(report[2:4],"little")
                if cmd==2 and len(report)>=10:
                    kind=report[4]
                    x=int.from_bytes(report[6:8],"little")
                    y=int.from_bytes(report[8:10],"little")
                    region=touch_zone(x)
                    counters["TOUCH_TOTAL"]+=1
                    counters["ZONE_"+ZONES[region][0]]+=1
                    gesture={1:"TAP",2:"PRESS",3:"FLICK"}.get(kind,f"TYPE_{kind}")
                    if kind==3 and len(report)>=14:
                        endx=int.from_bytes(report[10:12],"little")
                        endy=int.from_bytes(report[12:14],"little")
                        counters["FLICK"]+=1
                        print(f"TOUCH={gesture} X={x}->{endx} Y={y}->{endy} START_ZONE={ZONES[region][0]}",flush=True)
                    else:
                        counters[gesture]+=1
                        print(f"TOUCH={gesture} X={x} Y={y} ZONE={ZONES[region][0]}",flush=True)
                    # Update the bar only for infrequent individual presses/taps.
                    if kind in (1,2) and counters["TOUCH_TOTAL"]<=24:
                        try:
                            upload(fd,0x0B,0,strip_image(region,counters["TOUCH_TOTAL"]))
                            print(f"TOUCH_VISUAL_FEEDBACK=ZONE_{ZONES[region][0]}_UPDATED",flush=True)
                        except Exception as exc:
                            print(f"TOUCH_VISUAL_FEEDBACK_ERROR={exc!r}",flush=True)
                elif cmd==0 and len(report)>=12:
                    for idx,v in enumerate(report[4:12]):
                        if v==1:
                            counters["BUTTON_PRESS_"+str(idx+1)]+=1
                            print(f"BUTTON_PRESS={idx+1}",flush=True)
                elif cmd==3 and len(report)>5:
                    pass
            if time.monotonic()-last_heartbeat>=20:
                print(f"LISTEN_ALIVE elapsed={round(time.monotonic()-started)}s TOUCH={counters['TOUCH_TOTAL']}",flush=True)
                last_heartbeat=time.monotonic()
        print("TEST_REPORT "+str(dict(counters)),flush=True)
    finally:
        try:
            feature(fd,2)
            print("RESTORE_DEFAULT_LOGO=COMMAND_OK",flush=True)
        except Exception as exc:
            print(f"RESTORE_DEFAULT_LOGO=FAILED {exc!r}",flush=True)
        sel.close()
        os.close(fd)
        print("DEVICE_CLOSED=YES",flush=True)

if __name__=="__main__":
    main()
