"""Persona-scoped declarative extension manager."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persona_extensions import (  # noqa: E402
    inspect_plugin_package,
    install_plugin_package,
    list_installed_plugins,
    set_plugin_enabled,
    uninstall_plugin,
)
from memewiki_core import (  # noqa: E402
    SOURCE_REPO as MEMEWIKI_REPO,
    get_config as get_memewiki_config,
    get_stats as get_memewiki_stats,
    set_enabled_for_persona as set_memewiki_enabled,
    update_database as update_memewiki_database,
)
from persona_voice import active_persona_id, persona_catalog  # noqa: E402
from ui_theme import (  # noqa: E402
    BG_DEEP,
    BORDER,
    CARD as SURFACE,
    GREEN,
    INK,
    MUTED,
    ORANGE,
    PINK,
    SURFACE_ALT,
    SURFACE_SOFT,
)

BG = BG_DEEP
CARD = SURFACE
DOCS = ROOT / "docs" / "PERSONA_PLUGINS.md"


class PersonaPluginsPage(tk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=BG)
        self.personas: list[dict] = []
        self.persona_labels: dict[str, str] = {}
        self.selected_label = tk.StringVar()
        self.memewiki_updates: queue.Queue[tuple[bool, object]] = queue.Queue()
        self.memewiki_updating = False
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(
            toolbar,
            text="安装给",
            bg=BG,
            fg=INK,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left")
        self.selector = tk.Menubutton(
            toolbar,
            textvariable=self.selected_label,
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
        self.selector.pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="安装插件包",
            style="Accent.TButton",
            command=self._install,
        ).pack(side="left", padx=(14, 0))
        ttk.Button(
            toolbar,
            text="插件格式与安全说明",
            command=self._open_docs,
        ).pack(side="left", padx=(8, 0))
        self.count_label = tk.Label(
            toolbar,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        )
        self.count_label.pack(side="right")

        note = tk.Label(
            self,
            text=(
                "插件启用状态按人格独立保存。插件不能携带 Python、可执行文件、"
                "快捷方式或符号链接；安装前会校验包结构。"
            ),
            bg=SURFACE_SOFT,
            fg=MUTED,
            anchor="w",
            justify="left",
            padx=12,
            pady=8,
            font=("Microsoft YaHei UI", 9),
        )
        note.pack(fill="x", pady=(0, 10))

        host = tk.Frame(self, bg=BG)
        host.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(host, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            host,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.cards,
            anchor="nw",
        )
        self.cards.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(
                self.canvas_window,
                width=event.width,
            ),
        )

    def refresh(self) -> None:
        previous_id = (
            self.persona_labels.get(self.selected_label.get(), "")
            if self.persona_labels
            else ""
        )
        active = active_persona_id()
        self.personas = persona_catalog()
        if not self.personas:
            self.persona_labels = {}
            self.selected_label.set("")
            self.selector.configure(
                menu=tk.Menu(
                    self.selector,
                    tearoff=False,
                    bg=SURFACE_ALT,
                    fg=INK,
                )
            )
            for child in self.cards.winfo_children():
                child.destroy()
            self.count_label.configure(text="人格目录为空")
            return
        self.persona_labels = {
            f"{persona.get('display_name', persona['id'])}"
            f"{'（当前）' if persona['id'] == active else ''}": str(
                persona["id"]
            )
            for persona in self.personas
        }
        labels = list(self.persona_labels)
        target_id = previous_id or str(active)
        selected = next(
            (
                label
                for label, persona_id in self.persona_labels.items()
                if persona_id == target_id
            ),
            labels[0],
        )
        self.selected_label.set(selected)
        menu = tk.Menu(
            self.selector,
            tearoff=False,
            bg=SURFACE_ALT,
            fg=INK,
            activebackground=PINK,
            activeforeground=BG_DEEP,
        )
        for label in labels:
            menu.add_radiobutton(
                label=label,
                value=label,
                variable=self.selected_label,
                command=self._refresh,
            )
        self.selector.configure(menu=menu)
        self._refresh()

    def _persona_id(self) -> str:
        return self.persona_labels[self.selected_label.get()]

    def _persona_name(self, persona_id: str) -> str:
        persona = next(
            (item for item in self.personas if item["id"] == persona_id),
            {},
        )
        return str(persona.get("display_name") or persona_id)

    def _refresh(self) -> None:
        for child in self.cards.winfo_children():
            child.destroy()
        persona_id = self._persona_id()
        plugins = list_installed_plugins()
        memewiki_config = get_memewiki_config()
        memewiki_enabled = (
            memewiki_config.get("enabled", True)
            and persona_id in memewiki_config.get("enabled_personas", [])
        )
        enabled_count = int(memewiki_enabled) + sum(
            persona_id in plugin.get("enabled_personas", [])
            for plugin in plugins
        )
        self.count_label.configure(
            text=f"{self._persona_name(persona_id)}：已启用 {enabled_count} 个，"
            f"内置 1 个，额外安装 {len(plugins)} 个"
        )
        self._memewiki_card(persona_id, memewiki_enabled)
        if not plugins:
            empty = tk.Frame(
                self.cards,
                bg=CARD,
                highlightthickness=1,
                highlightbackground=BORDER,
                padx=24,
                pady=30,
            )
            empty.pack(fill="x", pady=4)
            tk.Label(
                empty,
                text="还没有安装额外插件",
                bg=CARD,
                fg=INK,
                font=("Microsoft YaHei UI", 15, "bold"),
            ).pack(anchor="w")
            tk.Label(
                empty,
                text=(
                    "点击上方“安装插件包”，选择 .tafeiplugin 或 .zip 文件。"
                    "安装后可以单独启用给塔菲或大肥鱼。"
                ),
                bg=CARD,
                fg=MUTED,
                justify="left",
                wraplength=760,
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(6, 0))
            return
        for plugin in plugins:
            self._plugin_card(plugin, persona_id)

    def _memewiki_card(self, persona_id: str, enabled: bool) -> None:
        stats = get_memewiki_stats()
        card = tk.Frame(
            self.cards,
            bg=SURFACE_SOFT,
            highlightthickness=2,
            highlightbackground=PINK,
            padx=16,
            pady=14,
        )
        card.pack(fill="x", pady=(4, 7))
        top = tk.Frame(card, bg=SURFACE_SOFT)
        top.pack(fill="x")
        tk.Label(
            top,
            text="梗百科（内置）",
            bg=SURFACE_SOFT,
            fg=INK,
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(side="left")
        version = (
            f"  {stats['entries']} 条词库"
            if stats["available"]
            else "  词库未下载"
        )
        tk.Label(
            top,
            text=version,
            bg=SURFACE_SOFT,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        tk.Label(
            top,
            text="已启用" if enabled else "未启用",
            bg=SURFACE_SOFT,
            fg=GREEN if enabled and stats["available"] else ORANGE,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="right")
        description = (
            stats.get("source")
            or "本地梗与黑话词库"
        )
        if stats.get("built_at"):
            description += f" · 构建于 {stats['built_at']}"
        tk.Label(
            card,
            text=(
                "自动识别“这是什么梗”或裸词查询，命中时只向当前人格注入一条词条。"
                f"来源：{description}"
            ),
            bg=SURFACE_SOFT,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=800,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill="x", pady=(5, 8))
        actions = tk.Frame(card, bg=SURFACE_SOFT)
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="关闭给此人格" if enabled else "启用给此人格",
            command=lambda value=not enabled: self._toggle_memewiki(value),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="更新词库中…" if self.memewiki_updating else "下载 / 更新词库",
            state="disabled" if self.memewiki_updating else "normal",
            command=self._update_memewiki,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="上游项目",
            command=lambda: self._open_url(MEMEWIKI_REPO),
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            actions,
            text="内置插件不可卸载，可对每个人格单独关闭",
            bg=SURFACE_SOFT,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(side="right")

    def _toggle_memewiki(self, enabled: bool) -> None:
        try:
            set_memewiki_enabled(self._persona_id(), enabled)
        except Exception as error:
            messagebox.showerror("梗百科设置失败", str(error), parent=self)
            return
        self._refresh()

    def _update_memewiki(self) -> None:
        if self.memewiki_updating:
            return
        self.memewiki_updating = True
        self._refresh()

        def worker() -> None:
            try:
                result = update_memewiki_database()
                self.memewiki_updates.put((True, result))
            except Exception as error:
                self.memewiki_updates.put((False, str(error)))

        threading.Thread(target=worker, daemon=True).start()
        self.after(300, self._poll_memewiki_update)

    def _poll_memewiki_update(self) -> None:
        try:
            success, value = self.memewiki_updates.get_nowait()
        except queue.Empty:
            if self.memewiki_updating and self.winfo_exists():
                self.after(300, self._poll_memewiki_update)
            return
        self.memewiki_updating = False
        if not self.winfo_exists():
            return
        self._refresh()
        if success:
            result = value
            messagebox.showinfo(
                "词库更新完成",
                f"已更新到 {result['entries']} 条词库。",
                parent=self,
            )
        else:
            messagebox.showerror("词库更新失败", str(value), parent=self)

    def _plugin_card(self, plugin: dict, persona_id: str) -> None:
        enabled = persona_id in plugin.get("enabled_personas", [])
        card = tk.Frame(
            self.cards,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=16,
            pady=14,
        )
        card.pack(fill="x", pady=5)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x")
        tk.Label(
            top,
            text=str(plugin.get("name") or plugin["id"]),
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(side="left")
        tk.Label(
            top,
            text=f"  v{plugin.get('version', '?')}",
            bg=CARD,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        tk.Label(
            top,
            text="已启用" if enabled else "未启用",
            bg=CARD,
            fg=GREEN if enabled else ORANGE,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="right")

        detail = str(plugin.get("description") or "")
        if plugin.get("author"):
            detail += f"  ·  作者：{plugin['author']}"
        tk.Label(
            card,
            text=detail,
            bg=CARD,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=800,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill="x", pady=(5, 4))
        triggers = plugin.get("triggers", [])
        trigger_text = (
            "触发词：" + " / ".join(triggers)
            if triggers
            else "触发方式：常驻扩展"
        )
        tk.Label(
            card,
            text=trigger_text,
            bg=CARD,
            fg=INK,
            anchor="w",
            font=("Microsoft YaHei UI", 9),
        ).pack(fill="x")
        tk.Label(
            card,
            text=f"插件 ID：{plugin['id']}",
            bg=CARD,
            fg=MUTED,
            anchor="w",
            font=("Microsoft YaHei UI", 8),
        ).pack(fill="x", pady=(2, 8))

        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="关闭给此人格" if enabled else "启用给此人格",
            command=lambda p=plugin["id"], value=not enabled: self._toggle(
                p, value
            ),
        ).pack(side="left")
        if plugin.get("homepage"):
            ttk.Button(
                actions,
                text="插件主页",
                command=lambda url=plugin["homepage"]: self._open_url(url),
            ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="卸载插件",
            command=lambda p=plugin: self._uninstall(p),
        ).pack(side="right")

    def _install(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="选择人格插件包",
            filetypes=[
                ("塔菲鱼人格插件", "*.tafeiplugin"),
                ("ZIP 文件", "*.zip"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            metadata = inspect_plugin_package(path)
        except Exception as error:
            messagebox.showerror("插件包校验失败", str(error), parent=self)
            return
        existing = next(
            (
                plugin
                for plugin in list_installed_plugins()
                if plugin["id"] == metadata["id"]
            ),
            None,
        )
        trigger_text = (
            "、".join(metadata.get("triggers", []))
            if metadata.get("triggers")
            else "常驻"
        )
        action = "更新" if existing else "安装"
        confirmed = messagebox.askyesno(
            f"确认{action}插件",
            (
                f"{metadata['name']}  v{metadata['version']}\n"
                f"{metadata['description']}\n\n"
                f"作者：{metadata.get('author') or '未填写'}\n"
                f"触发方式：{trigger_text}\n"
                f"权限：仅提示词扩展\n"
                f"目标人格：{self._persona_name(self._persona_id())}\n\n"
                "插件包不会执行 Python 或系统命令。确认继续吗？"
            ),
            parent=self,
        )
        if not confirmed:
            return
        try:
            install_plugin_package(
                path,
                self._persona_id(),
                replace=bool(existing),
            )
        except Exception as error:
            messagebox.showerror("插件安装失败", str(error), parent=self)
            return
        self._refresh()
        messagebox.showinfo(
            "安装完成",
            f"{metadata['name']} 已安装，并启用到"
            f"{self._persona_name(self._persona_id())}。",
            parent=self,
        )

    def _toggle(self, plugin_id: str, enabled: bool) -> None:
        try:
            set_plugin_enabled(plugin_id, self._persona_id(), enabled)
        except Exception as error:
            messagebox.showerror("插件设置失败", str(error), parent=self)
            return
        self._refresh()

    def _uninstall(self, plugin: dict) -> None:
        personas = [
            self._persona_name(persona_id)
            for persona_id in plugin.get("enabled_personas", [])
        ]
        enabled_text = (
            "当前启用人格：" + "、".join(personas)
            if personas
            else "当前没有启用此插件的人格"
        )
        if not messagebox.askyesno(
            "卸载插件",
            f"确定卸载“{plugin['name']}”吗？\n\n{enabled_text}\n"
            "卸载会删除插件文件，但不会删除聊天记录或人格。",
            icon="warning",
            default="no",
            parent=self,
        ):
            return
        try:
            uninstall_plugin(plugin["id"])
        except Exception as error:
            messagebox.showerror("卸载失败", str(error), parent=self)
            return
        self._refresh()

    def _open_docs(self) -> None:
        if not DOCS.is_file():
            messagebox.showerror("说明缺失", f"找不到说明文件：{DOCS}", parent=self)
            return
        os.startfile(str(DOCS))

    def _open_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("链接无效", "插件主页地址无效", parent=self)
            return
        import webbrowser

        webbrowser.open(url)
