"""Persona switcher and voice-pack center for tafeiyu."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from persona_voice import (
    active_persona_id,
    configure_feiyu_service,
    import_local_voice,
    open_guide,
    open_url,
    persona_catalog,
    set_active_persona,
    set_binding_enabled,
    voice_status,
)
from ui_theme import (
    BG_DEEP,
    BORDER,
    CARD as SURFACE,
    CYAN,
    GREEN,
    INK,
    MUTED,
    ORANGE,
    PINK,
    RED,
    SURFACE_SOFT,
)
from ui_widgets import RoundedButton

BG = BG_DEEP
CARD = SURFACE
CARD_SOFT = SURFACE_SOFT
BLUE = CYAN


class VoiceImportDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        on_saved,
        *,
        persona_id: str,
        display_name: str,
    ) -> None:
        super().__init__(parent)
        self.title(f"导入{display_name} GPT-SoVITS 声线")
        self.geometry("720x470")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.on_saved = on_saved
        self.persona_id = persona_id
        self.display_name = display_name
        self.vars = {
            "gpt": tk.StringVar(),
            "sovits": tk.StringVar(),
            "reference": tk.StringVar(),
            "text": tk.StringVar(),
            "version": tk.StringVar(value="v2"),
        }
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(
            body,
            text=f"导入{display_name}的本地声线",
            bg=BG,
            fg=INK,
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            body,
            text="只导入你已获得授权使用的 GPT-SoVITS 权重和参考音频。文件不会上传。",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(3, 13))
        form = tk.Frame(body, bg=CARD, padx=16, pady=13)
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(1, weight=1)
        self._file_row(form, 0, "GPT 权重", "gpt", ".ckpt")
        self._file_row(form, 1, "SoVITS 权重", "sovits", ".pth")
        self._file_row(form, 2, "参考音频", "reference", ".wav")
        self._text_row(form, 3, "参考文本", "text")
        tk.Label(
            form,
            text="模型版本",
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=4, column=0, sticky="w", pady=7)
        ttk.Combobox(
            form,
            textvariable=self.vars["version"],
            values=["v1", "v2", "v2Pro", "v2ProPlus", "v3", "v4"],
            state="readonly",
            width=18,
        ).grid(row=4, column=1, sticky="w", padx=(14, 0), pady=7)
        footer = tk.Frame(body, bg=BG)
        footer.pack(fill="x", pady=(11, 0))
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(
            footer,
            text=f"导入并绑定到{display_name}",
            style="Accent.TButton",
            command=self._save,
        ).pack(side="right", padx=8)

    def _file_row(self, parent, row: int, label: str, key: str, suffix: str) -> None:
        tk.Label(
            parent,
            text=label,
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=self.vars[key], width=58).grid(
            row=row, column=1, sticky="ew", padx=(14, 8), pady=7
        )
        ttk.Button(
            parent,
            text="浏览",
            command=lambda: self._browse(key, suffix),
        ).grid(row=row, column=2, pady=7)

    def _text_row(self, parent, row: int, label: str, key: str) -> None:
        tk.Label(
            parent,
            text=label,
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=self.vars[key], width=58).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(14, 0), pady=7
        )

    def _browse(self, key: str, suffix: str) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[(suffix.upper() + " 文件", "*" + suffix), ("所有文件", "*.*")],
        )
        if path:
            self.vars[key].set(path)

    def _save(self) -> None:
        try:
            import_local_voice(
                persona_id=self.persona_id,
                gpt_weights=self.vars["gpt"].get(),
                sovits_weights=self.vars["sovits"].get(),
                reference_audio=self.vars["reference"].get(),
                reference_text=self.vars["text"].get(),
                version=self.vars["version"].get(),
            )
        except Exception as error:
            messagebox.showerror("导入失败", str(error), parent=self)
            return
        self.grab_release()
        self.destroy()
        self.on_saved()


class FeiyuServiceDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        on_saved,
        *,
        persona_id: str,
        display_name: str,
    ) -> None:
        super().__init__(parent)
        self.title(f"连接{display_name}声音服务")
        self.geometry("560x310")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.on_saved = on_saved
        self.persona_id = persona_id
        self.display_name = display_name
        self.base_url = tk.StringVar(value="http://127.0.0.1:9880")
        self.api_key = tk.StringVar()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(
            body,
            text=f"连接{display_name}声音服务",
            bg=BG,
            fg=INK,
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            body,
            text="tafeiyu 只保存服务地址和密钥，不包含肥鱼模型、插件源码或参考音频。",
            bg=BG,
            fg=MUTED,
            wraplength=500,
            justify="left",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(3, 14))
        form = tk.Frame(body, bg=CARD, padx=16, pady=14)
        form.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)
        self._row(form, 0, "服务地址", self.base_url)
        self._row(form, 1, "API Key", self.api_key, show="*")
        footer = tk.Frame(body, bg=BG)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(
            footer,
            text=f"保存并绑定到{display_name}",
            style="Accent.TButton",
            command=self._save,
        ).pack(side="right", padx=8)

    def _row(self, parent, row: int, label: str, variable, show: str = "") -> None:
        tk.Label(
            parent,
            text=label,
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=variable, show=show).grid(
            row=row, column=1, sticky="ew", padx=(14, 0), pady=7
        )

    def _save(self) -> None:
        try:
            configure_feiyu_service(
                self.base_url.get(),
                self.api_key.get(),
                persona_id=self.persona_id,
                enabled=True,
            )
        except Exception as error:
            messagebox.showerror("连接失败", str(error), parent=self)
            return
        self.grab_release()
        self.destroy()
        self.on_saved()


class PersonaVoicePage(tk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=BG)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        copy = tk.Frame(toolbar, bg=BG)
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(
            copy,
            text="每个人格使用自己的声线",
            bg=BG,
            fg=INK,
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            copy,
            text="切换人格不会串用上一个人格的语音；未安装的声线保持关闭。",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(2, 0))
        RoundedButton(
            toolbar,
            text="刷新",
            kind="secondary",
            command=self._refresh,
        ).pack(side="right")
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        active = active_persona_id()
        personas = persona_catalog()
        for index, persona in enumerate(personas):
            self._persona_card(persona, active).grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=7,
                pady=7,
            )
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_columnconfigure(1, weight=1)

    def _persona_card(self, persona: dict, active: str) -> tk.Frame:
        display = str(persona.get("display_name") or persona.get("id"))
        is_active = persona["id"] == active
        binding_meta = persona.get("voice_binding") or {}
        provider = str(binding_meta.get("provider") or "")
        status = voice_status(persona["id"])
        card = tk.Frame(
            self.content,
            bg=CARD,
            highlightthickness=2 if is_active else 1,
            highlightbackground=PINK if is_active else BORDER,
            padx=16,
            pady=15,
        )
        tk.Label(
            card,
            text=display,
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text="当前人格" if is_active else "可切换",
            bg=CARD,
            fg=GREEN if is_active else MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(1, 9))
        tk.Label(
            card,
            text=f"绑定声线：{binding_meta.get('display_name', '未配置')}",
            bg=CARD,
            fg=INK,
            justify="left",
            wraplength=330,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text=status["detail"],
            bg=CARD,
            fg=GREEN if status.get("ready", status["installed"]) else ORANGE,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(3, 10))
        actions = tk.Frame(card, bg=CARD)
        actions.pack(fill="x", pady=(4, 0))
        action_buttons: list[tuple[str, object]] = []
        if not is_active:
            action_buttons.append(
                (
                    "切换到此人格",
                    lambda pid=persona["id"]: self._switch(pid),
                )
            )
        if provider == "gpt_sovits":
            action_buttons.append(
                ("导入本地声线", lambda p=persona: self._import_local(p))
            )
        elif provider == "feiyu_voice_http":
            action_buttons.extend(
                [
                    (
                        "官方项目",
                        lambda u=binding_meta.get("download_url", ""): self._open(u),
                    ),
                    (
                        "下载模型",
                        lambda u=binding_meta.get("model_url", ""): self._open(u),
                    ),
                    ("连接服务", lambda p=persona: self._connect_feiyu(p)),
                ]
            )
        if binding_meta.get("guide_url"):
            action_buttons.append(
                (
                    "查看教程",
                    lambda p=binding_meta.get("guide_url", ""): self._guide(p),
                )
            )
        for index, (text, command) in enumerate(action_buttons):
            button = ttk.Button(actions, text=text, command=command)
            button.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 6) if index % 2 == 0 else (6, 0),
                pady=(0, 6),
            )
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        if status["installed"]:
            toggle_text = "关闭此人格语音" if status["enabled"] else "启用此人格语音"
            ttk.Button(
                card,
                text=toggle_text,
                command=lambda pid=persona["id"], enabled=not status["enabled"]: self._toggle(pid, enabled),
            ).pack(anchor="w", pady=(9, 0))
        return card

    def _switch(self, persona_id: str) -> None:
        try:
            result = set_active_persona(persona_id)
        except Exception as error:
            messagebox.showerror("切换失败", str(error), parent=self)
            return
        display = result["persona"].get("display_name", persona_id)
        status = result["status"]
        if status["enabled"] and status.get("ready", status["installed"]):
            text = f"已切换至{display}，使用绑定声线。"
        elif status["enabled"]:
            text = (
                f"已切换至{display}。绑定声线已选中，"
                "但声音服务当前未连接，暂时只发文字。"
            )
        else:
            text = f"已切换至{display}。绑定声线尚未安装或已关闭，语音保持关闭。"
        messagebox.showinfo("人格已切换", text, parent=self)
        self._refresh()

    def _open(self, url: str) -> None:
        try:
            open_url(url)
        except Exception as error:
            messagebox.showinfo("没有公开链接", str(error), parent=self)

    def _guide(self, value: str) -> None:
        try:
            open_guide(value)
        except Exception as error:
            messagebox.showerror("教程打开失败", str(error), parent=self)

    def _import_local(self, persona: dict) -> None:
        VoiceImportDialog(
            self,
            self._refresh,
            persona_id=str(persona["id"]),
            display_name=str(persona.get("display_name") or persona["id"]),
        )

    def _connect_feiyu(self, persona: dict) -> None:
        FeiyuServiceDialog(
            self,
            self._refresh,
            persona_id=str(persona["id"]),
            display_name=str(persona.get("display_name") or persona["id"]),
        )

    def _toggle(self, persona_id: str, enabled: bool) -> None:
        try:
            set_binding_enabled(persona_id, enabled)
        except Exception as error:
            messagebox.showerror("语音设置失败", str(error), parent=self)
            return
        self._refresh()
