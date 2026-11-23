"""tafeiyu one-click launcher."""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from launcher_core import (
    ROOT,
    display_status,
    ensure_all,
    get_status,
    latest_login_qr,
    restart_after_setup,
    stop_all,
)
from memory_center import MemoryCenterPage
from persona_voice import (
    active_persona_id,
    persona_catalog,
    set_active_persona,
    voice_status,
)
from persona_manager_core import add_persona
from persona_plugins_center import PersonaPluginsPage
from persona_visuals_center import open_persona_visuals_center
from setup_core import setup_required
from setup_wizard import SetupWizard
from sticker_library import StickerLibraryPage
from ui_theme import (
    BACKGROUND_ASSET,
    APP_ICON,
    BG,
    BG_DEEP,
    BORDER,
    CARD,
    CYAN,
    GOLD,
    GREEN,
    INK,
    MUTED,
    LOCAL_TITLE_ICON,
    ORANGE,
    PINK,
    PINK_SOFT,
    RED,
    SIDEBAR,
    SOFT,
    SUBTLE,
    SURFACE,
    SURFACE_ALT,
    SURFACE_SOFT,
)
from ui_widgets import (
    NavPill,
    RoundedButton,
    apply_windows_dark_frame,
    apply_windows_window_icon,
    set_windows_app_user_model_id,
)
from voice_center import PersonaVoicePage

