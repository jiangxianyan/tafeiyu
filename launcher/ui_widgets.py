"""Rounded, dark-theme controls drawn with Tk canvases."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

from ui_theme import (
    BG_DEEP,
    BORDER,
    INK,
    MUTED,
    PINK,
    PINK_SOFT,
    RED,
    SIDEBAR,
    SURFACE_ALT,
    SURFACE_SOFT,
)


def set_windows_app_user_model_id(
    app_id: str = "com.tafeiyu.desktop",
) -> None:
    """Give the Python-hosted desktop client its own Windows taskbar identity."""

    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(app_id)
        )
    except Exception:
        pass


def apply_windows_window_icon(
    window: tk.Misc,
    icon_path: str | Path,
) -> None:
    """Use the ICO for both the title area and the Windows taskbar button."""

    path = Path(icon_path)
    if sys.platform != "win32" or not path.is_file():
        return
    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = wintypes.LPARAM
        get_class_icon = getattr(
            user32,
            "GetClassLongPtrW",
            user32.GetClassLongW,
        )
        set_class_icon = getattr(
            user32,
            "SetClassLongPtrW",
            user32.SetClassLongW,
        )
        get_class_icon.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
        ]
        get_class_icon.restype = ctypes.c_ssize_t
        set_class_icon.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_ssize_t,
        ]
        set_class_icon.restype = ctypes.c_ssize_t
        hwnd = int(window.winfo_id())
        parent = int(user32.GetParent(hwnd))
        if parent:
            hwnd = parent
        load_from_file = 0x00000010
        load_default_size = 0x00000040
        hicon = user32.LoadImageW(
            None,
            str(path),
            1,
            0,
            0,
            load_from_file | load_default_size,
        )
        hicon_small = user32.LoadImageW(
            None,
            str(path),
            1,
            16,
            16,
            load_from_file,
        )
        if hicon:
            user32.SendMessageW(hwnd, 0x0080, 1, hicon)
            set_class_icon(hwnd, -14, int(hicon))
        if hicon_small:
            user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)
            set_class_icon(hwnd, -34, int(hicon_small))
        window._tafeiyu_icon_handles = (hicon, hicon_small)
    except Exception:
        pass


def _parent_bg(widget: tk.Misc, fallback: str = BG_DEEP) -> str:
    try:
        value = widget.cget("bg")
        return str(value) if value else fallback
    except tk.TclError:
        return fallback


def apply_windows_dark_frame(
    window: tk.Misc,
    *,
    border: str | None = None,
    caption: str = SIDEBAR,
    text: str = INK,
) -> None:
    """Apply the dark DWM frame color on Windows 11."""

    if sys.platform != "win32":
        return

    def color_ref(value: str) -> int:
        value = value.lstrip("#")
        red, green, blue = (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
        return red | (green << 8) | (blue << 16)

    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        hwnd = int(window.winfo_id())
        parent = int(user32.GetParent(hwnd))
        if parent:
            hwnd = parent
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        style = int(get_style(hwnd, -20))
        style = (style | 0x00040000) & ~0x00000080
        set_style(hwnd, -20, style)
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            0x0001 | 0x0002 | 0x0004 | 0x0020,
        )
        enabled = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,
            ctypes.byref(enabled),
            ctypes.sizeof(enabled),
        )
        # DWMWA_COLOR_NONE disables the Windows 11 accent border entirely.
        border_value = ctypes.c_uint(0xFFFFFFFE)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            34,
            ctypes.byref(border_value),
            ctypes.sizeof(border_value),
        )
        for attribute, value in ((35, caption), (36, text)):
            color = ctypes.c_int(color_ref(value))
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(color),
                ctypes.sizeof(color),
            )
    except Exception:
        return


def _rounded_rectangle(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs,
):
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=30,
        **kwargs,
    )


class RoundedButton(tk.Canvas):
    """A compact canvas button with hover and disabled states."""

    PALETTES = {
        "primary": {
            "fill": PINK,
            "hover": "#FFA2CA",
            "pressed": "#E56CA3",
            "text": BG_DEEP,
            "border": PINK,
        },
        "secondary": {
            "fill": SURFACE_ALT,
            "hover": SURFACE_SOFT,
            "pressed": "#23304A",
            "text": INK,
            "border": BORDER,
        },
        "danger": {
            "fill": "#2A1720",
            "hover": "#3B1D2B",
            "pressed": "#24131B",
            "text": RED,
            "border": "#5B2C3E",
        },
        "ghost": {
            "fill": "",
            "hover": SURFACE_ALT,
            "pressed": SURFACE_SOFT,
            "text": MUTED,
            "border": "",
        },
    }

    def __init__(
        self,
        parent: tk.Misc,
        *,
        text: str,
        command: Callable[[], None] | None = None,
        kind: str = "secondary",
        height: int = 36,
        min_width: int = 82,
        padding: int = 15,
        font: tuple = ("Microsoft YaHei UI", 9),
        state: str = "normal",
    ) -> None:
        self._parent_bg = _parent_bg(parent)
        self._font = tkfont.Font(font=font)
        text_width = self._font.measure(str(text))
        width = max(min_width, text_width + padding * 2)
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=self._parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._text = str(text)
        self._command = command
        self._kind = kind if kind in self.PALETTES else "secondary"
        self._height = height
        self._width = width
        self._state = state
        self._hover = False
        self._pressed = False
        self._shape = None
        self._label = None
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _palette(self) -> dict[str, str]:
        palette = dict(self.PALETTES[self._kind])
        if not palette["fill"]:
            palette["fill"] = self._parent_bg
        if self._state == "disabled":
            palette.update(
                {
                    "fill": SURFACE_ALT,
                    "hover": SURFACE_ALT,
                    "pressed": SURFACE_ALT,
                    "text": "#59647B",
                    "border": "#202A3C",
                }
            )
            return palette
        if self._pressed:
            palette["fill"] = palette["pressed"]
        elif self._hover:
            palette["fill"] = palette["hover"]
        return palette

    def _draw(self) -> None:
        self.delete("all")
        palette = self._palette()
        outline = palette["border"] or palette["fill"]
        _rounded_rectangle(
            self,
            1,
            1,
            self._width - 1,
            self._height - 1,
            min(13, self._height / 2 - 1),
            fill=palette["fill"],
            outline=outline,
            width=1,
        )
        self._label = self.create_text(
            self._width / 2,
            self._height / 2,
            text=self._text,
            fill=palette["text"],
            font=self._font,
            anchor="center",
        )
        if self._state == "disabled":
            self.configure(cursor="arrow")
        else:
            self.configure(cursor="hand2")

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None) -> None:
        if self._state != "disabled":
            self._pressed = True
            self._draw()

    def _on_release(self, event=None) -> None:
        should_invoke = self._pressed and self._state != "disabled"
        self._pressed = False
        self._draw()
        if (
            should_invoke
            and event is not None
            and 0 <= event.x <= self._width
            and 0 <= event.y <= self._height
            and self._command is not None
        ):
            self._command()

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        text = kwargs.pop("text", None)
        command = kwargs.pop("command", None)
        if state is not None:
            self._state = str(state)
        if text is not None:
            self._text = str(text)
        if command is not None:
            self._command = command
        if state is not None or text is not None:
            self._draw()
        if cnf or kwargs:
            return super().configure(cnf, **kwargs)
        return None

    config = configure

    def set_enabled(self, enabled: bool) -> None:
        self._state = "normal" if enabled else "disabled"
        self._draw()

    def invoke(self) -> None:
        if self._state != "disabled" and self._command is not None:
            self._command()


class NavPill(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        text: str,
        command: Callable[[], None],
    ) -> None:
        self._parent_bg = _parent_bg(parent, SIDEBAR)
        super().__init__(
            parent,
            width=210,
            height=42,
            bg=self._parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._text = text
        self._command = command
        self._active = False
        self._hover = False
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", lambda _event: self._command())
        self._draw()

    def _enter(self, _event=None) -> None:
        self._hover = True
        self._draw()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._draw()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        if self._active:
            fill, text_color = PINK_SOFT, PINK
        elif self._hover:
            fill, text_color = SURFACE_ALT, INK
        else:
            fill, text_color = self._parent_bg, MUTED
        _rounded_rectangle(
            self,
            1,
            1,
            209,
            41,
            12,
            fill=fill,
            outline=PINK if self._active else fill,
            width=1,
        )
        if self._active:
            self.create_oval(15, 18, 21, 24, fill=PINK, outline="")
        self.create_text(
            29 if self._active else 24,
            21,
            text=self._text,
            anchor="w",
            fill=text_color,
            font=("Microsoft YaHei UI", 10, "bold" if self._active else "normal"),
        )
