"""Native AstrBot integration for the local meme-wiki dictionary."""

from __future__ import annotations

import asyncio
import os
import sys

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

PLUGIN_NAME = "tafei_memewiki"


def _data_dir() -> str:
    root = os.environ.get("ASTRBOT_ROOT") or ""
    if root:
        return os.path.join(root, "data")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "data")


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(_data_dir()))


def _active_persona_id() -> str:
    import io
    import json

    path = os.path.join(_project_root(), "config", "personas.json")
    try:
        with io.open(path, encoding="utf-8-sig") as handle:
            catalog = json.load(handle)
        return str(catalog.get("active") or "tafei")
    except (OSError, ValueError):
        return "tafei"


def _core():
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from memewiki_core import (
        find_for_message,
        get_config,
        get_stats,
        is_enabled_for_persona,
        lookup,
        render_entry,
        update_database,
    )

    return {
        "find_for_message": find_for_message,
        "get_config": get_config,
        "get_stats": get_stats,
        "is_enabled_for_persona": is_enabled_for_persona,
        "lookup": lookup,
        "render_entry": render_entry,
        "update_database": update_database,
    }


class TafeiMemeWiki(star.Star):
    """Local meme dictionary with per-persona opt-in."""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.dir, exist_ok=True)
        try:
            stats = _core()["get_stats"]()
            if stats["available"]:
                logger.info(
                    f"tafei_memewiki: loaded {stats['entries']} entries "
                    f"built_at={stats['built_at']}"
                )
            else:
                logger.warning("tafei_memewiki: 本地词库尚未下载")
        except Exception as error:
            logger.warning(f"tafei_memewiki: 初始化失败: {error}")

    @filter.on_llm_request()
    async def inject_meme(
        self, event: AstrMessageEvent, req
    ) -> None:
        try:
            core = _core()
            persona_id = _active_persona_id()
            if not core["is_enabled_for_persona"](persona_id):
                return
            if not core["get_config"]().get("auto_inject", True):
                return
            found = await asyncio.to_thread(
                core["find_for_message"],
                str(getattr(event, "message_str", "") or ""),
            )
            if not found:
                return
            query, _row, block = found
            current = (getattr(req, "prompt", "") or "") + (
                req.system_prompt or ""
            )
            if "[梗百科·内置用法]" in current:
                return
            if getattr(req, "prompt", None):
                req.prompt = req.prompt + block
                where = "prompt"
            else:
                req.system_prompt = (req.system_prompt or "") + block
                where = "system"
            logger.info(
                f"tafei_memewiki: injected query={query} "
                f"persona={persona_id} where={where}"
            )
        except Exception as error:
            logger.warning(f"tafei_memewiki: 注入失败: {error}")

    @filter.command("tf_meme")
    async def tf_meme(
        self, event: AstrMessageEvent, text: GreedyStr
    ) -> None:
        value = str(text).strip()
        if not value:
            yield event.plain_result(
                "用法：/tf_meme 词，比如 /tf_meme 哈基米"
            )
            return
        try:
            core = _core()
            config = core["get_config"]()
            if not core["is_enabled_for_persona"](_active_persona_id()):
                yield event.plain_result("梗百科还没有对这个人生效哦")
                return
            found = await asyncio.to_thread(core["find_for_message"], value)
            if found:
                query, row, _block = found
            else:
                query = value
                row = await asyncio.to_thread(core["lookup"], value)
            if not row:
                yield event.plain_result(
                    f"词库里没收录「{query}」。别硬编，说不知道就好。"
                )
                return
            yield event.plain_result(
                core["render_entry"](
                    row,
                    config.get("max_entry_chars", 1400),
                )
            )
        except Exception as error:
            yield event.plain_result(f"梗百科查询失败：{error}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_meme_status")
    async def tf_meme_status(self, event: AstrMessageEvent) -> None:
        try:
            core = _core()
            stats = core["get_stats"]()
            if not stats["available"]:
                yield event.plain_result(
                    "梗百科词库尚未下载。可在客户端“人格插件”里更新词库。"
                )
                return
            yield event.plain_result(
                f"梗百科：{stats['entries']} 条，"
                f"构建时间 {stats['built_at'] or '未知'}，"
                f"来源 {stats['source']}。"
            )
        except Exception as error:
            yield event.plain_result(f"读取梗百科状态失败：{error}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_meme_update")
    async def tf_meme_update(self, event: AstrMessageEvent) -> None:
        yield event.plain_result(
            "开始更新梗百科词库，完成后会再提示。"
        )
        try:
            result = await asyncio.to_thread(_core()["update_database"])
            yield event.plain_result(
                f"词库更新完成：{result['entries']} 条，"
                f"{result['size'] / 1024 / 1024:.1f} MB。"
            )
        except Exception as error:
            yield event.plain_result(f"词库更新失败：{error}")
