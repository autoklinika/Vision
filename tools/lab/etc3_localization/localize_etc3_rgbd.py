#!/usr/bin/env python3
"""Read-only offline RGB-D localization; all lengths in mm unless stated."""
import argparse, json, hashlib, math, sys
from pathlib import Path
import cv2
import numpy as np

ROI=(790,175,1360,795)
BOX=np.array([[1071,493],[1249,493],[1249,566],[1071,566]],np.float32)
CROP=np.array([[835,190],[1330,190],[1330,750],[835,750]],np.float32)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def warp(points,M): return cv2.transform(np.asarray(points,np.float32).reshape(1,-1,2),M)[0]
def deproject(u,v,z,K):
    return np.stack(((np.asarray(u)-K[0,2])*z/K[0,0],(np.asarray(v)-K[1,2])*z/K[1,1],np.asarray(z)),axis=-1)
def robust_keep(values, floor=5.0, minimum=4):
    a=np.asarray(values,float); valid=np.isfinite(a)&(a>=200)&(a<=2000)
    keep=np.zeros(len(a),bool)
    if valid.sum()<minimum: return keep
    med=np.median(a[valid]); mad=np.median(np.abs(a[valid]-med)); keep=valid&(np.abs(a-med)<=max(floor,3*1.4826*mad))
    if keep.sum()<minimum: keep[:]=False
    return keep

def affine_match(ref, img):
    x1,y1,x2,y2=ROI; sift=cv2.SIFT_create(); a,da=sift.detectAndCompute(ref[y1:y2,x1:x2],None); b,db=sift.detectAndCompute(img[y1:y2,x1:x2],None)
    if da is None or db is None: return None
    pairs=cv2.BFMatcher().knnMatch(da,db,k=2); good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.70*p[1].distance]
    if len(good)<20: return None
    src=np.float32([a[m.queryIdx].pt for m in good]); dst=np.float32([b[m.trainIdx].pt for m in good]); M,ins=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=3000,confidence=.995,refineIters=10)
    if M is None or ins is None: return None
    n=int(ins.sum()); ratio=n/len(good); scale=float(np.hypot(M[0,0],M[1,0])); angle=float(np.degrees(np.arctan2(M[1,0],M[0,0])))
    if n<20 or ratio<.5 or not .9<scale<1.1 or abs(angle)>15: return None
    M[:,2]+=np.array([x1,y1])-M[:,:2]@np.array([x1,y1]); return M,dict(matches=len(good),inliers=n,inlier_ratio=ratio,scale=scale,angle_deg=angle)

def fit_plane(points, threshold=5., min_inliers=1000, seed=42):
    p=np.asarray(points,float); p=p[np.isfinite(p).all(axis=1)]
    if len(p)<min_inliers*2: return None
    rng=np.random.default_rng(seed); p=p[rng.permutation(len(p))]; split=int(.8*len(p)); train=p[:split]; hold=p[split:]; best=None
    for _ in range(250):
        a,b,c=train[rng.choice(len(train),3,replace=False)]; n=np.cross(b-a,c-a); norm=np.linalg.norm(n)
        if norm<1e-9: continue
        n/=norm; d=-n@a; mask=np.abs(train@n+d)<threshold
        if best is None or mask.sum()>best.sum(): best=mask
    if best is None or best.sum()<min_inliers or best.mean()<.35: return None
    for _ in range(3):
        q=train[best]; center=q.mean(axis=0); _,_,vh=np.linalg.svd(q-center,full_matrices=False); n=vh[-1]; d=-n@center; best=np.abs(train@n+d)<threshold
    if best.sum()<min_inliers or best.mean()<.35: return None
    if d<0: n=-n; d=-d # camera origin lies on positive side
    residual=np.abs(train[best]@n+d); hr=np.abs(hold@n+d)
    return dict(normal=n.tolist(),d_mm=float(d),inliers=int(best.sum()),train_count=len(train),inlier_fraction=float(best.mean()),rms_mm=float(np.sqrt(np.mean(residual**2))),holdout_p95_mm=float(np.percentile(hr,95)),holdout_inlier_fraction=float(np.mean(hr<threshold)),threshold_mm=threshold)

