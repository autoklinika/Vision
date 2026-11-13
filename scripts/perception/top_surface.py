"""Automatic object top-face segmentation on rectified-left RAW16 depth.

Input ROI is a COARSE object proposal in stereo-left pixels, not a manually
drawn top-face region. Neither RGB alignment nor a known physical height
enters the estimator. Plane-to-plane height is an exploratory camera-frame
quantity; no robot-base coordinates and no safety assurance are provided.

Inspired by Luxonis BoxEstimator's ground-plane and top-plane decomposition.
No DepthAI/Open3D device access; safe for deterministic offline replay.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from perception_engine import fit_plane

FRAME = "stereo_left_rectified_optical"
VERSION = "perception.top_surface.v1"


@dataclass
class TopSurface:
    """Mask is local to ROI; never blindly map these pixels into RGB."""
    metadata: dict
    mask: np.ndarray


def _roi(roi, width, height):
    if len(roi) != 4:
        raise ValueError("ROI must be x0,y0,x1,y1")
    v = tuple(int(x) for x in roi)
    if not all(a == b for a, b in zip(v, roi)):
        raise ValueError("ROI must use integer pixels")
    x0,y0,x1,y1 = v
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("ROI outside depth frame")
    return v


def _points(x, y, z_m, K):
    return np.column_stack((
        (x-K[0,2])*z_m/K[0,0],
        (y-K[1,2])*z_m/K[1,1],
        z_m,
    ))


def _base(roi):
    return {"schema_version": VERSION, "frame_of_reference": FRAME,
            "validity": "NOT_READY", "reason": None, "height_mm": None,
            "top_surface_roi": list(roi), "top_mask_pixel_count": 0,
            "top_mask_bbox_xyxy": None,
            "table_frame": "UNAVAILABLE", "robot_base_frame": "UNAVAILABLE",
            "metrology_verified": False, "safety_function": False,
            "estimator": "MODE_GUIDED_CONNECTED_TOP_SURFACE_PARALLEL_TO_LOCAL_TABLE",
            "quality": {}}


def segment_top_surface(depth_mm: np.ndarray, K, object_roi,
                        table_roi, *, min_height_mm=15.0,
                        max_height_mm=150.0, min_top_pixels=80) -> TopSurface:
    """Find a coherent upper plateau and estimate its height above local table.

    Pipeline: local RANSAC table -> table-normal distance image -> dominant
    upper height mode -> connected top-face mask -> robust median-height plane.

    No known reference dimensions or object-specific parameters are used.
    Normals are constrained parallel to the local table: this describes a
    planar-height hypothesis, *not* a general tilted 3D object model.
    """
    if depth_mm.dtype != np.uint16 or depth_mm.ndim != 2:
        raise ValueError("expected RAW16 mm image")
    H,W = depth_mm.shape
    o = _roi(object_roi,W,H)
    t = _roi(table_roi,W,H)
    k = np.asarray(K,dtype=np.float64)
    if (k.shape != (3,3) or not np.isfinite(k).all()
            or k[0,0] <= 0 or k[1,1] <= 0 or
            not np.allclose(k[2], [0,0,1], atol=.001)):
        raise ValueError("invalid rectified depth intrinsics")
    if not (8 <= min_height_mm < max_height_mm <= 300
            and 25 <= min_top_pixels <= 1000):
        raise ValueError("invalid segmentation limits")

    x0,y0,x1,y1=o
    out=_base(o)
    empty=np.zeros((y1-y0,x1-x0),dtype=np.bool_)
    def fail(reason):
        out["reason"]=reason
        return TopSurface(out,empty.copy())

    tx0,ty0,tx1,ty1=t
    ty,tx=np.mgrid[ty0:ty1:3,tx0:tx1:3]
    tz=depth_mm[ty0:ty1:3,tx0:tx1:3].astype(np.float64)/1000.
    exclusion=18
    outside=((tx < x0-exclusion)|(tx >= x1+exclusion)|
             (ty < y0-exclusion)|(ty >= y1+exclusion))
    good=(tz>.25)&(tz<2.0)&outside
    if np.count_nonzero(good)<800:
        return fail("INSUFFICIENT_TABLE_POINTS")
    tp=_points(tx[good],ty[good],tz[good],k)
    plane=fit_plane(tp,threshold_m=.006,iterations=110,min_fraction=.55)
    if (plane is None or plane["residual_rmse_m"] > .005 or
            plane["inlier_fraction"] < .65 or plane["normal"][2] > -.85):
        return fail("TABLE_PLANE_UNRELIABLE")
    n=np.asarray(plane["normal"],dtype=np.float64)
    n /= np.linalg.norm(n)
    out["quality"]["table_rmse_mm"]=round(float(plane["residual_rmse_m"]*1000),3)
    out["quality"]["table_inlier_fraction"]=round(float(plane["inlier_fraction"]),4)

    yy,xx=np.mgrid[y0:y1,x0:x1]
    z=depth_mm[y0:y1,x0:x1].astype(np.float64)/1000.
    valid=(z>.25)&(z<2.0)
    height_mm=1000.*(((xx-k[0,2])*z/k[0,0])*n[0]+
                       ((yy-k[1,2])*z/k[1,1])*n[1]+
                       z*n[2]+plane["offset_m"])
    foreground=valid&(height_mm>=min_height_mm)&(height_mm<=max_height_mm)
    heights=height_mm[foreground]
    out["quality"]["foreground_points"]=int(len(heights))
    if len(heights)<min_top_pixels*2:
        return fail("INSUFFICIENT_FOREGROUND")

    # Locate the dominant *upper* elevation plateau without knowing its mm
    # reference. Sidewalls contribute broad distributed elevations rather than
    # a dense 1mm-level mode. The high quantile rejects the table/low edges.
    upper_floor=max(min_height_mm,float(np.quantile(heights,.70))-8.0)
    upper=heights[heights>=upper_floor]
    hist_edges=np.arange(min_height_mm,max_height_mm+2.,1.)
    hist,_=np.histogram(upper,bins=hist_edges)
    smoothed=np.convolve(hist.astype(float),[1,2,3,2,1],mode="same")
    best=int(np.argmax(smoothed))
    peak=float((hist_edges[best]+hist_edges[best+1])/2.)
    out["quality"]["candidate_height_mode_mm"]=round(peak,3)
    out["quality"]["upper_foreground_fraction"]=round(len(upper)/len(heights),3)

    # Exclude sloped sidewalls: points must lie near the dominant plateau.
    # Morphological close bridges isolated stereo holes without inventing
    # XYZ: only truly valid measured pixels enter the final height estimate.
    near=foreground&(np.abs(height_mm-peak)<=5.0)
    close=cv2.morphologyEx(near.astype(np.uint8),cv2.MORPH_CLOSE,
                           np.ones((5,5),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(close,8)
    parts=[i for i in range(1,count) if stats[i,cv2.CC_STAT_AREA]>=min_top_pixels]
    if not parts:
        return fail("NO_COHERENT_TOP_SURFACE")
    component=max(parts,key=lambda i:int(stats[i,cv2.CC_STAT_AREA]))
    candidate=(labels==component)&near
    if candidate.sum()<min_top_pixels:
        return fail("TOO_FEW_VALID_TOP_PIXELS")

    # Median-based refinement refuses peripheral depth bleeding/outliers.
    center=float(np.median(height_mm[candidate]))
    deviation=np.abs(height_mm-center)
    mask=candidate&(deviation<=4.0)
    if mask.sum()<min_top_pixels:
        return fail("TOP_SURFACE_TOO_FRAGMENTED")
    hvals=height_mm[mask]
    measured_height=float(np.median(hvals))
    mad=float(1.4826*np.median(np.abs(hvals-measured_height)))
    rmse=float(np.sqrt(np.mean((hvals-measured_height)**2)))
    ys,xs=np.where(mask)
    bbox=[int(x0+xs.min()),int(y0+ys.min()),
          int(x0+xs.max()+1),int(y0+ys.max()+1)]
    out["top_mask_pixel_count"]=int(mask.sum())
    out["top_mask_bbox_xyxy"]=bbox
    out["quality"].update({
        # Candidate is diagnostic-only; callers must NOT use it for motion.
        "candidate_height_mm":round(measured_height,3),
        "top_spread_mad_mm":round(mad,3),
        "top_spread_rmse_mm":round(rmse,3),
        "top_mode_distance_mm":round(measured_height-peak,3),
        "top_candidate_valid_fraction":round(mask.sum()/candidate.sum(),4),
        "top_mask_fraction_roi":round(mask.sum()/mask.size,4),
        "top_height_p05_p95_mm":[round(float(v),3) for v in np.quantile(hvals,[.05,.95])],
        "parallel_top_plane_assumption":True,
    })
    # A numerical result may still be unsuitable for a robot or metrology.
    if mad>2.5 or rmse>3.0:
        out["validity"]="NOT_READY"
        out["reason"]="UNSTABLE_TOP_SURFACE"
    else:
        out["height_mm"]=round(measured_height,3)
        out["validity"]="EXPLORATORY_UNVERIFIED_PROJECTION"
        out["reason"]="METROLOGY_AND_TABLE_TRANSFORM_UNVERIFIED"
    return TopSurface(out,mask)
