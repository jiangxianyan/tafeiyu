"""Stable, persona-scoped visual identity cards for tafeiyu.

Visual identity is configuration, not conversation memory. Keeping it in its
own store prevents ordinary chat from silently rewriting who a persona is.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
VISUAL_ROOT = PROJECT_ROOT / "astrbot" / "data" / "persona_visuals"
ASSET_ROOT = VISUAL_ROOT / "assets"
MAX_REFERENCE_BYTES = 16 * 1024 * 1024
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)

DEFAULT_CARDS: dict[str, dict[str, Any]] = {
    "tafei": {
        "id": "tafei",
        "display_name": "塔菲",
        "avatar_path": "",
        "appearance": (
            "永雏塔菲的经典二次元侦探/发明家形象：粉色头发和金瞳，"
            "整体气质偏可爱、俏皮。具体服装会随公开立绘变化，"
            "稳定识别特征以发型、瞳色和常用配饰为主。"
        ),
        "hair": "粉色齐肩中长发，M 形刘海，后发扎成低双马尾",
        "outfit": (
            "经典造型为白色长袖衬衫、深棕色披肩、红色领结、棕色半身裙、"
            "腰带腰包、黑色过膝袜和黑色长靴；其他公开服装按图片判断"
        ),
        "colors": ["粉色", "白色", "深棕色", "红色", "金色"],
        "motifs": [
            "呆毛",
            "心形护目镜",
            "红色发带",
            "领结齿轮",
            "放大镜",
            "药水",
            "虚拟偶像",
            "单机游戏主播",
        ],
        "reference_images": [],
        "self_recognition_notes": (
            "只有在本次对话确实看到用户发送的图片，且图片视觉特征与"
            "参考卡片相符时，才可以说“这看起来像我”。不要凭想象声称"
            "看过参考图，也不要把公开形象说成自己的现实照片。"
        ),
        "boundaries": [
            "区分二次元网络形象与真人照片",
            "不编造未在参考卡中确认的发型、服装、配饰或瞳色",
        ],
    },
    "dafeiyu": {
        "id": "dafeiyu",
        "display_name": "大肥鱼",
        "avatar_path": "",
        "appearance": (
            "DeepSeek 娘 / 小鲸鱼的二次元网络形象，蓝色与白色为主，"
            "长发，带有鲸鱼意象。社区同人常见鲸鱼尾巴、闭眼或蒙眼表现，"
            "这些属于同人识别特征，不代表现实身份。"
        ),
        "hair": "蓝色长发",
        "outfit": "蓝白配色服饰；具体款式以参考图为准",
        "colors": ["蓝色", "白色"],
        "motifs": ["小鲸鱼", "鲸鱼尾巴", "DeepSeek"],
        "reference_images": [],
        "self_recognition_notes": (
            "只有在本次对话确实看到用户发送的图片，且蓝白配色、长发、"
            "鲸鱼意象等可见特征与参考卡片吻合时，才可以说像自己。"
            "不要把所有蓝发动漫图都认定为自己。"
        ),
        "boundaries": [
            "区分社区同人形象与官方身份",
            "不把“大肥鱼”当成现实体型或人物描述",
            "不编造参考卡未确认的具体服装细节",
        ],
    },
}

STRING_FIELDS = (
    "id",
    "display_name",
    "avatar_path",
    "appearance",
    "hair",
    "outfit",
    "self_recognition_notes",
)
LIST_FIELDS = ("colors", "motifs", "reference_images", "boundaries")


def _safe_persona_id(persona_id: str) -> str:
    value = str(persona_id or "").strip().lower()
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in value):
        raise ValueError("人格 ID 无效")
    return value


def _card_path(persona_id: str) -> Path:
    return VISUAL_ROOT / f"{_safe_persona_id(persona_id)}.json"


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _normalized_card(persona_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    persona_id = _safe_persona_id(persona_id)
    defaults = DEFAULT_CARDS.get(
        persona_id,
        {
            "id": persona_id,
            "display_name": persona_id,
            "avatar_path": "",
            "appearance": "",
            "hair": "",
            "outfit": "",
            "colors": [],
            "motifs": [],
            "reference_images": [],
            "self_recognition_notes": "",
            "boundaries": [],
        },
    )
    card = dict(defaults)
    if isinstance(data, dict):
        card.update(data)
    card["id"] = persona_id
    for field in STRING_FIELDS:
        card[field] = str(card.get(field) or "").strip()
    for field in LIST_FIELDS:
        card[field] = _clean_list(card.get(field))
    return card


def _atomic_save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def load_visual_card(persona_id: str) -> dict[str, Any]:
    """Load a card, creating the initial one on first use."""

    persona_id = _safe_persona_id(persona_id)
    path = _card_path(persona_id)
    try:
        with io.open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("人格形象卡不是 JSON 对象")
    except FileNotFoundError:
        data = _normalized_card(persona_id)
        _atomic_save(path, data)
    except (OSError, ValueError):
        data = _normalized_card(persona_id)
    return _normalized_card(persona_id, data)


def save_visual_card(persona_id: str, values: dict[str, Any]) -> dict[str, Any]:
    card = _normalized_card(persona_id, values)
    _atomic_save(_card_path(persona_id), card)
    return card


def update_visual_card(persona_id: str, **values: Any) -> dict[str, Any]:
    card = load_visual_card(persona_id)
    card.update(values)
    return save_visual_card(persona_id, card)


def _image_extension(data: bytes) -> str:
    for signature, extension in IMAGE_SIGNATURES:
        if data.startswith(signature):
            return extension
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("只支持 PNG、JPG、GIF 或 WebP 图片")


def import_visual_reference(
    persona_id: str,
    source_path: str,
    *,
    make_avatar: bool = False,
) -> dict[str, Any]:
    """Copy one user-supplied image into the persona's private asset folder."""

    persona_id = _safe_persona_id(persona_id)
    source = Path(str(source_path or "")).expanduser().resolve()
    if not source.is_file():
        raise ValueError("选择的图片不存在")
    size = source.stat().st_size
    if size < 16:
        raise ValueError("图片文件过小")
    if size > MAX_REFERENCE_BYTES:
        raise ValueError("图片不能超过 16 MB")
    data = source.read_bytes()
    extension = _image_extension(data)
    digest = hashlib.sha256(data).hexdigest()
    target_dir = ASSET_ROOT / persona_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{digest[:20]}-{uuid.uuid4().hex[:8]}{extension}"
    temp_target = target.with_suffix(target.suffix + ".tmp")
    temp_target.write_bytes(data)
    os.replace(temp_target, target)

    relative = target.relative_to(PROJECT_ROOT).as_posix()
    card = load_visual_card(persona_id)
    references = _clean_list(card.get("reference_images"))
    if relative not in references:
        references.append(relative)
    card["reference_images"] = references
    if make_avatar:
        card["avatar_path"] = relative
    return save_visual_card(persona_id, card)


