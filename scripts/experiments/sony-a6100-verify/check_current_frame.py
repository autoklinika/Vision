from PIL import Image,ImageFilter,ImageStat
import os,sys
sys.path.insert(0,"/srv/vision-data/tools/npu-verify/.venv/lib/python3.12/site-packages")
import numpy as np
base="/srv/vision-data/vision/sessions/sony-a6100-test-20261010T202725Z"
im=Image.open(base+"/sony_a6100_test.jpg")
print("FILE_SIZE",os.path.getsize(base+"/sony_a6100_test.jpg"),"IMAGE_SIZE",im.size)
im.thumbnail((1200,800))
g=np.asarray(im.convert("L"),dtype=np.float32)
edge=np.asarray(im.convert("L").filter(ImageFilter.FIND_EDGES),dtype=np.float32)
print("MEAN",float(g.mean()),"STD",float(g.std()),"PERCENTILES",np.percentile(g,[1,5,50,95,99]).tolist(),"CLIPPED_BLACK",float(np.mean(g<5)),"CLIPPED_WHITE",float(np.mean(g>250)),"EDGE_MEAN",float(edge.mean()),"EDGE_P95",float(np.percentile(edge,95)))
im.save(base+"/preview.jpg",quality=86)
print("PREVIEW_PATH",base+"/preview.jpg")