DARK = INK


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("塔菲鱼")
        self.overrideredirect(True)
        window_width, window_height = 1120, 774
        window_x = max(0, (self.winfo_screenwidth() - window_width) // 2)
        window_y = max(0, (self.winfo_screenheight() - window_height) // 2)
        self.geometry(
            f"{window_width}x{window_height}+{window_x}+{window_y}"
        )
        self.minsize(980, 684)
        self.configure(bg=BG_DEEP)
        self.configure(borderwidth=0, highlightthickness=0)
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
        self._maximized = False
        self._restore_geometry = self.geometry()
        self._drag_offset = (0, 0)
        self.setup_wizard: SetupWizard | None = None
        self.status_labels: dict[str, tk.Label] = {}
        self.status_values: dict[str, tk.StringVar] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, NavPill] = {}
        self.page_title = tk.StringVar(value="运行概览")
        self.page_subtitle = tk.StringVar(value="查看服务状态并控制塔菲鱼")
        self.qr_window: tk.Toplevel | None = None
        self.qr_photo: tk.PhotoImage | None = None
        self.qr_refresh_job: str | None = None
        self.login_wait_job: str | None = None
        self.login_wait_deadline = 0.0
        self.launch_started_at = time.time()
        self.last_qr_mtime = 0.0
        self._build_ui()
        self.after(120, self._poll_events)
        self.after(180, lambda: apply_windows_dark_frame(self))
        if setup_required() and os.environ.get("TAFEI_SKIP_SETUP") != "1":
            self.withdraw()
            self.after(150, lambda: self._open_setup(first_run=True))
        else:
            if os.environ.get("TAFEI_NO_AUTOSTART") != "1":
                self.after(250, self.start)
                self._ensure_monitor()

    def _build_ui(self) -> None:
        try:
            self.iconbitmap(default=str(APP_ICON))
        except Exception:
            pass
        apply_windows_window_icon(self, APP_ICON)
        self.after_idle(lambda: apply_windows_window_icon(self, APP_ICON))
        self.bind(
            "<Map>",
            lambda _event: apply_windows_window_icon(self, APP_ICON),
            add="+",
        )

        self._build_titlebar()

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TButton",
            font=("Microsoft YaHei UI", 10),
            background=SURFACE_ALT,
            foreground=INK,
            bordercolor=BORDER,
            lightcolor=SURFACE_ALT,
            darkcolor=SURFACE_ALT,
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", SURFACE), ("pressed", PINK_SOFT)],
            foreground=[("active", INK), ("pressed", PINK)],
        )
        style.configure(
            "Accent.TButton",
            background=PINK,
            foreground="#160D16",
            bordercolor=PINK,
            lightcolor=PINK,
            darkcolor=PINK,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#FFA2CA"), ("pressed", PINK)],
            foreground=[("active", "#160D16")],
        )
        style.configure(
            "TEntry",
            fieldbackground=SURFACE_SOFT,
            foreground=INK,
            insertcolor=INK,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_ALT,
            background=SURFACE_ALT,
            foreground=INK,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            readonlybackground=SURFACE_ALT,
            selectbackground=SURFACE_ALT,
            selectforeground=INK,
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", SURFACE_ALT),
                ("active", SURFACE_ALT),
            ],
            foreground=[
                ("readonly", INK),
                ("active", INK),
            ],
            selectbackground=[("readonly", SURFACE_ALT)],
            selectforeground=[("readonly", INK)],
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=SURFACE_ALT,
            background=SURFACE_ALT,
            foreground=INK,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[
                ("readonly", SURFACE_ALT),
                ("active", SURFACE_ALT),
            ],
            foreground=[
                ("readonly", INK),
                ("active", INK),
            ],
            selectbackground=[("readonly", SURFACE_ALT)],
            selectforeground=[("readonly", INK)],
        )

        shell = tk.Frame(self, bg=BG_DEEP)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(shell, bg=SIDEBAR, width=236)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Canvas(
            sidebar,
            height=176,
            bg=SIDEBAR,
            highlightthickness=0,
        )
        brand.pack(fill="x")
        try:
            if Image is not None and ImageTk is not None and BACKGROUND_ASSET.is_file():
                with Image.open(BACKGROUND_ASSET) as image:
                    crop = image.crop((380, 0, 1160, 620)).resize((330, 255))
                    self.brand_photo = ImageTk.PhotoImage(crop.convert("RGB"))
                brand.create_image(-42, -32, anchor="nw", image=self.brand_photo)
        except Exception:
            self.brand_photo = None
        brand.create_rectangle(0, 0, 236, 176, fill=SIDEBAR, stipple="gray50", outline="")
        brand.create_text(
            22,
            62,
            text="塔菲鱼",
            anchor="w",
            fill=INK,
            font=("Microsoft YaHei UI", 23, "bold"),
        )
        brand.create_text(
            23,
            94,
            text="TAFEIYU · LOCAL COMPANION",
            anchor="w",
            fill=CYAN,
            font=("Microsoft YaHei UI", 7, "bold"),
        )
        brand.create_line(22, 118, 72, 118, fill=PINK, width=2)

        nav_definition = [
            ("home", "运行概览"),
            ("personas", "人格切换"),
            ("voice", "声音中心"),
            ("stickers", "表情包库"),
            ("memory", "记忆"),
            ("plugins", "人格插件"),
            ("settings", "设置与诊断"),
        ]
        for key, label in nav_definition:
            button = NavPill(
                sidebar,
                text=label,
                command=lambda page=key: self.show_page(page),
            )
            button.pack(anchor="w", padx=12, pady=3)
            self.nav_buttons[key] = button

        footer = tk.Frame(sidebar, bg=SIDEBAR)
        footer.pack(side="bottom", fill="x", padx=22, pady=18)
        status_dot = tk.Canvas(
            footer,
            width=8,
            height=8,
            bg=SIDEBAR,
            highlightthickness=0,
        )
        status_dot.pack(side="left")
        status_dot.create_oval(2, 2, 6, 6, fill=GREEN, outline="")
        tk.Label(
            footer,
            text="本地运行 · 数据不上传",
            bg=SIDEBAR,
            fg=SUBTLE,
            font=("Microsoft YaHei UI", 8),
        ).pack(side="left", padx=(5, 0))

        main = tk.Frame(shell, bg=BG_DEEP)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Canvas(
            main,
            height=116,
            bg=BG_DEEP,
            highlightthickness=0,
        )
        self.header_canvas = header
        header.pack(fill="x", padx=20)
        try:
            if Image is not None and ImageTk is not None and BACKGROUND_ASSET.is_file():
                with Image.open(BACKGROUND_ASSET) as image:
                    crop = image.crop((280, 0, 1600, 520)).resize((960, 312))
                    self.header_photo = ImageTk.PhotoImage(crop.convert("RGB"))
                header.create_image(30, -150, anchor="nw", image=self.header_photo)
        except Exception:
            self.header_photo = None
        header.create_rectangle(0, 0, 1200, 116, fill=BG_DEEP, stipple="gray50", outline="")
        self.header_title_item = header.create_text(
            8,
            35,
            text=self.page_title.get(),
            anchor="w",
            fill=INK,
            font=("Microsoft YaHei UI", 24, "bold"),
        )
        self.header_subtitle_item = header.create_text(
            9,
            67,
            text=self.page_subtitle.get(),
            anchor="w",
            fill=MUTED,
            font=("Microsoft YaHei UI", 9),
        )
        header.create_text(
            9,
            94,
            text="TAFEIYU DESKTOP",
            anchor="w",
            fill=CYAN,
            font=("Microsoft YaHei UI", 7, "bold"),
        )

        self.page_host = tk.Frame(main, bg=BG_DEEP)
        self.page_host.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        self.pages = {
            "home": self._build_home_page(),
            "personas": self._build_personas_page(),
            "voice": self._build_voice_page(),
            "stickers": self._build_stickers_page(),
            "memory": self._build_memory_page(),
            "plugins": self._build_plugins_page(),
            "settings": self._build_settings_page(),
        }
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page("home")
        self._append_log("客户端已就绪。")

    def _build_titlebar(self) -> None:
        titlebar = tk.Frame(self, bg=SIDEBAR, height=34)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        titlebar.bind("<ButtonPress-1>", self._begin_window_drag)
        titlebar.bind("<B1-Motion>", self._drag_window)
        titlebar.bind("<Double-Button-1>", lambda _event: self._toggle_maximize())

        icon = tk.Canvas(
            titlebar,
            width=24,
            height=24,
            bg=SIDEBAR,
            highlightthickness=0,
        )
        icon.pack(side="left", padx=(9, 5), pady=5)
        icon.create_oval(1, 1, 23, 23, fill=PINK_SOFT, outline=PINK, width=1)
        self.titlebar_icon_photo = None
        try:
            if (
                Image is not None
                and ImageTk is not None
                and LOCAL_TITLE_ICON.is_file()
            ):
                with Image.open(LOCAL_TITLE_ICON) as image:
                    self.titlebar_icon_photo = ImageTk.PhotoImage(
                        image.convert("RGBA").resize((22, 22))
                    )
                icon.create_image(
                    12,
                    12,
                    image=self.titlebar_icon_photo,
                )
            else:
                icon.create_text(
                    12,
                    12,
                    text="T",
                    fill=PINK,
                    font=("Microsoft YaHei UI", 9, "bold"),
                )
        except Exception:
            icon.create_text(
                12,
                12,
                text="T",
                fill=PINK,
                font=("Microsoft YaHei UI", 9, "bold"),
            )
        title_label = tk.Label(
            titlebar,
            text="塔菲鱼",
            bg=SIDEBAR,
            fg=INK,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        title_label.pack(side="left")
        for widget in (titlebar, title_label):
            widget.bind("<ButtonPress-1>", self._begin_window_drag)
            widget.bind("<B1-Motion>", self._drag_window)
            widget.bind(
                "<Double-Button-1>",
                lambda _event: self._toggle_maximize(),
            )

        controls = tk.Frame(titlebar, bg=SIDEBAR)
        controls.pack(side="right", fill="y")
        self._title_button(controls, "×", self._close, danger=True)
        self.maximize_button = self._title_button(
            controls,
            "□",
            self._toggle_maximize,
        )
        self._title_button(controls, "—", self._minimize_window)
        tk.Frame(titlebar, bg=BORDER, height=1).pack(
            side="bottom",
            fill="x",
        )

    def _title_button(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        danger: bool = False,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=SIDEBAR,
            fg=INK,
            activebackground=RED if danger else SURFACE_ALT,
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightthickness=0,
            width=4,
            font=("Microsoft YaHei UI", 10),
            cursor="hand2",
        )
        button.pack(side="right", fill="y")
        return button

    def _begin_window_drag(self, event) -> None:
        if self._maximized:
            return
        self._drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_window(self, event) -> None:
        if self._maximized:
            return
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _toggle_maximize(self) -> None:
        if self._maximized:
            self.geometry(self._restore_geometry)
            self._maximized = False
            self.maximize_button.configure(text="□")
            return
        self._restore_geometry = self.geometry()
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")
        self._maximized = True
        self.maximize_button.configure(text="❐")

    def _minimize_window(self) -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            ctypes.windll.user32.ShowWindow(hwnd, 6)
        except Exception:
            self.withdraw()

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
            "memory": ("记忆", "查看当前人格的偏好、关系与近期对话线索"),
            "plugins": ("人格插件", "扩展人格能力并管理梗百科"),
            "settings": ("设置与诊断", "重新配置、查看日志或管理运行状态"),
        }
        self.page_title.set(titles[key][0])
        self.page_subtitle.set(titles[key][1])
        self._update_header_text()
        for name, button in self.nav_buttons.items():
            button.set_active(name == key)
        if key == "personas":
            self._refresh_personas_page()
        elif key == "voice":
            self.voice_page.refresh()
        elif key == "stickers":
            self.sticker_page.refresh()
        elif key == "memory":
            self.memory_page.refresh()
        elif key == "plugins":
            self.plugins_page.refresh()

    def _update_header_text(self) -> None:
        canvas = getattr(self, "header_canvas", None)
        if canvas is None:
            return
        canvas.itemconfigure(self.header_title_item, text=self.page_title.get())
        canvas.itemconfigure(
            self.header_subtitle_item,
            text=self.page_subtitle.get(),
        )

    def _build_home_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        status_card = tk.Frame(
            page,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
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
        self.refresh_button = RoundedButton(
            actions,
            text="启动 / 重新检查",
            kind="primary",
            command=self.start,
        )
        self.refresh_button.pack(side="left")
        RoundedButton(
            actions,
            text="停止服务",
            kind="danger",
            command=self._stop_services,
        ).pack(side="left", padx=8)
        RoundedButton(
            actions,
            text="打开 AstrBot",
            kind="secondary",
            command=self._open_dashboard,
        ).pack(side="left")
        RoundedButton(
            actions,
            text="登录二维码",
            kind="secondary",
            command=self._show_login_qr,
        ).pack(side="left", padx=8)
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
            bg=BG_DEEP,
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
        RoundedButton(
            toolbar,
            text="添加人格",
            kind="primary",
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
                highlightbackground=PINK if persona_id == active else BORDER,
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
                RoundedButton(
                    controls,
                    text="切换到此人格",
                    kind="primary",
                    command=lambda pid=persona_id, label=name: self._switch_persona(pid, label),
                ).pack(side="left")
            RoundedButton(
                controls,
                text="人格形象",
                kind="secondary",
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
        self.voice_page = PersonaVoicePage(self.page_host)
        return self.voice_page

    def _build_stickers_page(self) -> tk.Frame:
        self.sticker_page = StickerLibraryPage(self.page_host)
        return self.sticker_page

    def _build_memory_page(self) -> tk.Frame:
        self.memory_page = MemoryCenterPage(self.page_host)
        return self.memory_page

    def _build_plugins_page(self) -> tk.Frame:
        self.plugins_page = PersonaPluginsPage(self.page_host)
        return self.plugins_page

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
            ("重新生成 QQ 登录二维码", self._restart_napcat_for_qr),
            ("重新检查并启动服务", self.start),
            ("停止所有服务", self._stop_services),
            ("关闭客户端窗口", self._close),
        ]
        for text, command in rows:
            RoundedButton(
                actions,
                text=text,
                kind="danger" if "停止" in text else "secondary",
                command=command,
                min_width=220,
            ).pack(anchor="w", pady=5)
        tk.Label(
            page,
            text=(
                "隐私：API Key 与账号配置保存在本机；聊天记忆、图片描述缓存和"
                "日志不会上传到 GitHub。公开仓库不包含声线权重和个人表情素材。"
            ),
            bg=SURFACE_ALT,
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
                    self._cancel_login_wait()
                    self._close_qr()
                    self.action_mode = "start"
                    continue
                if value.get("NapCat / QQ") == "在线":
                    self._append_log("启动检查完成，塔菲在线。")
                    self.login_success_seen = True
                    self._close_qr()
                else:
                    self._append_log(
                        "服务检查完成；QQ 可能正在快速登录，"
                        "正在等待本次登录结果。"
                    )
                    self._begin_login_wait()
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
            self._cancel_login_wait()
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
        return latest_login_qr(
            not_before=self.launch_started_at,
            max_age_seconds=120,
        )

    def _begin_login_wait(self) -> None:
        self._cancel_login_wait()
        self.login_wait_deadline = time.time() + 45
        self.login_wait_job = self.after(1200, self._login_wait_tick)

    def _login_wait_tick(self) -> None:
        self.login_wait_job = None
        if self.stop_event.is_set():
            return
        if self.login_success_seen:
            self._cancel_login_wait()
            self._close_qr()
            return
        path = self._latest_qr()
        if path is not None:
            self._cancel_login_wait()
            self._open_qr_window(path)
            return
        if time.time() >= self.login_wait_deadline:
            self._append_log(
                "未发现本次启动后生成的有效二维码。旧缓存不会显示；"
                "如仍无法登录，请点击“检查 QQ 登录”。"
            )
            return
        self.login_wait_job = self.after(1200, self._login_wait_tick)

    def _cancel_login_wait(self) -> None:
        if self.login_wait_job:
            self.after_cancel(self.login_wait_job)
            self.login_wait_job = None

    def _show_login_qr(self) -> None:
        self._cancel_login_wait()
        status = get_status()
        if status.get("napcat_online"):
            self.login_success_seen = True
            self._close_qr()
            messagebox.showinfo(
                "QQ 已在线",
                "NapCat 已连接 AstrBot，当前无需扫码登录。",
                parent=self,
            )
            return
        path = self._latest_qr()
        if not path:
            messagebox.showinfo(
                "未发现本次新二维码",
                "没有使用旧缓存二维码。QQ 可能正在快速登录；"
                "如果刚扫码成功，请等待几秒后重新检查。若仍未登录，"
                "请重新检查并启动服务以生成新二维码。",
                parent=self,
            )
            return
        self._open_qr_window(path)

    def _restart_napcat_for_qr(self) -> None:
        if not messagebox.askyesno(
            "重新生成登录二维码",
            "这会重启 AstrBot、本地语音和 QQ 桥，并断开当前 QQ 会话。"
            "扫码成功后会恢复在线。确定继续吗？",
            icon="warning",
            default="no",
            parent=self,
        ):
            return
        self._close_qr()
        self.launch_started_at = time.time()
        self.login_success_seen = False
        self.initial_done = False
        self.force_restart_after_setup = True
        self.force_restart_qq = True
        self._append_log("正在重启 QQ 桥以生成新的登录二维码...")
        self.start()

    def _open_qr_window(self, path: Path) -> None:
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.lift()
            self._refresh_qr(path)
            return

        window = tk.Toplevel(self)
        window.title("QQ 登录二维码")
        window.geometry("340x450")
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
        self.qr_status_var = tk.StringVar(
            value="此二维码仅对本次启动有效，过期后不会显示旧缓存。"
        )
        tk.Label(
            window,
            textvariable=self.qr_status_var,
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg=MUTED,
            justify="center",
            wraplength=285,
        ).pack(pady=(0, 10))
        self.qr_label = tk.Label(window, bg="white")
        self.qr_label.pack(expand=True)
        actions = tk.Frame(window, bg="white")
        actions.pack(pady=12)
        ttk.Button(
            actions,
            text="检查登录状态",
            command=self._show_login_qr,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text="重新生成二维码",
            command=self._restart_napcat_for_qr,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="关闭", command=self._close_qr).pack(
            side="left"
        )
        self.qr_window = window
        self.last_qr_mtime = 0.0
        self._refresh_qr(path)
        self._schedule_qr_refresh()

    def _refresh_qr(self, path: Path | None = None) -> None:
        if not self.qr_window or not self.qr_window.winfo_exists():
            return
        path = path or self._latest_qr()
        if not path:
            self.qr_label.configure(image="", text="")
            self.qr_status_var.set(
                "当前二维码已过期，正在等待本次启动生成的新二维码。"
            )
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
            self.qr_refresh_job = self.after(2000, self._qr_refresh_tick)

    def _qr_refresh_tick(self) -> None:
        self.qr_refresh_job = None
        if not self.qr_window or not self.qr_window.winfo_exists():
            return
        self._refresh_qr()
        self._schedule_qr_refresh()

    def _close_qr(self) -> None:
        self._cancel_login_wait()
        if self.qr_refresh_job:
            self.after_cancel(self.qr_refresh_job)
            self.qr_refresh_job = None
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.destroy()
        self.qr_window = None
        self.qr_photo = None

    def _close(self) -> None:
        self.stop_event.set()
        self._close_qr()
        self.destroy()


def main() -> None:
    set_windows_app_user_model_id()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    Launcher().mainloop()


if __name__ == "__main__":
    main()