def resolve_visual_path(relative_or_absolute: str) -> Path | None:
    value = str(relative_or_absolute or "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        return path.resolve()
    except OSError:
        return None


def remove_visual_reference(persona_id: str, relative_path: str) -> dict[str, Any]:
    """Remove a managed reference file, refusing paths outside the asset root."""

    persona_id = _safe_persona_id(persona_id)
    path = resolve_visual_path(relative_path)
    managed_root = ASSET_ROOT.resolve()
    if path is not None and managed_root in path.parents and path.is_file():
        path.unlink(missing_ok=True)
    card = load_visual_card(persona_id)
    card["reference_images"] = [
        item
        for item in card.get("reference_images", [])
        if item != str(relative_path)
    ]
    if card.get("avatar_path") == str(relative_path):
        card["avatar_path"] = ""
    return save_visual_card(persona_id, card)


def visual_identity_prompt(persona_id: str, *, include_capability: bool = True) -> str:
    card = load_visual_card(persona_id)
    display_name = card.get("display_name") or persona_id
    parts = [f"【{display_name}·稳定网络形象】"]
    if card.get("appearance"):
        parts.append("整体形象：" + card["appearance"])
    if card.get("hair"):
        parts.append("发型：" + card["hair"])
    if card.get("outfit"):
        parts.append("服饰：" + card["outfit"])
    if card.get("colors"):
        parts.append("主色：" + "、".join(card["colors"]))
    if card.get("motifs"):
        parts.append("识别意象：" + "、".join(card["motifs"]))
    references = card.get("reference_images", [])
    if references:
        parts.append(
            f"用户已为该人格配置 {len(references)} 张参考图；"
            "仅把它们当作稳定视觉设定，不要在文字对话中假装直接看到了文件。"
        )
    else:
        parts.append("当前没有已导入的参考图，不要假装看过具体参考图。")
    if card.get("self_recognition_notes"):
        parts.append("辨认规则：" + card["self_recognition_notes"])
    if card.get("boundaries"):
        parts.append("视觉边界：" + "；".join(card["boundaries"]))
    if include_capability:
        parts.append(
            "你能够理解本次对话中用户实际发送的图片；图片内容会以"
            "“【用户发送的图片】”或“[图片内容: …]”标记提供。"
            "先依据可见内容回答，无法确认的细节不要猜。"
        )
    return "\n".join(parts)
