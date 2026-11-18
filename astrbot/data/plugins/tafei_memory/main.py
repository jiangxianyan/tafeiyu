import asyncio
import hashlib
import io
import os
import re
import sqlite3
import time
from contextlib import contextmanager

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command import GreedyStr

PLUGIN_NAME = "tafei_memory"
RECALL_LIMIT = 4
RECALL_CHARS = 700
RETENTION_DAYS = 90
MAX_ROWS = 20000
MIN_TEXT_CHARS = 6


def _data_dir() -> str:
    root = os.environ.get("ASTRBOT_ROOT") or ""
    if root:
        return os.path.join(root, "data")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "data")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fingerprint(session: str, text: str) -> str:
    return hashlib.sha1((session + "\n" + text).encode("utf-8")).hexdigest()


def _trigrams(text: str) -> str:
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())[:240]
    if len(compact) < 3:
        return ""
    terms = {
        compact[i : i + 3]
        for i in range(min(len(compact) - 2, 32))
        if not compact[i : i + 3].isdigit()
    }
    return " OR ".join('"%s"' % term.replace('"', '""') for term in sorted(terms)[:12])


class TafeiMemory(star.Star):
    """Group-scoped, local, trigram-indexed conversation recall."""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.cfg_dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.db_path = os.path.join(self.cfg_dir, "memory.db")
        self._inserts = 0
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=15)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_db(self) -> None:
        with self._db() as db:
            db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(
                    content,
                    session UNINDEXED,
                    sender UNINDEXED,
                    created_at UNINDEXED,
                    priority UNINDEXED,
                    fingerprint UNINDEXED,
                    tokenize='trigram'
                )
                """
            )

    def _store(
        self, session: str, sender: str, text: str, priority: int = 0
    ) -> bool:
        text = _clean_text(text)[:600]
        if len(text) < MIN_TEXT_CHARS:
            return False
        fingerprint = _fingerprint(session, text)
        now = time.time()
        with self._db() as db:
            exists = db.execute(
                "SELECT 1 FROM memories WHERE session=? AND fingerprint=? LIMIT 1",
                (session, fingerprint),
            ).fetchone()
            if exists:
                return False
            db.execute(
                """
                INSERT INTO memories(
                    content, session, sender, created_at, priority, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (text, session, sender[:80], now, priority, fingerprint),
            )
            self._inserts += 1
            if self._inserts % 100 == 0:
                cutoff = now - RETENTION_DAYS * 86400
                db.execute("DELETE FROM memories WHERE created_at < ?", (cutoff,))
                db.execute(
                    """
                    DELETE FROM memories WHERE rowid NOT IN (
                        SELECT rowid FROM memories
                        ORDER BY priority DESC, created_at DESC
                        LIMIT ?
                    )
                    """,
                    (MAX_ROWS,),
                )
        return True

    def _recall(
        self, session: str, query: str, exclude_fingerprint: str
    ) -> list[tuple[str, str, float, int]]:
        terms = _trigrams(query)
        if not terms:
            return []
        cutoff = time.time() - RETENTION_DAYS * 86400
        with self._db() as db:
            rows = db.execute(
                """
                SELECT content, sender, created_at, priority
                FROM memories
                WHERE session=? AND created_at>=? AND fingerprint<>?
                  AND memories MATCH ?
                ORDER BY priority DESC, created_at DESC
                LIMIT ?
                """,
                (session, cutoff, exclude_fingerprint, terms, RECALL_LIMIT),
            ).fetchall()
        return rows

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def capture_message(self, event: AstrMessageEvent) -> None:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return
        text = _clean_text(event.message_str)
        if not text or text.startswith(("/", "!", "#")):
            return
        priority = 8 if any(k in text for k in ("记住", "以后记得", "别忘了")) else 0
        try:
            await asyncio.to_thread(
                self._store,
                event.unified_msg_origin,
                event.get_sender_name() or event.get_sender_id(),
                text,
                priority,
            )
        except Exception as exc:
            logger.warning(f"tafei_memory: 写入失败 {exc}")

    @filter.on_llm_request()
    async def inject_memories(self, event: AstrMessageEvent, req) -> None:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return
        current = (getattr(req, "prompt", "") or "") + (req.system_prompt or "")
        marker = "【群聊长期记忆·仅当前会话】"
        if marker in current:
            return
        text = _clean_text(event.message_str)
        if len(text) < 4:
            return
        session = event.unified_msg_origin
        fingerprint = _fingerprint(session, text[:600])
        try:
            sender = event.get_sender_name() or event.get_sender_id() or "群友"
            await asyncio.to_thread(self._store, session, sender, text)
            rows = await asyncio.to_thread(
                self._recall, session, text, fingerprint
            )
        except Exception as exc:
            logger.warning(f"tafei_memory: 召回失败 {exc}")
            return
        if not rows:
            return

        lines = []
        used = 0
        for content, sender, created_at, _priority in rows:
            age_days = max(0, int((time.time() - float(created_at)) / 86400))
            line = f"- {sender}（{age_days}天前）：{content}"
            if used + len(line) > RECALL_CHARS:
                break
            lines.append(line)
            used += len(line)
        if not lines:
            return
        block = (
            "\n\n" + marker
            + "\n以下是同一群聊中的历史片段，只用于理解关系和延续话题；"
            "不要逐字复述，不要跨群，也不要把它当成绝对事实。\n"
            + "\n".join(lines)
        )
        req.system_prompt = (req.system_prompt or "") + block
        logger.info(
            f"tafei_memory: recalled={len(lines)} chars={len(block)}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_remember")
    async def tf_remember(
        self, event: AstrMessageEvent, text: GreedyStr
    ) -> None:
        value = _clean_text(str(text))
        if not value:
            yield event.plain_result("用法：/tf_remember 要长期记住的内容")
            return
        added = await asyncio.to_thread(
            self._store,
            event.unified_msg_origin,
            event.get_sender_name() or "管理员",
            value,
            10,
        )
        yield event.plain_result("记下了" if added else "这条之前已经记过了")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_forget")
    async def tf_forget(
        self, event: AstrMessageEvent, text: GreedyStr
    ) -> None:
        keyword = _clean_text(str(text))
        if not keyword:
            yield event.plain_result("用法：/tf_forget 关键词")
            return

        def delete() -> int:
            with self._db() as db:
                cur = db.execute(
                    "DELETE FROM memories WHERE session=? AND content LIKE ?",
                    (event.unified_msg_origin, "%" + keyword + "%"),
                )
                return cur.rowcount

        count = await asyncio.to_thread(delete)
        yield event.plain_result(f"删除了 {count} 条记忆")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_memory_status")
    async def tf_memory_status(self, event: AstrMessageEvent) -> None:
        def count() -> int:
            with self._db() as db:
                row = db.execute(
                    "SELECT COUNT(*) FROM memories WHERE session=?",
                    (event.unified_msg_origin,),
                ).fetchone()
                return int(row[0] if row else 0)

        total = await asyncio.to_thread(count)
        yield event.plain_result(
            f"当前群记忆 {total} 条；最多保留 {MAX_ROWS} 条、{RETENTION_DAYS} 天"
        )
