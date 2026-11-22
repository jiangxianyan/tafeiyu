"""Local meme / slang dictionary adapted for tafeiyu.

The implementation is inspired by the MIT-licensed dsh-memewiki project. The
dictionary database is downloaded separately into the ignored runtime data
directory because its contents come from cnmeme.wiki and the upstream notice
does not claim copyright in that data.
"""

from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "astrbot" / "data" / "plugin_data" / "tafei_memewiki"
DB_PATH = DATA_DIR / "memes.db"
CONFIG_PATH = DATA_DIR / "config.json"

SOURCE_REPO = "https://github.com/thawline/dsh-memewiki"
DATABASE_URL = (
    "https://cdn.jsdelivr.net/gh/thawline/dsh-memewiki@main/data/memes.db"
)
MAX_DATABASE_BYTES = 32 * 1024 * 1024
DEFAULT_PERSONAS = ["tafei", "dafeiyu"]

_UPDATE_LOCK = threading.Lock()

QUESTION_RE = re.compile(
    r"(?:是)?(?:什么梗|啥梗|什么来头|什么来历|什么出处|什么意思|啥意思|"
    r"怎么用|怎么接|怎么玩|如何用)(?:啊|呀|呢|的|啊这是)?[？?。！!~～]*$"
)
BARE_WORD_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9·]{2,10}$")
TEACH_RE = re.compile(
    r"(?:这|那)(?:个)?(?:梗)?(?:其实|本来|就)?是\s*[「“\"'『]?"
    r"([^，,。！!？?：:；;\s「」“”\"'『』]{1,16})"
    r"[」”\"'』]?\s*的(?:梗|段子|说法|出处|来源)"
)
QUESTION_HEAD_RE = re.compile(r"^(?:谁|啥|什么|哪|哪个|哪位|咋|怎么|为什么|多少|几)")
SENTENCE_PART_RE = re.compile(
    r"怎么样|怎么|多少|为什么|能不能|是不是|什么|了吗|了没|一下|"
    r"你说|要不要|有没有"
)

EMPTY_WORDS = {
    "这",
    "那",
    "它",
    "他",
    "她",
    "这个",
    "那个",
    "你",
    "这句话",
    "那句话",
    "上面",
    "刚才",
    "下文",
    "前面",
}
STOP_WORDS = {
    "在吗",
    "在不在",
    "哈哈",
    "哈哈哈",
    "笑死",
    "好的",
    "好吧",
    "晚安",
    "早安",
    "睡觉",
    "吃饭",
    "干嘛",
    "没事",
    "收到",
    "谢谢",
    "好耶",
    "草",
    "典",
    "乐",
}
CHAT_PHRASES = {
    "我是谁",
    "错了",
    "情绪",
    "接下一句",
    "你也学一个",
    "今天看什么",
    "到底多少了",
    "搜出来了吗",
    "来点贴吧评价",
    "都是同龄人",
    "你同事",
    "道德这么高",
    "这是谁的手臂",
    "比我能串",
    "宝宝你醒了",
    "中国人能不能飞",
    "你现在什么人格",
}
WAKE_WORDS = [
    "小鲸鱼",
    "大鲸鱼",
    "大肥鲸",
    "小肥鲸",
    "大肥鱼",
    "奶鱼",
    "鲸鱼",
    "塔菲",
    "taffy",
    "deepseek",
    "ds",
]

MEME_RULES = (
    "[梗百科·内置用法]\n"
    "1. 查到词条就先按“怎么用/怎么接”自然接梗，不要照念百科；\n"
    "2. 只有对方明确问“这是什么梗”时，才用一两句解释出处；\n"
    "3. 查不到就说不知道，不要硬编或拼接不相干的梗；\n"
    "4. 保持当前人格的短句和语气，不要变成客服腔；\n"
    "5. 用户纠正梗的含义时，先接住，不要争辩。"
)


def _default_config() -> dict:
    return {
        "enabled": True,
        "enabled_personas": DEFAULT_PERSONAS,
        "auto_inject": True,
        "max_entry_chars": 1400,
    }


