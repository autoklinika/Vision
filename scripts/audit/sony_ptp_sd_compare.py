#!/usr/bin/env python3
"""Read-only PTP/SD comparison; preserve strict file and image distinctions."""
import argparse
import hashlib
import io
import json
import subprocess
from pathlib import Path

import sony_af_prototype as af


def jpeg_end(data):
    """Parse JPEG markers, respecting segment lengths and entropy escaping.

    A raw rfind(FFD9) can confuse metadata or trailing bytes with the real EOI.
    """
    if data[:2] != b"\xff\xd8":
        raise af.GateError("JPEG_SOI_MISSING")
    pos, entropy = 2, False
    while pos < len(data):
        if entropy:
            pos = data.find(b"\xff", pos)
            if pos < 0:
                break
        if data[pos] != 0xff:
            raise af.GateError("JPEG_MARKER_MISSING")
        pos += 1
        while pos < len(data) and data[pos] == 0xff:
            pos += 1
        if pos >= len(data):
            break
        code = data[pos]
        pos += 1
        if entropy and (code == 0 or 0xd0 <= code <= 0xd7):
            continue
        entropy = False
        if code == 0xd9:
            return pos
        if code == 1:
            continue
        if code in (0, 0xd8) or 0xd0 <= code <= 0xd7 or pos + 2 > len(data):
            raise af.GateError("JPEG_INVALID_MARKER")
        length = int.from_bytes(data[pos:pos + 2], "big")
        if length < 2 or pos + length > len(data):
            raise af.GateError("JPEG_SEGMENT_LENGTH")
        pos += length
        entropy = code == 0xda
    raise af.GateError("JPEG_EOI_MISSING")


def compare_jpeg_bytes(ptp, sd):
    pe, se = jpeg_end(ptp), jpeg_end(sd)
    encoded_equal = ptp[:pe] == sd[:se]
    tails_zero = not any(ptp[pe:]) and not any(sd[se:])
    # Sony originals can contain a second JPEG AFTER the primary image's EOI.
    # Preserve all those bytes. Only an SD suffix beyond the ENTIRE PTP file
    # may be classified as additional zero padding.
    prefix_equal = sd.startswith(ptp)
    sd_extra = sd[len(ptp):] if prefix_equal else b""
    padding_only = prefix_equal and len(sd) > len(ptp) and not any(sd_extra)
    return {"whole_file_equal": ptp == sd,
            "encoded_through_eoi_equal": encoded_equal,
            "ptp_eoi_end_bytes": pe, "sd_eoi_end_bytes": se,
            "ptp_tail_bytes": len(ptp) - pe, "sd_tail_bytes": len(sd) - se,
            "tails_all_zero": tails_zero,
            "entire_ptp_prefix_equal": prefix_equal,
            "sd_extra_bytes": len(sd_extra) if prefix_equal else None,
            "sd_extra_all_zero": not any(sd_extra) if prefix_equal else None,
            "classification": ("EXACT" if ptp == sd else
                               "PTP_PAYLOAD_IDENTICAL_SD_ZERO_PADDING_ONLY" if padding_only
                               else "DIFFERENT")}


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exact_files(left, right):
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            x, y = a.read(1024 * 1024), b.read(1024 * 1024)
            if x != y:
                return False
            if not x:
                return True


