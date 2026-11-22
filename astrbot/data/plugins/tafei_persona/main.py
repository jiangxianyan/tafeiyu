import io
import json
import os
import sys
import tempfile

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

PLUGIN_NAME = "tafei_persona"
MAX_INJECT_CHARS = 6000   # 每次回复最多注入的语录字符数，防止吃满上下文
MAX_SHOW_ITEMS = 40
MAX_PLUGIN_PROMPT_CHARS = 3000


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _data_dir() -> str:
    root = os.environ.get("ASTRBOT_ROOT") or ""
    if root:
        return os.path.join(root, "data")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "data")


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(_data_dir()))


def _plugin_prompt(persona_id: str, user_text: str) -> str:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from persona_extensions import build_plugin_prompt

        return build_plugin_prompt(
            persona_id,
            user_text,
            char_limit=MAX_PLUGIN_PROMPT_CHARS,
        )
    except Exception as error:
        logger.warning(f"tafei_persona: 人格插件读取失败: {error}")
        return ""


def _visual_identity_prompt(persona_id: str) -> str:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from persona_visuals_core import visual_identity_prompt

        return visual_identity_prompt(persona_id)
    except Exception as error:
        logger.warning(f"tafei_persona: 人格形象卡读取失败: {error}")
        return ""


def _active_persona() -> dict:
    fallback = {
        "id": "tafei",
        "display_name": "塔菲",
        "persona_file": "astrbot/data/personas/tafei.md",
        "style_file": "astrbot/data/plugin_data/tafei_persona/style.txt",
    }
    path = os.path.join(_project_root(), "config", "personas.json")
    try:
        with io.open(path, encoding="utf-8-sig") as handle:
            catalog = json.load(handle)
        active = str(catalog.get("active") or "tafei")
        persona = next(
            (
                item
                for item in catalog.get("personas", [])
                if str(item.get("id")) == active
            ),
            None,
        )
        return persona if persona else fallback
    except (OSError, ValueError):
        return fallback


