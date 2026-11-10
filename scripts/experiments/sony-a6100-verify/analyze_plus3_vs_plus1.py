from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageEnhance
sys.path.insert(0,"/srv/vision-data/tools/npu-verify/.venv/lib/python3.12/site-packages")
import numpy as np

def metric(arr):
    arr=arr.astype(np.float32)
    lap=4*arr[1:-1,1:-1]-arr[0:-2,1:-1]-arr[2:,1:-1]-arr[1:-1,0:-2]-arr[1:-1,2:]
    gy=np.diff(arr,axis=0)
    gx=np.diff(arr,axis=1)
    return float(np.var(lap)),float(np.mean(gy*gy)+np.mean(gx*gx)),float(np.std(arr))

rois={
  "torso_fabric":(335,40,750,420),
  "skirt_fabric":(445,390,865,675),
  "left_sleeve":(295,110,520,205),
  "dress_center":(500,100,700,450),
  "label_detail":(500,650,1080,735),
  "background":(15,40,260,570),
}
runs=[
    ("+1","/srv/vision-data/vision/sessions/focus-step-20261010T203439Z"),
    ("+3","/srv/vision-data/vision/sessions/focus-step-20261010T203642Z"),
]
for label,dirn in runs:
    base=Path(dirn)
    ia=Image.open(base/"image_1.jpg").convert("L")
    ib=Image.open(base/"image_2.jpg").convert("L")
    print("RUN",label,"IMAGE_SIZE",ia.size,ib.size,flush=True)
    for name,xy in rois.items():
        box=tuple(int(5*x) for x in xy)
        a=np.asarray(ia.crop(box),dtype=np.float32)
        b=np.asarray(ib.crop(box),dtype=np.float32)
        m0,m1=metric(a),metric(b)
        corr=float(np.corrcoef(a[::4,::4].ravel(),b[::4,::4].ravel())[0,1])
        delta=float(np.mean(np.abs(a-b)))
        ratio=(m1[0]/m0[0]-1)*100 if m0[0]>1e-8 else 0.
        print(f"{name}: lap_var {m0[0]:.1f} -> {m1[0]:.1f} ({ratio:+.3f}%); energy {m0[1]:.1f} -> {m1[1]:.1f} ({(m1[1]/m0[1]-1)*100:+.3f}%); delta={delta:.2f}; corr={corr:.6f}",flush=True)
    p0=ia.resize((1200,800))
    p1=ib.resize((1200,800))
    a=np.asarray(p0,dtype=np.float32);b=np.asarray(p1,dtype=np.float32)
    print("GLOBAL",label,"MEAN_ABS_DIFF",float(np.mean(np.abs(a-b))),"CORR",float(np.corrcoef(a.ravel(),b.ravel())[0,1]),"BRIGHTNESS",float(np.mean(a)),float(np.mean(b)),flush=True)
    if label=="+3":
        contact=Image.new("RGB",(2400,800))
        contact.paste(Image.open(base/"image_1.jpg").convert("RGB").resize((1200,800)),(0,0))
        contact.paste(Image.open(base/"image_2.jpg").convert("RGB").resize((1200,800)),(1200,0))
        contact.save(base/"comparison_side_by_side.jpg",quality=85)
        enhanced=ImageEnhance.Contrast(ImageChops.difference(p0,p1)).enhance(4)
        enhanced.save(base/"difference_4x.jpg",quality=90)
        box=(1700,500,3500,1900)
        Image.open(base/"image_1.jpg").crop(box).resize((900,700)).save(base/"fabric_before.jpg",quality=90)
        Image.open(base/"image_2.jpg").crop(box).resize((900,700)).save(base/"fabric_after.jpg",quality=90)
        print("OUTPUT",base/"comparison_side_by_side.jpg",flush=True)
