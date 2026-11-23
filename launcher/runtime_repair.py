"""Repair portable runtime paths after extracting an offline package."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def repair_venvs() -> None:
    candidates = [
        ROOT / "runtime" / "astrbot-tool",
        ROOT / "voice" / "GPT-SoVITS-run" / ".venv",
        ROOT / "runtime" / "GPT-SoVITS-run" / ".venv",
    ]
    for venv in candidates:
        config = venv / "pyvenv.cfg"
        python_exe = venv / "Scripts" / "python.exe"
        if not config.is_file() or not python_exe.is_file():
            continue
        lines = config.read_text(encoding="utf-8", errors="replace").splitlines()
        values = {}
        for line in lines:
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip()
        values["home"] = sys.base_prefix
        values["version_info"] = ".".join(str(item) for item in sys.version_info[:3])
        values["include-system-site-packages"] = "false"
        output = [
            f"home = {values['home']}",
            f"implementation = {values.get('implementation', 'CPython')}",
        ]
        output.extend(
            [
                f"version_info = {values['version_info']}",
                "include-system-site-packages = false",
            ]
        )
        config.write_text("\n".join(output) + "\n", encoding="utf-8")
        print(f"repaired {config}")


def main() -> int:
    if os.name != "nt":
        return 0
    repair_venvs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
