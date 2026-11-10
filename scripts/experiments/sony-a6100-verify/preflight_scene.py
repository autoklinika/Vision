import sys
sys.path.insert(0, "/srv/vision-data/tools/npu-verify/.venv/lib/python3.12/site-packages")
from PIL import Image,ImageFilter,ImageStat
import numpy as np
p="/srv/vision-data/vision/sessions/sony-a6100-test-20261010T201642Z/sony_a6100_test.jpg"
im=Image.open(p).convert("L")
im.thumbnail((1200,800))
a=np.asarray(im,dtype=np.float32)
e=np.asarray(im.filter(ImageFilter.FIND_EDGES),dtype=np.float32)
print("IMAGE",im.size,"mean",float(a.mean()),"contrast_std",float(a.std()),"edges_mean",float(e.mean()),"edges_p95",float(np.percentile(e,95)))
print("EXTREMA",im.getextrema())
