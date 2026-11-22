"""Persona visual identity card editor for tafeiyu."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persona_visuals_core import (  # noqa: E402
    import_visual_reference,
    load_visual_card,
    remove_visual_reference,
    resolve_visual_path,
    save_visual_card,
)
from persona_voice import active_persona_id, persona_catalog  # noqa: E402

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

BG = "#fff7fa"
CARD = "#ffffff"
SOFT = "#fbf5f8"
PINK = "#df6d98"
INK = "#342a37"
MUTED = "#7d6e81"
GREEN = "#2f946e"
ORANGE = "#c07a2f"


class PersonaVisualsCenter(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("塔菲鱼 · 人格形象")
        self.geometry("1040x760")
        self.minsize(880, 660)
        self.configure(bg=BG)
        self.transient(parent)
        self.personas = persona_catalog()
        if not self.personas:
            raise RuntimeError("人格目录为空，无法管理人格形象")
        current_id = active_persona_id()
        self.labels = {
            (
                str(persona.get("display_name") or persona["id"])
                + ("（当前）" if str(persona["id"]) == current_id else "")
            ): str(persona["id"])
            for persona in self.personas
        }
        selected = next(
            label for label, persona_id in self.labels.items()
            if persona_id == current_id
        )
        self.selected_label = tk.StringVar(value=selected)
        self.preview_photo = None
        self.reference_map: dict[str, str] = {}
        self.vars = {
            "appearance": tk.StringVar(),
            "hair": tk.StringVar(),
            "outfit": tk.StringVar(),
            "colors": tk.StringVar(),
            "motifs": tk.StringVar(),
            "self_recognition_notes": tk.StringVar(),
            "boundaries": tk.StringVar(),
        }
        self._build_ui()
        self._load_selected()

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg="#f9eaf1", height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="人格形象",
            bg="#f9eaf1",
            fg=INK,
            font=("Microsoft YaHei UI", 21, "bold"),
        ).pack(anchor="w", padx=24, pady=(13, 0))
        tk.Label(
            header,
            text=(
                "为塔菲和大肥鱼分别保存稳定的网络形象。这里存的是人格设定，"
                "不会被日常聊天自动改写。"
            ),
            bg="#f9eaf1",
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=25)

        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill="x", padx=20, pady=(14, 8))
        tk.Label(
            toolbar,
            text="编辑人格",
            bg=BG,
            fg=INK,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left")
        selector = ttk.Combobox(
            toolbar,
            textvariable=self.selected_label,
            values=list(self.labels),
            state="readonly",
            width=24,
        )
        selector.pack(side="left", padx=(8, 0))
        selector.bind("<<ComboboxSelected>>", lambda _event: self._load_selected())
        ttk.Button(
            toolbar,
            text="保存人格形象",
            style="Accent.TButton",
            command=self._save,
        ).pack(side="right")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        editor = tk.Frame(
            body,
            bg=CARD,
            highlightthickness=1,
            highlightbackground="#eadde5",
            padx=18,
            pady=15,
        )
        editor.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        editor.grid_columnconfigure(1, weight=1)
        self._text_field(editor, 0, "整体形象", "appearance", 5)
        self._entry_field(editor, 1, "发型", "hair")
        self._entry_field(editor, 2, "服饰", "outfit")
        self._entry_field(editor, 3, "主色", "colors", hint="用逗号分隔")
        self._entry_field(editor, 4, "识别意象", "motifs", hint="用逗号分隔")
        self._text_field(editor, 5, "辨认规则", "self_recognition_notes", 4)
        self._text_field(editor, 6, "视觉边界", "boundaries", 3, hint="每行一条")
        tk.Label(
            editor,
            text=(
                "提示：描述越具体，角色越不容易把所有相似角色都认成自己。"
                "请只使用你已获授权的参考图。"
            ),
            bg=CARD,
            fg=MUTED,
            justify="left",
            wraplength=560,
            font=("Microsoft YaHei UI", 8),
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))

        assets = tk.Frame(
            body,
            bg=CARD,
            highlightthickness=1,
            highlightbackground="#eadde5",
            padx=16,
            pady=15,
        )
        assets.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(
            assets,
            text="头像与参考图",
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            assets,
            text="图片会复制到本项目的人格资产目录，不会上传。",
            bg=CARD,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(2, 10))
        self.avatar_label = tk.Label(
            assets,
            text="尚未导入头像",
            bg=SOFT,
            fg=MUTED,
            width=30,
            height=11,
            relief="flat",
        )
        self.avatar_label.pack(fill="x")
        actions = tk.Frame(assets, bg=CARD)
        actions.pack(fill="x", pady=(10, 8))
        ttk.Button(
            actions,
            text="导入头像",
            command=lambda: self._import(make_avatar=True),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="添加参考图",
            command=lambda: self._import(make_avatar=False),
        ).pack(side="left", padx=(7, 0))
        ttk.Button(
            actions,
            text="打开图片",
            command=self._open_selected_reference,
        ).pack(side="right")
        tk.Label(
            assets,
            text="参考图",
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(4, 4))
        list_host = tk.Frame(assets, bg=CARD)
        list_host.pack(fill="both", expand=True)
        self.reference_list = tk.Listbox(
            list_host,
            bg=SOFT,
            fg=INK,
            selectbackground=PINK,
            selectforeground="white",
            relief="flat",
            font=("Microsoft YaHei UI", 9),
            activestyle="none",
        )
        scrollbar = ttk.Scrollbar(
            list_host,
            orient="vertical",
            command=self.reference_list.yview,
        )
        self.reference_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.reference_list.pack(side="left", fill="both", expand=True)
        self.reference_list.bind(
            "<Double-Button-1>",
            lambda _event: self._open_selected_reference(),
        )
        ttk.Button(
            assets,
            text="移除选中的参考图",
            command=self._remove_reference,
        ).pack(anchor="w", pady=(8, 0))

    def _label(self, parent, row: int, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=CARD,
            fg=INK,
            font=("Microsoft YaHei UI", 9, "bold"),
            justify="left",
        ).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=6)

    def _entry_field(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        hint: str = "",
    ) -> None:
        label_text = label + (f"\n{hint}" if hint else "")
        self._label(parent, row, label_text)
        ttk.Entry(parent, textvariable=self.vars[key]).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=(5, 5),
        )

    def _text_field(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        height: int,
        hint: str = "",
    ) -> None:
        label_text = label + (f"\n{hint}" if hint else "")
        self._label(parent, row, label_text)
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            bg=SOFT,
            fg=INK,
            relief="flat",
            padx=8,
            pady=6,
            font=("Microsoft YaHei UI", 9),
        )
        text.grid(row=row, column=1, sticky="ew", pady=5)
        text.bind(
            "<<Modified>>",
            lambda event, key=key, widget=text: self._sync_text(event, key, widget),
        )
        setattr(self, f"text_{key}", text)

    def _sync_text(self, _event, key: str, widget: tk.Text) -> None:
        widget.edit_modified(False)
        self.vars[key].set(widget.get("1.0", "end-1c"))

    def _set_text(self, key: str, value: str) -> None:
        widget = getattr(self, f"text_{key}", None)
        if widget is None:
            return
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.edit_modified(False)
        self.vars[key].set(value)

    def _persona_id(self) -> str:
        return self.labels[self.selected_label.get()]

    def _persona_name(self) -> str:
        persona_id = self._persona_id()
        persona = next(
            (item for item in self.personas if item["id"] == persona_id),
            {},
        )
        return str(persona.get("display_name") or persona_id)

    def _load_selected(self) -> None:
        card = load_visual_card(self._persona_id())
        for key in (
            "appearance",
            "hair",
            "outfit",
            "self_recognition_notes",
        ):
            value = str(card.get(key) or "")
            if key in {"appearance", "self_recognition_notes"}:
                self._set_text(key, value)
            else:
                self.vars[key].set(value)
        self.vars["colors"].set("，".join(card.get("colors", [])))
        self.vars["motifs"].set("，".join(card.get("motifs", [])))
        self._set_text("boundaries", "\n".join(card.get("boundaries", [])))
        self._show_avatar(card.get("avatar_path", ""))
        self._show_references(card.get("reference_images", []))

    def _show_avatar(self, value: str) -> None:
        path = resolve_visual_path(value)
        self.preview_photo = None
        if path is None or not path.is_file():
            self.avatar_label.configure(image="", text="尚未导入头像")
            return
        if Image is None or ImageTk is None:
            self.avatar_label.configure(
                image="",
                text=f"已导入头像\n{path.name}",
            )
            return
        try:
            with Image.open(path) as image:
                image.thumbnail((280, 230), Image.Resampling.LANCZOS)
                preview = image.convert("RGB")
            self.preview_photo = ImageTk.PhotoImage(preview)
            self.avatar_label.configure(image=self.preview_photo, text="")
        except Exception:
            self.avatar_label.configure(
                image="",
                text=f"头像已保存\n{path.name}",
            )

    def _show_references(self, references: list[str]) -> None:
        self.reference_list.delete(0, "end")
        self.reference_map = {}
        for index, value in enumerate(references, 1):
            path = resolve_visual_path(value)
            label = f"{index:02d}  {path.name if path else value}"
            self.reference_map[label] = value
            self.reference_list.insert("end", label)
        if not references:
            self.reference_list.insert("end", "还没有参考图")

    def _save(self) -> None:
        values = {
            key: self.vars[key].get().strip()
            for key in (
                "appearance",
                "hair",
                "outfit",
                "self_recognition_notes",
            )
        }
        values["colors"] = [
            item.strip()
            for item in self.vars["colors"].get().replace(",", "，").split("，")
            if item.strip()
        ]
        values["motifs"] = [
            item.strip()
            for item in self.vars["motifs"].get().replace(",", "，").split("，")
            if item.strip()
        ]
        values["boundaries"] = [
            item.strip()
            for item in self.vars["boundaries"].get().splitlines()
            if item.strip()
        ]
        try:
            save_visual_card(self._persona_id(), values)
        except Exception as error:
            messagebox.showerror("保存失败", str(error), parent=self)
            return
        self._load_selected()
        messagebox.showinfo(
            "已保存",
            f"{self._persona_name()}的人格形象已更新，下一条消息开始生效。",
            parent=self,
        )

    def _import(self, *, make_avatar: bool) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="选择人格头像" if make_avatar else "选择人格参考图",
            filetypes=[
                ("图片", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            import_visual_reference(
                self._persona_id(),
                path,
                make_avatar=make_avatar,
            )
        except Exception as error:
            messagebox.showerror("导入失败", str(error), parent=self)
            return
        self._load_selected()

    def _selected_reference(self) -> str:
        selection = self.reference_list.curselection()
        if not selection:
            return ""
        label = self.reference_list.get(selection[0])
        return self.reference_map.get(label, "")

    def _open_selected_reference(self) -> None:
        value = self._selected_reference()
        path = resolve_visual_path(value)
        if path is None or not path.is_file():
            messagebox.showinfo("没有选中图片", "先在列表里选择一张参考图。", parent=self)
            return
        os.startfile(str(path))

    def _remove_reference(self) -> None:
        value = self._selected_reference()
        if not value:
            messagebox.showinfo("没有选中图片", "先在列表里选择一张参考图。", parent=self)
            return
        path = resolve_visual_path(value)
        if not messagebox.askyesno(
            "移除参考图",
            f"确定从{self._persona_name()}的形象卡中移除这张图片吗？\n\n"
            f"{path.name if path else value}\n\n"
            "文件会从本项目的人格资产目录删除。",
            icon="warning",
            default="no",
            parent=self,
        ):
            return
        try:
            remove_visual_reference(self._persona_id(), value)
        except Exception as error:
            messagebox.showerror("移除失败", str(error), parent=self)
            return
        self._load_selected()


def open_persona_visuals_center(parent: tk.Misc) -> PersonaVisualsCenter:
    existing = next(
        (
            child
            for child in parent.winfo_children()
            if isinstance(child, PersonaVisualsCenter) and child.winfo_exists()
        ),
        None,
    )
    if existing:
        existing.lift()
        existing.focus_force()
        return existing
    window = PersonaVisualsCenter(parent)
    window.focus_force()
    return window
