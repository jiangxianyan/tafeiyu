#!/usr/bin/env python3
"""Regenerate the human-readable persona snapshot from runtime sources."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "astrbot" / "data" / "personas" / "tafei.md"
STYLE = ROOT / "astrbot" / "data" / "plugin_data" / "tafei_persona" / "style.txt"
GLOSSARY = (
    ROOT / "astrbot" / "data" / "plugin_data" / "tafei_persona" / "glossary.txt"
)
OUTPUT = ROOT / "tafei_role.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def main() -> None:
    content = f"""# 永雏塔菲

> 这是由 `scripts/export_persona.py` 生成的可读快照。
> 实际运行时以 `personas/tafei.md`、`style.txt` 和 `glossary.txt` 为准。

## 一、基础人格

{read(BASE)}

## 二、说话规则

{read(STYLE)}

## 三、词义表

{read(GLOSSARY)}
"""
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