class TafeiPersona(star.Star):
    """塔菲人设教学：在 QQ 里用命令教她说话方式，实时注入 system prompt。"""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.dir, exist_ok=True)
        self.styles_dir = os.path.join(self.dir, "styles")
        os.makedirs(self.styles_dir, exist_ok=True)

    def _style_path(self) -> str:
        persona = _active_persona()
        configured = str(persona.get("style_file") or "").strip()
        if configured:
            return os.path.join(_project_root(), configured.replace("/", os.sep))
        return os.path.join(self.styles_dir, f"{persona.get('id', 'tafei')}.txt")

    def _glossary_path(self) -> str:
        persona_id = str(_active_persona().get("id") or "tafei")
        if persona_id == "tafei":
            return os.path.join(self.dir, "glossary.txt")
        return os.path.join(self.styles_dir, f"{persona_id}.glossary.txt")

    def _load(self) -> list[str]:
        path = self._style_path()
        if not os.path.exists(path):
            return []
        with io.open(path, encoding="utf-8") as f:
            return _dedupe([ln.strip() for ln in f if ln.strip()])

    def _save(self, items: list[str]) -> None:
        items = _dedupe(items)
        path = self._style_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="style-", suffix=".tmp", dir=os.path.dirname(path)
        )
        try:
            with io.open(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(items) + ("\n" if items else ""))
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_add")
    async def tf_add(self, event: AstrMessageEvent, text: GreedyStr) -> None:
        """教一条：/tf_add 喜欢用「诶嘿」结尾（可以多行）"""
        item = str(text).strip()
        if not item:
            yield event.plain_result("后面要跟内容呀，比如 /tf_add 说话爱用「诶嘿」")
            return
        items = self._load()
        lines = [ln.strip() for ln in item.splitlines() if ln.strip()]
        items.extend(lines)
        self._save(items)
        yield event.plain_result(f"记住了 {len(lines)} 条，现在一共 {len(items)} 条")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_bulk")
    async def tf_bulk(self, event: AstrMessageEvent, text: GreedyStr) -> None:
        """整段语录批量导入：每行一条，/tf_bulk 后面跟一大段"""
        raw = str(text).strip()
        if not raw:
            yield event.plain_result("后面要跟语录正文，可以整段粘贴")
            return
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not lines:
            yield event.plain_result("没读到内容")
            return
        items = self._load()
        items.extend(lines)
        self._save(items)
        yield event.plain_result(
            f"导入 {len(lines)} 行，现在一共 {len(items)} 条（每次回复最多注入 {MAX_INJECT_CHARS} 字）"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_show")
    async def tf_show(self, event: AstrMessageEvent) -> None:
        """查看已教的内容"""
        items = self._load()
        if not items:
            yield event.plain_result("还没教过我什么呢，用 /tf_add 开始教吧")
            return
        head = items[:MAX_SHOW_ITEMS]
        lines = [f"{i}. {t}" for i, t in enumerate(head, 1)]
        tail = "" if len(items) <= MAX_SHOW_ITEMS else f"\n……（共 {len(items)} 条，只显示前 {MAX_SHOW_ITEMS} 条）"
        yield event.plain_result("学到的内容：\n" + "\n".join(lines) + tail)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_del")
    async def tf_del(self, event: AstrMessageEvent, idx: str = "") -> None:
        """删掉第 N 条：/tf_del 3"""
        items = self._load()
        try:
            n = int(str(idx).strip())
        except ValueError:
            yield event.plain_result("要给个序号，比如 /tf_del 3")
            return
        if n < 1 or n > len(items):
            yield event.plain_result(f"没有第 {n} 条，现在一共 {len(items)} 条")
            return
        removed = items.pop(n - 1)
        self._save(items)
        yield event.plain_result(f"删掉了：{removed}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_set")
    async def tf_set(self, event: AstrMessageEvent, text: GreedyStr) -> None:
        """整段覆盖：/tf_set 说话要更冲一点，多怼人"""
        item = str(text).strip()
        if not item:
            yield event.plain_result("要用 /tf_set 加内容呀")
            return
        self._save([item])
        yield event.plain_result("好的，已经整段换成新的了")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_clear")
    async def tf_clear(self, event: AstrMessageEvent) -> None:
        """清空全部"""
        self._save([])
        yield event.plain_result("都清掉了，回到基础人设")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_help")
    async def tf_help(self, event: AstrMessageEvent) -> None:
        """命令列表"""
        display_name = str(_active_persona().get("display_name") or "当前人格")
        yield event.plain_result(
            f"教{display_name}（仅管理员）：\n"
            "/tf_add 内容 —— 加一条（可多行）\n"
            "/tf_bulk 整段 —— 每行一条，批量导入语录\n"
            "/tf_show —— 看前 40 条\n"
            "/tf_del 序号 —— 删一条\n"
            "/tf_set 内容 —— 整段覆盖\n"
            "/tf_clear —— 全清空\n"
            "改完立刻生效，不用重启"
        )

    def _load_glossary(self) -> list[str]:
        path = self._glossary_path()
        if not os.path.exists(path):
            return []
        with io.open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]

    @filter.on_llm_request()
    async def inject_style(self, event: AstrMessageEvent, req) -> None:
        try:
            items = self._load()
            terms = self._load_glossary()
        except Exception as e:
            logger.error(f"tafei_persona: 读取规则失败: {e}")
            return

        persona_text = ""
        persona = _active_persona()
        persona_id = str(persona.get("id") or "tafei")
        display_name = str(persona.get("display_name") or "当前人格")
        try:
            configured = str(persona.get("persona_file") or "").strip()
            persona_path = (
                os.path.join(_project_root(), configured.replace("/", os.sep))
                if configured
                else os.path.join(_data_dir(), "personas", "tafei.md")
            )
            if os.path.exists(persona_path):
                with io.open(persona_path, encoding="utf-8") as f:
                    persona_text = f.read().strip()
        except Exception as e:
            logger.error(f"tafei_persona: 读取人设失败: {e}")

        marker = f"【{display_name}·人设与说话方式】"
        current = (getattr(req, "prompt", "") or "") + (req.system_prompt or "")
        if marker in current:
            return

        parts = [
            "\n\n" + marker,
            "以下内容优先级高于上文所有通用要求；冲突时以这里为准。",
        ]
        if persona_text and persona_text not in current:
            parts.append("\n【人设】\n" + persona_text)
        if items:
            used, total = [], 0
            for i, t in enumerate(items, 1):
                if total + len(t) > MAX_INJECT_CHARS:
                    break
                used.append(f"{i}. {t}")
                total += len(t)
            parts.append("\n【说话规则】\n" + "\n".join(used))
        if terms:
            parts.append("\n【词义表】\n" + "\n".join(f"- {t}" for t in terms))
        visual_prompt = _visual_identity_prompt(persona_id)
        if visual_prompt:
            parts.append("\n" + visual_prompt)
        plugin_prompt = _plugin_prompt(
            persona_id, str(getattr(event, "message_str", "") or "")
        )
        if plugin_prompt:
            parts.append(plugin_prompt)
        block = "\n".join(parts)

        # 群聊插件会把很长的指令塞进 prompt，规则落在最后才压得住。
        if getattr(req, "prompt", None):
            req.prompt = req.prompt + block
            where = "prompt"
        else:
            req.system_prompt = (req.system_prompt or "") + block
            where = "system"
        logger.info(
            f"tafei_persona: 注入到 {where} persona={bool(persona_text)} "
            f"rules={len(items)} visual={bool(visual_prompt)} "
            f"plugins={bool(plugin_prompt)} "
            f"block_len={len(block)}"
        )
