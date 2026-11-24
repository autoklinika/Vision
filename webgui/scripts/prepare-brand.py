"""Opt-in local extraction. Never writes the original or embeds its source path."""
import hashlib
import json
import sys
import struct
import zlib
from pathlib import Path

REFERENCE = json.loads((Path(__file__).resolve().parents[1] / 'src/startup/brand-reference.json').read_text())
EXPECTED = REFERENCE['sourceSha256']
DEST = Path(__file__).resolve().parents[1] / 'public' / 'local-brand'


def strip_loop(data):
    """Walk GIF blocks; remove only recognized looping application extensions."""
    if data[:6] not in (b'GIF87a', b'GIF89a'):
        raise ValueError('Invalid GIF header')
    pos = 13 + (3 * 2 ** ((data[10] & 7) + 1) if data[10] & 128 else 0)
    output = bytearray(data[:pos])

    def subblocks(offset):
        while True:
            size = data[offset]
            offset += 1
            if not size:
                return offset
            offset += size
            if offset >= len(data):
                raise ValueError('Truncated GIF')

    while pos < len(data):
        start = pos
        tag = data[pos]
        pos += 1
        remove = False
        if tag == 0x3B:
            if pos != len(data):
                raise ValueError('Trailing GIF data')
            output.extend(data[start:pos])
            return bytes(output)
        if tag == 0x21:
            label = data[pos]
            pos += 1
            remove = label == 0xFF and data[pos:pos + 12] in (
                b'\x0bNETSCAPE2.0', b'\x0bANIMEXTS1.0')
            pos = subblocks(pos)
        elif tag == 0x2C:
            packed = data[pos + 8]
            pos += 9
            if packed & 128:
                pos += 3 * 2 ** ((packed & 7) + 1)
            pos = subblocks(pos + 1)  # LZW minimum code size
        else:
            raise ValueError('Unexpected GIF block')
        if not remove:
            output.extend(data[start:pos])
    raise ValueError('Missing GIF trailer')


def canonical_png(width, height, pixels):
    """RGB8, filter 0, stored DEFLATE blocks: independent of Pillow/zlib encoders."""
    if len(pixels) != width * height * 3:
        raise ValueError('Invalid RGB length')
    raw = b''.join(b'\0' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    compressed = b'\x78\x01'
    for start in range(0, len(raw), 65535):
        block = raw[start:start + 65535]
        compressed += bytes([int(start + len(block) == len(raw))]) + struct.pack('<HH', len(block), 65535 - len(block)) + block
    compressed += struct.pack('>I', zlib.adler32(raw))
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')


def verify_derivatives(animation, logo):
    if hashlib.sha256(animation).hexdigest() != REFERENCE['introSha256'] or hashlib.sha256(logo).hexdigest() != REFERENCE['logoSha256']:
        raise ValueError('Derivative trusted reference mismatch')


def prepare(source):
    # Invalidate stale output even when a later import fails.
    DEST.mkdir(parents=True, exist_ok=True)
    for name in ('manifest.json', 'intro.gif', 'logo.png'):
        (DEST / name).unlink(missing_ok=True)
    data = Path(source).read_bytes()
    if len(data) != 29462 or hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Original checksum/size mismatch; no asset prepared')
    try:
        from PIL import Image
    except ImportError:
        raise ValueError('Optional Pillow unavailable; skip preparation or use a private virtualenv') from None
    from io import BytesIO
    original = Image.open(BytesIO(data))
    if original.size != (800, 100) or original.n_frames != 29:
        raise ValueError('Unexpected original dimensions/frames')
    duration = 0
    for i in range(original.n_frames):
        original.seek(i)
        duration += original.info['duration']
    if duration != 3490:
        raise ValueError('Unexpected playback duration')
    # Frame 12 is the completed white-background hold (990 ms), before black fade.
    original.seek(12)
    logo = original.convert('RGB')
    animation = strip_loop(data)
    check = Image.open(BytesIO(animation))
    if 'loop' in check.info:
        raise ValueError('Loop extension remains')
    for i in range(29):
        original.seek(i)
        check.seek(i)
        if original.convert('RGB').tobytes() != check.convert('RGB').tobytes() or original.info['duration'] != check.info['duration']:
            raise ValueError('Frame or timing changed')
    logo_bytes = canonical_png(800, 100, logo.tobytes())
    verify_derivatives(animation, logo_bytes)
    (DEST / 'intro.gif').write_bytes(animation)
    (DEST / 'logo.png').write_bytes(logo_bytes)
    manifest = {'sourceSha256': EXPECTED, 'durationMs': duration,
                'introSha256': hashlib.sha256(animation).hexdigest(),
                'logoSha256': hashlib.sha256((DEST / 'logo.png').read_bytes()).hexdigest()}
    (DEST / 'manifest.json').write_text(json.dumps(manifest) + '\n')
    print('Prepared private local-only assets: 29 unchanged frames, 3490 ms, no loop; original frame 12 logo.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Usage: python3 scripts/prepare-brand.py <authorized-original.gif>')
        prepare(sys.argv[1])
    except (ValueError, OSError, IndexError) as error:
        # Do not echo private filesystem paths.
        print(str(error) if isinstance(error, ValueError) else 'Asset read/parse failed', file=sys.stderr)
        sys.exit(1)