def get_config() -> dict:
    config = _default_config()
    try:
        with CONFIG_PATH.open(encoding="utf-8-sig") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            config.update(stored)
    except (OSError, ValueError):
        pass
    config["enabled"] = bool(config.get("enabled", True))
    config["auto_inject"] = bool(config.get("auto_inject", True))
    personas = config.get("enabled_personas", DEFAULT_PERSONAS)
    config["enabled_personas"] = [
        str(item) for item in personas if str(item).strip()
    ] if isinstance(personas, list) else list(DEFAULT_PERSONAS)
    try:
        config["max_entry_chars"] = max(
            400,
            min(4000, int(config.get("max_entry_chars", 1400))),
        )
    except (TypeError, ValueError):
        config["max_entry_chars"] = 1400
    return config


def _save_config(config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix="memewiki-config-",
        suffix=".tmp",
        dir=DATA_DIR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, CONFIG_PATH)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def is_enabled_for_persona(persona_id: str) -> bool:
    config = get_config()
    return (
        config["enabled"]
        and str(persona_id) in config.get("enabled_personas", [])
        and DB_PATH.is_file()
    )


def set_enabled_for_persona(persona_id: str, enabled: bool) -> dict:
    config = get_config()
    personas = set(config.get("enabled_personas", []))
    if enabled:
        personas.add(str(persona_id))
        config["enabled"] = True
    else:
        personas.discard(str(persona_id))
    config["enabled_personas"] = sorted(personas)
    _save_config(config)
    return config


def get_stats() -> dict:
    stats = {
        "available": DB_PATH.is_file(),
        "entries": 0,
        "built_at": "",
        "source": "cnmeme.wiki",
        "size": DB_PATH.stat().st_size if DB_PATH.is_file() else 0,
    }
    if not stats["available"]:
        return stats
    try:
        with closing(
            sqlite3.connect(
                f"file:{DB_PATH.as_posix()}?mode=ro",
                uri=True,
                timeout=3,
            )
        ) as db:
            stats["entries"] = int(
                db.execute("SELECT COUNT(*) FROM memes").fetchone()[0]
            )
            row = db.execute(
                "SELECT value FROM meta WHERE key='built_at'"
            ).fetchone()
            stats["built_at"] = str(row[0] if row else "")
            source = db.execute(
                "SELECT value FROM meta WHERE key='source'"
            ).fetchone()
            if source:
                stats["source"] = str(source[0])
    except sqlite3.Error:
        stats["available"] = False
    return stats


def _connect_readonly() -> sqlite3.Connection:
    db = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
        timeout=3,
    )
    db.row_factory = sqlite3.Row
    return db


def lookup(query: str) -> dict | None:
    query = str(query or "").strip()
    if not query or not DB_PATH.is_file():
        return None
    try:
        with closing(_connect_readonly()) as db:
            row = db.execute(
                "SELECT * FROM memes WHERE title = ? COLLATE NOCASE LIMIT 1",
                (query,),
            ).fetchone()
            if row:
                return dict(row)
            row = db.execute(
                """
                SELECT *
                FROM memes
                WHERE aliases IS NOT NULL
                  AND instr(',' || lower(aliases) || ',',
                            ',' || lower(?) || ',') > 0
                LIMIT 1
                """,
                (query,),
            ).fetchone()
            if row:
                return dict(row)
            row = db.execute(
                """
                SELECT *
                FROM memes
                WHERE lower(title) LIKE lower(?) || '%'
                ORDER BY length(title) ASC
                LIMIT 1
                """,
                (query,),
            ).fetchone()
            if row:
                return dict(row)
            row = db.execute(
                """
                SELECT *
                FROM memes
                WHERE length(title) >= 2 AND instr(?, title) > 0
                ORDER BY length(title) DESC
                LIMIT 1
                """,
                (query,),
            ).fetchone()
            if row:
                return dict(row)
            short_ascii = len(query) >= 2 and bool(
                re.fullmatch(r"[0-9A-Za-z]+", query)
            )
            if len(query) >= 3 or short_ascii:
                row = db.execute(
                    """
                    SELECT *
                    FROM memes
                    WHERE instr(title, ?) > 0
                    ORDER BY length(title) ASC
                    LIMIT 1
                    """,
                    (query,),
                ).fetchone()
                if row:
                    return dict(row)
    except sqlite3.Error:
        return None
    return None


