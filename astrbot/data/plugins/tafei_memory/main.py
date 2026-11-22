import asyncio
import json
import hashlib
import io
import os
import re
import sqlite3
import time
import math
from contextlib import contextmanager

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command import GreedyStr

PLUGIN_NAME = "tafei_memory"
RECALL_LIMIT = 4
RECALL_CHARS = 700
RETENTION_DAYS = 365
MAX_ROWS = 20000
MIN_TEXT_CHARS = 6
SUMMARY_TRIGGER_ROWS = 40
SUMMARY_BATCH_ROWS = 30
SUMMARY_MAX_CHARS = 1400
PERSONA_PREFIX = "persona:"
HOT_DAYS = 14
HOT_THRESHOLD = 0.85
MAX_HEAT = 5.0
SHORT_CUE_STOP_WORDS = {
    "今天",
    "现在",
    "这个",
    "那个",
    "什么",
    "怎么",
    "哈哈",
    "可以",
    "没有",
    "就是",
    "真的",
    "感觉",
    "一个",
    "我们",
    "你们",
    "他们",
    "然后",
    "所以",
    "但是",
    "因为",
    "已经",
    "还是",
}


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


def _short_cue(text: str) -> str:
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", text or "")
    if (
        len(compact) == 2
        and re.fullmatch(r"[\u4e00-\u9fff]{2}", compact)
        and compact not in SHORT_CUE_STOP_WORDS
    ):
        return compact
    return ""


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(_data_dir()))


def _persona_from_session(session: str) -> str:
    if session.startswith(PERSONA_PREFIX) and "|" in session:
        return session[len(PERSONA_PREFIX) :].split("|", 1)[0] or "tafei"
    return "tafei"


def _effective_heat(
    stored_heat: float,
    last_accessed: float,
    created_at: float,
    *,
    now: float | None = None,
) -> float:
    now = now or time.time()
    anchor = max(float(last_accessed or 0), float(created_at or 0), 0)
    age_days = max(0.0, (now - anchor) / 86400) if anchor else 365.0
    # Heat decays over roughly 30 days without a useful recall.
    decayed = max(0.0, float(stored_heat or 0)) * math.exp(-age_days / 30)
    return min(MAX_HEAT, decayed)


def _memory_layer(
    pinned: int,
    effective_heat: float,
    last_accessed: float,
    *,
    now: float | None = None,
) -> str:
    now = now or time.time()
    if pinned:
        return "fixed"
    if float(last_accessed or 0) and now - float(last_accessed) <= HOT_DAYS * 86400:
        return "hot"
    return "hot" if effective_heat >= HOT_THRESHOLD else "cold"


def _active_persona() -> tuple[str, str]:
    catalog_path = os.path.join(_project_root(), "config", "personas.json")
    try:
        with io.open(catalog_path, encoding="utf-8-sig") as handle:
            catalog = json.load(handle)
        persona_id = str(catalog.get("active") or "tafei")
        persona = next(
            (
                item
                for item in catalog.get("personas", [])
                if str(item.get("id")) == persona_id
            ),
            {},
        )
        return persona_id, str(persona.get("display_name") or persona_id)
    except (OSError, ValueError):
        return "tafei", "塔菲"


