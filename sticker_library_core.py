"""Local sticker library metadata shared by the desktop client."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STICKER_DIR = ROOT / "stickers" / "tafei"
META_PATH = STICKER_DIR / "meta.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _atomic_json(path: Path, value: Any) -> None:
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


def load_meta() -> dict[str, dict[str, Any]]:
    try:
        with META_PATH.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_meta(meta: dict[str, dict[str, Any]]) -> None:
    _atomic_json(META_PATH, meta)


def list_stickers() -> list[dict[str, Any]]:
    meta = load_meta()
    result = []
    if not STICKER_DIR.is_dir():
        return result
    for path in sorted(STICKER_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        info = meta.get(path.name)
        if not isinstance(info, dict):
            info = {}
        result.append(
            {
                **info,
                "filename": path.name,
                "path": path,
                "size": path.stat().st_size,
                "tagged": any(
                    info.get(field)
                    for field in ("kw", "emotion", "intent", "tone")
                ),
            }
        )
    return result


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace(",", "，").split("，")
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def save_sticker_metadata(
    filename: str,
    *,
    keywords: list[str] | str,
    emotion: list[str] | str,
    intent: list[str] | str,
    tone: list[str] | str,
    note: str,
) -> dict[str, Any]:
    path = STICKER_DIR / Path(filename).name
    if not path.is_file():
        raise ValueError("表情图片不存在")
    meta = load_meta()
    old = dict(meta.get(path.name) or {})
    q = int(old.get("q") or max(
        (
            int(item.get("q") or 0)
            for item in meta.values()
            if isinstance(item, dict)
        ),
        default=0,
    ) + 1)
    info = {
        **old,
        "q": q,
        "kw": _clean_list(keywords),
        "emotion": _clean_list(emotion),
        "intent": _clean_list(intent),
        "tone": _clean_list(tone),
        "note": str(note or "").strip()[:200],
        "source": "manual",
        "auto_tagged": bool(old.get("auto_tagged", False)),
    }
    if not any(info[field] for field in ("kw", "emotion", "intent", "tone")):
        raise ValueError("至少填写一组关键词、情绪、意图或语气")
    meta[path.name] = info
    save_meta(meta)
    return info


def _image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("只支持 PNG、JPG、GIF 或 WebP 表情图片")


def import_sticker(source: str) -> Path:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError("选择的图片不存在")
    size = path.stat().st_size
    if size < 16 or size > MAX_IMAGE_BYTES:
        raise ValueError("表情图片大小必须在 16 字节到 8 MB 之间")
    data = path.read_bytes()
    extension = _image_type(data)
    STICKER_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:20]
    target = STICKER_DIR / f"local_{digest}{extension}"
    if not target.exists():
        target.write_bytes(data)
    return target


def remove_sticker(filename: str) -> None:
    safe_name = Path(filename).name
    path = STICKER_DIR / safe_name
    if path.is_file():
        path.unlink()
    meta = load_meta()
    meta.pop(safe_name, None)
    save_meta(meta)
