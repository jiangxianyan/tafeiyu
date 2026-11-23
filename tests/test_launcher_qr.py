"""Regression tests for stale QQ login QR rejection."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher"
if str(LAUNCHER) not in sys.path:
    sys.path.insert(0, str(LAUNCHER))

import launcher_core  # noqa: E402


class LoginQrTest(unittest.TestCase):
    def test_qr_must_be_new_and_recent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "qrcode.png"
            path.write_bytes(b"test")
            now = time.time()
            os.utime(path, (now - 300, now - 300))
            self.assertFalse(
                launcher_core.qr_is_fresh(
                    path,
                    not_before=now - 60,
                    max_age_seconds=120,
                    now=now,
                )
            )
            os.utime(path, (now - 10, now - 10))
            self.assertTrue(
                launcher_core.qr_is_fresh(
                    path,
                    not_before=now - 60,
                    max_age_seconds=120,
                    now=now,
                )
            )

    def test_latest_login_qr_ignores_old_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shell = Path(temp_dir) / "NapCat.Test.Shell"
            cache = (
                shell
                / "versions"
                / "test"
                / "resources"
                / "app"
                / "napcat"
                / "cache"
            )
            cache.mkdir(parents=True)
            qr = cache / "qrcode.png"
            qr.write_bytes(b"test")
            now = time.time()
            os.utime(qr, (now - 86400, now - 86400))
            self.assertIsNone(
                launcher_core.latest_login_qr(
                    {"napcat_shell_dir": str(shell)},
                    not_before=now - 60,
                    max_age_seconds=120,
                )
            )


if __name__ == "__main__":
    unittest.main()
