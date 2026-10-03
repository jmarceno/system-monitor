"""Shared painted widgets: grid cells, bars, chips, sparklines."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ..theme import THEME


def paint_rounded(painter: QPainter, rect: QRectF, bg: str, border: str, radius: float, width: float = 1.0) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, QColor(bg))
    if width > 0:
        painter.setPen(QPen(QColor(border), width))
        painter.drawPath(path)


class Text(QLabel):
    def __init__(
        self,
        text: str = "",
        color: str = THEME.text,
        size: int = THEME.font_size_sm,
        bold: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setFont(THEME.font(size, bold))
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(0)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"color: {color}; background: transparent;")

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        if self.wordWrap():
            return QSize(48, self.fontMetrics().lineSpacing())
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), 220), self.fontMetrics().height() + 2)

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        if self.wordWrap() and self.width() > 48:
            return QSize(self.width(), max(hint.height(), self.heightForWidth(self.width())))
        return QSize(min(hint.width(), 280), max(hint.height(), self.fontMetrics().height() + 2))


class ElideText(Text):
    """Single-line label that shrinks with its cell instead of forcing the layout wider."""

    def __init__(
        self,
        text: str = "",
        color: str = THEME.text,
        size: int = THEME.font_size_sm,
        bold: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        self._full = text
        super().__init__(text, color, size, bold, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self._apply()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(80, self.fontMetrics().height() + 2)

    def _apply(self) -> None:
        width = self.contentsRect().width()
        if width < 8:
            shown = self._full
        else:
            shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, width)
        if shown != self.text():
            QLabel.setText(self, shown)


class GridCell(QWidget):
    """One cell of the application grid. Cells share edges; they are not separate panels."""

    def __init__(self, parent: QWidget | None = None, *, min_height: int = 96, grow: bool = True) -> None:
        super().__init__(parent)
        vertical = QSizePolicy.Policy.Expanding if grow else QSizePolicy.Policy.Preferred
        self.setSizePolicy(QSizePolicy.Policy.Expanding, vertical)
        self.setMinimumSize(160, min_height)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self._layout.addWidget(widget, stretch)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(THEME.window_bg))
        painter.setPen(QPen(QColor(THEME.window_border), 1))
        right = self.width() - 1
        bottom = self.height() - 1
        painter.drawLine(right, 0, right, bottom)
        painter.drawLine(0, bottom, right, bottom)


def fill_bg(widget: QWidget) -> None:
    palette = widget.palette()
    color = QColor(THEME.window_bg)
    palette.setColor(QPalette.ColorRole.Window, color)
    palette.setColor(QPalette.ColorRole.Base, color)
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


class FlatBody(QWidget):
    """Scroll content that always paints the window background."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        fill_bg(self)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(THEME.window_bg))


class FitScroll(QScrollArea):
    """Scrolls inside a grid cell. Its own size hint stays small so lists cannot blow up the window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            f"QScrollArea {{ background: {THEME.window_bg}; border: none; }}"
            f"QScrollBar:vertical {{ background: {THEME.window_bg}; width: 8px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {THEME.track}; border-radius: 3px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {THEME.window_bg}; }}"
        )
        fill_bg(self)
        fill_bg(self.viewport())
        self.viewport().setStyleSheet(f"background: {THEME.window_bg};")

    def setWidget(self, widget: QWidget) -> None:  # noqa: N802
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        fill_bg(widget)
        super().setWidget(widget)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 48)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 120)


class RoundedPanel(QWidget):
    def __init__(
        self,
        bg: str = THEME.card_bg,
        border: str = THEME.card_border,
        radius: int = 12,
        border_width: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bg = bg
        self._border = border
        self._radius = radius
        self._border_width = border_width
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_chrome(self, bg: str, border: str, border_width: float = 1.0) -> None:
        self._bg = bg
        self._border = border
        self._border_width = border_width
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        inset = max(1.0, self._border_width)
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        paint_rounded(painter, rect, self._bg, self._border, self._radius, self._border_width)


class Bar(QWidget):
    def __init__(self, parent: QWidget | None = None, height: int = 12) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._fill = THEME.accent_cyan
        self.setFixedHeight(height)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(100.0, value))
        self.update()

    def set_fill(self, color: str) -> None:
        self._fill = color
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(track, self.height() / 2, self.height() / 2)
        painter.fillPath(path, QColor(THEME.track))
        frac = self._value / 100.0
        if frac <= 0:
            return
        width = max(8.0 if self.width() > 0 else 0.0, self.width() * frac)
        fill = QRectF(track.x(), track.y(), min(width, track.width()), track.height())
        fill_path = QPainterPath()
        fill_path.addRoundedRect(fill, self.height() / 2, self.height() / 2)
        painter.fillPath(fill_path, QColor(self._fill))


class Sparkline(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[float] = []
        self._color = THEME.accent_cyan
        self.setFixedHeight(18)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_history(self, history: list[float], color: str | None = None) -> None:
        self._history = list(history or [])
        if color:
            self._color = color
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if len(self._history) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        peak = max(1.0, max(self._history))
        step = self.width() / (len(self._history) - 1)
        points = []
        for index, value in enumerate(self._history):
            x = index * step
            y = self.height() - 2 - (self.height() - 4) * (value / peak)
            points.append(QPointF(x, y))
        painter.setPen(QPen(QColor(self._color), 1.5))
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)


class Chip(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(4)
        self._label = Text(label, THEME.text_faint, THEME.font_size_sm, parent=self)
        self._value = Text("", THEME.text, THEME.font_size_sm, bold=True, parent=self)
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def set_value(self, value: str, color: str = THEME.text) -> None:
        self._value.setText(value)
        self._value.set_color(color)


class Card(GridCell):
    def __init__(
        self,
        title: str,
        icon: str,
        icon_color: str = THEME.accent_cyan,
        parent: QWidget | None = None,
        *,
        min_height: int = 72,
    ) -> None:
        super().__init__(parent, min_height=min_height, grow=False)
        _ = icon  # kept so existing call sites stay stable; section titles replaced the icon chips
        header = QHBoxLayout()
        header.setSpacing(8)
        self._title = ElideText(title, icon_color, THEME.font_size_lg, bold=True, parent=self)
        header.addWidget(self._title, 0)
        header.addStretch(1)
        self.extras = QHBoxLayout()
        self.extras.setSpacing(6)
        header.addLayout(self.extras, 0)
        self._layout.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self._layout.addLayout(self.body, 1)

    def set_title(self, title: str) -> None:
        self._title.setText(title)