def decode_rgb(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        size = list(image.size)
        digest = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
    return {"dimensions": size, "decoded_rgb_sha256": digest}


def metadata(path):
    from PIL import Image
    with Image.open(path) as image:
        exif = image.getexif().get_ifd(34665)
        date = exif.get(36867)
        focal = exif.get(37386)
        if date is None or focal is None:
            raise af.GateError("JPEG_MATCH_METADATA_MISSING")
        return str(date), float(focal)


def sd_guard(root):
    root = root.resolve()
    mounts = json.loads(subprocess.check_output(
        ["findmnt", "-J", "-T", str(root), "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
        text=True))["filesystems"]
    if len(mounts) != 1:
        raise af.GateError("SD_MOUNT_NOT_UNIQUE")
    mount = mounts[0]
    if (Path(mount["target"]).resolve() != root or mount["fstype"] != "exfat"
            or "ro" not in mount["options"].split(",")
            or not mount["source"].startswith("/dev/sd")):
        raise af.GateError("SD_MUST_BE_SONY_EXFAT_READONLY_MOUNTPOINT")
    sysdev = (Path("/sys/class/block") / Path(mount["source"]).name).resolve(strict=True)
    identified = False
    for parent in sysdev.parents:
        if (parent / "idVendor").exists() and (parent / "idProduct").exists():
            identified = ((parent / "idVendor").read_text().strip() == "054c"
                          and (parent / "idProduct").read_text().strip() == "0f0b")
            break
    if not identified or not (root / "DCIM").is_dir():
        raise af.GateError("SD_SONY_MASS_STORAGE_IDENTITY_OR_DCIM_FAILED")
    return {"filesystem": "exfat", "readonly": True, "usb_identity": "054c:0f0b"}


def compare(manifest, sdroot, output):
    af.nvme_guard()
    sd_identity = sd_guard(sdroot)
    if not output.resolve().is_relative_to(af.BASE.resolve()):
        raise af.GateError("OUTPUT_OUTSIDE_NVME")
    if output.exists():
        raise af.GateError("OUTPUT_EXISTS_NO_OVERWRITE")
    source = json.loads(manifest.read_text())
    if source.get("status") != "PASS" or len(source["shots"]) != 13:
        raise af.GateError("EXPECTED_13_VERIFIED_PTP_PAIRS")
    needed = {}
    for shot in source["shots"]:
        jpeg = next(f for f in shot["files"] if Path(f["path"]).suffix.lower() == ".jpg")
        key = jpeg["exif_datetime"], shot["focal_mm"]
        if key in needed:
            raise af.GateError("PTP_MATCH_KEY_NOT_UNIQUE")
        needed[key] = shot
    candidates = {key: [] for key in needed}
    for path in sorted((sdroot / "DCIM").rglob("*")):
        if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg"):
            try:
                key = metadata(path)
            except Exception:
                continue  # Unrelated card files are not part of this comparison.
            if key in candidates:
                candidates[key].append(path)
    report = {"test": "PTP_SD_13_RAW_JPEG_PAIRS", "status": "FAIL",
              "sd_mount": sd_identity, "shots": [], "raw_full_decode": "UNKNOWN",
              "matching_method": "unique_EXIF_DateTimeOriginal_and_FocalLength_then_bytes",
              "scope": "13_zoom_AF_test_pairs_only; no_shutter_no_SD_writes"}
    for key, shot in needed.items():
        af.nvme_guard()
        sd_guard(sdroot)
        row = {"session": shot["session"], "shot": shot["shot"],
               "focal_mm": shot["focal_mm"], "status": "FAIL"}
        report["shots"].append(row)
        if len(candidates[key]) != 1:
            row["error"] = "SD_EXPOSURE_MISSING_OR_AMBIGUOUS"
            continue
        sdjpeg = candidates[key][0]
        sd_raw = [p for p in sdjpeg.parent.iterdir()
                  if p.stem.lower() == sdjpeg.stem.lower() and p.suffix.lower() == ".arw"]
        if len(sd_raw) != 1:
            row["error"] = "SD_RAW_MISSING_OR_AMBIGUOUS"
            continue
        by_ext = {Path(f["path"]).suffix.lower(): f for f in shot["files"]}
        originals = {ext: Path(f["path"]) for ext, f in by_ext.items()}
        for ext, path in originals.items():
            if (not path.resolve().is_relative_to(af.BASE.resolve())
                    or path.stat().st_size != by_ext[ext]["size_bytes"]
                    or sha_file(path) != by_ext[ext]["sha256"]):
                raise af.GateError("PTP_ORIGINAL_CHANGED")
        row["sd_stem"] = sdjpeg.stem
        row["raw"] = {"whole_file_equal": exact_files(originals[".arw"], sd_raw[0]),
                      "ptp_sha256": by_ext[".arw"]["sha256"], "sd_sha256": sha_file(sd_raw[0]),
                      "ptp_size_bytes": originals[".arw"].stat().st_size,
                      "sd_size_bytes": sd_raw[0].stat().st_size}
        ptp_bytes, sd_bytes = originals[".jpg"].read_bytes(), sdjpeg.read_bytes()
        result = compare_jpeg_bytes(ptp_bytes, sd_bytes)
        pdecoded, sdecoded = decode_rgb(ptp_bytes), decode_rgb(sd_bytes)
        result.update(ptp_sha256=by_ext[".jpg"]["sha256"], sd_sha256=hashlib.sha256(sd_bytes).hexdigest(),
                      ptp_size_bytes=len(ptp_bytes), sd_size_bytes=len(sd_bytes),
                      decoded_rgb_equal=pdecoded == sdecoded,
                      ptp_decoded=pdecoded, sd_decoded=sdecoded)
        row["jpeg"] = result
        if (row["raw"]["whole_file_equal"] and result["classification"] != "DIFFERENT"
                and result["decoded_rgb_equal"] and pdecoded["dimensions"] == [6000, 4000]):
            row["status"] = "PASS"
        print("PAIR %s/%02d %s %s" % (shot["session"], shot["shot"], row["status"], result["classification"]), flush=True)
    report["verified_pairs"] = sum(row["status"] == "PASS" for row in report["shots"])
    report["status"] = "PASS" if report["verified_pairs"] == 13 else "FAIL"
    report["raw_exact_files"] = sum(row.get("raw", {}).get("whole_file_equal", False) for row in report["shots"])
    report["jpeg_exact_files"] = sum(row.get("jpeg", {}).get("whole_file_equal", False) for row in report["shots"])
    report["jpeg_zero_padding_only"] = sum(row.get("jpeg", {}).get("classification") == "PTP_PAYLOAD_IDENTICAL_SD_ZERO_PADDING_ONLY" for row in report["shots"])
    sd_guard(sdroot)
    af.write_json(output, report)
    print("FINAL %s %d/13; OUTPUT %s" % (report["status"], report["verified_pairs"], output), flush=True)
    return 0 if report["status"] == "PASS" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--sd-root", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    return compare(args.manifest, args.sd_root, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
