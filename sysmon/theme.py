"""Palette matching mock/mockup.png (dark navy, cyan accents)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont


@dataclass(frozen=True)
class Theme:
    window_bg: str = "#0d1526"
    window_border: str = "#1e2a44"

    card_bg: str = "#0f1930"
    card_border: str = "#1e2a44"
    card_highlight_bg: str = "#0c2030"
    card_highlight_border: str = "#22d3ee"

    accent_cyan: str = "#22d3ee"
    accent_blue: str = "#3b82f6"
    accent_amber: str = "#f5b942"
    accent_green: str = "#22c55e"
    accent_red: str = "#ef4444"

    text: str = "#e2e8f0"
    text_muted: str = "#94a3b8"
    text_faint: str = "#64748b"

    track: str = "#1b2942"

    font_family: str = "Noto Sans"
    font_size_sm: int = 12
    font_size_md: int = 13
    font_size_lg: int = 15
    font_size_xl: int = 16

    def color(self, hex_color: str) -> QColor:
        return QColor(hex_color)

    def font(self, pixel_size: int, bold: bool = False) -> QFont:
        font = QFont(self.font_family)
        font.setPixelSize(pixel_size)
        font.setBold(bold)
        return font


THEME = Theme()
