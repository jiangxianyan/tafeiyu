"""Built-in persona memory and habit star map for tafeiyu."""

from __future__ import annotations

import json
import math
import random
import sqlite3
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent.parent
PERSONA_INDEX = ROOT / "config" / "personas.json"
MEMORY_DB = ROOT / "astrbot" / "data" / "plugin_data" / "tafei_memory" / "memory.db"

BG = "#16111c"
CARD = "#221b2a"
CARD_2 = "#2a2132"
INK = "#f8eef9"
MUTED = "#bbaec1"
LINE = "#44384e"
PINK = "#e978a4"
BLUE = "#69a8e8"
GOLD = "#d9a35f"
GREEN = "#61c49b"
HOT_DAYS = 14
HOT_THRESHOLD = 0.85
MAX_HEAT = 5.0


def _load_json(path: Path, default):
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def persona_catalog() -> list[dict]:
    data = _load_json(PERSONA_INDEX, {})
    personas = data.get("personas", []) if isinstance(data, dict) else []
    result = []
    for item in personas:
        if not isinstance(item, dict):
            continue
        persona_file = ROOT / str(item.get("persona_file") or "")
        if not persona_file.is_file():
            continue
        result.append(
            {
                **item,
                "id": str(item.get("id") or persona_file.stem),
                "display_name": str(item.get("display_name") or persona_file.stem),
                "persona_path": persona_file,
                "style_path": (
                    ROOT / str(item.get("style_file"))
                    if str(item.get("style_file") or "").strip()
                    else None
                ),
            }
        )
    if not result:
        result.append(
            {
                "id": "tafei",
                "display_name": "塔菲",
                "aliases": ["taffy"],
                "persona_path": ROOT / "astrbot" / "data" / "personas" / "tafei.md",
                "style_path": ROOT
                / "astrbot"
                / "data"
                / "plugin_data"
                / "tafei_persona"
                / "style.txt",
                "accent": PINK,
            }
        )
    return result


def active_persona_id() -> str:
    data = _load_json(PERSONA_INDEX, {})
    active = str(data.get("active") or "tafei") if isinstance(data, dict) else "tafei"
    valid = {persona["id"] for persona in persona_catalog()}
    return active if active in valid else next(iter(valid))