def _clean_text(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^(@\S+\s*)+", "", value)
    lowered = value.lower()
    for wake_word in WAKE_WORDS:
        if lowered.startswith(wake_word.lower()):
            value = value[len(wake_word) :].strip()
            value = value.strip("，,。.！!？?:：")
            break
    return value.strip()


def extract_query(text: str) -> str | None:
    value = _clean_text(text)
    if not value:
        return None
    match = QUESTION_RE.search(value)
    if match:
        head = value[: match.start()].strip(" ，,。.！!？?")
        head = re.sub(r"^[是]+|[是]+$", "", head).strip()
        head = re.sub(r"(这个梗|那个梗|这梗|那梗|这个|那个)$", "", head).strip()
        head = re.sub(r"(到底|究竟)$", "", head).strip()
        if head in EMPTY_WORDS:
            return None
        if head and len(head) <= 2 and head[0] in "这那它他她":
            return None
        if 1 < len(head) <= 12:
            return head
        return None
    if (
        BARE_WORD_RE.fullmatch(value)
        and value not in STOP_WORDS
        and value not in CHAT_PHRASES
        and not SENTENCE_PART_RE.search(value)
    ):
        return value
    return None


def extract_teaching(text: str) -> str:
    value = _clean_text(text)
    match = TEACH_RE.search(value)
    if not match or QUESTION_HEAD_RE.search(match.group(1)):
        return ""
    return value


def _truncate(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def render_entry(row: dict, max_chars: int = 1400) -> str:
    title = str(row.get("title") or "")
    tags = _truncate(row.get("tags"), 120)
    usage = _truncate(row.get("usage"), 700)
    explanation = _truncate(row.get("summary") or row.get("origin"), 500)
    lines = [f"[梗百科]「{title}」"]
    if tags:
        lines.append(f"标签：{tags}")
    if usage:
        lines.append(f"怎么用 / 怎么接：\n{usage}")
    if explanation:
        lines.append(f"出处与含义：\n{explanation}")
    return "\n".join(lines)[:max_chars]


def build_context(row: dict, max_chars: int = 1400) -> str:
    return (
        f"\n\n{MEME_RULES}\n"
        "以下只注入当前消息命中的一条词条；不要把它当成对整个群的长期判断。\n"
        + render_entry(row, max_chars)
    )


def find_for_message(text: str) -> tuple[str, dict, str] | None:
    query = extract_query(text)
    if not query:
        return None
    row = lookup(query)
    if not row:
        return None
    config = get_config()
    return query, row, build_context(row, config["max_entry_chars"])


def update_database(timeout: int = 180) -> dict:
    """Download and atomically replace the local dictionary."""
    if not _UPDATE_LOCK.acquire(blocking=False):
        raise RuntimeError("词库正在更新，请稍后再试")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = DATA_DIR / "memes.db.download"
    try:
        request = urllib.request.Request(
            DATABASE_URL,
            headers={"User-Agent": "tafeiyu-memewiki/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > MAX_DATABASE_BYTES:
                raise RuntimeError("词库文件超过 32 MB，已拒绝下载")
            with temp_path.open("wb") as handle:
                total = 0
                while True:
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DATABASE_BYTES:
                        raise RuntimeError("词库文件超过 32 MB，已中止下载")
                    handle.write(chunk)
        with temp_path.open("rb") as handle:
            if handle.read(15) != b"SQLite format 3":
                raise RuntimeError("下载内容不是有效的 SQLite 词库")
        with closing(
            sqlite3.connect(
                f"file:{temp_path.as_posix()}?mode=ro",
                uri=True,
                timeout=5,
            )
        ) as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"词库完整性检查失败：{integrity}")
            count = int(db.execute("SELECT COUNT(*) FROM memes").fetchone()[0])
            if count < 100:
                raise RuntimeError("下载词库条目数量异常")
        backup = DATA_DIR / "memes.db.bak"
        try:
            if DB_PATH.is_file():
                if backup.is_file():
                    backup.unlink()
                os.replace(DB_PATH, backup)
            os.replace(temp_path, DB_PATH)
        except Exception:
            if not DB_PATH.exists() and backup.is_file():
                os.replace(backup, DB_PATH)
            raise
        return {
            "entries": count,
            "size": DB_PATH.stat().st_size,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        _UPDATE_LOCK.release()
