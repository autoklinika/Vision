"""Conservative optical geometry for a rectified image and one PCB plane.

Camera poses map optical coordinates (+X right, +Y down, +Z forward) into
ECU-local coordinates, in millimetres. A predicted footprint is not evidence
that a photograph was captured, sharp, unobstructed, or spatially complete.
"""
import math

from vision_core.models import GateError
from vision_core.profiles import valid_quaternion

MAX_COORDINATE_MM = 1_000_000.0


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def vector(value, length):
    if (not isinstance(value, (tuple, list)) or len(value) != length
            or not all(finite_number(v) for v in value)):
        raise GateError('finite geometric vector required')
    return tuple(float(v) for v in value)


def rotate(quaternion, point):
    """Rotate a vector by a unit xyzw quaternion, without a matrix dependency."""
    if not valid_quaternion(quaternion):
        raise GateError('unit optical orientation required')
    x, y, z, w = quaternion
    norm = math.hypot(x, y, z, w)
    x, y, z, w = (v / norm for v in (x, y, z, w))
    a, b, c = vector(point, 3)
    tx, ty, tz = 2 * (y*c-z*b), 2 * (z*a-x*c), 2 * (x*b-y*a)
    result = (a+w*tx+y*tz-z*ty, b+w*ty+z*tx-x*tz, c+w*tz+x*ty-y*tx)
    if not all(math.isfinite(v) for v in result):
        raise GateError('optical rotation overflow')
    return result


def project_point(position_mm, quaternion, point_mm, calibration):
    """Project one ECU-local point into the rectified capture image."""
    position = vector(position_mm, 3)
    point = vector(point_mm, 3)
    q = vector(quaternion, 4)
    camera = rotate((-q[0], -q[1], -q[2], q[3]), tuple(p-o for p, o in zip(point, position)))
    if camera[2] <= 1e-9:
        raise GateError('PCB point is behind or on the optical image plane')
    pixel = (calibration.fx * camera[0] / camera[2] + calibration.cx,
             calibration.fy * camera[1] / camera[2] + calibration.cy)
    if not all(math.isfinite(v) for v in pixel):
        raise GateError('optical projection overflow')
    return pixel


def image_contains(pixel, rectangle):
    u, v = vector(pixel, 2)
    x, y, width, height = vector(rectangle, 4)
    return x <= u <= x+width and y <= v <= y+height


def footprint_polygon(position_mm, quaternion, calibration, plane_z_mm):
    """Intersect the four useful-image boundary rays with the PCB plane.

    Every corner must intersect in front of the camera. Horizon-crossing and
    grazing views fail closed rather than creating an unbounded footprint.
    """
    position = vector(position_mm, 3)
    if not finite_number(plane_z_mm) or abs(plane_z_mm) > MAX_COORDINATE_MM:
        raise GateError('invalid PCB plane')
    x, y, width, height = calibration.usable_image_xywh_px
    points = []
    for u, v in ((x, y), (x+width, y), (x+width, y+height), (x, y+height)):
        direction = rotate(quaternion, ((u-calibration.cx)/calibration.fx,
                                        (v-calibration.cy)/calibration.fy, 1.0))
        if abs(direction[2]) < 1e-9:
            raise GateError('grazing image ray has no bounded PCB footprint')
        distance = (plane_z_mm-position[2]) / direction[2]
        if distance <= 0 or not math.isfinite(distance):
            raise GateError('useful image does not face the PCB plane')
        point = (position[0]+distance*direction[0], position[1]+distance*direction[1])
        if not all(math.isfinite(v) and abs(v) <= MAX_COORDINATE_MM for v in point):
            raise GateError('PCB footprint exceeds geometry limits')
        points.append(point)
    twice_area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]+points[:1]))
    if abs(twice_area) < 1e-9 or not math.isfinite(twice_area):
        raise GateError('degenerate PCB footprint')
    if twice_area < 0:
        points.reverse()
    return tuple(points)


def inscribed_rectangle(polygon):
    """Return a conservative axis-aligned rectangle inside a convex polygon.

    The bounding rectangle is never used as covered area. Its centred half
    extents are jointly reduced against every polygon half-plane; consequently
    all four reported rectangle corners lie in the optical footprint. This is
    intentionally conservative for oblique/rotated views, not a maximal-area
    rectangle algorithm.
    """
    if not isinstance(polygon, (tuple, list)) or len(polygon) != 4:
        raise GateError('four-corner footprint required')
    p = tuple(vector(v, 2) for v in polygon)
    if any(abs(v) > MAX_COORDINATE_MM for point in p for v in point):
        raise GateError('footprint exceeds geometry limits')
    cx = sum(v[0] for v in p) / 4
    cy = sum(v[1] for v in p) / 4
    hx = min(cx-min(v[0] for v in p), max(v[0] for v in p)-cx)
    hy = min(cy-min(v[1] for v in p), max(v[1] for v in p)-cy)
    if hx <= 0 or hy <= 0:
        raise GateError('degenerate footprint extents')
    scale = 1.0
    for a, b in zip(p, p[1:]+p[:1]):
        ex, ey = b[0]-a[0], b[1]-a[1]
        distance = ex*(cy-a[1])-ey*(cx-a[0])
        extent = abs(ex)*hy+abs(ey)*hx
        if distance <= 0 or extent <= 0:
            raise GateError('nonconvex or incorrectly ordered footprint')
        # Also reject a self-intersecting or concave input, independently of
        # its centre being inside each edge half-plane.
        if any(ex*(v[1]-a[1])-ey*(v[0]-a[0]) < -1e-8 for v in p):
            raise GateError('nonconvex footprint')
        scale = min(scale, distance/extent)
    hx *= scale
    hy *= scale
    if min(hx, hy) <= 1e-9 or not all(math.isfinite(v) for v in (hx, hy)):
        raise GateError('usable conservative footprint is empty')
    return (cx-hx, cy-hy, 2*hx, 2*hy)
