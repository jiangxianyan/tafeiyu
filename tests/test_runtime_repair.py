"""Tests for portable Python virtual-environment repair."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher"
if str(LAUNCHER) not in sys.path:
    sys.path.insert(0, str(LAUNCHER))

import runtime_repair  # noqa: E402


class RuntimeRepairTest(unittest.TestCase):
    def test_astrbot_and_voice_venvs_are_made_portable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = (
                root / "runtime" / "astrbot-tool",
                root / "runtime" / "GPT-SoVITS-run" / ".venv",
            )
            for venv in paths:
                (venv / "Scripts").mkdir(parents=True)
                (venv / "Scripts" / "python.exe").write_bytes(b"test")
                (venv / "pyvenv.cfg").write_text(
                    "home = C:\\Users\\developer\\Python312\n"
                    "implementation = CPython\n"
                    "uv = 0.13.4\n"
                    "version_info = 3.12.2\n",
                    encoding="utf-8",
                )

            with patch.object(runtime_repair, "ROOT", root):
                runtime_repair.repair_venvs()

            for venv in paths:
                config = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
                self.assertIn(f"home = {sys.base_prefix}", config)
                self.assertNotIn("C:\\Users\\developer", config)
                self.assertNotIn("uv =", config)


if __name__ == "__main__":
    unittest.main()