def _read_lines(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    try:
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []


def _persona_habits(persona: dict) -> list[dict]:
    style = _read_lines(persona.get("style_path"))
    if not style:
        keywords = (
            "默认",
            "短句",
            "不要",
            "不写",
            "傲娇",
            "称呼",
            "记住",
            "群聊",
            "说话",
            "风格",
            "一句",
        )
        style = [
            line.lstrip("- ").strip()
            for line in _read_lines(persona.get("persona_path"))
            if line.lstrip().startswith("- ")
            and any(keyword in line for keyword in keywords)
        ]
    habits = []
    for index, text in enumerate(style[:14], 1):
        habits.append(
            {
                "id": f"habit-{index}",
                "kind": "habit",
                "title": text[:32],
                "text": text,
                "source": "人格说话规则",
                "created": "",
                "priority": 2,
            }
        )
    return habits


def _effective_heat(
    stored_heat: float,
    last_accessed: float,
    created_at: float,
) -> float:
    now = time.time()
    anchor = max(float(last_accessed or 0), float(created_at or 0), 0)
    age_days = max(0.0, (now - anchor) / 86400) if anchor else 365.0
    return min(
        MAX_HEAT,
        max(0.0, float(stored_heat or 0)) * math.exp(-age_days / 30),
    )


def _memory_layer(
    pinned: int,
    effective_heat: float,
    last_accessed: float,
) -> str:
    if pinned:
        return "fixed"
    if float(last_accessed or 0) and (
        time.time() - float(last_accessed) <= HOT_DAYS * 86400
    ):
        return "hot"
    return "hot" if effective_heat >= HOT_THRESHOLD else "cold"


def _memory_nodes(persona_id: str, limit: int = 120) -> list[dict]:
    if not MEMORY_DB.is_file():
        return []
    prefix = f"persona:{persona_id}|"
    if persona_id == "tafei":
        where = "(instr(session, ?) = 1 OR instr(session, 'persona:') <> 1)"
        params = (prefix, limit)
    else:
        where = "instr(session, ?) = 1"
        params = (prefix, limit)
    try:
        db = sqlite3.connect(MEMORY_DB)
        db.row_factory = sqlite3.Row
        rows = db.execute(
            f"""
            SELECT
                memories.rowid,
                memories.content,
                memories.session,
                memories.sender,
                memories.created_at,
                memories.priority,
                COALESCE(memory_state.heat, 1.0) AS heat,
                COALESCE(memory_state.last_accessed, memories.created_at)
                    AS last_accessed,
                COALESCE(memory_state.access_count, 0) AS access_count,
                COALESCE(memory_state.pinned, 0) AS pinned
            FROM memories
            LEFT JOIN memory_state
              ON memory_state.memory_rowid = memories.rowid
            WHERE {where}
            ORDER BY priority DESC, created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        db.close()
    except sqlite3.Error:
        return []

    nodes = []
    for row in rows:
        content = str(row["content"] or "").strip()
        if not content:
            continue
        priority = int(row["priority"] or 0)
        heat = _effective_heat(
            float(row["heat"] or 0),
            float(row["last_accessed"] or 0),
            float(row["created_at"] or 0),
        )
        layer = _memory_layer(
            int(row["pinned"] or 0),
            heat,
            float(row["last_accessed"] or 0),
        )
        relation_words = ("喜欢", "讨厌", "主人", "朋友", "关系", "称呼")
        topic_words = ("游戏", "语音", "模型", "代码", "音乐", "群", "直播")
        if priority > 0 or any(word in content for word in relation_words):
            kind = "relation"
        elif any(word in content for word in topic_words):
            kind = "topic"
        else:
            kind = "memory"
        created = time.strftime(
            "%m-%d %H:%M", time.localtime(float(row["created_at"] or 0))
        )
        session = str(row["session"] or "")
        if session.startswith("persona:") and "|" in session:
            session = session.split("|", 1)[1]
        session_label = session.rsplit(":", 1)[-1] if ":" in session else session
        nodes.append(
            {
                "id": f"memory-{row['rowid']}",
                "kind": kind,
                "title": content[:26],
                "text": content,
                "source": f"{row['sender'] or '群友'} · 会话 {session_label}",
                "created": created,
                "ts": float(row["created_at"] or 0),
                "session_id": session,
                "priority": priority,
                "heat": heat,
                "last_accessed": float(row["last_accessed"] or 0),
                "access_count": int(row["access_count"] or 0),
                "pinned": bool(row["pinned"]),
                "layer": layer,
            }
        )
    return nodes


def load_star_map(persona: dict) -> dict:
    habits = _persona_habits(persona)
    memories = _memory_nodes(persona["id"])
    core = {
        "id": f"core-{persona['id']}",
        "kind": "core",
        "title": persona["display_name"],
        "text": "当前人格核心。星图中的习惯与记忆仅属于这个角色。",
        "source": "人格卡",
        "created": "",
        "priority": 3,
        "items": [],
    }
    groups = []
    if habits:
        groups.append(
            {
                "id": "group-habit",
                "kind": "habit",
                "title": "说话习惯",
                "text": f"当前人格共有 {len(habits)} 条表达与互动习惯。",
                "source": "人格说话规则",
                "created": "持续有效",
                "priority": min(3, len(habits) // 5 + 1),
                "items": habits,
            }
        )
    for kind, title, source in (
        ("relation", "关系记忆", "群聊长期记忆"),
        ("topic", "话题偏好", "群聊话题记忆"),
        ("memory", "会话记忆", "群聊对话记忆"),
    ):
        items = [node for node in memories if node["kind"] == kind]
        if not items:
            continue
        groups.append(
            {
                "id": f"group-{kind}",
                "kind": kind,
                "title": title,
                "text": f"共有 {len(items)} 条与“{title}”相关的本地记忆。",
                "source": source,
                "created": max(
                    (node.get("created") or "" for node in items),
                    default="",
                ),
                "priority": min(3, len(items) // 6 + 1),
                "items": items,
            }
        )
    return {
        "persona": persona,
        "nodes": [core, *groups],
        "habit_count": len(habits),
        "memory_count": len(memories),
    }


class MemoryStarMap(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("塔菲鱼 · 记忆星图")
        self.geometry("1120x760")
        self.minsize(860, 620)
        self.configure(bg=BG)
        self.personas = persona_catalog()
        names = [self._persona_label(item) for item in self.personas]
        active_id = active_persona_id()
        active_index = next(
            (index for index, item in enumerate(self.personas) if item["id"] == active_id),
            0,
        )
        self.persona_var = tk.StringVar(value=names[active_index])
        self.current_data: dict = {}
        self.node_items: dict[int, dict] = {}
        self.selected: dict | None = None
        self._stars: list[tuple[float, float, float]] = []
        self._build_ui()
        self._load()

    @staticmethod
    def _persona_label(persona: dict) -> str:
        aliases = [str(item) for item in persona.get("aliases", []) if item]
        suffix = f" · {' / '.join(aliases[:2])}" if aliases else ""
        return f"{persona['display_name']}{suffix}"

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Map.TCombobox", fieldbackground=CARD_2, foreground=INK)

        header = tk.Frame(self, bg="#211727", height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="记忆星图",
            bg="#211727",
            fg=INK,
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(side="left", padx=24)
        tk.Label(
            header,
            text="按人格查看记忆、习惯、关系与话题",
            bg="#211727",
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(0, 22))
        self.persona_combo = ttk.Combobox(
            header,
            textvariable=self.persona_var,
            values=[self._persona_label(item) for item in self.personas],
            state="readonly",
            style="Map.TCombobox",
            width=24,
        )
        self.persona_combo.pack(side="right", padx=14)
        self.persona_combo.bind("<<ComboboxSelected>>", self._persona_changed)
        ttk.Button(header, text="刷新", command=self._load).pack(side="right")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=16)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0)
        body.grid_rowconfigure(0, weight=1)

        map_frame = tk.Frame(body, bg="#0d0a13", highlightthickness=1, highlightbackground=LINE)
        map_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.canvas = tk.Canvas(
            map_frame,
            bg="#0d0a13",
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._canvas_resized)

        detail = tk.Frame(body, bg=CARD, width=310)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.grid_propagate(False)
        self.detail_title = tk.Label(
            detail,
            text="选择一个星点",
            bg=CARD,
            fg=INK,
            wraplength=245,
            justify="left",
            anchor="w",
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        self.detail_title.pack(fill="x", padx=18, pady=(20, 8))
        self.detail_kind = tk.Label(
            detail,
            text="",
            bg=CARD,
            fg=PINK,
            anchor="w",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.detail_kind.pack(fill="x", padx=18)
        self.detail_text = tk.Text(
            detail,
            height=9,
            bg=CARD,
            fg=MUTED,
            relief="flat",
            wrap="word",
            font=("Microsoft YaHei UI", 10),
            padx=18,
            pady=12,
        )
        self.detail_text.pack(fill="both", expand=True, padx=0, pady=(4, 0))
        self.detail_text.configure(state="disabled")
        self.stats = tk.Label(
            detail,
            text="",
            bg=CARD,
            fg=MUTED,
            anchor="w",
            justify="left",
            font=("Microsoft YaHei UI", 9),
        )
        self.stats.pack(fill="x", padx=18, pady=(0, 18))

        legend = tk.Frame(self, bg=BG)
        legend.pack(fill="x", padx=24, pady=(0, 14))
        for color, label in (
            (PINK, "人格核心"),
            (GOLD, "习惯"),
            (BLUE, "关系"),
            (GREEN, "记忆 / 话题"),
        ):
            dot = tk.Canvas(legend, width=12, height=12, bg=BG, highlightthickness=0)
            dot.create_oval(2, 2, 10, 10, fill=color, outline="")
            dot.pack(side="left", padx=(0, 5))
            tk.Label(
                legend,
                text=label,
                bg=BG,
                fg=MUTED,
                font=("Microsoft YaHei UI", 9),
            ).pack(side="left", padx=(0, 16))

    def _selected_persona(self) -> dict:
        label = self.persona_var.get()
        return next(
            (
                item
                for item in self.personas
                if self._persona_label(item) == label
            ),
            self.personas[0],
        )

    def _persona_changed(self, _event=None) -> None:
        self._load()

    def _load(self) -> None:
        persona = self._selected_persona()
        self.current_data = load_star_map(persona)
        self.selected = None
        self.stats.configure(
            text=(
                f"人格：{persona['display_name']}\n"
                f"记忆：{self.current_data['memory_count']} 条\n"
                f"习惯：{self.current_data['habit_count']} 条"
            )
        )
        self._detail(
            {
                "title": persona["display_name"],
                "kind": "人格核心",
                "text": "点击任一星点查看来源和关联信息。",
                "source": "人格卡",
                "created": "",
                "priority": 0,
            }
        )
        self._draw()

    def _canvas_resized(self, _event=None) -> None:
        self._draw()

    def _build_stars(self, width: int, height: int, seed: int) -> None:
        rng = random.Random(seed)
        self._stars = [
            (
                rng.random() * width,
                rng.random() * height,
                rng.choice((0.35, 0.5, 0.7, 1.0)),
            )
            for _ in range(max(60, width * height // 9000))
        ]

    def _draw(self) -> None:
        if not self.current_data or not self.canvas.winfo_exists():
            return
        width = max(self.canvas.winfo_width(), 480)
        height = max(self.canvas.winfo_height(), 420)
        self.canvas.delete("all")
        self.node_items.clear()
        seed = sum(ord(char) for char in self.current_data["persona"]["id"])
        self._build_stars(width, height, seed)
        for x, y, alpha in self._stars:
            shade = int(150 + 90 * alpha)
            self.canvas.create_oval(
                x - alpha,
                y - alpha,
                x + alpha,
                y + alpha,
                fill=f"#{shade:02x}{shade:02x}{shade:02x}",
                outline="",
            )

        core_x, core_y = width * 0.5, height * 0.5
        groups = [
            node
            for node in self.current_data["nodes"]
            if node["kind"] != "core"
        ]
        positions: dict[str, tuple[float, float]] = {}
        for index, node in enumerate(groups):
            angle = -1.5708 + (index * 2 * 3.14159 / max(len(groups), 1))
            x = core_x + 190 * (0.82 if width > 650 else 0.58) * math.cos(angle)
            y = core_y + 150 * (0.82 if height > 500 else 0.58) * math.sin(angle)
            positions[node["id"]] = (x, y)

        for node in groups:
            x, y = positions[node["id"]]
            self.canvas.create_line(
                core_x,
                core_y,
                x,
                y,
                fill="#6b4d62" if node["kind"] == "habit" else "#365d70",
                width=1,
            )

        core = next(node for node in self.current_data["nodes"] if node["kind"] == "core")
        self._draw_node(core, core_x, core_y, 38)
        for node in groups:
            x, y = positions[node["id"]]
            radius = 22 + min(11, len(node.get("items", [])) // 3)
            self._draw_node(node, x, y, radius)

        if self.selected:
            self._detail(self.selected)

    def _draw_node(self, node: dict, x: float, y: float, radius: int) -> None:
        color = {
            "core": PINK,
            "habit": GOLD,
            "relation": BLUE,
            "memory": GREEN,
            "topic": "#75c1c1",
        }.get(node["kind"], GREEN)
        outline = "#ffffff" if node is self.selected else color
        item = self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=color,
            outline=outline,
            width=2,
            tags=("memory-node", f"node-{node['id']}"),
        )
        label = node["title"]
        if len(label) > 11:
            label = label[:10] + "…"
        text = self.canvas.create_text(
            x,
            y + radius + 11,
            text=label,
            fill="#f5ebf7",
            font=("Microsoft YaHei UI", 9),
            width=max(75, radius * 5),
            justify="center",
            tags=("memory-node", f"node-{node['id']}"),
        )
        self.node_items[item] = node
        self.node_items[text] = node
        self.canvas.tag_bind(
            f"node-{node['id']}",
            "<Button-1>",
            lambda _event, data=node: self._select_node(data),
        )

    def _select_node(self, node: dict) -> None:
        self.selected = node
        self._detail(node)
        self._draw()

    def _detail(self, node: dict) -> None:
        kind_labels = {
            "core": "人格核心",
            "habit": "说话习惯",
            "relation": "长期记忆 / 关系",
            "memory": "对话记忆",
            "topic": "话题与偏好",
        }
        self.detail_title.configure(text=node.get("title") or "未命名记忆")
        self.detail_kind.configure(
            text=kind_labels.get(node.get("kind"), "记忆节点")
        )
        text = (
            f"{node.get('text') or ''}\n\n"
            f"来源：{node.get('source') or '未知'}\n"
            f"记录时间：{node.get('created') or '未记录'}\n"
            f"重要度：{node.get('priority') or 0}"
        )
        items = node.get("items") or []
        if items:
            text += "\n\n具体条目：\n" + "\n".join(
                f"• {(item.get('title') or item.get('text') or '').strip()}"
                for item in items[:20]
            )
            if len(items) > 20:
                text += f"\n…另有 {len(items) - 20} 条"
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text.strip())
        self.detail_text.configure(state="disabled")


def open_memory_map(parent: tk.Misc) -> MemoryStarMap:
    existing = next(
        (
            child
            for child in parent.winfo_children()
            if isinstance(child, MemoryStarMap) and child.winfo_exists()
        ),
        None,
    )
    if existing:
        existing.lift()
        existing.focus_force()
        return existing
    window = MemoryStarMap(parent)
    window.focus_force()
    return window
