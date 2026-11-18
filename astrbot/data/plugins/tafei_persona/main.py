import io
import os
import tempfile

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

PLUGIN_NAME = "tafei_persona"
MAX_INJECT_CHARS = 6000   # 每次回复最多注入的语录字符数，防止吃满上下文
MAX_SHOW_ITEMS = 40


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


class TafeiPersona(star.Star):
    """塔菲人设教学：在 QQ 里用命令教她说话方式，实时注入 system prompt。"""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.dir, exist_ok=True)
        self.file = os.path.join(self.dir, "style.txt")
        self.glossary_file = os.path.join(self.dir, "glossary.txt")

    def _load(self) -> list[str]:
        if not os.path.exists(self.file):
            return []
        with io.open(self.file, encoding="utf-8") as f:
            return _dedupe([ln.strip() for ln in f if ln.strip()])

    def _save(self, items: list[str]) -> None:
        items = _dedupe(items)
        fd, temp_path = tempfile.mkstemp(
            prefix="style-", suffix=".tmp", dir=self.dir
        )
        try:
            with io.open(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(items) + ("\n" if items else ""))
            os.replace(temp_path, self.file)
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
        yield event.plain_result(
            "教塔菲（仅管理员）：\n"
            "/tf_add 内容 —— 加一条（可多行）\n"
            "/tf_bulk 整段 —— 每行一条，批量导入语录\n"
            "/tf_show —— 看前 40 条\n"
            "/tf_del 序号 —— 删一条\n"
            "/tf_set 内容 —— 整段覆盖\n"
            "/tf_clear —— 全清空\n"
            "改完立刻生效，不用重启"
        )

    def _load_glossary(self) -> list[str]:
        if not os.path.exists(self.glossary_file):
            return []
        with io.open(self.glossary_file, encoding="utf-8") as f:
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
        try:
            persona_path = os.path.join(_data_dir(), "personas", "tafei.md")
            if os.path.exists(persona_path):
                with io.open(persona_path, encoding="utf-8") as f:
                    persona_text = f.read().strip()
        except Exception as e:
            logger.error(f"tafei_persona: 读取人设失败: {e}")

        marker = "【永雏塔菲·人设与说话方式】"
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
            f"rules={len(items)} block_len={len(block)}"
        )
