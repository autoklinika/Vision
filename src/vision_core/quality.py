"""Explicit image QA; metrics do not establish physical PCB coverage."""
from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True)
class QualityPolicy:
    min_focus: float
    max_dark_fraction: float
    max_bright_fraction: float
    dark_level: int
    bright_level: int
    min_width: int
    min_height: int
    roi: tuple[int, int, int, int] | None = None

    def __post_init__(self):
        if (not math.isfinite(self.min_focus) or self.min_focus < 0
                or not 0 <= self.max_dark_fraction <= 1 or not 0 <= self.max_bright_fraction <= 1
                or not 0 <= self.dark_level < self.bright_level <= 255
                or self.min_width < 1 or self.min_height < 1):
            raise ValueError('invalid explicit QA policy')


def evaluate(data: bytes, policy: QualityPolicy) -> dict:
    import cv2
    import numpy as np
    if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('unsupported image format')
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError('unreadable image')
    height, width = image.shape[:2]
    if width < policy.min_width or height < policy.min_height:
        raise ValueError('image dimensions below policy')
    if policy.roi is not None:
        x, y, w, h = policy.roi
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height:
            raise ValueError('ROI out of bounds')
        image = image[y:y+h, x:x+w]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    focus = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    dark = float(np.mean(gray <= policy.dark_level))
    bright = float(np.mean(gray >= policy.bright_level))
    if focus < policy.min_focus or dark > policy.max_dark_fraction or bright > policy.max_bright_fraction:
        raise ValueError('focus or exposure outside policy')
    return {'width': width, 'height': height, 'focus': focus, 'dark_fraction': dark,
            'bright_fraction': bright, 'policy': asdict(policy)}
