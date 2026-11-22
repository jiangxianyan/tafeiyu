"""Visual sticker asset library embedded in the desktop client."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sticker_library_core import (  # noqa: E402
    import_sticker,
    list_stickers,
    remove_sticker,
    save_sticker_metadata,
)
from ui_theme import (  # noqa: E402
    BG_DEEP,
    BORDER,
    CARD,
    CYAN,
    GREEN,
    INK,
    MUTED,
    ORANGE,
    PINK,
    RED,
    SURFACE_ALT,
    SURFACE_SOFT,
)

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

PAGE_BG = BG_DEEP
SURFACE = CARD
PINK_SOFT = "#3A2032"
GREEN_SOFT = "#16362F"
ORANGE_SOFT = "#3A2B1B"
CARD_SIZE = 142


class StickerLibraryPage(tk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=PAGE_BG)
        self.items: list[dict] = []
        self.selected_filename = ""
        self.card_photos: dict[str, object] = {}
        self.preview_photo = None
        self.gallery_columns = 0
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="全部表情")
        self.field_widgets: dict[str, tk.Text] = {}
        self.detail_title = tk.StringVar(value="标签与使用说明")
        self.detail_status = tk.StringVar(value="从左侧选择一张表情")
        self.detail_meta = tk.StringVar(value="")
        self._build()
        self.refresh()

    def _build(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Sticker.TCombobox",
            fieldbackground=SURFACE_ALT,
            background=SURFACE_ALT,
            foreground=INK,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "Sticker.TCombobox",
            fieldbackground=[("readonly", SURFACE_ALT), ("active", SURFACE_ALT)],
            foreground=[("readonly", INK), ("active", INK)],
            selectbackground=[("readonly", SURFACE_ALT)],
            selectforeground=[("readonly", INK)],
        )
        toolbar = tk.Frame(self, bg=PAGE_BG)
        toolbar.pack(fill="x", pady=(0, 12))
        search_host = tk.Frame(
            toolbar,
            bg=SURFACE,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        search_host.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(
            search_host,
            text="搜索",
            bg=SURFACE,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(12, 6), pady=8)
        search = ttk.Entry(
            search_host,
            textvariable=self.search_var,
            font=("Microsoft YaHei UI", 10),
        )
        search.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=7)
        search.bind("<KeyRelease>", lambda _event: self._render_gallery())
        status = ttk.Combobox(
            toolbar,
            textvariable=self.status_var,
            values=["全部表情", "已标注", "待标注"],
            state="readonly",
            width=12,
            font=("Microsoft YaHei UI", 9),
            style="Sticker.TCombobox",
        )
        status.pack(side="left", padx=(0, 10))
        status.bind("<<ComboboxSelected>>", lambda _event: self._render_gallery())
        self.count_label = tk.Label(
            toolbar,
            text="",
            bg=PAGE_BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        )
        self.count_label.pack(side="left", padx=(0, 12))
        ttk.Button(toolbar, text="刷新", command=self.refresh).pack(side="left")
        ttk.Button(
            toolbar,
            text="导入表情",
            style="Accent.TButton",
            command=self._import,
        ).pack(side="left", padx=(8, 0))

        content = tk.Frame(self, bg=PAGE_BG)
        content.pack(fill="both", expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1, minsize=500)
        content.grid_columnconfigure(1, weight=0, minsize=340)

        gallery_panel = tk.Frame(
            content,
            bg=SURFACE,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        gallery_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        gallery_header = tk.Frame(gallery_panel, bg=SURFACE)
        gallery_header.pack(fill="x", padx=16, pady=(13, 8))
        tk.Label(
            gallery_header,
            text="表情资源",
            bg=SURFACE,
            fg=INK,
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side="left")
        tk.Label(
            gallery_header,
            text="点击图片进行编辑",
            bg=SURFACE,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(side="right")

        canvas_host = tk.Frame(gallery_panel, bg=SURFACE)
        canvas_host.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(
            canvas_host,
            bg=SURFACE,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            canvas_host,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.gallery_frame = tk.Frame(self.canvas, bg=SURFACE)
        self.gallery_window = self.canvas.create_window(
            (0, 0),
            window=self.gallery_frame,
            anchor="nw",
        )
        self.gallery_frame.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind("<Configure>", self._gallery_resized)
        self.canvas.bind_all("<MouseWheel>", self._mousewheel, add="+")

        inspector = tk.Frame(
            content,
            bg=SURFACE,
            width=340,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        inspector.grid(row=0, column=1, sticky="nsew")
        inspector.grid_propagate(False)
        inspector_header = tk.Frame(inspector, bg=SURFACE)
        inspector_header.pack(fill="x", padx=17, pady=(15, 0))
        tk.Label(
            inspector_header,
            textvariable=self.detail_title,
            bg=SURFACE,
            fg=INK,
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            inspector_header,
            textvariable=self.detail_status,
            bg=SURFACE,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", pady=(2, 0))

        preview_host = tk.Frame(
            inspector,
            bg=SURFACE_SOFT,
            height=102,
        )
        preview_host.pack(fill="x", padx=17, pady=(12, 8))
        preview_host.pack_propagate(False)
        self.preview = tk.Label(
            preview_host,
            bg=SURFACE_SOFT,
            fg=MUTED,
            text="选择一张表情查看详情",
            font=("Microsoft YaHei UI", 9),
        )
        self.preview.pack(fill="both", expand=True, padx=8, pady=8)
        tk.Label(
            inspector,
            textvariable=self.detail_meta,
            bg=SURFACE,
            fg=MUTED,
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", padx=18)

        fields = tk.Frame(inspector, bg=SURFACE)
        fields.pack(fill="both", expand=True, padx=17, pady=(6, 0))
        definitions = (
            ("keywords", "关键词", "用逗号分隔，用于搜索与匹配"),
            ("emotion", "情绪", "例如开心、无语、委屈"),
            ("intent", "意图", "例如吐槽、安慰、拒绝"),
            ("tone", "语气", "例如可爱、阴阳怪气、认真"),
        )
        for key, label, hint in definitions:
            self._field(fields, key, label, hint, height=1)
        self._field(
            fields,
            "note",
            "适用场景备注",
            "描述什么聊天情况下适合发送这张表情",
            height=2,
        )

        actions = tk.Frame(inspector, bg=SURFACE)
        actions.pack(fill="x", padx=17, pady=10)
        ttk.Button(
            actions,
            text="保存修改",
            style="Accent.TButton",
            command=self._save,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="打开图片",
            command=self._open_image,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="删除",
            command=self._remove,
        ).pack(side="left", padx=(8, 0))
        self._set_editor_enabled(False)

    def _field(
        self,
        parent: tk.Misc,
        key: str,
        label: str,
        hint: str,
        *,
        height: int,
    ) -> None:
        block = tk.Frame(parent, bg=SURFACE)
        block.pack(fill="x", pady=(0, 5))
        header = tk.Frame(block, bg=SURFACE)
        header.pack(fill="x")
        tk.Label(
            header,
            text=label,
            bg=SURFACE,
            fg=INK,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text=hint,
            bg=SURFACE,
            fg=MUTED,
            font=("Microsoft YaHei UI", 7),
        ).pack(side="right")
        text = tk.Text(
            block,
            height=height,
            wrap="word",
            relief="flat",
            bg=SURFACE_SOFT,
            fg=INK,
            insertbackground=INK,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PINK,
            padx=7,
            pady=4,
            font=("Microsoft YaHei UI", 8),
        )
        text.pack(fill="x", pady=(4, 0))
        self.field_widgets[key] = text

    def refresh(self) -> None:
        previous = self.selected_filename
        self.items = list_stickers()
        self.card_photos = {}
        filenames = {item["filename"] for item in self.items}
        self.selected_filename = previous if previous in filenames else ""
        tagged = sum(bool(item["tagged"]) for item in self.items)
        self.count_label.configure(
            text=f"{len(self.items)} 张 · 已标注 {tagged}"
        )
        self._render_gallery()
        if self.selected_filename:
            self._select_file(self.selected_filename)
        elif self.items:
            self._select_file(self.items[0]["filename"])
        else:
            self._clear_inspector()

    def _gallery_resized(self, event) -> None:
        width = max(250, event.width)
        columns = max(1, min(4, width // 166))
        self.canvas.itemconfigure(self.gallery_window, width=width)
        if columns != self.gallery_columns:
            self.gallery_columns = columns
            self._render_gallery()

    def _mousewheel(self, event) -> None:
        if self.winfo_containing(event.x_root, event.y_root) is None:
            return
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None or not str(widget).startswith(str(self.canvas)):
                return
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    def _filtered_items(self) -> list[dict]:
        query = self.search_var.get().strip().lower()
        status = self.status_var.get()
        result = []
        for item in self.items:
            if status == "已标注" and not item["tagged"]:
                continue
            if status == "待标注" and item["tagged"]:
                continue
            searchable = " ".join(
                [
                    *item.get("kw", []),
                    *item.get("emotion", []),
                    *item.get("intent", []),
                    *item.get("tone", []),
                    str(item.get("note") or ""),
                ]
            ).lower()
            if query and query not in searchable:
                continue
            result.append(item)
        return result

    def _render_gallery(self) -> None:
        if not hasattr(self, "gallery_frame"):
            return
        for child in self.gallery_frame.winfo_children():
            child.destroy()
        items = self._filtered_items()
        columns = self.gallery_columns or max(
            1,
            min(4, max(250, self.canvas.winfo_width()) // 166),
        )
        for index, info in enumerate(items):
            card = tk.Frame(
                self.gallery_frame,
                bg=SURFACE,
                width=CARD_SIZE + 12,
                height=CARD_SIZE + 12,
                cursor="hand2",
                highlightthickness=2
                if info["filename"] == self.selected_filename
                else 1,
                highlightbackground=PINK
                if info["filename"] == self.selected_filename
                else BORDER,
            )
            card.grid(
                row=index // columns,
                column=index % columns,
                padx=7,
                pady=7,
            )
            card.grid_propagate(False)
            image = self._thumbnail(info.get("path"), CARD_SIZE)
            if image is not None:
                label = tk.Label(
                    card,
                    image=image,
                    bg=SURFACE,
                    cursor="hand2",
                )
            else:
                label = tk.Label(
                    card,
                    text="图片预览不可用",
                    bg=SURFACE_SOFT,
                    fg=MUTED,
                    width=18,
                    height=7,
                    cursor="hand2",
                )
            label.pack(expand=True, fill="both", padx=3, pady=3)
            for widget in (card, label):
                widget.bind(
                    "<Button-1>",
                    lambda _event, filename=info["filename"]: self._select_file(
                        filename
                    ),
                )

    def _thumbnail(self, path, size: int):
        if Image is None or ImageTk is None or not path:
            return None
        try:
            with Image.open(path) as image:
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                preview = image.convert("RGBA")
                background = Image.new("RGBA", preview.size, (255, 255, 255, 255))
                background.alpha_composite(preview)
                output = ImageTk.PhotoImage(background.convert("RGB"))
            self.card_photos[str(path)] = output
            return output
        except Exception:
            return None

    def _select_file(self, filename: str) -> None:
        self.selected_filename = filename
        info = next(
            (item for item in self.items if item["filename"] == filename),
            None,
        )
        if info is None:
            self._clear_inspector()
            return
        self._render_gallery()
        self.detail_title.set("标签与使用说明")
        self.detail_status.set(
            "已由 AI 或用户完成标注"
            if info["tagged"]
            else "等待 AI 下次启动时自动标注"
        )
        self.detail_meta.set(
            f"{info['size'] / 1024:.0f} KB · "
            f"{'自动标签已就绪' if info['tagged'] else '尚未生成标签'}"
        )
        for key, source in (
            ("keywords", "kw"),
            ("emotion", "emotion"),
            ("intent", "intent"),
            ("tone", "tone"),
        ):
            self._set_field(key, "，".join(info.get(source, [])))
        self._set_field("note", str(info.get("note") or ""))
        self._set_editor_enabled(True)
        self._show_preview(info.get("path"))

    def _set_field(self, key: str, value: str) -> None:
        widget = self.field_widgets[key]
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _get_field(self, key: str) -> str:
        return self.field_widgets[key].get("1.0", "end-1c").strip()

    def _set_editor_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in self.field_widgets.values():
            widget.configure(state=state)

    def _show_preview(self, path) -> None:
        self.preview_photo = None
        if not path or not Path(path).is_file():
            self.preview.configure(image="", text="选择一张表情查看详情")
            return
        if Image is None or ImageTk is None:
            self.preview.configure(image="", text="Pillow 未安装，无法预览")
            return
        try:
            with Image.open(path) as image:
                image.thumbnail((270, 86), Image.Resampling.LANCZOS)
                preview = image.convert("RGBA")
                background = Image.new("RGBA", preview.size, (248, 249, 251, 255))
                background.alpha_composite(preview)
                output = ImageTk.PhotoImage(background.convert("RGB"))
            self.preview_photo = output
            self.preview.configure(image=output, text="")
        except Exception:
            self.preview.configure(image="", text="图片预览不可用")

    def _clear_inspector(self) -> None:
        self.detail_title.set("标签与使用说明")
        self.detail_status.set("从左侧选择一张表情")
        self.detail_meta.set("")
        for key in self.field_widgets:
            self._set_field(key, "")
        self._set_editor_enabled(False)
        self.preview.configure(image="", text="选择一张表情查看详情")
        self.preview_photo = None

    def _current(self) -> dict:
        return next(
            (
                item
                for item in self.items
                if item["filename"] == self.selected_filename
            ),
            {},
        )

    def _import(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="导入表情图片",
            filetypes=[
                ("表情图片", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not paths:
            return
        imported = 0
        errors = []
        for path in paths:
            try:
                import_sticker(path)
                imported += 1
            except Exception as error:
                errors.append(f"{Path(path).name}: {error}")
        self.refresh()
        text = f"已导入 {imported} 张表情。AI 下次启动时会自动生成标签和适用场景。"
        if errors:
            text += "\n\n" + "\n".join(errors[:8])
        messagebox.showinfo("导入结果", text, parent=self)

    def _save(self) -> None:
        info = self._current()
        if not info:
            return
        try:
            save_sticker_metadata(
                info["filename"],
                keywords=self._get_field("keywords"),
                emotion=self._get_field("emotion"),
                intent=self._get_field("intent"),
                tone=self._get_field("tone"),
                note=self._get_field("note"),
            )
        except Exception as error:
            messagebox.showerror("保存失败", str(error), parent=self)
            return
        filename = info["filename"]
        self.refresh()
        self._select_file(filename)

    def _open_image(self) -> None:
        info = self._current()
        if info:
            os.startfile(str(info["path"]))

    def _remove(self) -> None:
        info = self._current()
        if not info:
            return
        if not messagebox.askyesno(
            "删除表情",
            "确定删除当前表情及其标签吗？\n\n这会同时删除本地图片文件。",
            icon="warning",
            default="no",
            parent=self,
        ):
            return
        remove_sticker(info["filename"])
        self.selected_filename = ""
        self.refresh()
