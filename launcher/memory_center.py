"""Embedded, card-first memory dashboard for the desktop client."""

from __future__ import annotations

import math
import sqlite3
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from persona_voice import active_persona_id, persona_catalog
from ui_theme import (
    BG_DEEP,
    BORDER,
    CARD,
    CYAN,
    GOLD,
    GREEN,
    INK,
    MUTED,
    PINK,
    SURFACE_ALT,
    SURFACE_SOFT,
)
from ui_widgets import RoundedButton

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DB = (
    ROOT / "astrbot" / "data" / "plugin_data" / "tafei_memory" / "memory.db"
)
MAX_HEAT = 5.0
HOT_DAYS = 14
HOT_THRESHOLD = 0.85

CATEGORIES = {
    "all": ("全部", CYAN),
    "fixed": ("固定事实", GOLD),
    "hot": ("热记忆", PINK),
    "cold": ("冷记忆", CYAN),
    "relation": ("关系与偏好", GREEN),
    "habit": ("说话习惯", "#B28CFF"),
}


def _persona_label(persona: dict) -> str:
    return str(persona.get("display_name") or persona.get("id") or "")


def _read_lines(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    try:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError:
        return []


def _persona_habits(persona: dict) -> list[dict]:
    style_path = persona.get("style_path") or persona.get("style_file")
    persona_path = persona.get("persona_path") or persona.get("persona_file")
    style_path = ROOT / str(style_path) if style_path else None
    persona_path = ROOT / str(persona_path) if persona_path else None
    style = _read_lines(style_path)
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
            for line in _read_lines(persona_path)
            if line.lstrip().startswith("- ")
            and any(keyword in line for keyword in keywords)
        ]
    return [
        {
            "id": f"habit-{index}",
            "kind": "habit",
            "title": text[:34],
            "text": text,
            "source": "人格说话规则",
            "created": "持续有效",
            "heat": 0.0,
            "access_count": 0,
            "priority": 2,
            "pinned": False,
            "layer": "habit",
            "tags": ["habit"],
        }
        for index, text in enumerate(style[:14], 1)
    ]


def _effective_heat(
    stored_heat: float,
    last_accessed: float,
    created_at: float,
) -> float:
    anchor = max(float(last_accessed or 0), float(created_at or 0), 0)
    age_days = (
        max(0.0, (time.time() - anchor) / 86400)
        if anchor
        else 365.0
    )
    return min(
        MAX_HEAT,
        max(0.0, float(stored_heat or 0)) * math.exp(-age_days / 30),
    )


def _memory_layer(
    pinned: int,
    heat: float,
    last_accessed: float,
) -> str:
    if pinned:
        return "fixed"
    if float(last_accessed or 0) and (
        time.time() - float(last_accessed) <= HOT_DAYS * 86400
    ):
        return "hot"
    return "hot" if heat >= HOT_THRESHOLD else "cold"


