import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[2] / "scripts/calibration/vision_station_profile.py"

def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], text=True, capture_output=True)

class ProfileV1Tests(unittest.TestCase):
    def test_prepare_and_refuse_incomplete_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = run("prepare", "--session", "20261119-lab-v1", "--storage", tmp)
            self.assertEqual(cmd.returncode, 0, cmd.stderr)
            session = Path(tmp) / "sessions" / "20261119-lab-v1"
            self.assertTrue((session / "measurements.csv").is_file())
            self.assertTrue((session / "sources.yaml").is_file())
            self.assertFalse((session / "approval.yaml").read_text().find("NOT_APPROVED") == -1)
            result = run("freeze", "--session-dir", str(session), "--storage", tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REJECTED", result.stdout)
            self.assertFalse((Path(tmp) / "approved" / session.name).exists())

    def test_session_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run("prepare", "--session", "20261119-lab-v1", "--storage", tmp).returncode, 0)
            self.assertNotEqual(run("prepare", "--session", "20261119-lab-v1", "--storage", tmp).returncode, 0)

    def test_manifest_verification_fails_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "manifest.json").write_text(json.dumps({"sha256": {"camera.yaml": "deadbeef"}}))
            (p / "camera.yaml").write_text("camera: test")
            result = run("verify", "--approved-dir", tmp)
            self.assertEqual(result.returncode, 2)
            self.assertIn("FAIL", result.stdout)

if __name__ == "__main__":
    unittest.main()
