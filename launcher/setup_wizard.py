"""First-run configuration wizard for tafeiyu."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from setup_core import (
    MODEL_PRESETS,
    apply_model_settings,
    apply_qq_and_groups,
    current_model_settings,
    current_qq_settings,
    disable_voice,
    existing_voice_settings,
    import_voice_bundle,
    import_voice_pack,
    keep_existing_voice,
    reset_setup_for_test,
    write_setup_complete,
)
from ui_theme import (
    APP_ICON,
    BG,
    BG_DEEP,
    BORDER,
    CARD,
    GREEN,
    INK,
    MUTED,
    ORANGE,
    PINK,
    SURFACE_ALT,
    SURFACE_SOFT,
)
from ui_widgets import (
    RoundedButton,
    apply_windows_dark_frame,
    apply_windows_window_icon,
)

DARK = INK


class SetupWizard(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        first_run: bool,
        on_complete: Callable[[bool], None],
        on_cancel: Callable[[], None],
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("塔菲鱼配置向导")
        self.geometry("820x680")
        self.minsize(760, 630)
        self.configure(bg=BG)
        self.transient(parent)
        self.first_run = first_run
        self.on_complete_callback = on_complete
        self.on_cancel_callback = on_cancel
        self.on_reset_callback = on_reset
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.model_data = current_model_settings()
        self.qq_data = current_qq_settings()
        self.voice_data = existing_voice_settings()
        self.pages: list[tk.Frame] = []
        self.page_names = [
            "模型服务",
            "机器人 QQ",
            "语音声线",
            "群聊名单",
            "确认启动",
        ]
        self.page_index = 0
        self.page_title = tk.StringVar(value="模型服务")
        self.step_label = tk.StringVar(value="步骤 1 / 5")
        self._build_ui()
        self.after(180, lambda: apply_windows_dark_frame(self))
        self._show_page(0)
        self.grab_set()
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

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=SURFACE_ALT, height=92)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="塔菲鱼配置向导",
            font=("Microsoft YaHei UI", 21, "bold"),
            bg=SURFACE_ALT,
            fg=INK,
        ).pack(anchor="w", padx=26, pady=(14, 0))
        tk.Label(
            header,
            text="完成模型、QQ、语音与群聊设置。默认人格为 tafei，完成后可在客户端切换。",
            font=("Microsoft YaHei UI", 9),
            bg=SURFACE_ALT,
            fg=MUTED,
        ).pack(anchor="w", padx=27)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=16)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        step_row = tk.Frame(body, bg=BG)
        step_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Label(
            step_row,
            textvariable=self.step_label,
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        tk.Label(
            step_row,
            textvariable=self.page_title,
            bg=BG,
            fg=DARK,
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(side="right")

        card = tk.Frame(
            body,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        card.grid(row=1, column=0, sticky="nsew")
        self.page_host = tk.Frame(card, bg=CARD)
        self.page_host.pack(fill="both", expand=True, padx=26, pady=22)

        self.pages = [
            self._build_model_page(),
            self._build_qq_page(),
            self._build_voice_page(),
            self._build_group_page(),
            self._build_finish_page(),
        ]
        for page in self.pages:
            page.grid(row=0, column=0, sticky="nsew")
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)

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
        )
        style.map(
            "TButton",
            background=[("active", SURFACE_SOFT), ("pressed", PINK)],
            foreground=[("active", INK)],
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
            "Setup.TCombobox",
            fieldbackground=SURFACE_ALT,
            background=SURFACE_ALT,
            foreground=INK,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "Setup.TCombobox",
            fieldbackground=[("readonly", SURFACE_ALT), ("active", SURFACE_ALT)],
            foreground=[("readonly", INK), ("active", INK)],
            selectbackground=[("readonly", SURFACE_ALT)],
            selectforeground=[("readonly", INK)],
        )
        style.configure(
            "Accent.TButton",
            font=("Microsoft YaHei UI", 10, "bold"),
            background=PINK,
            foreground=BG_DEEP,
            bordercolor=PINK,
            lightcolor=PINK,
            darkcolor=PINK,
        )
        style.map(
            "Accent.TButton",
            background=[
                ("disabled", SURFACE_SOFT),
                ("pressed", "#FFA2CA"),
                ("active", "#FFA2CA"),
                ("!disabled", PINK),
            ],
        )

        footer = tk.Frame(body, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.back_button = RoundedButton(
            footer,
            text="上一步",
            kind="secondary",
            command=self._back,
        )
        self.back_button.pack(side="left")
        RoundedButton(
            footer,
            text="取消",
            kind="secondary",
            command=self._cancel,
        ).pack(side="left", padx=8)
        RoundedButton(
            footer,
            text="配置卡住？安全重置",
            kind="danger",
            command=self._safe_reset,
        ).pack(side="left", padx=(8, 0))
        self.next_button = RoundedButton(
            footer,
            text="下一步",
            kind="primary",
            command=self._next,
        )
        self.next_button.pack(side="right")

    def _page_shell(self, title: str, subtitle: str) -> tk.Frame:
        frame = tk.Frame(self.page_host, bg=CARD)
        tk.Label(
            frame,
            text=title,
            bg=CARD,
            fg=DARK,
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=subtitle,
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=690,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(3, 12))
        return frame

    def _entry_row(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        variable: tk.StringVar,
        *,
        show: str | None = None,
        width: int = 54,
    ) -> ttk.Entry:
        tk.Label(
            parent,
            text=label,
            bg=CARD,
            fg=DARK,
            font=("Microsoft YaHei UI", 10),
            anchor="w",
        ).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(
            parent, textvariable=variable, show=show or "", width=width
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(18, 0), pady=5)
        parent.grid_columnconfigure(1, weight=1)
        return entry

    def _build_model_page(self) -> tk.Frame:
        page = self._page_shell(
            "大模型服务",
            "填写你拥有的 API Key。密钥只保存在本机 AstrBot 配置中，不会上传到 GitHub。",
        )
        form = tk.Frame(page, bg=CARD)
        form.pack(fill="x")
        self.model_preset = tk.StringVar(value=self.model_data["preset"])
        self.api_base = tk.StringVar(value=self.model_data["api_base"])
        self.model_name = tk.StringVar(value=self.model_data["model"])
        self.vision_model = tk.StringVar(
            value=self.model_data.get("vision_model")
            or self.model_data["model"]
        )
        self.api_key = tk.StringVar()

        tk.Label(
            form,
            text="服务商",
            bg=CARD,
            fg=DARK,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=0, column=0, sticky="w", pady=5)
        preset = ttk.Combobox(
            form,
            textvariable=self.model_preset,
            values=list(MODEL_PRESETS),
            state="readonly",
            width=30,
            style="Setup.TCombobox",
        )
        preset.grid(row=0, column=1, sticky="w", padx=(18, 0), pady=5)
        preset.bind("<<ComboboxSelected>>", self._preset_selected)
        self._entry_row(form, 1, "API Base", self.api_base)
        self._entry_row(form, 2, "模型名称", self.model_name)
        self._entry_row(form, 3, "视觉模型", self.vision_model)
        self._entry_row(form, 4, "API Key", self.api_key, show="*")

        note = (
            "已检测到本机保存过 API Key；留空表示继续使用原 Key。"
            if self.model_data["api_key_configured"]
            else "当前尚未配置 API Key。"
        )
        tk.Label(
            page,
            text=note,
            bg=CARD,
            fg=GREEN if self.model_data["api_key_configured"] else ORANGE,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(12, 0))
        tk.Label(
            page,
            text=(
                "提示：视觉模型必须支持图片输入；如果服务商与文字模型相同，"
                "可以填写同一模型名称。OpenAI 兼容服务通常以 /v1 结尾。"
            ),
            bg=CARD,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(6, 0))
        return page

    def _preset_selected(self, _event=None) -> None:
        preset = MODEL_PRESETS.get(self.model_preset.get())
        if not preset:
            return
        self.api_base.set(preset["api_base"])
        self.model_name.set(preset["model"])
        self.vision_model.set(preset["model"])

    def _build_qq_page(self) -> tk.Frame:
        page = self._page_shell(
            "机器人 QQ",
            "请使用一个独立 QQ 号作为机器人。填写完成后点击下一步，最后启动时会自动显示登录二维码。",
        )
        form = tk.Frame(page, bg=CARD)
        form.pack(fill="x")
        self.bot_qq = tk.StringVar(value=self.qq_data["bot_qq"])
        self.owner_qq = tk.StringVar(value=self.qq_data["owner_qq"])
        self._entry_row(form, 0, "机器人 QQ", self.bot_qq)
        self._entry_row(form, 1, "主人 QQ", self.owner_qq)
        tk.Label(
            page,
            text=(
                "机器人 QQ 用于 NapCat 登录；主人 QQ 用于管理员权限和私聊白名单。"
                "不要填写密码，塔菲鱼不会要求或保存 QQ 密码。"
            ),
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=690,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(18, 0))
        return page

    def _build_voice_page(self) -> tk.Frame:
        page = self._page_shell(
            "语音声线（可选）",
            "可以直接选择 .tafeivoice.zip 语音包，也可以手动导入 GPT-SoVITS 权重和参考音频。",
        )
        self.voice_mode = tk.StringVar(
            value="existing" if self.voice_data["enabled"] else "none"
        )
        mode = tk.Frame(page, bg=CARD)
        mode.pack(fill="x")
        if self.voice_data["enabled"]:
            ttk.Radiobutton(
                mode,
                text="保留当前声线",
                value="existing",
                variable=self.voice_mode,
                command=self._voice_mode_changed,
            ).pack(anchor="w")
        ttk.Radiobutton(
            mode,
            text="导入新的 GPT-SoVITS 声线",
            value="import",
            variable=self.voice_mode,
            command=self._voice_mode_changed,
        ).pack(anchor="w")
        ttk.Radiobutton(
            mode,
            text="不使用语音，仅文字聊天",
            value="none",
            variable=self.voice_mode,
            command=self._voice_mode_changed,
        ).pack(anchor="w")

        bundle_row = tk.Frame(page, bg=CARD)
        bundle_row.pack(fill="x", pady=(10, 0))
        self.voice_bundle = tk.StringVar()
        self.voice_widgets: list[tk.Widget] = [
            tk.Label(
                bundle_row,
                text="一键语音包",
                bg=CARD,
                fg=DARK,
                font=("Microsoft YaHei UI", 10),
            )
        ]
        self.voice_widgets[0].pack(side="left")
        bundle_entry = ttk.Entry(
            bundle_row,
            textvariable=self.voice_bundle,
            state="readonly",
        )
        bundle_entry.pack(side="left", fill="x", expand=True, padx=(18, 8))
        bundle_button = RoundedButton(
            bundle_row,
            text="选择 .tafeivoice.zip",
            kind="secondary",
            min_width=160,
            command=self._browse_bundle,
        )
        bundle_button.pack(side="right")
        self.voice_widgets.extend([bundle_entry, bundle_button])

        if self.voice_data["enabled"]:
            tk.Label(
                page,
                text=f"已检测到声线：{self.voice_data['manifest_path']}",
                bg=CARD,
                fg=GREEN,
                wraplength=700,
                justify="left",
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w", pady=(10, 0))

        form = tk.Frame(page, bg=CARD)
        form.pack(fill="x", pady=(7, 0))
        self.gpt_weights = tk.StringVar()
        self.sovits_weights = tk.StringVar()
        self.reference_audio = tk.StringVar()
        self.reference_text = tk.StringVar()
        self.voice_version = tk.StringVar(value="v2")
        self.voice_widgets.extend(
            self._browse_row(form, 0, "GPT 权重", self.gpt_weights, ".ckpt")
        )
        self.voice_widgets.extend(
            self._browse_row(form, 1, "SoVITS 权重", self.sovits_weights, ".pth")
        )
        self.voice_widgets.extend(
            self._browse_row(form, 2, "参考音频", self.reference_audio, ".wav")
        )
        self.voice_widgets.append(
            self._entry_row(form, 3, "参考文本", self.reference_text)
        )
        tk.Label(
            form,
            text="模型版本",
            bg=CARD,
            fg=DARK,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=4, column=0, sticky="w", pady=5)
        version = ttk.Combobox(
            form,
            textvariable=self.voice_version,
            values=["v1", "v2", "v2Pro", "v2ProPlus", "v3", "v4"],
            state="readonly",
            width=20,
            style="Setup.TCombobox",
        )
        version.grid(row=4, column=1, sticky="w", padx=(18, 0), pady=5)
        self.voice_widgets.append(version)
        tk.Label(
            page,
            text="安全提示：PyTorch 权重文件可能包含可执行反序列化内容，只导入可信来源的模型。",
            bg=CARD,
            fg=ORANGE,
            wraplength=700,
            justify="left",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(7, 0))
        self._voice_mode_changed()
        return page

    def _browse_row(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        variable: tk.StringVar,
        suffix: str,
    ) -> list[tk.Widget]:
        entry = self._entry_row(parent, row, label, variable)
        entry.configure(width=47)
        button = RoundedButton(
            parent,
            text="浏览",
            kind="secondary",
            min_width=64,
            command=lambda: self._browse(variable, suffix),
        )
        button.grid(row=row, column=2, padx=(8, 0), pady=5)
        return [entry, button]

    def _browse(self, variable: tk.StringVar, suffix: str) -> None:
        filetypes = [(suffix.upper() + " 文件", "*" + suffix), ("所有文件", "*.*")]
        path = filedialog.askopenfilename(parent=self, filetypes=filetypes)
        if path:
            variable.set(path)

    def _browse_bundle(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="选择塔菲鱼语音包",
            filetypes=[
                ("塔菲鱼语音包", "*.tafeivoice.zip"),
                ("ZIP 文件", "*.zip"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.voice_bundle.set(path)

    def _voice_mode_changed(self) -> None:
        enabled = self.voice_mode.get() == "import"
        for widget in getattr(self, "voice_widgets", []):
            try:
                widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def _build_group_page(self) -> tk.Frame:
        page = self._page_shell(
            "群聊名单",
            "每行或空格分隔多个群号。白名单群允许 AI 参与；黑名单群始终排除，不会触发回复。",
        )
        tk.Label(
            page,
            text="群聊白名单",
            bg=CARD,
            fg=DARK,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.group_white = tk.Text(
            page, height=7, relief="solid", borderwidth=1,
            font=("Microsoft YaHei UI", 10), padx=8, pady=6
        )
        self.group_white.pack(fill="x", pady=(0, 12))
        self.group_white.insert("1.0", self.qq_data["whitelist"])
        tk.Label(
            page,
            text="群聊黑名单",
            bg=CARD,
            fg=DARK,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.group_black = tk.Text(
            page, height=5, relief="solid", borderwidth=1,
            font=("Microsoft YaHei UI", 10), padx=8, pady=6
        )
        self.group_black.pack(fill="x")
        self.group_black.insert("1.0", self.qq_data["blacklist"])
        return page

    def _build_finish_page(self) -> tk.Frame:
        page = self._page_shell(
            "确认并启动",
            "点击完成后会保存配置、重启 AstrBot 和 NapCat，并显示 QQ 登录二维码。",
        )
        self.summary = tk.Label(
            page,
            text="",
            bg=SURFACE_SOFT,
            fg=DARK,
            justify="left",
            anchor="nw",
            padx=14,
            pady=12,
            font=("Microsoft YaHei UI", 10),
            wraplength=680,
        )
        self.summary.pack(fill="x")
        tk.Label(
            page,
            text=(
                "配置会写入本机。API Key 不会被写进 README、日志或 GitHub；"
                "声线权重和参考音频也不会被复制到公开仓库。"
            ),
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=690,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(16, 0))
        return page

    def _show_page(self, index: int) -> None:
        self.page_index = index
        self.pages[index].tkraise()
        self.page_title.set(self.page_names[index])
        self.step_label.set(f"步骤 {index + 1} / {len(self.pages)}")
        self.back_button.configure(state="normal" if index else "disabled")
        self.next_button.configure(
            text="完成并启动" if index == len(self.pages) - 1 else "下一步"
        )
        if index == len(self.pages) - 1:
            self._update_summary()

    def _update_summary(self) -> None:
        voice_mode = self.voice_mode.get()
        voice_text = {
            "existing": "保留当前声线",
            "import": (
                self.voice_bundle.get()
                or self.gpt_weights.get()
                or "导入新声线"
            ),
            "none": "仅文字聊天",
        }[voice_mode]
        white = " ".join(self.group_white.get("1.0", "end").split())
        black = " ".join(self.group_black.get("1.0", "end").split())
        self.summary.configure(
            text=(
                f"角色：tafei（固定人格）\n"
                f"模型：{self.model_name.get().strip()}\n"
                f"视觉模型：{self.vision_model.get().strip()}\n"
                f"机器人 QQ：{self.bot_qq.get().strip()}\n"
                f"主人 QQ：{self.owner_qq.get().strip()}\n"
                f"语音：{voice_text}\n"
                f"群聊白名单：{white or '无'}\n"
                f"群聊黑名单：{black or '无'}"
            )
        )

    def _back(self) -> None:
        if self.page_index > 0:
            self._show_page(self.page_index - 1)

    def _next(self) -> None:
        if self.page_index < len(self.pages) - 1:
            self._show_page(self.page_index + 1)
        else:
            self._finish()

    def _finish(self) -> None:
        qq_changed = self.bot_qq.get().strip() != self.qq_data["bot_qq"]
        try:
            bot_qq = self.bot_qq.get().strip()
            owner_qq = self.owner_qq.get().strip()
            model = apply_model_settings(
                preset=self.model_preset.get(),
                api_base=self.api_base.get(),
                model=self.model_name.get(),
                api_key=self.api_key.get(),
                vision_model=self.vision_model.get(),
            )
            qq = apply_qq_and_groups(
                bot_qq=bot_qq,
                owner_qq=owner_qq,
                whitelist=self.group_white.get("1.0", "end"),
                blacklist=self.group_black.get("1.0", "end"),
            )
            mode = self.voice_mode.get()
            if mode == "import":
                if self.voice_bundle.get().strip():
                    voice = import_voice_bundle(
                        self.voice_bundle.get(),
                        persona_id="tafei",
                    )
                else:
                    voice = import_voice_pack(
                        gpt_weights=self.gpt_weights.get(),
                        sovits_weights=self.sovits_weights.get(),
                        reference_audio=self.reference_audio.get(),
                        reference_text=self.reference_text.get(),
                        version=self.voice_version.get(),
                    )
            elif mode == "existing":
                voice = keep_existing_voice()
                if not voice.get("enabled"):
                    raise ValueError("没有检测到可保留的声线，请选择导入或不使用语音")
            else:
                voice = disable_voice()
            write_setup_complete(model=model, qq=qq, voice=voice)
        except Exception as error:
            messagebox.showerror("配置保存失败", str(error), parent=self)
            return
        self.grab_release()
        self.destroy()
        self.on_complete_callback(qq_changed)

    def _cancel(self) -> None:
        if messagebox.askyesno(
            "退出配置",
            "配置尚未完成。退出后塔菲鱼不会自动运行，确定退出吗？",
            parent=self,
        ):
            self.grab_release()
            self.destroy()
            self.on_cancel_callback()

    def _safe_reset(self) -> None:
        first_confirm = messagebox.askyesno(
            "安全重置配置",
            (
                "这会重新进入配置向导，但不会删除聊天记录、记忆、"
                "已导入的声线或 API Key。\n\n"
                "只有在配置卡住或反复失败时才需要重置。继续吗？"
            ),
            icon="warning",
            default="no",
            parent=self,
        )
        if not first_confirm:
            return
        typed = simpledialog.askstring(
            "二次确认",
            "为避免误触，请输入大写 RESET：",
            parent=self,
        )
        if typed is None:
            return
        if typed.strip() != "RESET":
            messagebox.showinfo(
                "未执行重置",
                "输入不匹配，配置没有发生任何改动。",
                parent=self,
            )
            return
        reset_setup_for_test()
        self.grab_release()
        self.destroy()
        if self.on_reset_callback:
            self.on_reset_callback()
            return
        messagebox.showinfo(
            "已安全重置",
            "配置标记已清除。重新打开塔菲鱼即可再次进入配置向导。",
        )
