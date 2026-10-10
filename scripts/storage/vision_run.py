#!/usr/bin/env python3
"""Fail-closed launcher for VENTUNO Vision applications.

Checks the expected NVMe and restricts direct filesystem writes using a
bubblewrap mount namespace. Every Vision process must use this launcher.
This is not a global OS write prohibition or a hostile-code security boundary.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path("/srv/vision-data")
DEVICE = Path("/dev/nvme0n1p1")
EXPECTED_UUID = "80f1f04c-490c-49cd-8c7a-1baf56bf0c9d"
EXPECTED_LABEL = "VISION_DATA"
PROJECT = ROOT / "projects" / "Vision"
DIRECTORIES = {
    "HOME": ROOT / "home",
    "TMPDIR": ROOT / "tmp",
    "XDG_CACHE_HOME": ROOT / "cache",
    "XDG_CONFIG_HOME": ROOT / "config",
    "XDG_DATA_HOME": ROOT / "data",
    "XDG_STATE_HOME": ROOT / "state",
    "PIP_CACHE_DIR": ROOT / "cache" / "pip",
    "HF_HOME": ROOT / "cache" / "huggingface",
    "TORCH_HOME": ROOT / "cache" / "torch",
    "PYTHONPYCACHEPREFIX": ROOT / "cache" / "pycache",
}

class StorageError(RuntimeError):
    """Refuse unsafe storage configurations."""

def command_output(arguments: list[str]) -> str:
    try:
        result = subprocess.run(arguments, check=True, text=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as exc:
        raise StorageError(f"cannot verify storage ({arguments[0]}): {exc}") from exc
    return result.stdout.strip()

def parse_mount(line: str) -> tuple[str, str, str]:
    parts = line.split()
    if len(parts) != 3:
        raise StorageError(f"ambiguous mount information: {line!r}")
    return parts[0], parts[1], parts[2]

def validate_snapshot(
    source: str, fs_type: str, mount_options: str,
    device_path: str, uuid: str, label: str,
) -> None:
    if source != device_path:
        raise StorageError(f"unexpected mount source: {source!r}")
    if fs_type != "ext4":
        raise StorageError(f"unexpected filesystem: {fs_type!r}")
    opts = set(mount_options.split(","))
    if "rw" not in opts or "ro" in opts:
        raise StorageError("NVMe mount is not read-write")
    if uuid.lower() != EXPECTED_UUID:
        raise StorageError(f"unexpected filesystem UUID: {uuid!r}")
    if label != EXPECTED_LABEL:
        raise StorageError(f"unexpected volume label: {label!r}")

def require_storage() -> None:
    if os.geteuid() == 0:
        raise StorageError("run as an unprivileged user; do not use sudo")
    if ROOT.is_symlink() or not ROOT.is_dir() or not ROOT.is_mount():
        raise StorageError(f"expected mounted NVMe at {ROOT}; refusing eMMC fallback")
    if not DEVICE.exists() or not DEVICE.is_block_device():
        raise StorageError(f"missing expected block device: {DEVICE}")
    source, fs_type, opts = parse_mount(command_output([
        "findmnt", "-rn", "--mountpoint", str(ROOT), "-o", "SOURCE,FSTYPE,OPTIONS"
    ]))
    uuid = command_output(["lsblk", "-dn", "-o", "UUID", str(DEVICE)])
    label = command_output(["lsblk", "-dn", "-o", "LABEL", str(DEVICE)])
    if os.path.realpath(source) != os.path.realpath(DEVICE):
        raise StorageError(f"mount source does not resolve to {DEVICE}: {source}")
    validate_snapshot(source, fs_type, opts, str(DEVICE), uuid, label)
    if os.stat(ROOT).st_dev == os.stat(ROOT.parent).st_dev:
        raise StorageError("NVMe and parent have same device ID; unexpected mount")
    if os.statvfs(ROOT).f_flag & getattr(os, "ST_RDONLY", 1):
        raise StorageError("NVMe is mounted read-only")
    if not os.access(ROOT, os.W_OK | os.X_OK):
        raise StorageError("NVMe is not writable by the current user")
    if PROJECT.is_symlink() or not PROJECT.is_dir():
        raise StorageError(f"missing physical project directory on NVMe: {PROJECT}")
    if not PROJECT.resolve().is_relative_to(ROOT.resolve()):
        raise StorageError("project directory is outside NVMe")
    if shutil.which("bwrap") is None:
        raise StorageError("bubblewrap (bwrap) is unavailable; refusing unsafe launch")

def prepare_directories() -> None:
    # Check ALL ancestors before mkdir: e.g. ROOT/cache could redirect to eMMC.
    for path in sorted(set(DIRECTORIES.values()), key=lambda p: len(p.parts)):
        ancestor = path
        while ancestor != ROOT:
            if ancestor.is_symlink():
                raise StorageError(f"unsafe symlink in data directory: {ancestor}")
            if ancestor.exists() and not ancestor.resolve().is_relative_to(ROOT.resolve()):
                raise StorageError(f"data directory escapes NVMe: {ancestor}")
            ancestor = ancestor.parent
        path.mkdir(parents=True, exist_ok=True)
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise StorageError(f"data directory escapes NVMe: {path}")

def bubblewrap_args(command: list[str]) -> list[str]:
    if not command:
        raise StorageError("missing application command")
    # Order matters: read-only host root, then the ONE writable data mount.
    args = [
        "bwrap", "--die-with-parent", "--new-session",
        "--ro-bind", "/", "/",
        "--bind", str(ROOT), str(ROOT),
        "--chdir", str(PROJECT),
    ]
    for key, path in DIRECTORIES.items():
        args.extend(["--setenv", key, str(path)])
    args.extend([
        "--setenv", "TMP", str(DIRECTORIES["TMPDIR"]),
        "--setenv", "TEMP", str(DIRECTORIES["TMPDIR"]),
        "--", *command,
    ])
    return args

def smoke_test() -> int:
    snippet = r"""
