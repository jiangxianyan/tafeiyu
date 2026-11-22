#!/usr/bin/env python3
"""Fast, dependency-free project integrity checks."""

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def check_python(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def main() -> int:
    errors = []
    python_paths = [
        ROOT / ".bot_runtime" / "bot_manager.py",
        ROOT / ".bot_runtime" / "tafei_watchdog.py",
        *sorted((ROOT / "launcher").glob("*.py")),
        *sorted((ROOT / "launcher").glob("*.pyw")),
        ROOT / "astrbot" / "data" / "plugins" / "tafei_persona" / "main.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_sticker" / "main.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_memory" / "main.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_vision" / "main.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_voice" / "main.py",
        ROOT / "astrbot" / "data" / "plugins" / "tafei_web" / "main.py",
        ROOT / "persona_visuals_core.py",
        ROOT / "persona_manager_core.py",
        ROOT / "sticker_library_core.py",
        ROOT / "scripts" / "build_offline_package.py",
        *sorted((ROOT / "persona_extensions").glob("*.py")),
        *sorted((ROOT / "memewiki_core").glob("*.py")),
        *sorted((ROOT / "tests").glob("test_*.py")),
    ]
    for path in dict.fromkeys(python_paths):
        try:
            check_python(path)
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    json_paths = [
        ROOT / "config" / "personas.json",
        ROOT / "astrbot" / "data" / "plugin_data" / "tafei_vision" / "config.json",
        *sorted((ROOT / "astrbot" / "data" / "persona_visuals").glob("*.json")),
    ]
    for path in json_paths:
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    meta_path = ROOT / "stickers" / "tafei" / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for filename, info in meta.items():
                if not (ROOT / "stickers" / "tafei" / filename).is_file():
                    errors.append(f"{filename}: metadata exists but image file is missing")
                for keyword in info.get("kw", []):
                    if len(keyword.strip()) < 2:
                        errors.append(f"{filename}: overly broad keyword {keyword!r}")
                for field in ("emotion", "intent", "tone"):
                    if not info.get(field):
                        errors.append(f"{filename}: missing semantic field {field}")
        except Exception as exc:
            errors.append(f"{meta_path}: {exc}")

    sticker_source = (
        ROOT / "astrbot" / "data" / "plugins" / "tafei_sticker" / "main.py"
    ).read_text(encoding="utf-8")
    if 'random.random() >= 0.6' in sticker_source:
        errors.append("tafei_sticker: hard-coded probability is still present")
    if 'NAPCAT_TOKEN = "tafei-local"' in sticker_source:
        errors.append("tafei_sticker: hard-coded NapCat token is still present")

    watchdog_source = (
        ROOT / ".bot_runtime" / "tafei_watchdog.py"
    ).read_text(encoding="utf-8")
    if "smtplib" in watchdog_source or "send_drop_mail" in watchdog_source:
        errors.append("watchdog: offline email code is still present")

    requirements = ROOT / "requirements-launcher.txt"
    try:
        requirement_text = requirements.read_text(encoding="utf-8").lower()
        if "pyyaml" not in requirement_text:
            errors.append("requirements-launcher.txt: PyYAML is missing")
        if "pillow" not in requirement_text:
            errors.append("requirements-launcher.txt: Pillow is missing")
    except OSError as exc:
        errors.append(f"{requirements}: {exc}")

    if not (ROOT / "LICENSE").is_file():
        errors.append("LICENSE: project license is missing")
    if not (
        ROOT
        / "astrbot"
        / "data"
        / "plugins"
        / "astrbot_plugin_group_chat_plus"
        / "LICENSE"
    ).is_file():
        errors.append("Group Chat Plus AGPL license is missing")

    personal_patterns = ("REDACTED_QQ", "REDACTED_GROUP", "REDACTED_GROUP")
    for path in dict.fromkeys(python_paths):
        source = path.read_text(encoding="utf-8")
        for value in personal_patterns:
            if value in source:
                errors.append(f"{path}: deployment-specific ID {value} is hard-coded")
        if re.search(r"C:\\\\tafei(?:\\\\|\")", source, re.IGNORECASE):
            errors.append(f"{path}: hard-coded C:\\tafei path")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("project checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
