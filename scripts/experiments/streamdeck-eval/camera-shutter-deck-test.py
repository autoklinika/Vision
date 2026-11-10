#!/usr/bin/env python3
"""Stream Deck Plus -> Sony ILCE-6100A single still proof; temporary isolated test.
Arm key 1 only, exactly one capture, preserve camera data (--keep), no settings writes.
"""
import fcntl, hashlib, io, os, selectors, struct, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
BASE=Path("/srv/vision-data/tools/streamdeck-eval")
SONY=Path("/srv/vision-data/tools/sony-a6100-verify")
G=SONY/"root/usr/bin/gphoto2"
RUN=BASE/"camera-test-captures"/datetime.now(timezone.utc).strftime("shutter-%Y%m%dT%H%M%SZ")
HID="/dev/hidraw0"
JPG_PART=1016
CAPTURE_TIMEOUT=100
ARM_SEC=120

def msg(x):
    print(x,flush=True)

def port_and_access():
    hits=[]
    for d in Path("/sys/bus/usb/devices").iterdir():
        try:
            if (d/"idVendor").read_text().strip()=="054c" and (d/"idProduct").read_text().strip()=="0f0d":
                bus=int((d/"busnum").read_text())
                dev=int((d/"devnum").read_text())
                hits.append((bus,dev))
        except (OSError,ValueError):pass
    if len(hits)!=1:raise RuntimeError(f"EXPECTED_SINGLE_A6100 found={hits}")
    b,d=hits[0]
    n=Path(f"/dev/bus/usb/{b:03d}/{d:03d}")
    if not os.access(n,os.R_OK|os.W_OK):raise PermissionError(f"CAMERA_NOT_ACCESSIBLE {n}")
    return f"usb:{b:03d},{d:03d}"

def icon_bytes():
    im=Image.new("RGB",(120,120),(11,95,74))
    dr=ImageDraw.Draw(im)
    dr.rounded_rectangle((3,3,116,116),radius=13,outline="white",width=3)
    try:
        f1=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",30)
        f2=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",19)
        dr.text((16,22),"FOTO",font=f1,fill="white")
        dr.text((26,73),"1 RAZ",font=f2,fill="white")
    except Exception:
        dr.text((18,25),"FOTO",fill="white")
    b=io.BytesIO()
    im.save(b,format="JPEG",quality=85)
    return b.getvalue()

def set_icon(fd):
    content=icon_bytes()
    for index,start in enumerate(range(0,len(content),JPG_PART)):
        part=content[start:start+JPG_PART]
        last=int(start+len(part)>=len(content))
        report=(bytes((2,7,0,last))+struct.pack("<HH",len(part),index)+part).ljust(1024,bytes(1))
        for retry in range(20):
            try:
                written=os.write(fd,report)
                if written!=1024:raise RuntimeError(f"SHORT_HID_WRITE={written}")
                break
            except BlockingIOError:
                time.sleep(.015)
        else:raise RuntimeError("HID_ICON_WRITE_TIMED_OUT")
    msg("DECK_KEY1_ICON=FOTO_READY")

def restore_logo(fd):
    buf=bytearray(32)
    buf[0],buf[1]=3,2
    request=(3<<30)|(32<<16)|(ord("H")<<8)|6
    fcntl.ioctl(fd,request,buf,True)
    msg("DECK_LOGO_RESTORED=COMMAND_PASS")

def capture_once(port):
    RUN.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy()
    env["LD_LIBRARY_PATH"]=str(SONY/"root/usr/lib/aarch64-linux-gnu")+(":"+env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    cmd=[str(G),f"--port={port}","--camera=USB PTP Class Camera","--keep","--filename=deck_shutter.%C","--capture-image-and-download"]
    msg("CAMERA_CAPTURE_START=YES SESSION="+str(RUN))
    t=time.monotonic()
    try:
        result=subprocess.run(cmd,cwd=str(RUN),env=env,capture_output=True,text=True,timeout=CAPTURE_TIMEOUT)
        msg("CAMERA_CAPTURE_EXIT="+str(result.returncode)+" ELAPSED_SEC="+str(round(time.monotonic()-t,2)))
        (RUN/"capture.log").write_text(result.stdout+chr(10)+result.stderr)
        for line in (result.stdout+chr(10)+result.stderr).splitlines()[-18:]:
            msg("GPHOTO "+line)
    except subprocess.TimeoutExpired as exc:
        msg("CAMERA_CAPTURE_TIMEOUT="+str(CAPTURE_TIMEOUT))
        (RUN/"capture.log").write_text("TIMEOUT="+str(exc))
        return 124
    shots=[]
    for p in sorted(RUN.iterdir()):
        if p.suffix.lower() in (".jpg",".jpeg",".arw",".raw"):
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            msg(f"CAPTURE_FILE={p.name} BYTES={p.stat().st_size} SHA256={digest}")
            if p.suffix.lower() in (".jpg",".jpeg"):
                try:
                    im=Image.open(p);im.verify()
                    im=Image.open(p)
                    msg("JPEG_VALID=YES RESOLUTION="+str(im.size))
                except Exception as exc:msg("JPEG_VERIFY_FAILED="+repr(exc))
            shots.append(p)
    if result.returncode!=0 or not shots:
        msg("CAPTURE_RESULT=FAIL_OR_UNVERIFIED")
        return 1
    msg("CAPTURE_RESULT=PASS")
    return 0

def main():
    ident=Path("/sys/class/hidraw/hidraw0/device/uevent").read_text()
    if "HID_NAME=Elgato Stream Deck Plus" not in ident or "00000FD9:00000084" not in ident:
        raise RuntimeError("UNEXPECTED_HID_DEVICE")
    port=port_and_access()
    msg("SONY_A6100_USB="+port+" CAMERA_ACCESS=PASS")
    fd=os.open(HID,os.O_RDWR|os.O_NONBLOCK)
    sel=selectors.DefaultSelector()
    try:
        set_icon(fd)
        sel.register(fd,selectors.EVENT_READ)
        deadline=time.monotonic()+ARM_SEC
        msg("DECK_SHUTTER_ARMED=YES PRESS_TOP_LEFT_FOTO_KEY_ONCE")
        old=False
        pressed=False
        while time.monotonic()<deadline:
            for key,mask in sel.select(timeout=.25):
                try:r=os.read(fd,512)
                except BlockingIOError:continue
                if len(r)<12 or r[:2]!=bytes((1,0)):continue
                pressed_now=(r[4]==1)
                if pressed_now and not old:
                    pressed=True
                    msg("DECK_SHUTTER_BUTTON1_PRESS=DETECTED")
                    break
                old=pressed_now
            if pressed:break
        if not pressed:
            msg("DECK_SHUTTER_TEST=TIMEOUT_NO_KEY_PRESS")
            return 2
        return capture_once(port)
    finally:
        try:restore_logo(fd)
        except Exception as exc:msg("DECK_RESTORE_LOGO_ERROR="+repr(exc))
        sel.close()
        os.close(fd)
        msg("TEST_END_HID_RELEASED=YES")

if __name__=="__main__":
    sys.exit(main())
