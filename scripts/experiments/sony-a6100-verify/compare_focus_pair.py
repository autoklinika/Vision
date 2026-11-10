from PIL import Image, ImageChops, ImageEnhance, ImageStat, ImageDraw
import numpy as np
from pathlib import Path
b=Path("/srv/vision-data/vision/sessions/focus-step-20261010T203439Z")
images=[Image.open(str(b/f"image_{i}.jpg")).convert("RGB") for i in (1,2)]
print("DIMENSIONS", [im.size for im in images], flush=True)
for j,im in enumerate(images,1):
    im.getexif()
    im.thumbnail((1200,800))
    im.save(str(b/f"preview_{j}.jpg"),quality=87)
frames=[np.asarray(im.convert("L"),dtype=np.float32) for im in images]
a,bb=frames
print("BRIGHTNESS",float(a.mean()),float(bb.mean()))
print("STD_CONTRAST",float(a.std()),float(bb.std()))
print("GLOBAL_ABS_DIFF",float(np.mean(np.abs(a-bb))))
print("GLOBAL_CORRELATION",float(np.corrcoef(a.ravel(),bb.ravel())[0,1]))
# Metric on texture: mean squared second-derivative approximates focus energy.
def metrics(frame):
    x=frame
    lap=x[:-2,1:-1]+x[2:,1:-1]+x[1:-1,:-2]+x[1:-1,2:]-4*x[1:-1,1:-1]
    g1=np.diff(x,axis=0)
    g2=np.diff(x,axis=1)
    return (round(float(np.var(lap)),2),round(float(np.mean(g1*g1)+np.mean(g2*g2)),2),round(float(np.std(x)),2))
rois={
    "all":(0,0,1200,800),
    "torso_fabric":(335,40,750,420),
    "skirt_fabric":(445,390,865,675),
    "left_sleeve":(295,110,520,205),
    "dress_center":(500,100,700,450),
    "label_detail":(500,650,1080,735),
    "neutral_background":(15,40,260,570),
}
for name,(x0,y0,x1,y1) in rois.items():
    m1=metrics(a[y0:y1,x0:x1]);m2=metrics(bb[y0:y1,x0:x1])
    print(f"REGION {name}: focus_lap_var {m1[0]} -> {m2[0]} ({(m2[0]/m1[0]-1)*100:+.2f}%), tenengrad {m1[1]} -> {m2[1]} ({(m2[1]/m1[1]-1)*100:+.2f}%), mean_abs_diff {float(np.mean(np.abs(a[y0:y1,x0:x1]-bb[y0:y1,x0:x1]))):.2f}")
# A contact sheet for camera geometry; the image is only for internal verification.
sheet=Image.new("RGB",(2400,800))
sheet.paste(images[0],(0,0));sheet.paste(images[1],(1200,0))
sheet.save(str(b/"side_by_side.jpg"),quality=88)
heat=ImageEnhance.Contrast(ImageChops.difference(images[0],images[1])).enhance(3.5)
heat.save(str(b/"difference_3p5x.jpg"),quality=87)
print("COMPARISON_IMAGES",b/"side_by_side.jpg",b/"difference_3p5x.jpg")
