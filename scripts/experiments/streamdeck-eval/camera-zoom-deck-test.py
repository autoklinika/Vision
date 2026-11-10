#!/usr/bin/env python3
"""Temporary Vision Stream Deck Plus -> Sony a6100 *single* zoom command diagnostic.
Per run at most one gphoto zoom set action, unless restoration is necessary.
Never changes firmware/services/repo. If response is invalid, fail closed.
"""
import fcntl, io, json, os, re, selectors, struct, subprocess, time, sys
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
BASE=Path("/srv/vision-data/tools/streamdeck-eval")
CAM=Path("/srv/vision-data/tools/sony-a6100-verify")
G=CAM/"root/usr/bin/gphoto2"
TIMEOUT=150
TEST=BASE/"camera-test-captures"/datetime.now(timezone.utc).strftime("zoom-%Y%m%dT%H%M%SZ")
env=os.environ.copy()
env["LD_LIBRARY_PATH"]=str(CAM/"root/usr/lib/aarch64-linux-gnu")+(":"+env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
metrics={"test":"Zoom_USB_single_step","started_utc":datetime.now(timezone.utc).isoformat()}
def out(msg):print(msg,flush=True)

def sony_port():
    hits=[]
    for d in Path("/sys/bus/usb/devices").iterdir():
        try:
            if (d/"idVendor").read_text().strip()=="054c" and (d/"idProduct").read_text().strip()=="0f0d":
                b=int((d/"busnum").read_text()); n=int((d/"devnum").read_text())
                if not os.access(f"/dev/bus/usb/{b:03d}/{n:03d}",os.R_OK|os.W_OK):raise PermissionError("CAMERA_USB_ACCESS_DENIED")
                hits.append(f"usb:{b:03d},{n:03d}")
        except (OSError,ValueError):pass
    if len(hits)!=1:raise RuntimeError(f"SONY_DEVICE_COUNT_INVALID: {hits}")
    return hits[0]

def execute(port,*args,limit=25):
    cmd=[str(G),f"--port={port}","--camera=USB PTP Class Camera",*args]
    t=time.monotonic()
    result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=limit)
    return result.returncode,result.stdout+chr(10)+result.stderr,round(time.monotonic()-t,2)

def read_current_zoom(port):
    rc,txt,seconds=execute(port,"--get-config=/main/capturesettings/zoom",limit=20)
    if rc!=0:raise RuntimeError("GET_ZOOM_FAILED="+txt[-300:])
    m=re.search(r"^Current:\s*([\d.]+)",txt,re.M)
    if not m:raise RuntimeError("ZOOM_CURRENT_NOT_FOUND="+txt[-300:])
    return float(m.group(1))

def read_exact_raw(port):
    rc,txt,_=execute(port,"--summary",limit=25)
    if rc!=0:raise RuntimeError("CAMERA_SUMMARY_FAILED")
    m=re.search(r"Zoom\(0xd214\):.*?value:\s*(\d+)",txt)
    if not m:raise RuntimeError("EXACT_RAW_ZOOM_UNAVAILABLE")
    return int(m.group(1))