def _base_query(
    db: sqlite3.Connection,
    where: str,
    params: tuple,
    limit: int,
):
    return db.execute(
        f"""
        SELECT
            rowid,
            content,
            session,
            sender,
            created_at,
            priority,
            1.0 AS heat,
            created_at AS last_accessed,
            0 AS access_count,
            0 AS pinned
        FROM memories
        WHERE {where}
        ORDER BY priority DESC, created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def _memory_records(persona_id: str, limit: int = 300) -> list[dict]:
    if not MEMORY_DB.is_file():
        return []
    prefix = f"persona:{persona_id}|"
    if persona_id == "tafei":
        where = "(instr(session, ?) = 1 OR instr(session, 'persona:') <> 1)"
    else:
        where = "instr(session, ?) = 1"
    params = (prefix, limit)
    db = None
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
            ORDER BY memories.priority DESC, memories.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    except sqlite3.Error:
        rows = []
        if db is not None:
            try:
                rows = _base_query(db, where, params, limit)
            except sqlite3.Error:
                rows = []
    finally:
        if db is not None:
            db.close()

    relation_words = ("喜欢", "讨厌", "主人", "朋友", "关系", "称呼", "爱吃", "不吃")
    records = []
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
        pinned = int(row["pinned"] or 0)
        layer = _memory_layer(
            pinned,
            heat,
            float(row["last_accessed"] or 0),
        )
        tags = [layer]
        if priority > 0 or any(word in content for word in relation_words):
            tags.append("relation")
        session = str(row["session"] or "")
        if session.startswith("persona:") and "|" in session:
            session = session.split("|", 1)[1]
        session_label = session.rsplit(":", 1)[-1] if ":" in session else session
        records.append(
            {
                "id": f"memory-{row['rowid']}",
                "kind": "memory",
                "title": content[:38],
                "text": content,
                "source": f"{row['sender'] or '群友'} · 会话 {session_label}",
                "created": time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(float(row["created_at"] or 0)),
                ),
                "created_at": float(row["created_at"] or 0),
                "heat": heat,
                "access_count": int(row["access_count"] or 0),
                "priority": priority,
                "pinned": bool(pinned),
                "layer": layer,
                "tags": tags,
            }
        )
    return records


class MemoryCenterPage(tk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=BG_DEEP)
        self.personas = persona_catalog()
        self.persona_labels = {
            _persona_label(persona): str(persona["id"])
            for persona in self.personas
        }
        active = active_persona_id()
        initial = next(
            (
                label
                for label, persona_id in self.persona_labels.items()
                if persona_id == active
            ),
            next(iter(self.persona_labels), ""),
        )
        self.persona_var = tk.StringVar(value=initial)
        self.search_var = tk.StringVar()
        self.category = "all"
        self.items: list[dict] = []
        self.visible: list[dict] = []
        self.selected_id = ""
        self.category_buttons: dict[str, RoundedButton] = {}
        self.card_widgets: dict[str, tk.Frame] = {}
        self._build_ui()
        self.bind_all("<MouseWheel>", self._mousewheel, add="+")
        self._sync_persona_menu()
        self._load()

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self, bg=BG_DEEP)
        toolbar.pack(fill="x", pady=(0, 10))
        copy = tk.Frame(toolbar, bg=BG_DEEP)
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(
            copy,
            text="记忆概览",
            bg=BG_DEEP,
            fg=INK,
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            copy,
            text="查看当前人格记住的偏好、关系与近期对话线索。",
            bg=BG_DEEP,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        self.persona_selector = tk.Menubutton(
            toolbar,
            textvariable=self.persona_var,
            bg=SURFACE_ALT,
            fg=INK,
            activebackground=BORDER,
            activeforeground=INK,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        self.persona_selector.pack(side="right", padx=(8, 0))
        RoundedButton(
            toolbar,
            text="刷新",
            kind="secondary",
            command=self._load,
        ).pack(side="right")

        metrics = tk.Frame(self, bg=BG_DEEP)
        metrics.pack(fill="x", pady=(0, 12))
        self.metric_values: dict[str, tk.StringVar] = {}
        definitions = (
            ("fixed", "固定事实", GOLD),
            ("hot", "热记忆", PINK),
            ("cold", "冷记忆", CYAN),
            ("habit", "相处习惯", "#B28CFF"),
        )
        for column, (key, label, color) in enumerate(definitions):
            card = tk.Frame(
                metrics,
                bg=CARD,
                highlightthickness=1,
                highlightbackground=BORDER,
                padx=13,
                pady=10,
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0, 8) if column < 3 else 0,
            )
            tk.Label(
                card,
                text=label,
                bg=CARD,
                fg=MUTED,
                font=("Microsoft YaHei UI", 8),
            ).pack(anchor="w")
            value = tk.StringVar(value="0")
            self.metric_values[key] = value
            tk.Label(
                card,
                textvariable=value,
                bg=CARD,
                fg=color,
                font=("Microsoft YaHei UI", 19, "bold"),
            ).pack(anchor="w", pady=(2, 0))
            metrics.grid_columnconfigure(column, weight=1)

        controls = tk.Frame(self, bg=BG_DEEP)
        controls.pack(fill="x", pady=(0, 8))
        for key, (label, _color) in CATEGORIES.items():
            button = RoundedButton(
                controls,
                text=label,
                kind="secondary",
                height=32,
                min_width=62,
                command=lambda value=key: self._set_category(value),
            )
            button.pack(side="left", padx=(0, 6))
            self.category_buttons[key] = button
        search = ttk.Entry(
            controls,
            textvariable=self.search_var,
            width=22,
            font=("Microsoft YaHei UI", 9),
        )
        search.pack(side="right")
        search.bind("<KeyRelease>", lambda _event: self._render_cards())
        tk.Label(
            controls,
            text="搜索",
            bg=BG_DEEP,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="right", padx=(0, 7))

        body = tk.Frame(self, bg=BG_DEEP)
        body.pack(fill="both", expand=True)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=310)

        list_panel = tk.Frame(
            body,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(
            list_panel,
            text="记忆卡片",
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))
        self.count_label = tk.Label(
            list_panel,
            text="",
            bg=CARD,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        )
        self.count_label.pack(anchor="w", padx=14, pady=(0, 6))
        list_host = tk.Frame(list_panel, bg=CARD)
        list_host.pack(fill="both", expand=True, padx=(10, 4), pady=(0, 8))
        self.list_canvas = tk.Canvas(
            list_host,
            bg=CARD,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            list_host,
            orient="vertical",
            command=self.list_canvas.yview,
        )
        self.list_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.cards = tk.Frame(self.list_canvas, bg=CARD)
        self.cards_window = self.list_canvas.create_window(
            (0, 0),
            window=self.cards,
            anchor="nw",
        )
        self.cards.bind(
            "<Configure>",
            lambda _event: self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")
            ),
        )
        self.list_canvas.bind(
            "<Configure>",
            lambda event: self.list_canvas.itemconfigure(
                self.cards_window,
                width=event.width,
            ),
        )

        self.detail = tk.Frame(
            body,
            bg=CARD,
            width=310,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail.grid_propagate(False)
        tk.Label(
            self.detail,
            text="记忆详情",
            bg=CARD,
            fg=MUTED,
            anchor="w",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill="x", padx=16, pady=(14, 5))
        self.detail_title = tk.Label(
            self.detail,
            text="选择一张记忆卡片",
            bg=CARD,
            fg=INK,
            anchor="w",
            justify="left",
            wraplength=274,
            font=("Microsoft YaHei UI", 13, "bold"),
        )
        self.detail_title.pack(fill="x", padx=16)
        self.detail_meta = tk.Label(
            self.detail,
            text="",
            bg=CARD,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=274,
            font=("Microsoft YaHei UI", 8),
        )
        self.detail_meta.pack(fill="x", padx=16, pady=(5, 10))
        self.detail_text = tk.Text(
            self.detail,
            bg=CARD,
            fg=INK,
            relief="flat",
            wrap="word",
            padx=16,
            pady=0,
            font=("Microsoft YaHei UI", 9),
        )
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.configure(state="disabled")
        RoundedButton(
            self.detail,
            text="复制原文",
            kind="secondary",
            command=self._copy_text,
        ).pack(anchor="w", padx=16, pady=12)

    def refresh(self) -> None:
        previous_id = self.persona_labels.get(self.persona_var.get(), "")
        active = active_persona_id()
        self.personas = persona_catalog()
        self.persona_labels = {
            _persona_label(persona): str(persona["id"])
            for persona in self.personas
        }
        target_id = previous_id or active
        selected = next(
            (
                label
                for label, persona_id in self.persona_labels.items()
                if persona_id == target_id
            ),
            next(iter(self.persona_labels), ""),
        )
        self.persona_var.set(selected)
        self._sync_persona_menu()
        self._load()

    def _sync_persona_menu(self) -> None:
        menu = tk.Menu(
            self.persona_selector,
            tearoff=False,
            bg=SURFACE_ALT,
            fg=INK,
            activebackground=PINK,
            activeforeground=BG_DEEP,
        )
        for label in self.persona_labels:
            menu.add_radiobutton(
                label=label,
                value=label,
                variable=self.persona_var,
                command=self._load,
            )
        self.persona_selector.configure(menu=menu)

    def _selected_persona(self) -> dict:
        persona_id = self.persona_labels.get(self.persona_var.get(), "")
        return next(
            (item for item in self.personas if str(item["id"]) == persona_id),
            self.personas[0],
        )

    def _load(self) -> None:
        active_id = str(self._selected_persona()["id"])
        habits = _persona_habits(self._selected_persona())
        memories = _memory_records(active_id)
        self.items = [*habits, *memories]
        counts = {
            "fixed": sum(item["layer"] == "fixed" for item in memories),
            "hot": sum(item["layer"] == "hot" for item in memories),
            "cold": sum(item["layer"] == "cold" for item in memories),
            "habit": len(habits),
        }
        for key, value in counts.items():
            self.metric_values[key].set(str(value))
        self.selected_id = ""
        self._render_cards()
        self._show_detail(None)

    def _set_category(self, value: str) -> None:
        self.category = value
        self._render_cards()

    def _filtered(self) -> list[dict]:
        query = self.search_var.get().strip().lower()
        result = []
        for item in self.items:
            if self.category != "all":
                if self.category == "habit":
                    matches = item["layer"] == "habit"
                elif self.category in ("fixed", "hot", "cold"):
                    matches = item["layer"] == self.category
                else:
                    matches = self.category in item.get("tags", [])
                if not matches:
                    continue
            searchable = " ".join(
                (
                    str(item.get("title") or ""),
                    str(item.get("text") or ""),
                    str(item.get("source") or ""),
                    str(item.get("created") or ""),
                )
            ).lower()
            if query and query not in searchable:
                continue
            result.append(item)
        return result

    def _render_cards(self) -> None:
        for key, button in self.category_buttons.items():
            button.set_kind("primary" if key == self.category else "secondary")
        for child in self.cards.winfo_children():
            child.destroy()
        self.card_widgets.clear()
        self.visible = self._filtered()
        self.count_label.configure(text=f"{len(self.visible)} 条匹配记录")
        if not self.visible:
            empty = tk.Frame(self.cards, bg=SURFACE_SOFT, padx=18, pady=26)
            empty.pack(fill="x", padx=4, pady=4)
            tk.Label(
                empty,
                text="没有匹配的记忆",
                bg=SURFACE_SOFT,
                fg=INK,
                font=("Microsoft YaHei UI", 11, "bold"),
            ).pack(anchor="w")
            tk.Label(
                empty,
                text="换一个关键词或记忆分类试试。",
                bg=SURFACE_SOFT,
                fg=MUTED,
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(4, 0))
            return
        for item in self.visible:
            self._memory_card(item)

    def _memory_card(self, item: dict) -> None:
        selected = item["id"] == self.selected_id
        card = tk.Frame(
            self.cards,
            bg=SURFACE_ALT,
            highlightthickness=2 if selected else 1,
            highlightbackground=PINK if selected else BORDER,
            padx=12,
            pady=10,
            cursor="hand2",
        )
        card.pack(fill="x", padx=4, pady=4)
        self.card_widgets[item["id"]] = card

        title = tk.Label(
            card,
            text=item.get("title") or item.get("text") or "未命名记忆",
            bg=SURFACE_ALT,
            fg=INK,
            anchor="w",
            justify="left",
            wraplength=420,
            font=("Microsoft YaHei UI", 10, "bold"),
            cursor="hand2",
        )
        title.pack(fill="x")
        body = item.get("text") or ""
        clickable = [card, title]
        if body and body != item.get("title"):
            snippet = tk.Label(
                card,
                text=body[:96] + ("…" if len(body) > 96 else ""),
                bg=SURFACE_ALT,
                fg=MUTED,
                anchor="w",
                justify="left",
                wraplength=470,
                font=("Microsoft YaHei UI", 8),
                cursor="hand2",
            )
            snippet.pack(fill="x", pady=(3, 7))
            clickable.append(snippet)
        meta = tk.Frame(card, bg=SURFACE_ALT)
        meta.pack(fill="x")
        category = item.get("layer") or "hot"
        label, color = CATEGORIES.get(category, ("记忆", CYAN))
        tk.Label(
            meta,
            text=label,
            bg=SURFACE_ALT,
            fg=color,
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(side="left")
        if "relation" in item.get("tags", []):
            tk.Label(
                meta,
                text="关系线索",
                bg=SURFACE_ALT,
                fg=GREEN,
                font=("Microsoft YaHei UI", 8),
            ).pack(side="left", padx=(8, 0))
        clickable.append(meta)
        footer = tk.Label(
            card,
            text=f"{item.get('created') or ''} · {item.get('source') or ''}",
            bg=SURFACE_ALT,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=470,
            font=("Microsoft YaHei UI", 7),
            cursor="hand2",
        )
        footer.pack(fill="x", pady=(5, 0))
        clickable.append(footer)
        for widget in clickable:
            widget.bind(
                "<Button-1>",
                lambda _event, value=item: self._select(value),
            )

    def _select(self, item: dict) -> None:
        self.selected_id = item["id"]
        self._render_cards()
        self._show_detail(item)

    def _show_detail(self, item: dict | None) -> None:
        if item is None:
            self.detail_title.configure(text="选择一张记忆卡片")
            self.detail_meta.configure(text="")
            content = "点击左侧记忆查看完整内容、来源和热度信息。"
        else:
            label, _color = CATEGORIES.get(item.get("layer"), ("记忆", CYAN))
            self.detail_title.configure(text=item.get("title") or "记忆")
            self.detail_meta.configure(
                text=(
                    f"{label} · 热度 {float(item.get('heat') or 0):.2f} · "
                    f"召回 {int(item.get('access_count') or 0)} 次\n"
                    f"{item.get('created') or ''} · {item.get('source') or ''}"
                )
            )
            content = str(item.get("text") or "")
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", content)
        self.detail_text.configure(state="disabled")

    def _copy_text(self) -> None:
        item = next(
            (value for value in self.items if value["id"] == self.selected_id),
            None,
        )
        if item is None:
            return
        self.clipboard_clear()
        self.clipboard_append(str(item.get("text") or ""))

    def _mousewheel(self, event) -> None:
        if not self.winfo_ismapped():
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not str(widget).startswith(str(self.list_canvas)):
            return
        self.list_canvas.yview_scroll(int(-event.delta / 120), "units")
