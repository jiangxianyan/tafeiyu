"""Create additional local personas without editing JSON by hand."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "config" / "personas.json"
PERSONA_DIR = ROOT / "astrbot" / "data" / "personas"
ACCENTS = ("#7e72c9", "#4f91d8", "#df6d98", "#3f9c7b", "#c47b3b")


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _catalog() -> dict:
    try:
        with CATALOG_PATH.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {"active": "tafei", "personas": []}
    except (OSError, ValueError):
        return {"active": "tafei", "personas": []}


def add_persona(
    *,
    persona_id: str,
    display_name: str,
    source_file: str,
    aliases: list[str] | None = None,
) -> dict:
    persona_id = str(persona_id or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", persona_id):
        raise ValueError(
            "人格 ID 需为 2～32 位英文小写字母、数字、下划线或短横线，"
            "并且以字母开头"
        )
    display_name = str(display_name or "").strip()
    if not display_name:
        raise ValueError("人格名称不能为空")
    source = Path(source_file).expanduser().resolve()
    if not source.is_file():
        raise ValueError("人格 Markdown 文件不存在")
    if source.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("人格文件必须是 Markdown 或文本文件")
    if source.stat().st_size > 512 * 1024:
        raise ValueError("人格文件不能超过 512 KB")

    catalog = _catalog()
    personas = catalog.setdefault("personas", [])
    if any(str(item.get("id")) == persona_id for item in personas):
        raise ValueError(f"人格 ID 已存在：{persona_id}")

    PERSONA_DIR.mkdir(parents=True, exist_ok=True)
    target = PERSONA_DIR / f"{persona_id}.md"
    if target.exists():
        raise ValueError(f"人格文件已存在：{target.name}")
    text = source.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        raise ValueError("人格文件内容为空")
    target.write_text(text + "\n", encoding="utf-8", newline="\n")

    entry = {
        "id": persona_id,
        "display_name": display_name,
        "aliases": [
            str(item).strip()
            for item in (aliases or [])
            if str(item).strip()
        ],
        "persona_file": target.relative_to(ROOT).as_posix(),
        "style_file": "",
        "accent": ACCENTS[len(personas) % len(ACCENTS)],
        "voice_binding": {
            "voice_id": "",
            "display_name": "未绑定声线",
            "provider": "none",
            "install_mode": "none",
        },
    }
    personas.append(entry)
    _atomic_json(CATALOG_PATH, catalog)
    return entry
