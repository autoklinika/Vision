"""Pure policy tests; no NVMe or bubblewrap required for CI."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "storage" / "vision_run.py"
spec = importlib.util.spec_from_file_location("vision_run", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

class TestVisionStorage(unittest.TestCase):
    def test_correct_nvme_snapshot(self):
        mod.validate_snapshot(
            "/dev/nvme0n1p1", "ext4", "rw,relatime",
            "/dev/nvme0n1p1", mod.EXPECTED_UUID, mod.EXPECTED_LABEL,
        )

    def test_wrong_device_fs_ro_uuid_or_label_fails_closed(self):
        cases = [
            ("/dev/mmcblk0p71", "ext4", "rw", mod.EXPECTED_UUID, mod.EXPECTED_LABEL),
            ("/dev/nvme0n1p1", "ntfs", "rw", mod.EXPECTED_UUID, mod.EXPECTED_LABEL),
            ("/dev/nvme0n1p1", "ext4", "ro,relatime", mod.EXPECTED_UUID, mod.EXPECTED_LABEL),
            ("/dev/nvme0n1p1", "ext4", "rw", "other-uuid", mod.EXPECTED_LABEL),
            ("/dev/nvme0n1p1", "ext4", "rw", mod.EXPECTED_UUID, "OTHER"),
        ]
        for source, fs, opts, uuid, label in cases:
            with self.subTest(source=source, fs=fs, opts=opts, uuid=uuid, label=label):
                with self.assertRaises(mod.StorageError):
                    mod.validate_snapshot(source, fs, opts, "/dev/nvme0n1p1", uuid, label)

    def test_ambiguous_findmnt_output_is_rejected(self):
        for value in ("", "/dev/nvme0n1p1 ext4", "garbage", "a b c d"):
            with self.subTest(value=value), self.assertRaises(mod.StorageError):
                mod.parse_mount(value)

    def test_mount_order_and_scoped_environment(self):
        args = mod.bubblewrap_args(["python3", "-c", "print('ok')"])
        self.assertLess(args.index("--ro-bind"), args.index("--bind"))
        ix = args.index("--ro-bind")
        self.assertEqual(args[ix + 1:ix + 3], ["/", "/"])
        ix = args.index("--bind")
        self.assertEqual(args[ix + 1:ix + 3], [str(mod.ROOT), str(mod.ROOT)])
        self.assertEqual(args[-4:], ["--", "python3", "-c", "print('ok')"])
        for key, path in mod.DIRECTORIES.items():
            self.assertTrue(path.is_relative_to(mod.ROOT), key)
            self.assertIn(key, args)

    def test_command_is_required(self):
        with self.assertRaises(mod.StorageError):
            mod.bubblewrap_args([])

    def test_unmounted_root_rejected_before_commands(self):
        with patch.object(mod, "ROOT") as root, patch.object(mod.os, "geteuid", return_value=1000):
            root.is_symlink.return_value = False
            root.is_dir.return_value = True
            root.is_mount.return_value = False
            with self.assertRaises(mod.StorageError):
                mod.require_storage()

    def test_directory_symlink_escaping_to_emmc_never_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "nvme"
            emmc = base / "emmc"
            root.mkdir()
            emmc.mkdir()
            (root / "cache").symlink_to(emmc, target_is_directory=True)
            old_root, old_dirs = mod.ROOT, mod.DIRECTORIES
            try:
                mod.ROOT = root
                mod.DIRECTORIES = {"PIP_CACHE_DIR": root / "cache" / "pip"}
                with self.assertRaises(mod.StorageError):
                    mod.prepare_directories()
                self.assertEqual(list(emmc.iterdir()), [])
            finally:
                mod.ROOT, mod.DIRECTORIES = old_root, old_dirs

    def test_valid_directories_created_under_nvme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root, old_dirs = mod.ROOT, mod.DIRECTORIES
            try:
                mod.ROOT = root
                mod.DIRECTORIES = {"PIP_CACHE_DIR": root / "cache" / "pip"}
                mod.prepare_directories()
                self.assertTrue((root / "cache" / "pip").is_dir())
            finally:
                mod.ROOT, mod.DIRECTORIES = old_root, old_dirs

if __name__ == "__main__":
    unittest.main()
