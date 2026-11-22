"""tafeiyu one-click launcher."""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from launcher_core import (
    ROOT,
    display_status,
    ensure_all,
    get_status,
    restart_after_setup,
    stop_all,
)
from persona_voice import (
    active_persona_id,
    persona_catalog,
    set_active_persona,
    voice_status,
)
from persona_manager_core import add_persona
from persona_plugins_center import open_persona_plugins_center
from persona_visuals_center import open_persona_visuals_center
from setup_core import setup_required
from setup_wizard import SetupWizard
from sticker_library import StickerLibraryPage
from voice_center import open_persona_voice_center
from yaoguang_memory import open_memory_map

BG = "#fff7fa"
CARD = "#ffffff"
PINK = "#ed6f9f"
DARK = "#352a30"
INK = DARK
MUTED = "#786a72"
GREEN = "#2f9e6f"
ORANGE = "#d88635"
RED = "#c94d5f"
SOFT = "#fbf6f8"


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("塔菲鱼")
        self.geometry("1120x740")
        self.minsize(980, 650)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.stop_event = threading.Event()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.monitor_worker: threading.Thread | None = None
        self.monitor_started = False
        self.initial_done = False
        self.login_success_seen = False
        self.force_restart_after_setup = False
        self.force_restart_qq = False
        self.action_mode = "start"
        self.setup_wizard: SetupWizard | None = None
        self.status_labels: dict[str, tk.Label] = {}
        self.status_values: dict[str, tk.StringVar] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.page_title = tk.StringVar(value="运行概览")
        self.page_subtitle = tk.StringVar(value="查看服务状态并控制塔菲鱼")
        self.qr_window: tk.Toplevel | None = None
        self.qr_photo: tk.PhotoImage | None = None
        self.qr_refresh_job: str | None = None
        self.last_qr_mtime = 0.0
        self._build_ui()
        self.after(120, self._poll_events)
        if setup_required() and os.environ.get("TAFEI_SKIP_SETUP") != "1":
            self.withdraw()
            self.after(150, lambda: self._open_setup(first_run=True))
        else:
            if os.environ.get("TAFEI_NO_AUTOSTART") != "1":
                self.after(250, self.start)
                self._ensure_monitor()

    def _build_ui(self) -> None:
        icon = ROOT / "icons" / "start.ico"
        try:
            self.iconbitmap(str(icon))
        except Exception:
            pass

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", background=PINK, foreground="white")
        style.map("Accent.TButton", background=[("active", "#dc5d91")])

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(shell, bg="#f8e8ef", width=222)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="塔菲鱼",
            bg="#f8e8ef",
            fg=DARK,
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w", padx=22, pady=(24, 0))
        tk.Label(
            sidebar,
            text="tafeiyu",
            bg="#f8e8ef",
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=23, pady=(0, 22))

        nav_definition = [
            ("home", "运行概览"),
            ("personas", "人格切换"),
            ("voice", "声音中心"),
            ("stickers", "表情包库"),
            ("memory", "记忆星图"),
            ("plugins", "人格插件"),
            ("settings", "设置与诊断"),
        ]
        for key, label in nav_definition:
            button = tk.Button(
                sidebar,
                text=label,
                command=lambda page=key: self.show_page(page),
                anchor="w",
                relief="flat",
                bd=0,
                padx=22,
                pady=10,
                bg="#f8e8ef",
                fg=DARK,
                activebackground="#f1d8e3",
                activeforeground=DARK,
                cursor="hand2",
                font=("Microsoft YaHei UI", 10),
            )
            button.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = button

        tk.Label(
            sidebar,
            text="本地运行 · 数据不上传",
            bg="#f8e8ef",
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(side="bottom", anchor="w", padx=22, pady=18)

        main = tk.Frame(shell, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=BG, height=82)
        header.pack(fill="x", padx=24)
        header.pack_propagate(False)
        tk.Label(
            header,
            textvariable=self.page_title,
            bg=BG,
            fg=DARK,
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w", pady=(17, 0))
        tk.Label(
            header,
            textvariable=self.page_subtitle,
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        self.page_host = tk.Frame(main, bg=BG)
        self.page_host.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        self.pages = {
            "home": self._build_home_page(),
            "personas": self._build_personas_page(),
            "voice": self._build_voice_page(),
            "stickers": self._build_stickers_page(),
            "memory": self._build_link_page(
                "记忆星图",
                "以人格为单位查看习惯、关系、话题与冷热记忆。",
                "打开瑶光记忆星图",
                lambda: open_memory_map(self),
            ),
            "plugins": self._build_link_page(
                "人格插件",
                "安装文本扩展、启用梗百科，并按人格独立管理。",
                "打开人格插件中心",
                lambda: open_persona_plugins_center(self),
            ),
            "settings": self._build_settings_page(),
        }
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page("home")
        self._append_log("客户端已就绪。")

    def show_page(self, key: str) -> None:
        if key not in self.pages:
            return
        page = self.pages[key]
        page.tkraise()
        titles = {
            "home": ("运行概览", "查看服务状态、启动或停止塔菲鱼"),
            "personas": ("人格切换", "当前角色的语音、形象和插件互不混用"),
            "voice": ("声音中心", "为每个人格绑定独立声线"),
            "stickers": ("表情包库", "查看、导入并修改表情标签与适用场景"),
            "memory": ("记忆星图", "查看当前人格的长期记忆与说话习惯"),
            "plugins": ("人格插件", "扩展人格能力并管理梗百科"),
            "settings": ("设置与诊断", "重新配置、查看日志或管理运行状态"),
        }
        self.page_title.set(titles[key][0])
        self.page_subtitle.set(titles[key][1])
        for name, button in self.nav_buttons.items():
            if name == key:
                button.configure(bg=CARD, fg=PINK, font=("Microsoft YaHei UI", 10, "bold"))
            else:
                button.configure(bg="#f8e8ef", fg=DARK, font=("Microsoft YaHei UI", 10))
        if key == "personas":
            self._refresh_personas_page()
        elif key == "voice":
            self._refresh_voice_page()
        elif key == "stickers":
            self.sticker_page.refresh()

    def _build_home_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        status_card = tk.Frame(
            page,
            bg=CARD,
            highlightthickness=1,
            highlightbackground="#f1dbe4",
        )
        status_card.pack(fill="x")
        for index, name in enumerate(
            ("AstrBot", "NapCat / QQ", "角色语音", "自动守护")
        ):
            tk.Label(
                status_card,
                text=name,
                font=("Microsoft YaHei UI", 10, "bold"),
                bg=CARD,
                fg=DARK,
                anchor="w",
            ).grid(row=index, column=0, sticky="w", padx=(18, 28), pady=8)
            value = tk.StringVar(value="检测中...")
            label = tk.Label(
                status_card,
                textvariable=value,
                font=("Microsoft YaHei UI", 10),
                bg=CARD,
                fg=ORANGE,
                anchor="w",
            )
            label.grid(row=index, column=1, sticky="w", padx=(0, 18), pady=8)
            self.status_values[name] = value
            self.status_labels[name] = label

        actions = tk.Frame(page, bg=BG)
        actions.pack(fill="x", pady=(12, 8))
        self.refresh_button = ttk.Button(actions, text="启动 / 重新检查", command=self.start)
        self.refresh_button.pack(side="left")
        ttk.Button(actions, text="停止服务", command=self._stop_services).pack(
            side="left", padx=8
        )
        ttk.Button(actions, text="打开 AstrBot", command=self._open_dashboard).pack(
            side="left"
        )
        ttk.Button(actions, text="登录二维码", command=self._show_login_qr).pack(
            side="left", padx=8
        )
        tk.Label(
            page,
            text="关闭客户端窗口不会停止机器人；需要停服时请点击“停止服务”。",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w")
        self.log = tk.Text(
            page,
            height=12,
            relief="flat",
            bg="#fbf6f8",
            fg=DARK,
            insertbackground=DARK,
            font=("Microsoft YaHei UI", 9),
            padx=12,
            pady=10,
            state="disabled",
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, pady=(10, 0))
        return page

    def _build_personas_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(
            toolbar,
            text="每个人格使用独立人格卡、语音、形象和记忆范围。",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="添加人格",
            command=self._add_persona,
        ).pack(side="right")
        self.persona_cards = tk.Frame(page, bg=BG)
        self.persona_cards.pack(fill="both", expand=True)
        return page

    def _refresh_personas_page(self) -> None:
        for child in self.persona_cards.winfo_children():
            child.destroy()
        active = active_persona_id()
        for index, persona in enumerate(persona_catalog()):
            persona_id = str(persona.get("id"))
            name = str(persona.get("display_name") or persona_id)
            status = voice_status(persona_id)
            card = tk.Frame(
                self.persona_cards,
                bg=CARD,
                highlightthickness=2 if persona_id == active else 1,
                highlightbackground=PINK if persona_id == active else "#eadde5",
                padx=18,
                pady=16,
            )
            card.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=6,
                pady=6,
            )
            tk.Label(
                card,
                text=name,
                bg=CARD,
                fg=INK,
                font=("Microsoft YaHei UI", 16, "bold"),
            ).pack(anchor="w")
            tk.Label(
                card,
                text="当前人格" if persona_id == active else "可切换",
                bg=CARD,
                fg=GREEN if persona_id == active else MUTED,
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(2, 10))
            binding = persona.get("voice_binding") or {}
            tk.Label(
                card,
                text=f"声线：{binding.get('display_name') or '未绑定'}",
                bg=CARD,
                fg=INK,
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(anchor="w")
            tk.Label(
                card,
                text=status.get("detail") or "",
                bg=CARD,
                fg=GREEN if status.get("ready") else ORANGE,
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(3, 12))
            controls = tk.Frame(card, bg=CARD)
            controls.pack(fill="x")
            if persona_id != active:
                ttk.Button(
                    controls,
                    text="切换到此人格",
                    command=lambda pid=persona_id, label=name: self._switch_persona(pid, label),
                ).pack(side="left")
            ttk.Button(
                controls,
                text="人格形象",
                command=lambda: open_persona_visuals_center(self),
            ).pack(side="left", padx=(7, 0))
        self.persona_cards.grid_columnconfigure(0, weight=1)
        self.persona_cards.grid_columnconfigure(1, weight=1)

    def _switch_persona(self, persona_id: str, name: str) -> None:
        try:
            set_active_persona(persona_id)
        except Exception as error:
            messagebox.showerror("切换失败", str(error), parent=self)
            return
        self._refresh_personas_page()
        self._append_log(f"人格已切换为 {name}。")

    def _add_persona(self) -> None:
        source = filedialog.askopenfilename(
            parent=self,
            title="选择人格 Markdown 文件",
            filetypes=[
                ("人格文件", "*.md *.txt"),
                ("Markdown", "*.md"),
                ("文本文件", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if not source:
            return
        display_name = simpledialog.askstring(
            "添加人格",
            "人格显示名称：",
            parent=self,
        )
        if display_name is None:
            return
        persona_id = simpledialog.askstring(
            "添加人格",
            "人格 ID（英文小写，例如 newfish）：",
            parent=self,
        )
        if persona_id is None:
            return
        try:
            entry = add_persona(
                persona_id=persona_id,
                display_name=display_name,
                source_file=source,
            )
        except Exception as error:
            messagebox.showerror("人格添加失败", str(error), parent=self)
            return
        self._refresh_personas_page()
        messagebox.showinfo(
            "人格已添加",
            f"{entry['display_name']} 已加入人格目录。\n"
            "可在声音中心为它绑定独立声线。",
            parent=self,
        )

    def _build_voice_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=CARD)
        self.voice_summary = tk.Label(
            page,
            text="",
            bg=CARD,
            fg=INK,
            justify="left",
            anchor="nw",
            padx=22,
            pady=18,
            font=("Microsoft YaHei UI", 11),
        )
        self.voice_summary.pack(fill="x")
        ttk.Button(
            page,
            text="打开人格与声线中心",
            style="Accent.TButton",
            command=lambda: open_persona_voice_center(self),
        ).pack(anchor="w", padx=22, pady=(0, 18))
        return page

    def _refresh_voice_page(self) -> None:
        lines = []
        for persona in persona_catalog():
            persona_id = str(persona["id"])
            name = persona.get("display_name") or persona_id
            status = voice_status(persona_id)
            lines.append(
                f"{name}：{status.get('detail')}\n"
                f"  绑定声线：{(persona.get('voice_binding') or {}).get('display_name', '未配置')}"
            )
        self.voice_summary.configure(text="\n\n".join(lines))

    def _build_stickers_page(self) -> tk.Frame:
        self.sticker_page = StickerLibraryPage(self.page_host)
        return self.sticker_page

    def _build_link_page(
        self,
        title: str,
        description: str,
        button_text: str,
        command,
    ) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=CARD)
        tk.Label(
            page,
            text=title,
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(anchor="w", padx=24, pady=(24, 5))
        tk.Label(
            page,
            text=description,
            bg=CARD,
            fg=MUTED,
            wraplength=700,
            justify="left",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", padx=24)
        ttk.Button(
            page,
            text=button_text,
            style="Accent.TButton",
            command=command,
        ).pack(anchor="w", padx=24, pady=18)
        return page

    def _build_settings_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=CARD)
        tk.Label(
            page,
            text="设置与诊断",
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(anchor="w", padx=24, pady=(24, 4))
        tk.Label(
            page,
            text="配置向导会保留聊天、记忆和已导入资源，只重新应用运行设置。",
            bg=CARD,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=24, pady=(0, 14))
        actions = tk.Frame(page, bg=CARD)
        actions.pack(fill="x", padx=24)
        rows = [
            ("重新打开配置向导", lambda: self._open_setup(False)),
            ("打开 AstrBot 管理页", self._open_dashboard),
            ("显示 QQ 登录二维码", self._show_login_qr),
            ("重新检查并启动服务", self.start),
            ("停止所有服务", self._stop_services),
            ("关闭客户端窗口", self._close),
        ]
        for text, command in rows:
            ttk.Button(actions, text=text, command=command, width=28).pack(
                anchor="w", pady=5
            )
        tk.Label(
            page,
            text=(
                "隐私：API Key 与账号配置保存在本机；聊天记忆、图片描述缓存和"
                "日志不会上传到 GitHub。公开仓库不包含声线权重和个人表情素材。"
            ),
            bg="#fbf6f8",
            fg=MUTED,
            wraplength=720,
            justify="left",
            padx=14,
            pady=12,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill="x", padx=24, pady=(24, 0))
        return page

    def _set_status(self, status: dict) -> None:
        for name, value in self.status_values.items():
            text = str(status.get(name, "未知"))
            value.set(text)
            label = self.status_labels[name]
            if "在线" in text or text == "运行中":
                label.configure(fg=GREEN)
            elif "等待" in text:
                label.configure(fg=ORANGE)
            elif "未" in text or "失败" in text:
                label.configure(fg=RED)
            else:
                label.configure(fg=ORANGE)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _post(self, kind: str, value: object) -> None:
        self.events.put((kind, value))

    def _poll_events(self) -> None:
        if self.stop_event.is_set():
            return
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(value))
            elif kind == "status":
                self._set_status(value)
            elif kind == "qr":
                self._open_qr_window(Path(str(value)))
            elif kind == "monitor":
                self._apply_monitor_status(value)
            elif kind == "done":
                self._set_status(value)
                self.refresh_button.configure(state="normal")
                self.initial_done = True
                if self.action_mode == "stop":
                    self._append_log("服务停止流程完成。")
                    self.login_success_seen = False
                    self.action_mode = "start"
                    continue
                if value.get("NapCat / QQ") == "在线":
                    self._append_log("启动检查完成，塔菲在线。")
                    self.login_success_seen = True
                    self._close_qr()
                else:
                    self._append_log("服务检查完成；QQ 未连线时需要人工登录。")
                    self._show_login_qr()
        self.after(120, self._poll_events)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.action_mode = "start"
        self.refresh_button.configure(state="disabled")
        for value in self.status_values.values():
            value.set("检测中...")
        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()

    def _stop_services(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not messagebox.askyesno(
            "停止塔菲鱼服务",
            "这会停止 QQ、AstrBot 和本地语音服务，但不会删除配置、"
            "聊天记录、记忆或表情包。确定停止吗？",
            icon="warning",
            default="no",
            parent=self,
        ):
            return
        self.action_mode = "stop"
        self.refresh_button.configure(state="disabled")
        self.worker = threading.Thread(target=self._run_stop_worker, daemon=True)
        self.worker.start()

    def _monitor_tick(self) -> None:
        if self.stop_event.is_set():
            return
        busy = self.worker and self.worker.is_alive()
        checking = self.monitor_worker and self.monitor_worker.is_alive()
        if self.initial_done and not busy and not checking:
            self.monitor_worker = threading.Thread(
                target=self._monitor_status, daemon=True
            )
            self.monitor_worker.start()
        self.after(4000, self._monitor_tick)

    def _ensure_monitor(self) -> None:
        if self.monitor_started:
            return
        self.monitor_started = True
        self.after(3000, self._monitor_tick)

    def _monitor_status(self) -> None:
        try:
            self._post("monitor", display_status(get_status()))
        except Exception as error:
            self._post("log", f"状态刷新失败：{error}")

    def _apply_monitor_status(self, shown: dict) -> None:
        self._set_status(shown)
        raw = shown.get("_raw", {})
        online = bool(raw.get("napcat_online"))
        if online:
            if not self.login_success_seen:
                self._append_log("检测到 QQ 登录成功，塔菲已恢复在线。")
                self.login_success_seen = True
            self._close_qr()
        elif self.login_success_seen:
            self._append_log("检测到 QQ 已离线，请查看二维码或重新检查。")
            self.login_success_seen = False

    def _run_worker(self) -> None:
        try:
            if self.force_restart_after_setup:
                restart_napcat = self.force_restart_qq
                self.force_restart_after_setup = False
                self.force_restart_qq = False
                restart_after_setup(
                    self._post,
                    self.stop_event,
                    restart_napcat=restart_napcat,
                )
            else:
                ensure_all(self._post, self.stop_event)
        except Exception as error:
            self._post("log", f"启动失败：{error}")
            failed = {name: "检查失败" for name in self.status_values}
            self._post("status", failed)
            self._post("done", failed)

    def _run_stop_worker(self) -> None:
        try:
            stop_all(self._post, self.stop_event)
        except Exception as error:
            self._post("log", f"停止失败：{error}")
            failed = {name: "停止失败" for name in self.status_values}
            self._post("status", failed)
            self._post("done", failed)

    def _open_setup(self, first_run: bool) -> None:
        if self.setup_wizard and self.setup_wizard.winfo_exists():
            self.setup_wizard.lift()
            self.setup_wizard.focus_force()
            return
        if first_run:
            self.withdraw()
        self.setup_wizard = SetupWizard(
            self,
            first_run=first_run,
            on_complete=self._setup_complete,
            on_cancel=self._setup_cancelled,
            on_reset=self._reopen_setup_after_reset,
        )

    def _reopen_setup_after_reset(self) -> None:
        self.setup_wizard = None
        self.withdraw()
        self.after(120, lambda: self._open_setup(True))

    def _setup_complete(self, qq_changed: bool) -> None:
        self.setup_wizard = None
        self.force_restart_after_setup = True
        self.force_restart_qq = qq_changed
        self.initial_done = False
        self.deiconify()
        self._ensure_monitor()
        self.start()

    def _setup_cancelled(self) -> None:
        self.setup_wizard = None
        if self.winfo_viewable():
            return
        self._close()

    def _open_dashboard(self) -> None:
        status = get_status()
        if not status["astrbot_online"]:
            messagebox.showwarning(
                "AstrBot 未就绪", "AstrBot 当前未在线，请先重新检查。"
            )
            return
        os.startfile("http://127.0.0.1:6185")

    def _latest_qr(self) -> Path | None:
        cache_root = (
            ROOT
            / "napcat"
            / "NapCat.52230.Shell"
            / "versions"
        )
        candidates = list(
            cache_root.glob("*/resources/app/napcat/cache/qrcode.png")
        )
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _show_login_qr(self) -> None:
        path = self._latest_qr()
        if not path:
            messagebox.showinfo(
                "暂无二维码",
                "还没有生成登录二维码。请先等待 NapCat 启动完成。",
            )
            return
        self._open_qr_window(path)

    def _open_qr_window(self, path: Path) -> None:
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.lift()
            self._refresh_qr(path)
            return

        window = tk.Toplevel(self)
        window.title("QQ 登录二维码")
        window.geometry("320x410")
        window.resizable(False, False)
        window.configure(bg="white")
        window.protocol("WM_DELETE_WINDOW", self._close_qr)
        tk.Label(
            window,
            text="使用恢复登录的 QQ 扫码",
            font=("Microsoft YaHei UI", 13, "bold"),
            bg="white",
            fg=DARK,
        ).pack(pady=(18, 4))
        tk.Label(
            window,
            text="二维码会在登录成功后失效；过期时启动器会自动刷新。",
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg=MUTED,
        ).pack(pady=(0, 10))
        self.qr_label = tk.Label(window, bg="white")
        self.qr_label.pack(expand=True)
        ttk.Button(window, text="关闭", command=self._close_qr).pack(pady=12)
        self.qr_window = window
        self._refresh_qr(path)
        self._schedule_qr_refresh()

    def _refresh_qr(self, path: Path | None = None) -> None:
        if not self.qr_window or not self.qr_window.winfo_exists():
            return
        path = path or self._latest_qr()
        if not path:
            return
        try:
            mtime = path.stat().st_mtime
            if mtime == self.last_qr_mtime and self.qr_photo is not None:
                return
            self.qr_photo = tk.PhotoImage(file=str(path))
            self.qr_label.configure(image=self.qr_photo)
            self.last_qr_mtime = mtime
        except Exception as error:
            self._append_log(f"二维码加载失败：{error}")

    def _schedule_qr_refresh(self) -> None:
        if self.qr_refresh_job:
            self.after_cancel(self.qr_refresh_job)
        self.qr_refresh_job = self.after(3000, self._qr_refresh_tick)

    def _qr_refresh_tick(self) -> None:
        self.qr_refresh_job = None
        if not self.qr_window or not self.qr_window.winfo_exists():
            return
        self._refresh_qr()
        self._schedule_qr_refresh()

    def _close_qr(self) -> None:
        if self.qr_refresh_job:
            self.after_cancel(self.qr_refresh_job)
            self.qr_refresh_job = None
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.destroy()
        self.qr_window = None

    def _close(self) -> None:
        self.stop_event.set()
        self._close_qr()
        self.destroy()


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    Launcher().mainloop()


if __name__ == "__main__":
    main()