def plane_samples(depth,K,poly,step=4):
    mask=np.zeros(depth.shape,np.uint8); mask[100:900,750:1600]=1; cv2.fillPoly(mask,[np.rint(poly).astype(np.int32)],0); mask[:,:650]=0
    yy,xx=np.mgrid[0:depth.shape[0]:step,0:depth.shape[1]:step]; z=depth[::step,::step]; valid=(mask[::step,::step]>0)&(z>=200)&(z<=2000)
    return deproject(xx[valid],yy[valid],z[valid].astype(float),K)

def patch_depth(depth,center,radius=6):
    x,y=np.rint(center).astype(int); patch=depth[max(0,y-radius):min(depth.shape[0],y+radius+1),max(0,x-radius):min(depth.shape[1],x+radius+1)]; a=patch[(patch>=200)&(patch<=2000)]
    if len(a)<max(20,patch.size*.35): return None
    return float(np.median(a))

def segment(depth,K,plane,poly,center,threshold):
    mask=np.zeros(depth.shape,np.uint8); cv2.fillPoly(mask,[np.rint(poly).astype(np.int32)],1)
    yy,xx=np.nonzero(mask); z=depth[yy,xx].astype(float); valid=(z>=200)&(z<=2000); yy=yy[valid]; xx=xx[valid]; z=z[valid]; pts=deproject(xx,yy,z,K); h=pts@np.array(plane['normal'])+plane['d_mm']; sel=(h>=threshold)&(h<=100)
    binary=np.zeros(depth.shape,np.uint8); binary[yy[sel],xx[sel]]=1
    # Closing only bridges small sensor holes, not large occlusions.
    binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8)); count,labels,stats,centroids=cv2.connectedComponentsWithStats(binary,8)
    if count<=1: return None,None
    eligible=[]
    for i in range(1,count):
        if stats[i,cv2.CC_STAT_AREA]<500: continue
        ys,xs=np.where(labels==i); distance=float(np.min((xs-center[0])**2+(ys-center[1])**2))**.5
        if distance<100: eligible.append((stats[i,cv2.CC_STAT_AREA],i))
    if not eligible: return None,None
    i=max(eligible)[1]; component=(labels==i); take=component[yy,xx]&sel; p=pts[take]; heights=h[take]
    if len(p)<500: return None,None
    n=np.array(plane['normal']); ex=np.array([1.,0.,0.]); ex-=n*(ex@n); ex/=np.linalg.norm(ex); ey=np.cross(n,ex); ey*=np.sign(ey[1]) or 1
    coords=np.column_stack((p@ex,p@ey)).astype(np.float32); rect=cv2.minAreaRect(coords); corners=cv2.boxPoints(rect); center3=ex*rect[0][0]+ey*rect[0][1]-plane['d_mm']*n
    imagepoints=np.column_stack((xx[take],yy[take])).astype(np.int32); hull=cv2.convexHull(imagepoints); x,y,w,hbox=cv2.boundingRect(hull)
    result=dict(threshold_mm=threshold,measured_points=len(p),hull_center_on_plane_camera_mm=center3.tolist(),visible_hull_rectangle_size_mm=list(map(float,rect[1])),rectangle_angle_deg_relative_to_projected_camera_x=float(rect[2]),plane_basis_camera_x=ex.tolist(),plane_basis_camera_y=ey.tolist(),rectangle_corners_plane_basis_mm=corners.tolist(),height_median_mm=float(np.median(heights)),height_p95_mm=float(np.percentile(heights,95)),height_p99_mm=float(np.percentile(heights,99)),height_max_mm=float(np.max(heights)),image_hull_bounds_xywh=[x,y,w,hbox],status='PROVISIONAL_INCOMPLETE_OR_OCCLUDED',note='Visible depth component and its convex hull only; not certified full physical dimensions.')
    return result,hull

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--capture',required=True); ap.add_argument('--reference',required=True); ap.add_argument('--candidate'); ap.add_argument('--out',required=True); args=ap.parse_args(); cap=Path(args.capture); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((cap/'manifest.json').read_text()); K=np.array(manifest['camera_info']['depth']['K'],float).reshape(3,3); rgbK=np.array(manifest['camera_info']['rgb']['K']).reshape(3,3)
    if not np.allclose(K,rgbK) or K[0,0]<=0 or K[1,1]<=0 or np.any(np.array(manifest['camera_info']['depth']['D'])!=0): raise ValueError('Unsupported intrinsics/alignment/distortion')
    ref=cv2.imread(args.reference,0); rgbs=[]; depths=[]; hashes={}
    for i in range(8):
        rp=cap/f'rgb_{i:02}.png'; dp=cap/f'depth_{i:02}.png'; hashes[rp.name]=sha(rp); hashes[dp.name]=sha(dp)
        if hashes[rp.name]!=manifest['image_sha256'][rp.name] or hashes[dp.name]!=manifest['image_sha256'][dp.name]: raise ValueError('Image hash mismatch')
        rgb=cv2.imread(str(rp)); depth=cv2.imread(str(dp),cv2.IMREAD_UNCHANGED)
        if rgb is None or depth is None or depth.dtype!=np.uint16 or depth.shape!=(1080,1920) or rgb.shape[:2]!=depth.shape or ref is None or ref.shape!=depth.shape: raise ValueError('Invalid image dimensions or type')
        rgbs.append(rgb); depths.append(depth)
    matches=[]
    for rgb in rgbs:
        matches.append(affine_match(ref,cv2.cvtColor(rgb,cv2.COLOR_BGR2GRAY)))
    centers=np.array([warp(BOX.mean(axis=0).reshape(1,2),m[0])[0] if m else [np.nan,np.nan] for m in matches]); good=np.isfinite(centers).all(axis=1)
    if good.sum()>=4:
        med=np.median(centers[good],axis=0); dist=np.linalg.norm(centers-med,axis=1); stable=good&(dist<=max(3.,3*1.4826*np.median(dist[good])))
    else: stable=np.zeros(8,bool)
    result=dict(status='LOCALIZATION_FAILED',identity='ETC3 identity declared by user; SIFT establishes visual correspondence only',camera_extrinsics_status='UNAPPROVED_CANDIDATE',absolute_coordinates='ABSOLUTE XY/Z NOT CERTIFIED',units='mm except pixels and angles',capture_time_utc=manifest.get('time_utc'),rgb_stamps=manifest['rgb_stamps'],depth_stamps=manifest['depth_stamps'],image_sha256=hashes,reference_sha256=sha(args.reference),manifest_sha256=sha(cap/'manifest.json'),candidate_sha256=sha(args.candidate) if args.candidate else None,camera_intrinsics_K=K.tolist(),assurance='Offline file reads only; no camera, ROS, robot commands, or transform publication',blockers=['S03: ETC3 profile not approved','S04: station transform unapproved','Independent estimator not authenticated'],rgb_matches=[])
    for i,m in enumerate(matches): result['rgb_matches'].append(dict(frame=i,stable=bool(stable[i]),center_px=centers[i].tolist() if good[i] else None,**(m[1] if m else {})))
    if stable.sum()<4:
        result['limitation']='Insufficient stable visual matches'; (out/'localization.json').write_text(json.dumps(result,indent=2,allow_nan=False)); return 1
    ds=[]; per=[]
    for i,depth in enumerate(depths):
        j=int(np.argmin(np.abs(np.array(manifest['rgb_stamps'])-manifest['depth_stamps'][i]))); center=centers[j] if stable[j] else np.median(centers[stable],axis=0); z=patch_depth(depth,center); ds.append(z if z is not None else np.nan); per.append(dict(depth_frame=i,nearest_rgb_frame=j,time_offset_rgb_minus_depth_ms=1000*(manifest['rgb_stamps'][j]-manifest['depth_stamps'][i]),center_px=center.tolist(),depth_mm=z,center_source='matched_rgb' if stable[j] else 'stable_rgb_median'))
    keep=robust_keep(ds); xyz=[]
    for i,p in enumerate(per):
        p['accepted']=bool(keep[i]); p['camera_xyz_mm']=deproject(*p['center_px'],p['depth_mm'],K).tolist() if p['depth_mm'] is not None else None
        if keep[i]: xyz.append(p['camera_xyz_mm'])
    result['depth_frames']=per
    if not keep.any():
        result['limitation']='Insufficient consistent valid connector depths'; (out/'localization.json').write_text(json.dumps(result,indent=2,allow_nan=False)); return 1
    xyz=np.array(xyz); z=np.array(ds)[keep]; anchor=np.median(xyz,axis=0); result['connector']=dict(center_px_median=np.median(centers[stable],axis=0).tolist(),camera_xyz_mm=anchor.tolist(),depth_median_mm=float(np.median(z)),depth_mad_mm=float(np.median(abs(z-np.median(z)))),depth_std_mm=float(np.std(z)),xyz_std_mm=np.std(xyz,axis=0).tolist(),accepted_frames=int(keep.sum()),rgb_center_std_px=np.std(centers[stable],axis=0).tolist())
    planes=[]; segments=[]; hulls=[]
    for i,depth in enumerate(depths):
        j=per[i]['nearest_rgb_frame']; M=matches[j][0] if stable[j] else matches[np.flatnonzero(stable)[0]][0]; poly=warp(CROP,M); plane=fit_plane(plane_samples(depth,K,poly),seed=42+i); planes.append(plane)
        frame={}
        if plane and plane['holdout_p95_mm']<=15 and plane['holdout_inlier_fraction']>=.35:
            for t in (8,12,18):
                seg,hull=segment(depth,K,plane,poly,per[i]['center_px'],t); frame[str(t)]=seg
                if t==12: hulls.append((i,hull))
        segments.append(frame)
    result['table_planes_per_frame']=planes; result['visible_hull_per_frame_thresholds']=segments
    usable=[i for i in range(8) if keep[i] and segments[i].get('12')]; chosen=usable[len(usable)//2] if usable else int(np.flatnonzero(keep)[0]); plane=planes[chosen]; seg=segments[chosen].get('12'); result['representative_depth_frame']=chosen; result['table_plane']=plane; result['visible_hull']=seg
    result['geometric_limitations']=[]
    if not seg: result['geometric_limitations'].append('Plane or visible silhouette failed validation; no envelope reported.')
    result['geometric_limitations'].append('RGB and depth are asynchronous; offsets are reported per frame, and stationarity is assumed.')
    result['geometric_limitations'].append('Thresholded visible surface hull may include holes, occlusions, crop truncation or disconnected parts; dimensions are provisional.')
    if args.candidate:
        T=np.array(json.loads(Path(args.candidate).read_text())['T_table_rgb_optical_candidate'],float)
        if T.shape!=(4,4) or not np.isfinite(T).all() or not np.allclose(T[3],[0,0,0,1]) or not np.allclose(T[:3,:3].T@T[:3,:3],np.eye(3),atol=.002) or np.linalg.det(T[:3,:3])<.99: raise ValueError('Invalid candidate transform')
        transform=lambda p:(T[:3,:3]@np.asarray(p)+T[:3,3]*1000).tolist()
        ct=transform(anchor); old=np.array([695.9114,461.7553,36.16]); result['candidate_table_frame']={'status':'UNAPPROVED_CANDIDATE','absolute_coordinates':'ABSOLUTE XY/Z NOT CERTIFIED','connector_xyz_mm':ct,'visible_hull_center_on_plane_xyz_mm':transform(seg['hull_center_on_plane_camera_mm']) if seg else None,'historical_connector_xyz_mm':old.tolist(),'connector_delta_from_historical_mm':(np.array(ct)-old).tolist(),'comparison':'Plausibility only; historical position is not independently verified.'}
    result['status']='PROVISIONAL_LIVE_ECU_LOCALIZED'; j=per[chosen]['nearest_rgb_frame']; img=rgbs[j].copy(); hull=next((h for i,h in hulls if i==chosen),None)
    if hull is not None: cv2.polylines(img,[hull],True,(0,220,0),3)
    c=tuple(np.rint(per[chosen]['center_px']).astype(int)); cv2.drawMarker(img,c,(0,0,255),cv2.MARKER_CROSS,30,3); cv2.putText(img,f'USER-DECLARED ETC3 | depth {np.median(z):.1f} mm | PROVISIONAL', (50,70),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),3); cv2.putText(img,f'RGB {j:02} depth {chosen:02} | dt {per[chosen]["time_offset_rgb_minus_depth_ms"]:.0f} ms | hull visible only', (50,115),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,0,255),2)
    cv2.imwrite(str(out/'ecu_overlay_full.jpg'),img); cv2.imwrite(str(out/'ecu_overlay_preview.jpg'),cv2.resize(img,(960,540))); (out/'localization.json').write_text(json.dumps(result,indent=2,allow_nan=False)); return 0
if __name__=='__main__': sys.exit(main())