class TafeiMemory(star.Star):
    """Group-scoped, local, trigram-indexed conversation recall."""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.cfg_dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.db_path = os.path.join(self.cfg_dir, "memory.db")
        self._inserts = 0
        self._summary_tasks: dict[str, asyncio.Task] = {}
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
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_summaries(
                    session TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    last_rowid INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_state(
                    memory_rowid INTEGER PRIMARY KEY,
                    persona_id TEXT NOT NULL,
                    heat REAL NOT NULL DEFAULT 1.0,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    last_accessed REAL NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS memory_state_persona_layer_idx
                ON memory_state(persona_id, pinned, heat, last_accessed)
                """
            )
            migrated = db.execute(
                "SELECT value FROM memory_meta WHERE key='persona_scope_v1'"
            ).fetchone()
            if not migrated:
                # Existing rows predate multi-persona support and belong to Tafei.
                db.execute(
                    """
                    UPDATE memories
                    SET session=? || session
                    WHERE session NOT LIKE 'persona:%'
                    """,
                    (PERSONA_PREFIX + "tafei|",),
                )
                db.execute(
                    """
                    UPDATE memory_summaries
                    SET session=? || session
                    WHERE session NOT LIKE 'persona:%'
                    """,
                    (PERSONA_PREFIX + "tafei|",),
                )
                db.execute(
                    """
                    INSERT INTO memory_meta(key, value)
                    VALUES ('persona_scope_v1', 'tafei')
                    """
                )
            self._backfill_memory_state(db)

    def _backfill_memory_state(self, db: sqlite3.Connection) -> None:
        rows = db.execute(
            """
            SELECT rowid, session, priority, created_at
            FROM memories
            WHERE rowid NOT IN (
                SELECT memory_rowid FROM memory_state
            )
            """
        ).fetchall()
        now = time.time()
        for rowid, session, priority, created_at in rows:
            priority = int(priority or 0)
            created_at = float(created_at or now)
            age_days = max(0.0, (now - created_at) / 86400)
            heat = min(MAX_HEAT, 1.35 + priority * 0.25) * math.exp(
                -age_days / 45
            )
            if age_days <= HOT_DAYS:
                heat = max(heat, HOT_THRESHOLD + 0.1)
            db.execute(
                """
                INSERT INTO memory_state(
                    memory_rowid, persona_id, heat, access_count,
                    last_accessed, pinned, updated_at
                ) VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    int(rowid),
                    _persona_from_session(str(session or "")),
                    heat,
                    created_at,
                    1 if priority >= 8 else 0,
                    now,
                ),
            )

    @staticmethod
    def _scoped_session(session: str) -> str:
        persona_id, _ = _active_persona()
        prefix = f"{PERSONA_PREFIX}{persona_id}|"
        if session.startswith(prefix):
            return session
        return prefix + session

    def _event_session(self, event: AstrMessageEvent) -> str:
        return self._scoped_session(event.unified_msg_origin)

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
            memory_rowid = db.execute(
                """
                SELECT rowid FROM memories
                WHERE session=? AND fingerprint=?
                LIMIT 1
                """,
                (session, fingerprint),
            ).fetchone()[0]
            initial_heat = min(MAX_HEAT, 1.35 + int(priority or 0) * 0.25)
            db.execute(
                """
                INSERT OR REPLACE INTO memory_state(
                    memory_rowid, persona_id, heat, access_count,
                    last_accessed, pinned, updated_at
                ) VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    int(memory_rowid),
                    _persona_from_session(session),
                    initial_heat,
                    now,
                    1 if int(priority or 0) >= 8 else 0,
                    now,
                ),
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
                db.execute(
                    """
                    DELETE FROM memory_state
                    WHERE memory_rowid NOT IN (
                        SELECT rowid FROM memories
                    )
                    """
                )
        return True

    def _get_summary_state(self, session: str) -> tuple[str, int]:
        with self._db() as db:
            row = db.execute(
                "SELECT summary, last_rowid FROM memory_summaries WHERE session=?",
                (session,),
            ).fetchone()
        return (row[0], int(row[1])) if row else ("", 0)

    def _get_summary_batch(self, session: str) -> tuple[list[tuple], int]:
        _, last_rowid = self._get_summary_state(session)
        with self._db() as db:
            pending = db.execute(
                "SELECT COUNT(*) FROM memories WHERE session=? AND rowid>?",
                (session, last_rowid),
            ).fetchone()[0]
            if pending < SUMMARY_TRIGGER_ROWS:
                return [], pending
            rows = db.execute(
                """
                SELECT rowid, sender, created_at, content
                FROM memories
                WHERE session=? AND rowid>?
                ORDER BY rowid ASC
                LIMIT ?
                """,
                (session, last_rowid, SUMMARY_BATCH_ROWS),
            ).fetchall()
        return rows, pending

    def _save_summary(self, session: str, summary: str, last_rowid: int) -> None:
        with self._db() as db:
            db.execute(
                """
                INSERT INTO memory_summaries(session, summary, last_rowid, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session) DO UPDATE SET
                    summary=excluded.summary,
                    last_rowid=excluded.last_rowid,
                    updated_at=excluded.updated_at
                """,
                (session, summary, last_rowid, time.time()),
            )

    async def _summarize_group(self, session: str) -> None:
        try:
            rows, pending = await asyncio.to_thread(self._get_summary_batch, session)
            if not rows:
                return
            old_summary, _ = await asyncio.to_thread(self._get_summary_state, session)
            provider = await self.context.get_using_provider_async(umo=session)
            if provider is None:
                return
            history_lines = []
            for rowid, sender, created_at, content in rows:
                stamp = time.strftime("%m-%d %H:%M", time.localtime(created_at))
                history_lines.append(
                    f"[{stamp}] {sender or '群友'}: {_clean_text(content)[:240]}"
                )
            prompt = (
                "请把旧摘要和新增群聊历史合并成一份便于继续聊天的摘要。\n"
                "保留：未解决问题、重要事件、群友偏好、当前人格的承诺、当前话题走向。\n"
                "去掉：重复复读、无意义表情、已经结束的临时闲聊。\n"
                "不要虚构事实，按发言者区分群友，使用中文，控制在1200字以内。\n\n"
                f"旧摘要：\n{old_summary or '无'}\n\n"
                "新增历史：\n" + "\n".join(history_lines)
            )
            response = await provider.text_chat(
                prompt=prompt,
                contexts=[],
                system_prompt=(
                    "你负责压缩多人群聊记忆。只输出摘要正文，不要解释压缩过程。"
                ),
                request_max_retries=1,
            )
            summary = _clean_text(response.completion_text or "")[:SUMMARY_MAX_CHARS]
            if not summary:
                return
            last_rowid = int(rows[-1][0])
            await asyncio.to_thread(
                self._save_summary, session, summary, last_rowid
            )
            logger.info(
                f"tafei_memory: summarized {len(rows)} rows, "
                f"pending_before={pending}, chars={len(summary)}"
            )
        except Exception as exc:
            logger.warning(f"tafei_memory: 摘要压缩失败 {exc}")
        finally:
            self._summary_tasks.pop(session, None)

    def _schedule_summary(self, session: str) -> None:
        task = self._summary_tasks.get(session)
        if task and not task.done():
            return
        self._summary_tasks[session] = asyncio.create_task(
            self._summarize_group(session)
        )

    def _recall(
        self, session: str, query: str, exclude_fingerprint: str
    ) -> list[tuple]:
        terms = _trigrams(query)
        short_cue = _short_cue(query)
        if not terms and not short_cue:
            return []
        cutoff = time.time() - RETENTION_DAYS * 86400
        with self._db() as db:
            select_sql = """
                SELECT
                    memories.rowid,
                    content,
                    sender,
                    created_at,
                    priority,
                    COALESCE(memory_state.heat, 1.0),
                    COALESCE(memory_state.last_accessed, created_at),
                    COALESCE(memory_state.access_count, 0),
                    COALESCE(memory_state.pinned, 0)
                FROM memories
                LEFT JOIN memory_state
                  ON memory_state.memory_rowid = memories.rowid
                WHERE memories.session=?
                  AND memories.created_at>=?
                  AND memories.fingerprint<>?
            """
            order_sql = """
                ORDER BY
                    COALESCE(memory_state.pinned, 0) DESC,
                    COALESCE(memory_state.heat, 1.0) DESC,
                    priority DESC,
                    created_at DESC
                LIMIT ?
            """
            rows = []
            if terms:
                rows = db.execute(
                    select_sql
                    + " AND memories MATCH ? "
                    + order_sql,
                    (
                        session,
                        cutoff,
                        exclude_fingerprint,
                        terms,
                        RECALL_LIMIT,
                    ),
                ).fetchall()
            if not rows and short_cue:
                rows = db.execute(
                    select_sql
                    + " AND memories.content LIKE ? "
                    + order_sql,
                    (
                        session,
                        cutoff,
                        exclude_fingerprint,
                        "%" + short_cue + "%",
                        RECALL_LIMIT,
                    ),
                ).fetchall()
            touched = [int(row[0]) for row in rows]
            now = time.time()
            for memory_rowid in touched:
                db.execute(
                    """
                    UPDATE memory_state
                    SET heat=MIN(?, heat + 0.45),
                        access_count=access_count + 1,
                        last_accessed=?,
                        updated_at=?
                    WHERE memory_rowid=?
                    """,
                    (MAX_HEAT, now, now, memory_rowid),
                )
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
            session = self._event_session(event)
            stored = await asyncio.to_thread(
                self._store,
                session,
                event.get_sender_name() or event.get_sender_id(),
                text,
                priority,
            )
            if stored:
                self._schedule_summary(session)
        except Exception as exc:
            logger.warning(f"tafei_memory: 写入失败 {exc}")

    @filter.on_llm_request()
    async def inject_memories(self, event: AstrMessageEvent, req) -> None:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return
        current = (getattr(req, "prompt", "") or "") + (req.system_prompt or "")
        text = _clean_text(event.message_str)
        if len(text) < 4:
            return
        session = self._event_session(event)
        fingerprint = _fingerprint(session, text[:600])
        summary = ""
        try:
            summary, _ = await asyncio.to_thread(self._get_summary_state, session)
        except Exception as exc:
            logger.warning(f"tafei_memory: 读取滚动摘要失败 {exc}")
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
            rows = []

        lines = []
        used = 0
        recalled_layers = []
        for (
            _rowid,
            content,
            sender,
            created_at,
            _priority,
            stored_heat,
            last_accessed,
            access_count,
            pinned,
        ) in rows:
            age_days = max(0, int((time.time() - float(created_at)) / 86400))
            heat = _effective_heat(
                float(stored_heat or 0),
                float(last_accessed or 0),
                float(created_at or 0),
            )
            layer = _memory_layer(
                int(pinned or 0),
                heat,
                float(last_accessed or 0),
            )
            layer_label = {
                "fixed": "固定事实",
                "hot": "热记忆",
                "cold": "冷记忆",
            }.get(layer, "记忆")
            recalled_layers.append(layer)
            line = (
                f"- [{layer_label}；热度 {heat:.2f}；"
                f"已召回 {int(access_count or 0)} 次] "
                f"{sender}（{age_days}天前）：{content}"
            )
            if used + len(line) > RECALL_CHARS:
                break
            lines.append(line)
            used += len(line)
        if not lines:
            lines = []
        block = ""
        if summary and "【群聊滚动摘要·仅当前会话】" not in current:
            block += (
                "\n\n【群聊滚动摘要·仅当前会话】\n"
                "以下内容来自同一群聊的较早历史，用于理解关系和延续话题；"
                "不要逐字复述，也不要跨群。\n"
                + summary
            )
        if lines and "【群聊长期记忆·仅当前会话】" not in current:
            block += (
                "\n\n【群聊长期记忆·仅当前会话】\n"
                "以下是同一群聊中的相关历史片段，只用于理解关系和延续话题；"
                "冷记忆只有在当前消息提供了相关线索时才会出现。"
                "不要逐字复述，不要跨群，也不要把它当成绝对事实。\n"
                + "\n".join(lines)
            )
        if not block:
            return
        req.system_prompt = (req.system_prompt or "") + block
        logger.info(
            f"tafei_memory: recalled={len(lines)} chars={len(block)} "
            f"layers={','.join(recalled_layers)}"
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
            self._event_session(event),
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
                rowids = [
                    int(row[0])
                    for row in db.execute(
                        """
                        SELECT rowid FROM memories
                        WHERE session=? AND content LIKE ?
                        """,
                        (
                            self._event_session(event),
                            "%" + keyword + "%",
                        ),
                    ).fetchall()
                ]
                cur = db.execute(
                    "DELETE FROM memories WHERE session=? AND content LIKE ?",
                    (self._event_session(event), "%" + keyword + "%"),
                )
                for memory_rowid in rowids:
                    db.execute(
                        "DELETE FROM memory_state WHERE memory_rowid=?",
                        (memory_rowid,),
                    )
                return cur.rowcount

        count = await asyncio.to_thread(delete)
        yield event.plain_result(f"删除了 {count} 条记忆")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_memory_status")
    async def tf_memory_status(self, event: AstrMessageEvent) -> None:
        def count() -> tuple[int, int, int, int]:
            with self._db() as db:
                rows = db.execute(
                    """
                    SELECT
                        COALESCE(memory_state.pinned, 0),
                        COALESCE(memory_state.heat, 1.0),
                        COALESCE(memory_state.last_accessed, memories.created_at),
                        memories.created_at
                    FROM memories
                    LEFT JOIN memory_state
                      ON memory_state.memory_rowid = memories.rowid
                    WHERE memories.session=?
                    """,
                    (self._event_session(event),),
                ).fetchall()
            layers = {"fixed": 0, "hot": 0, "cold": 0}
            for pinned, heat, last_accessed, created_at in rows:
                effective = _effective_heat(
                    float(heat or 0),
                    float(last_accessed or 0),
                    float(created_at or 0),
                )
                layer = _memory_layer(
                    int(pinned or 0),
                    effective,
                    float(last_accessed or 0),
                )
                layers[layer] = layers.get(layer, 0) + 1
            return len(rows), layers["hot"], layers["cold"], layers["fixed"]

        total, hot, cold, fixed = await asyncio.to_thread(count)
        _, persona_name = _active_persona()
        yield event.plain_result(
            f"{persona_name}在当前群的记忆 {total} 条："
            f"固定 {fixed}、热 {hot}、冷 {cold}；"
            f"最多保留 {MAX_ROWS} 条、{RETENTION_DAYS} 天"
        )
