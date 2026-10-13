"""Reusable UI building blocks."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QLayout, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QAbstractItemView, QHeaderView,
)
from PySide6.QtGui import QColor, QPainter

from . import theme
from .icons import icon


def button(text: str, icon_name: str | None = None, variant: str | None = None,
           tooltip: str = "", size: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        btn.setProperty("variant", variant)
    if size:
        btn.setProperty("size", size)
    if icon_name:
        role = "on_accent" if variant == "primary" else ("danger" if variant == "danger" else "text")
        btn.setIcon(icon(icon_name, role))
        btn.setIconSize(QSize(16, 16))
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def field_label(text: str) -> QLabel:
    return label(text, "FieldLabel")


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    return line


def set_tone(widget: QWidget, tone: str | None) -> None:
    widget.setProperty("tone", tone or "")
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 20)
        self.body.setSpacing(spacing)
        self.header = None
        self.header_actions = None
        if title:
            self.header = QHBoxLayout()
            self.header.setSpacing(8)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            self.title_label = label(title, "CardTitle")
            text_col.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = label(subtitle, "CardSubtitle", wrap=True)
                text_col.addWidget(self.subtitle_label)
            self.header.addLayout(text_col, 1)
            self.header_actions = QHBoxLayout()
            self.header_actions.setSpacing(6)
            self.header.addLayout(self.header_actions)
            self.body.addLayout(self.header)

    def add(self, widget_or_layout, stretch: int = 0):
        if isinstance(widget_or_layout, QWidget):
            self.body.addWidget(widget_or_layout, stretch)
        else:
            self.body.addLayout(widget_or_layout, stretch)
        return widget_or_layout

    def add_action(self, widget: QWidget):
        if self.header_actions is not None:
            self.header_actions.addWidget(widget)
        return widget


class Pill(QLabel):
    def __init__(self, text: str = "", tone: str | None = None):
        super().__init__(text)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if tone:
            set_tone(self, tone)

    def set(self, text: str, tone: str | None = None):
        self.setText(text)
        set_tone(self, tone)


class IconLabel(QWidget):
    """Paints a theme-aware icon on every repaint, so it follows theme switches."""

    def __init__(self, icon_name: str, role: str = "text", size: int = 18):
        super().__init__()
        self.setFixedSize(size, size)
        self._icon = icon(icon_name, role)

    def set_icon(self, icon_name: str, role: str = "text"):
        self._icon = icon(icon_name, role)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._icon.paint(painter, self.rect())


class IconBadge(QFrame):
    def __init__(self, icon_name: str, tone: str = "accent", size: int = 40):
        super().__init__()
        self.setObjectName("StatIcon")
        self.setFixedSize(size, size)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.icon_label = IconLabel(icon_name, tone, int(size * 0.5))
        lay.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        if tone != "accent":
            set_tone(self, tone)


class StatCard(Card):
    def __init__(self, title: str, value: str = "0", icon_name: str = "mail", tone: str = "accent",
                 caption: str = ""):
        super().__init__(spacing=6)
        self.body.setContentsMargins(18, 16, 18, 16)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.badge = IconBadge(icon_name, tone)
        row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = label(title.upper(), "StatLabel")
        self.value = label(value, "StatValue")
        col.addWidget(self.title)
        col.addWidget(self.value)
        self.caption = label(caption, "Hint", wrap=True)
        self.caption.setVisible(bool(caption))
        col.addWidget(self.caption)
        row.addLayout(col, 1)
        self.body.addLayout(row)

    def set_value(self, value, caption: str | None = None):
        self.value.setText(str(value))
        if caption is not None:
            self.caption.setText(caption)
            self.caption.setVisible(bool(caption))


class Banner(QFrame):
    def __init__(self, text: str, tone: str = "warning", icon_name: str = "alert"):
        super().__init__()
        self.setObjectName("Banner")
        if tone != "warning":
            set_tone(self, tone)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        ico = IconLabel(icon_name, "warning" if tone == "warning" else "accent", 18)
        lay.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
        self.text = label(text, wrap=True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.text.setOpenExternalLinks(True)
        lay.addWidget(self.text, 1)


class Page(QWidget):
    """Scrollable page with a title header. Add content to ``self.content``."""

    def __init__(self, title: str, subtitle: str = "", scroll: bool = True):
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        inner.setObjectName("PageInner")
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(32, 26, 32, 28)
        self.content.setSpacing(18)

        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.title_label = label(title, "PageTitle")
        titles.addWidget(self.title_label)
        if subtitle:
            titles.addWidget(label(subtitle, "PageSubtitle", wrap=True))
        head.addLayout(titles, 1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        head.addLayout(self.header_actions)
        self.content.addLayout(head)

        if scroll:
            area = QScrollArea()
            area.setObjectName("PageScroll")
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(inner)
            outer.addWidget(area)
        else:
            outer.addWidget(inner)

    def on_show(self):
        """Called every time the page becomes visible."""


class Toast(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 11, 16, 11)
        lay.setSpacing(10)
        self.icon = IconLabel("mail", "bg", 18)
        lay.addWidget(self.icon)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setMaximumWidth(420)
        lay.addWidget(self.text)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)
        self._hiding = False
        self.anim.finished.connect(self._anim_finished)
        self.hide()

    def show_message(self, message: str, tone: str = "info", msecs: int = 3500):
        set_tone(self, tone if tone in ("success", "danger") else None)
        name = {"success": "check", "danger": "x-circle"}.get(tone, "mail")
        role = "on_accent" if tone in ("success", "danger") else "bg"
        self.icon.set_icon(name, role)
        self.text.setText(message)
        self.text.setFixedWidth(int(min(self.text.fontMetrics().horizontalAdvance(message) * 1.08 + 8, 440)))
        self.adjustSize()
        self.reposition()
        self.raise_()
        was_visible = self.isVisible()
        self.show()
        self._hiding = False
        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity() if was_visible else 0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(msecs)

    def _fade_out(self):
        self._hiding = True
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _anim_finished(self):
        if self._hiding:
            self.hide()

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = parent.width() - self.width() - 28
        y = parent.height() - self.height() - 28
        self.move(max(10, x), max(10, y))


def make_table(headers: list[str], stretch_column: int = -1) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(34)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    if stretch_column >= 0:
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
    else:
        header.setStretchLastSection(True)
    return table


def table_item(text, align_right: bool = False, data=None) -> QTableWidgetItem:
    item = QTableWidgetItem("" if text is None else str(text))
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if data is not None:
        item.setData(Qt.ItemDataRole.UserRole, data)
    return item


def status_item(status: str) -> QTableWidgetItem:
    colors = theme.current()
    tone = {"sent": "success", "failed": "danger", "skipped": "warning",
            "sending": "accent", "pending": "text_muted"}.get(status, "text_muted")
    item = QTableWidgetItem({"sent": "✓  Sent", "failed": "✕  Failed", "skipped": "–  Skipped",
                             "sending": "…  Sending", "pending": "Pending"}.get(status, status.title()))
    item.setForeground(QColor(colors[tone]))
    font = item.font()
    font.setBold(True)
    item.setFont(font)
    item.setData(Qt.ItemDataRole.UserRole, status)
    return item


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


class FlowLayout(QLayout):
    """Lays widgets out left-to-right, wrapping onto new lines when space runs out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect, apply):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        spacing = self.spacing()
        lines, line, line_width = [], [], 0
        for item in self._items:
            w = item.sizeHint().width()
            if line and line_width + spacing + w > area.width():
                lines.append(line)
                line, line_width = [], 0
            line_width += (spacing if line else 0) + w
            line.append(item)
        if line:
            lines.append(line)
        y = area.y()
        for line in lines:
            height = max(i.sizeHint().height() for i in line)
            x = area.x()
            for item in line:
                hint = item.sizeHint()
                if apply:
                    item.setGeometry(QRect(QPoint(x, y + (height - hint.height()) // 2), hint))
                x += hint.width() + spacing
            y += height + spacing
        return (y - spacing if lines else y) - rect.y() + m.bottom()
