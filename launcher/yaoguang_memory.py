"""A richer, read-only memory atlas inspired by companion memory dashboards."""

from __future__ import annotations

import math
import random
import re
import time
import tkinter as tk
from collections import Counter
from tkinter import ttk

from memory_map import (
    active_persona_id,
    load_star_map,
    persona_catalog,
)

BG = "#070b13"
PANEL = "#0f1522"
PANEL_2 = "#151d2c"
PANEL_3 = "#1b2435"
INK = "#edf5ff"
MUTED = "#8291a8"
LINE = "#263247"
CYAN = "#64d6ff"
BLUE = "#7197ff"
PINK = "#f07aaa"
GOLD = "#e5b96c"
GREEN = "#66d5aa"
ORANGE = "#e59461"
RED = "#eb7187"

CATEGORY_META = {
    "all": ("全部星光", CYAN),
    "fact": ("固定事实", GOLD),
    "hot": ("热记忆", PINK),
    "cold": ("冷记忆", BLUE),
    "relation": ("关系线索", GREEN),
    "habit": ("相处习惯", "#b28cff"),
    "open": ("未完成事项", ORANGE),
}

RELATION_WORDS = ("主人", "喜欢", "讨厌", "朋友", "称呼", "关系", "不吃", "爱吃")
OPEN_WORDS = (
    "以后",
    "下次",
    "待会",
    "记得",
    "约定",
    "还没",
    "要一起",
    "计划",
    "明天",
    "改天",
)
TOPIC_WORDS = ("游戏", "语音", "模型", "代码", "音乐", "群", "直播", "塔菲")


def _persona_label(persona: dict) -> str:
    return str(persona.get("display_name") or persona.get("id"))


def _classify(item: dict) -> str:
    kind = str(item.get("kind") or "")
    priority = int(item.get("priority") or 0)
    text = str(item.get("text") or item.get("title") or "")
    if kind == "habit":
        return "habit"
    layer = str(item.get("layer") or "")
    if layer in {"fact", "hot", "cold"}:
        return layer
    if any(word in text for word in OPEN_WORDS):
        return "open"
    if kind == "relation":
        return "relation"
    if priority >= 8 or any(word in text for word in ("不吃", "爱吃", "称呼")):
        return "fact"
    ts = float(item.get("ts") or 0)
    if ts and time.time() - ts <= 30 * 86400:
        return "hot"
    if ts:
        return "cold"
    return "relation" if kind == "relation" else "hot"


def _collect_nodes(persona: dict) -> list[dict]:
    data = load_star_map(persona)
    nodes = []
    for group in data.get("nodes", []):
        for item in group.get("items", []):
            category = _classify(item)
            text = str(item.get("text") or item.get("title") or "")
            tags = []
            if any(word in text for word in RELATION_WORDS):
                tags.append("relation")
            if any(word in text for word in OPEN_WORDS):
                tags.append("open")
            nodes.append(
                {
                    **item,
                    "category": category,
                    "tags": tags,
                    "group_title": group.get("title") or "记忆",
                    "source_id": item.get("id") or "",
                }
            )
    return nodes


