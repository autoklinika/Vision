from PIL import Image, ExifTags
import numpy as np
from pathlib import Path
runs=[("+1","/srv/vision-data/vision/sessions/focus-step-20261010T203439Z"),("+3","/srv/vision-data/vision/sessions/focus-step-20261010T203642Z")]
for label,folder in runs:
    files=[Path(folder)/f"image_{n}.jpg" for n in [1,2]]
    print("=== PAIR",label,"===")
    for f in files:
        im=Image.open(f)
        ex=im.getexif()
        vals={ExifTags.TAGS.get(k,str(k)):v for k,v in ex.items()}
        interesting={k:vals.get(k) for k in ("ExposureTime","FNumber","ISOSpeedRatings","PhotographicSensitivity","ExposureProgram","WhiteBalance","DateTimeOriginal","DateTime","FocalLength") if k in vals}
        print(f.name,"EXIF",interesting)
        box=(1800,400,3300,1700)
        a=np.asarray(im.crop(box).convert("L"),dtype=np.float32)
        lap=4*a[1:-1,1:-1]-a[:-2,1:-1]-a[2:,1:-1]-a[1:-1,:-2]-a[1:-1,2:]
        print("ROI_MEAN",float(a.mean()),"ROI_VARIANCE",float(np.var(a)),"ROI_LAP_VAR",float(np.var(lap)),"NORM_LAP",float(np.var(lap)/np.var(a)))
