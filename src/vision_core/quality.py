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

    max_encoded_bytes: int = 128 * 1024 * 1024
    max_pixels: int = 50_000_000

    def __post_init__(self):
        if (not math.isfinite(self.min_focus) or self.min_focus < 0
                or not 0 <= self.max_dark_fraction <= 1 or not 0 <= self.max_bright_fraction <= 1
                or not 0 <= self.dark_level < self.bright_level <= 255
                or self.min_width < 1 or self.min_height < 1
                or type(self.max_encoded_bytes) is not int or self.max_encoded_bytes < 1
                or type(self.max_pixels) is not int or self.max_pixels < 1):
            raise ValueError('invalid explicit QA policy')


def _dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(data) < 33 or data[8:12] != b'\x00\x00\x00\r' or data[12:16] != b'IHDR':
            raise ValueError('malformed PNG header')
        return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('unsupported image format')
    pos = 2
    sof = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
    while pos < len(data):
        if data[pos] != 0xff:
            break
        while pos < len(data) and data[pos] == 0xff:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0xd8, 0xd9, 0xda, 0x00) or 0xd0 <= marker <= 0xd7:
            break
        if marker == 0x01:
            continue
        if pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos:pos+2], 'big')
        if length < 2 or pos + length > len(data):
            break
        if marker in sof:
            if length < 11 or data[pos+7] == 0 or length != 8 + 3 * data[pos+7]:
                break
            return int.from_bytes(data[pos+5:pos+7], 'big'), int.from_bytes(data[pos+3:pos+5], 'big')
        pos += length
    raise ValueError('malformed JPEG header')


def evaluate(data: bytes, policy: QualityPolicy) -> dict:
    import cv2
    import numpy as np
    if not isinstance(data, bytes) or len(data) > policy.max_encoded_bytes:
        raise ValueError('encoded image exceeds limit')
    width, height = _dimensions(data)
    if width < 1 or height < 1 or width * height > policy.max_pixels:
        raise ValueError('image dimensions exceed limit')
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError('unreadable image')
    height, width = image.shape[:2]
    if (width, height) != _dimensions(data):
        raise ValueError('decoded image dimensions mismatch')
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