import errno, os, pathlib, tempfile, uuid
root = pathlib.Path('/srv/vision-data')
with tempfile.NamedTemporaryFile(dir=os.environ['TMPDIR'], prefix='vision-smoke-', delete=True) as f:
    f.write(b'vision nvme test')
    f.flush()
    assert f.name.startswith(str(root) + '/')
print('NVME_WRITE=PASS')
probe = pathlib.Path('/home/arduino') / ('.vision-emmc-probe-' + uuid.uuid4().hex)
try:
    with probe.open('wb') as f:
        f.write(b'UNEXPECTED')
except OSError as e:
    if e.errno != errno.EROFS:
        raise SystemExit(f'EMMC_WRITE=FAIL, error was {e}')
    print('EMMC_WRITE_DENIED=PASS')
else:
    probe.unlink(missing_ok=True)
    raise SystemExit('EMMC_WRITE=FAIL, host filesystem writable')
"""
    return subprocess.call(bubblewrap_args([sys.executable, "-c", snippet]))

def main(argv: list[str]) -> int:
    if not argv or argv == ["--help"]:
        print("Usage: vision_run.py --check | --smoke | -- PROGRAM [ARG ...]")
        return 0 if argv else 2
    if argv[0] not in ("--check", "--smoke", "--"):
        raise StorageError("expected --check, --smoke, or -- before command")
    if argv[0] in ("--check", "--smoke") and len(argv) != 1:
        raise StorageError("unexpected trailing arguments")
    require_storage()
    if argv[0] == "--check":
        print("VISION_STORAGE=PASS (NVMe verified; sandbox executable available)")
        return 0
    prepare_directories()
    if argv[0] == "--smoke":
        result = smoke_test()
        if result != 0:
            raise StorageError(f"sandbox smoke test failed, exit={result}")
        print("VISION_STORAGE_SANDBOX=PASS")
        return 0
    if len(argv) < 2:
        raise StorageError("missing command after --")
    os.execvp("bwrap", bubblewrap_args(argv[1:]))
    return 1

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except StorageError as error:
        print(f"VISION_STORAGE_BLOCKED: {error}", file=sys.stderr)
        sys.exit(77)