def image_bar():
    im=Image.new("RGB",(800,100),(15,15,22))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((3,3,195,97),radius=9,fill=(124,65,10),outline="white",width=3)
    f=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",23)
    d.text((37,14),"ZOOM",font=f,fill="white")
    d.text((35,52),"+1 KROK",font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",16),fill="white")
    d.text((231,39),"Pokrętło 1: obróć W PRAWO",font=f,fill=(245,245,245))
    buf=io.BytesIO();im.save(buf,format="JPEG",quality=86)
    return buf.getvalue()

def set_bar(fd):
    content=image_bar()
    for n,start in enumerate(range(0,len(content),1016)):
        part=content[start:start+1016]
        last=int(start+len(part)>=len(content))
        report=(bytes((2,11,0,last))+struct.pack("<HH",len(part),n)+part).ljust(1024,bytes(1))
        for retry in range(20):
            try:
                written=os.write(fd,report)
                if written!=1024:raise RuntimeError("HID_SHORT_WRITE")
                break
            except BlockingIOError:time.sleep(.025)
        else:raise RuntimeError("HID_BAR_WRITE_TIMEOUT")
    out("TOUCH_BAR_ZOOM_ICON=DISPLAY_COMMAND_ACCEPTED")

def restore_deck(fd):
    buf=bytearray(32);buf[0]=3;buf[1]=2
    req=(3<<30)|(32<<16)|(ord("H")<<8)|6
    fcntl.ioctl(fd,req,buf,True)
    out("STREAMDECK_RESTORE_LOGO=COMMAND_PASS")

def capture_after(port):
    out("ZOOM_VERIFICATION_CAPTURE=START")
    rc,txt,elapsed=execute(port,"--keep","--filename=zoom_after.%C","--capture-image-and-download",limit=95)
    (TEST/"capture_after.log").write_text(txt)
    out("ZOOM_VERIFICATION_CAPTURE_RC="+str(rc)+" ELAPSED_SEC="+str(elapsed))
    images=[]
    for path in TEST.glob("zoom_after.*"):
        if path.suffix.lower() in (".jpg",".jpeg",".arw"):
            res={"name":path.name,"bytes":path.stat().st_size}
            if path.suffix.lower() in (".jpg",".jpeg"):
                im=Image.open(path)
                exif=im.getexif().get_ifd(34665)
                res["lens_model"]=exif.get(42036)
                res["focal_length_mm"]=exif.get(37386)
                res["size_px"]=im.size
            images.append(res)
    metrics["images"]=images
    out("ZOOM_VERIFY_IMAGES="+json.dumps(images,ensure_ascii=False))
    return rc==0 and bool(images)

def main():
    ident=Path("/sys/class/hidraw/hidraw0/device/uevent").read_text()
    assert "HID_NAME=Elgato Stream Deck Plus" in ident and "00000FD9:00000084" in ident
    port=sony_port()
    before=read_current_zoom(port)
    raw=read_exact_raw(port)
    metrics["before"]={"zoom":before,"raw":raw}
    out(f"CAMERA={port} ZOOM_BEFORE={before} ZOOM_RAW={raw}")
    if not 20.0<=before<=45.0 or not 16000000<=raw<=50000000:
        raise RuntimeError("ZOOM_PRECHECK_OUT_OF_CONSERVATIVE_BOUNDS")
    target=int(before)+1
    assert 21<=target<=46
    out("ZOOM_TARGET_FOR_ONE_STEP="+str(target)+" HOLD_OR_ROTATION_NOT_REPEATED")
    fd=os.open("/dev/hidraw0",os.O_RDWR|os.O_NONBLOCK)
    sel=selectors.DefaultSelector()
    try:
        set_bar(fd)
        sel.register(fd,selectors.EVENT_READ)
        stop=time.monotonic()+TIMEOUT
        out("ARMED=YES ROTATE_ENCODER_1_CLOCKWISE_ONCE")
        triggered=False
        while time.monotonic()<stop:
            for key,events in sel.select(timeout=.30):
                try:buf=os.read(fd,512)
                except BlockingIOError:continue
                if len(buf)<9 or buf[:2]!=bytes((1,3)) or buf[4]!=1:continue
                delta=int.from_bytes(buf[5:6],byteorder="little",signed=True)
                if delta>0:
                    triggered=True
                    out("ENCODER_1_CW_DETECTED ticks="+str(delta))
                    break
            if triggered:break
        if not triggered:
            out("ZOOM_TEST=NO_ENCODER_INPUT_TIMEOUT")
            metrics["status"]="TIMEOUT"
            return 2
        TEST.mkdir(parents=True,exist_ok=False)
        out("USB_ZOOM_WRITE=ONE_ATTEMPT_TARGET_"+str(target))
        set_rc,set_text,duration=execute(port,f"--set-config-value=/main/capturesettings/zoom={target}",limit=25)
        metrics["write"]={"target":target,"rc":set_rc,"seconds":duration,"log":set_text[-1200:]}
        out(f"ZOOM_SET_RC={set_rc} DURATION={duration} OUTPUT={set_text[-250:].strip()!r}")
        time.sleep(1)
        after=read_current_zoom(port)
        metrics["after_write"]=after
        out("ZOOM_AFTER_WRITE="+str(after))
        changed=abs(after-before)>0.1
        metrics["property_changed"]=changed
        if changed or set_rc==0:
            try:capture_after(port)
            except Exception as exc:out("ZOOM_VERIFICATION_CAPTURE_ERROR="+repr(exc))
        if changed:
            out("ZOOM_RESTORE_RAW=START requested_raw="+str(raw))
            restore_rc,restore_txt,restore_duration=execute(port,f"--set-config-value=/main/other/d214={raw}",limit=25)
            metrics["restore"]={"rc":restore_rc,"log":restore_txt[-800:]}
            out("ZOOM_RESTORE_RAW_RC="+str(restore_rc)+" OUTPUT="+repr(restore_txt[-140:].strip()))
            final=read_current_zoom(port)
            metrics["after_restore"]=final
            out("ZOOM_AFTER_RESTORE="+str(final))
            if abs(final-before)>0.12:
                metrics["status"]="RESTORE_UNVERIFIED"
                out("ZOOM_RESULT=RESTORE_NEEDS_ATTENTION")
                return 3
            metrics["status"]="PROPERTY_CHANGED_AND_RESTORED"
        else:metrics["status"]="NO_ZOOM_PROPERTY_CHANGE"
        out("ZOOM_RESULT="+metrics["status"])
        return 0 if changed else 4
    finally:
        try:restore_deck(fd)
        except Exception as exc:out("STREAMDECK_RESTORE_ERROR="+repr(exc))
        sel.close();os.close(fd)
        out("HID_RELEASED=YES")
        metrics["ended_utc"]=datetime.now(timezone.utc).isoformat()
        (BASE/"camera-zoom-test-result.json").write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+chr(10))

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        out("ZOOM_TEST_ABORT="+repr(exc))
        sys.exit(5)
