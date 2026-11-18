#!/usr/bin/env python3
"""Fast, dependency-free project integrity checks."""

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def check_python(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def main() -> int:
    errors = []
    for path in (
        ROOT / ".bot_runtime" / "bot_manager.py",
        ROOT / ".bot_runtime" / "tafei_watchdog.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_persona" / "main.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_sticker" / "main.py",
    ):
        try:
            check_python(path)
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    meta_path = ROOT / "stickers" / "tafei" / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for filename, info in meta.items():
            for keyword in info.get("kw", []):
                if len(keyword.strip()) < 2:
                    errors.append(f"{filename}: overly broad keyword {keyword!r}")
    except Exception as exc:
        errors.append(f"{meta_path}: {exc}")

    sticker_source = (
        ROOT / "astrbot" / "data" / "plugins" / "tafei_sticker" / "main.py"
    ).read_text(encoding="utf-8")
    if 'random.random() >= 0.6' in sticker_source:
        errors.append("tafei_sticker: hard-coded probability is still present")
    if 'NAPCAT_TOKEN = "tafei-local"' in sticker_source:
        errors.append("tafei_sticker: hard-coded NapCat token is still present")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("project checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