class YaoguangMemory(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("瑶光 · 记忆星图")
        self.geometry("1180x780")
        self.minsize(960, 640)
        self.configure(bg=BG)
        self.transient(parent)
        self.personas = persona_catalog()
        self.persona_names = [_persona_label(item) for item in self.personas]
        active = active_persona_id()
        active_index = next(
            (
                index
                for index, persona in enumerate(self.personas)
                if persona["id"] == active
            ),
            0,
        )
        self.persona_var = tk.StringVar(value=self.persona_names[active_index])
        self.search_var = tk.StringVar()
        self.category = "all"
        self.all_nodes: list[dict] = []
        self.visible_nodes: list[dict] = []
        self.selected: dict | None = None
        self.node_tags: dict[str, dict] = {}
        self.category_buttons: dict[str, tk.Button] = {}
        self.layer_counts: dict[str, int] = {}
        self._stars: list[tuple[float, float, float, float]] = []
        self._build_ui()
        self.search_var.trace_add("write", lambda *_args: self._apply_filter())
        self._load()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=PANEL_3,
            background=PANEL_3,
            foreground=INK,
            arrowcolor=CYAN,
        )
        style.configure("Dark.TButton", background=PANEL_3, foreground=INK)
        style.map("Dark.TButton", background=[("active", "#25324a")])

        header = tk.Frame(self, bg="#0a101b", height=74)
        header.pack(fill="x")
        header.pack_propagate(False)
        brand = tk.Frame(header, bg="#0a101b")
        brand.pack(side="left", padx=22, pady=11)
        tk.Label(
            brand,
            text="瑶光",
            bg="#0a101b",
            fg=INK,
            font=("Microsoft YaHei UI", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="大肥鱼记忆系统 · 本地记忆星图",
            bg="#0a101b",
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w")
        self.persona_combo = tk.Menubutton(
            header,
            textvariable=self.persona_var,
            bg=PANEL_3,
            fg=INK,
            activebackground="#25324a",
            activeforeground=INK,
            relief="flat",
            padx=12,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        persona_menu = tk.Menu(
            self.persona_combo,
            tearoff=False,
            bg=PANEL_3,
            fg=INK,
            activebackground=CYAN,
            activeforeground="#071019",
        )
        for name in self.persona_names:
            persona_menu.add_radiobutton(
                label=name,
                value=name,
                variable=self.persona_var,
                command=self._load,
            )
        self.persona_combo.configure(menu=persona_menu)
        self.persona_combo.pack(side="right", padx=(0, 18))
        ttk.Button(
            header,
            text="刷新",
            style="Dark.TButton",
            command=self._load,
        ).pack(side="right", padx=(0, 8))
        tk.Label(
            header,
            text="私密 · 本地 · 可审计",
            bg="#0a101b",
            fg=GREEN,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="right", padx=14)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self.sidebar = tk.Frame(body, bg=PANEL, width=210)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.sidebar.pack_propagate(False)
        tk.Label(
            self.sidebar,
            text="记忆层",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill="x", padx=15, pady=(16, 8))
        for key, (label, color) in CATEGORY_META.items():
            button = tk.Button(
                self.sidebar,
                text=label,
                bg=PANEL,
                fg=INK,
                activebackground=PANEL_3,
                activeforeground=INK,
                relief="flat",
                bd=0,
                anchor="w",
                padx=16,
                pady=8,
                cursor="hand2",
                font=("Microsoft YaHei UI", 9),
                command=lambda value=key: self._set_category(value),
            )
            button.pack(fill="x", padx=7, pady=1)
            self.category_buttons[key] = button
        tk.Frame(self.sidebar, bg=LINE, height=1).pack(fill="x", padx=14, pady=14)
        tk.Label(
            self.sidebar,
            text="记忆分布",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill="x", padx=15)
        self.layer_canvas = tk.Canvas(
            self.sidebar,
            height=122,
            bg=PANEL,
            highlightthickness=0,
        )
        self.layer_canvas.pack(fill="x", padx=12, pady=(8, 0))
        self.sidebar_note = tk.Label(
            self.sidebar,
            text="",
            bg=PANEL,
            fg=MUTED,
            justify="left",
            anchor="nw",
            wraplength=175,
            font=("Microsoft YaHei UI", 8),
        )
        self.sidebar_note.pack(fill="x", padx=15, pady=(12, 0))

        center = tk.Frame(body, bg=PANEL)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)
        tools = tk.Frame(center, bg=PANEL, height=54)
        tools.grid(row=0, column=0, sticky="ew")
        tools.grid_propagate(False)
        tk.Label(
            tools,
            text="线索检索",
            bg=PANEL,
            fg=CYAN,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left", padx=(14, 8))
        self.search_entry = tk.Entry(
            tools,
            textvariable=self.search_var,
            bg=PANEL_2,
            fg=INK,
            insertbackground=CYAN,
            relief="flat",
            font=("Microsoft YaHei UI", 10),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=10)
        self.search_entry.insert(0, "")
        tk.Label(
            tools,
            text="线索：人物 / 时间 / 地点 / 物品",
            bg=PANEL,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(side="right", padx=(0, 14))
        self.canvas = tk.Canvas(
            center,
            bg="#050912",
            highlightthickness=1,
            highlightbackground=LINE,
            cursor="hand2",
        )
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._draw())

        self.detail = tk.Frame(body, bg=PANEL, width=320)
        self.detail.grid(row=0, column=2, sticky="nsew")
        self.detail.pack_propagate(False)
        tk.Label(
            self.detail,
            text="记忆详情",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill="x", padx=17, pady=(16, 8))
        self.detail_title = tk.Label(
            self.detail,
            text="选择一颗星",
            bg=PANEL,
            fg=INK,
            anchor="w",
            justify="left",
            wraplength=280,
            font=("Microsoft YaHei UI", 15, "bold"),
        )
        self.detail_title.pack(fill="x", padx=17)
        self.detail_kind = tk.Label(
            self.detail,
            text="",
            bg=PANEL,
            fg=CYAN,
            anchor="w",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.detail_kind.pack(fill="x", padx=17, pady=(4, 10))
        text_host = tk.Frame(self.detail, bg=PANEL)
        text_host.pack(fill="both", expand=True)
        detail_scroll = ttk.Scrollbar(
            text_host,
            orient="vertical",
        )
        detail_scroll.pack(side="right", fill="y")
        self.detail_text = tk.Text(
            text_host,
            bg=PANEL,
            fg=INK,
            relief="flat",
            wrap="word",
            font=("Microsoft YaHei UI", 9),
            padx=17,
            pady=0,
            height=18,
            yscrollcommand=detail_scroll.set,
        )
        self.detail_text.pack(side="left", fill="both", expand=True)
        detail_scroll.configure(command=self.detail_text.yview)
        self.detail_text.configure(state="disabled")
        self.source_label = tk.Label(
            self.detail,
            text="",
            bg=PANEL,
            fg=MUTED,
            anchor="nw",
            justify="left",
            wraplength=280,
            font=("Microsoft YaHei UI", 8),
        )
        self.source_label.pack(fill="x", padx=17, pady=(10, 8))
        ttk.Button(
            self.detail,
            text="复制原文",
            style="Dark.TButton",
            command=self._copy_text,
        ).pack(anchor="w", padx=17, pady=(0, 16))

    def _selected_persona(self) -> dict:
        label = self.persona_var.get()
        return next(
            (item for item in self.personas if _persona_label(item) == label),
            self.personas[0],
        )

    def _load(self) -> None:
        self.selected = None
        self.all_nodes = _collect_nodes(self._selected_persona())
        self.layer_counts = Counter(node["category"] for node in self.all_nodes)
        for tag in ("relation", "open"):
            self.layer_counts[tag] = sum(
                tag in node.get("tags", []) for node in self.all_nodes
            )
        self.layer_counts["all"] = len(self.all_nodes)
        for key, button in self.category_buttons.items():
            label, _color = CATEGORY_META[key]
            button.configure(text=f"{label}   {self.layer_counts.get(key, 0)}")
            if key == self.category:
                button.configure(bg=PANEL_3, fg=CATEGORY_META[key][1])
            else:
                button.configure(bg=PANEL, fg=INK)
        self.sidebar_note.configure(
            text=(
                f"当前人格：{self._selected_persona().get('display_name', '')}\n"
                f"本地记忆节点：{len(self.all_nodes)} 个\n\n"
                "固定、热、冷状态来自记忆库的真实热度与召回记录；关系、未完成事项是附加线索标签。"
            )
        )
        self._draw_layer_bars()
        self._apply_filter()
        self._show_detail(None)

    def _draw_layer_bars(self) -> None:
        self.layer_canvas.delete("all")
        keys = ["fact", "hot", "cold", "relation", "habit", "open"]
        max_count = max([self.layer_counts.get(key, 0) for key in keys] + [1])
        for index, key in enumerate(keys):
            label, color = CATEGORY_META[key]
            y = 7 + index * 18
            self.layer_canvas.create_text(
                0,
                y,
                text=label,
                fill=MUTED,
                anchor="nw",
                font=("Microsoft YaHei UI", 7),
            )
            width = 75 * self.layer_counts.get(key, 0) / max_count
            self.layer_canvas.create_rectangle(
                78,
                y + 2,
                78 + width,
                y + 8,
                fill=color,
                outline="",
            )

    def _set_category(self, category: str) -> None:
        self.category = category
        for key, button in self.category_buttons.items():
            if key == category:
                button.configure(bg=PANEL_3, fg=CATEGORY_META[key][1])
            else:
                button.configure(bg=PANEL, fg=INK)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_var.get().strip().lower()
        nodes = self.all_nodes
        if self.category != "all":
            if self.category in {"fact", "hot", "cold", "habit"}:
                nodes = [
                    node
                    for node in nodes
                    if node["category"] == self.category
                ]
            else:
                nodes = [
                    node
                    for node in nodes
                    if self.category in node.get("tags", [])
                ]
        if query:
            nodes = [
                node
                for node in nodes
                if query
                in " ".join(
                    (
                        str(node.get("text") or ""),
                        str(node.get("source") or ""),
                        str(node.get("group_title") or ""),
                        str(node.get("created") or ""),
                    )
                ).lower()
            ]
        self.visible_nodes = nodes
        self._draw()
        if not nodes:
            self._show_detail(None, empty=True)

    def _build_stars(self, width: int, height: int) -> None:
        if self._stars and self._stars[0][3] == width * height:
            return
        rng = random.Random(20261121 + width + height)
        self._stars = [
            (
                rng.random() * width,
                rng.random() * height,
                rng.choice((0.5, 0.8, 1.2, 1.7)),
                width * height,
            )
            for _ in range(max(90, width * height // 6500))
        ]

    def _draw(self) -> None:
        if not self.canvas.winfo_exists():
            return
        width = max(480, self.canvas.winfo_width())
        height = max(420, self.canvas.winfo_height())
        self.canvas.delete("all")
        self.node_tags.clear()
        self._build_stars(width, height)
        for x, y, radius, _size in self._stars:
            shade = "#9bb2d0" if radius > 1.2 else "#59708e"
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=shade,
                outline="",
            )
        core_x, core_y = width * 0.5, height * 0.53
        self._glow(core_x, core_y, 48, PINK)
        core = self.canvas.create_oval(
            core_x - 27,
            core_y - 27,
            core_x + 27,
            core_y + 27,
            fill="#351d30",
            outline=PINK,
            width=2,
        )
        self.canvas.create_text(
            core_x,
            core_y - 2,
            text="角色核心",
            fill=INK,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.canvas.create_text(
            core_x,
            core_y + 16,
            text=str(self._selected_persona().get("display_name") or ""),
            fill=MUTED,
            font=("Microsoft YaHei UI", 7),
        )
        categories = [
            key
            for key in CATEGORY_META
            if key != "all"
            and any(self._display_category(node) == key for node in self.visible_nodes)
        ]
        if not categories:
            self.canvas.create_text(
                core_x,
                core_y + 92,
                text="没有符合条件的记忆",
                fill=MUTED,
                font=("Microsoft YaHei UI", 10),
            )
            return
        for index, key in enumerate(categories):
            angle = -math.pi / 2 + index * 2 * math.pi / len(categories)
            hub_x = core_x + math.cos(angle) * min(width * 0.28, 245)
            hub_y = core_y + math.sin(angle) * min(height * 0.29, 205)
            color = CATEGORY_META[key][1]
            self.canvas.create_line(
                core_x,
                core_y,
                hub_x,
                hub_y,
                fill="#2f4058",
                width=1,
                dash=(3, 5),
            )
            self._glow(hub_x, hub_y, 24, color)
            self.canvas.create_oval(
                hub_x - 13,
                hub_y - 13,
                hub_x + 13,
                hub_y + 13,
                fill="#111927",
                outline=color,
                width=2,
            )
            items = [
                node
                for node in self.visible_nodes
                if self._display_category(node) == key
            ]
            self.canvas.create_text(
                hub_x,
                hub_y + 22,
                text=f"{CATEGORY_META[key][0]}  {len(items)}",
                fill=color,
                font=("Microsoft YaHei UI", 8, "bold"),
            )
            count = len(items)
            for item_index, node in enumerate(items[:18]):
                spread = min(2.1, 0.35 + count * 0.09)
                child_angle = angle - spread / 2 + (
                    spread * item_index / max(1, min(count, 18) - 1)
                )
                distance = 58 + (item_index % 3) * 16
                x = hub_x + math.cos(child_angle) * distance
                y = hub_y + math.sin(child_angle) * distance
                x = min(width - 18, max(18, x))
                y = min(height - 26, max(20, y))
                self.canvas.create_line(
                    hub_x,
                    hub_y,
                    x,
                    y,
                    fill="#22354b",
                    width=1,
                )
                radius = 5 + min(5, int(node.get("priority") or 0))
                tag = f"memory-{node.get('source_id') or item_index}"
                self.node_tags[tag] = node
                outline = "#ffffff" if node is self.selected else color
                self.canvas.create_oval(
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                    fill=color,
                    outline=outline,
                    width=2,
                    tags=(tag,),
                )
                label = str(node.get("title") or node.get("text") or "")[:16]
                if label and node is self.selected:
                    text = self.canvas.create_text(
                        x,
                        y + radius + 10,
                        text=label,
                        fill="#ffffff",
                        font=("Microsoft YaHei UI", 8, "bold"),
                        width=130,
                        tags=(tag,),
                    )
                    self.node_tags[tag] = node
                self.canvas.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _event, data=node: self._select(data),
                )

    def _glow(self, x: float, y: float, radius: float, color: str) -> None:
        for scale, width in ((1.0, 1), (0.78, 1), (0.56, 1)):
            self.canvas.create_oval(
                x - radius * scale,
                y - radius * scale,
                x + radius * scale,
                y + radius * scale,
                outline=color,
                width=width,
            )

    def _display_category(self, node: dict) -> str:
        if self.category != "all" and self.category in {
            "relation",
            "open",
        }:
            return self.category
        return str(node.get("category") or "hot")

    def _select(self, node: dict) -> None:
        self.selected = node
        self._show_detail(node)
        self._draw()

    def _show_detail(self, node: dict | None, *, empty: bool = False) -> None:
        if node is None:
            self.detail_title.configure(
                text="没有符合条件的记忆" if empty else "选择一颗星"
            )
            self.detail_kind.configure(text="")
            content = (
                "换一个线索词或记忆层再试试。"
                if empty
                else "点击星点查看原始内容、来源、时间和分类。"
            )
            self.source_label.configure(text="")
        else:
            label, color = CATEGORY_META.get(
                node["category"], ("记忆", CYAN)
            )
            self.detail_title.configure(text=node.get("title") or "记忆")
            self.detail_kind.configure(text=label, fg=color)
            created = node.get("created") or "未记录时间"
            tags = [
                CATEGORY_META.get(tag, (tag, ""))[0]
                for tag in node.get("tags", [])
            ]
            content = (
                f"原文：\n{node.get('text') or ''}\n\n"
                f"分类：{label}\n"
                f"线索标签：{' / '.join(tags) or '无'}\n"
                f"记录时间：{created}\n"
                f"有效热度：{float(node.get('heat') or 0):.2f}\n"
                f"已召回：{int(node.get('access_count') or 0)} 次\n"
                f"重要度：{node.get('priority') or 0}\n"
                f"所属层：{node.get('group_title') or '记忆'}"
            )
            self.source_label.configure(
                text=(
                    f"来源：{node.get('source') or '未知'}\n"
                    f"来源 ID：{node.get('source_id') or '无'}"
                )
            )
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", content)
        self.detail_text.configure(state="disabled")

    def _copy_text(self) -> None:
        if not self.selected:
            return
        self.clipboard_clear()
        self.clipboard_append(str(self.selected.get("text") or ""))


def open_memory_map(parent: tk.Misc) -> YaoguangMemory:
    existing = next(
        (
            child
            for child in parent.winfo_children()
            if isinstance(child, YaoguangMemory) and child.winfo_exists()
        ),
        None,
    )
    if existing:
        existing.lift()
        existing.focus_force()
        return existing
    window = YaoguangMemory(parent)
    window.focus_force()
    return window
