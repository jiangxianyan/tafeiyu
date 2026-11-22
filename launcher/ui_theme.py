"""Shared visual tokens for the tafeiyu desktop client."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKGROUND_ASSET = ROOT / "assets" / "ui" / "tafeiyu_aurora.png"
LOCAL_APP_ICON = ROOT / "assets" / "local" / "tafeiyu.ico"
LOCAL_TITLE_ICON = ROOT / "assets" / "local" / "tafeiyu_titlebar.png"
APP_ICON = LOCAL_APP_ICON if LOCAL_APP_ICON.is_file() else ROOT / "icons" / "start.ico"

BG = "#080C15"
BG_DEEP = "#050810"
SIDEBAR = "#0C1220"
SURFACE = "#111A2A"
CARD = SURFACE
SURFACE_ALT = "#172135"
SURFACE_SOFT = "#1C2740"
SOFT = SURFACE_SOFT
BORDER = "#2A3652"
BORDER_ACTIVE = "#75557B"
INK = "#F5F2FA"
MUTED = "#9AA7C2"
SUBTLE = "#6F7C98"
PINK = "#FF83B9"
PINK_DEEP = "#D95C98"
PINK_SOFT = "#3A2032"
CYAN = "#67D8FF"
CYAN_SOFT = "#17354A"
GOLD = "#F2C879"
GREEN = "#68D7A9"
GREEN_SOFT = "#16362F"
ORANGE = "#F0A75B"
ORANGE_SOFT = "#3A2B1B"
RED = "#FF7087"

FONT = "Microsoft YaHei UI"
TITLE_FONT = (FONT, 20, "bold")
PAGE_FONT = (FONT, 10)
SMALL_FONT = (FONT, 8)
