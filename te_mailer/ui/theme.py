"""Light and dark themes (palette + Qt style sheet)."""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette

PALETTES = {
    "light": {
        "bg": "#F2F5F9", "surface": "#FFFFFF", "surface_alt": "#F6F8FB", "sidebar": "#FFFFFF",
        "border": "#E2E8F0", "border_strong": "#CBD5E1", "text": "#0F172A", "text_muted": "#64748B",
        "accent": "#0B7A8F", "accent_hover": "#096B7E", "accent_pressed": "#075A6A",
        "accent_soft": "#E2F3F6", "accent2": "#14A3B8", "on_accent": "#FFFFFF",
        "danger": "#DC2626", "danger_soft": "#FDECEC", "success": "#15803D", "success_soft": "#E6F6EC",
        "warning": "#B45309", "warning_soft": "#FEF3E2", "input": "#FFFFFF", "selection": "#CBEAF0",
        "gold": "#E0A526", "shadow": "#0F172A",
    },
    "dark": {
        "bg": "#0A101B", "surface": "#111A29", "surface_alt": "#162133", "sidebar": "#0D1522",
        "border": "#1F2B40", "border_strong": "#2C3B55", "text": "#E6ECF5", "text_muted": "#8B9AB1",
        "accent": "#1597AD", "accent_hover": "#1BA8C0", "accent_pressed": "#12849A",
        "accent_soft": "#11303B", "accent2": "#3CC7DC", "on_accent": "#FFFFFF",
        "danger": "#F05252", "danger_soft": "#3A1A20", "success": "#34C77B", "success_soft": "#11301F",
        "warning": "#F5A524", "warning_soft": "#3A2A12", "input": "#0D1522", "selection": "#1C4A57",
        "gold": "#F0B840", "shadow": "#000000",
    },
}

_mode = "light"
_arrow_paths: dict[str, str] = {}


def mode() -> str:
    return _mode


def current() -> dict:
    return PALETTES[_mode]


def _palette(c: dict) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Base, QColor(c["input"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface_alt"]))
    p.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Button, QColor(c["surface"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(c["on_accent"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["surface"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_muted"]))
    p.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["text_muted"]))
    return p


QSS = Template(r"""
* { font-family: "Segoe UI", "Segoe UI Variable", "Inter", "Helvetica Neue", Arial, sans-serif; font-size: 10pt; }
QMainWindow, QDialog { background: $bg; }
QWidget { color: $text; }
QWidget#Page, QWidget#PageInner, QScrollArea#PageScroll, QStackedWidget#Pages { background: $bg; border: none; }
QToolTip { background: $surface; color: $text; border: 1px solid $border_strong; padding: 6px 8px; border-radius: 6px; }

/* ---------- sidebar ---------- */
QFrame#Sidebar { background: $sidebar; border: none; border-right: 1px solid $border; }
QLabel#BrandTitle { font-size: 12.5pt; font-weight: 700; color: $text; }
QLabel#BrandSubtitle { font-size: 8.5pt; color: $text_muted; letter-spacing: 0.5px; }
QLabel#BrandLogo { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $accent, stop:1 $accent2); border-radius: 12px; }
QLabel#NavSection { color: $text_muted; font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 10px 14px 4px 14px; }
QPushButton#NavButton { text-align: left; padding: 10px 14px; border: none; border-radius: 9px; background: transparent; color: $text_muted; font-weight: 600; font-size: 10pt; }
QPushButton#NavButton:hover { background: $surface_alt; color: $text; }
QPushButton#NavButton:checked { background: $accent; color: $on_accent; }
QFrame#SidebarStatus { background: $surface_alt; border: 1px solid $border; border-radius: 10px; }
QLabel#SidebarStatusText { color: $text_muted; font-size: 8.5pt; }
QPushButton#ThemeToggle { text-align: left; padding: 9px 14px; border: 1px solid $border; border-radius: 9px; background: $surface_alt; color: $text; font-weight: 600; }
QPushButton#ThemeToggle:hover { border-color: $accent; }

/* ---------- typography ---------- */
QLabel#PageTitle { font-size: 19pt; font-weight: 700; color: $text; }
QLabel#PageSubtitle { color: $text_muted; font-size: 10pt; }
QLabel#CardTitle { font-size: 11pt; font-weight: 700; color: $text; }
QLabel#CardSubtitle, QLabel#Muted { color: $text_muted; }
QLabel#FieldLabel { color: $text_muted; font-weight: 600; font-size: 9pt; }
QLabel#StatValue { font-size: 21pt; font-weight: 700; color: $text; }
QLabel#StatLabel { color: $text_muted; font-size: 9pt; font-weight: 600; }
QLabel#BigCounter { font-size: 28pt; font-weight: 700; color: $text; }
QLabel#Countdown { font-size: 22pt; font-weight: 700; color: $accent; }
QLabel#Hint { color: $text_muted; font-size: 9pt; }
QLabel#Pill { border-radius: 10px; padding: 3px 10px; font-weight: 700; font-size: 8.5pt; background: $surface_alt; color: $text_muted; }
QLabel#Pill[tone="success"] { background: $success_soft; color: $success; }
QLabel#Pill[tone="danger"] { background: $danger_soft; color: $danger; }
QLabel#Pill[tone="warning"] { background: $warning_soft; color: $warning; }
QLabel#Pill[tone="accent"] { background: $accent_soft; color: $accent; }
QFrame#Banner { border-radius: 10px; background: $warning_soft; border: 1px solid $warning; }
QFrame#Banner[tone="accent"] { background: $accent_soft; border: 1px solid $accent; }
QFrame#Banner QLabel { color: $text; }
QFrame#StatIcon { border-radius: 10px; background: $accent_soft; }
QFrame#StatIcon[tone="success"] { background: $success_soft; }
QFrame#StatIcon[tone="danger"] { background: $danger_soft; }
QFrame#StatIcon[tone="warning"] { background: $warning_soft; }

/* ---------- cards ---------- */
QFrame#Card { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#Divider { background: $border; max-height: 1px; min-height: 1px; border: none; }

/* ---------- buttons ---------- */
QPushButton { background: $surface; color: $text; border: 1px solid $border_strong; border-radius: 8px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background: $surface_alt; border-color: $accent; }
QPushButton:pressed { background: $accent_soft; }
QPushButton:disabled { color: $text_muted; background: $surface_alt; border-color: $border; }
QPushButton[variant="primary"] { background: $accent; color: $on_accent; border: 1px solid $accent; }
QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[variant="primary"]:pressed { background: $accent_pressed; }
QPushButton[variant="primary"]:disabled { background: $border_strong; border-color: $border_strong; color: $surface; }
QPushButton[variant="danger"] { background: $surface; color: $danger; border: 1px solid $danger; }
QPushButton[variant="danger"]:hover { background: $danger_soft; }
QPushButton[variant="danger"]:disabled { color: $text_muted; border-color: $border; background: $surface_alt; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; color: $text_muted; }
QPushButton[variant="ghost"]:hover { background: $surface_alt; color: $text; border-color: $border; }
QPushButton[size="large"] { padding: 11px 22px; font-size: 10.5pt; }
QPushButton::menu-indicator { image: none; width: 0; }

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QDateEdit, QDateTimeEdit, QTextBrowser {
    background: $input; color: $text; border: 1px solid $border_strong; border-radius: 8px; padding: 6px 9px;
    selection-background-color: $selection; selection-color: $text; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus { border: 1px solid $accent; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: $text_muted; background: $surface_alt; }
QLineEdit[large="true"] { padding: 9px 12px; font-size: 11pt; }
QTextEdit#EmailPaper, QTextBrowser#EmailPaper { background: #FFFFFF; color: #1F2937; border: 1px solid $border_strong; border-radius: 10px; padding: 18px 22px; selection-background-color: #CBEAF0; selection-color: #0F172A; }
QTextEdit#EmailPaper:focus { border: 1px solid $accent; }
QComboBox { padding-right: 26px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }
QComboBox::down-arrow { image: url("$chevron_down"); width: 11px; height: 11px; }
QComboBox QAbstractItemView { background: $surface; color: $text; border: 1px solid $border_strong; selection-background-color: $accent_soft; selection-color: $text; outline: 0; padding: 4px; }
QSpinBox, QDateEdit { padding-left: 10px; padding-right: 24px; }
QSpinBox::up-button, QDateEdit::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; margin-top: 2px; margin-right: 2px; }
QSpinBox::down-button, QDateEdit::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; margin-bottom: 2px; margin-right: 2px; }
QSpinBox::up-arrow, QDateEdit::up-arrow { image: url("$chevron_up"); width: 9px; height: 9px; }
QSpinBox::down-arrow, QDateEdit::down-arrow { image: url("$chevron_down"); width: 9px; height: 9px; }
QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }
QCheckBox, QRadioButton { spacing: 8px; color: $text; }
QCalendarWidget QWidget { alternate-background-color: $surface_alt; }
QCalendarWidget QToolButton { color: $text; background: transparent; padding: 4px 8px; border-radius: 6px; }
QCalendarWidget QToolButton:hover { background: $accent_soft; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: $surface; }
QCalendarWidget QAbstractItemView:enabled { background: $surface; color: $text; selection-background-color: $accent; selection-color: $on_accent; }

/* ---------- editor toolbar ---------- */
QFrame#EditorToolbar { background: $surface_alt; border: 1px solid $border; border-radius: 10px; }
QToolButton#EditorTool { border: 1px solid transparent; border-radius: 6px; padding: 4px; background: transparent; color: $text; }
QToolButton#EditorTool:hover { background: $surface; border-color: $border; }
QToolButton#EditorTool:checked { background: $accent_soft; border-color: $accent; }
QToolButton#EditorTool::menu-indicator { image: none; width: 0; }
QFrame#ToolSep { background: $border_strong; min-width: 1px; max-width: 1px; margin: 4px 3px; }

/* ---------- progress ---------- */
QProgressBar { background: $surface_alt; border: 1px solid $border; border-radius: 9px; min-height: 18px; max-height: 18px; text-align: center; color: $text; font-weight: 700; font-size: 8.5pt; }
QProgressBar::chunk { border-radius: 8px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent2); }
QProgressBar#BigProgress { min-height: 26px; max-height: 26px; border-radius: 13px; font-size: 10pt; }
QProgressBar#BigProgress::chunk { border-radius: 12px; }
QProgressBar#ThinProgress { min-height: 6px; max-height: 6px; border-radius: 3px; border: none; }
QProgressBar#ThinProgress::chunk { border-radius: 3px; }

/* ---------- tables / lists ---------- */
QTableView, QTableWidget, QListWidget, QTreeWidget { background: $surface; alternate-background-color: $surface_alt; color: $text; gridline-color: $border; border: 1px solid $border; border-radius: 10px; selection-background-color: $selection; selection-color: $text; outline: 0; }
QTableView::item, QTableWidget::item { padding: 4px 6px; border: none; }
QListWidget::item { padding: 6px; border-radius: 6px; }
QListWidget::item:selected { background: $selection; color: $text; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section { background: $surface_alt; color: $text_muted; padding: 8px 8px; border: none; border-bottom: 1px solid $border; font-weight: 700; font-size: 8.5pt; }
QTableCornerButton::section { background: $surface_alt; border: none; }

/* ---------- tabs ---------- */
QTabWidget::pane { border: none; top: -1px; }
QTabBar::tab { background: transparent; color: $text_muted; padding: 8px 16px; margin-right: 4px; border: none; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected { color: $accent; border-bottom: 2px solid $accent; }

/* ---------- scroll bars ---------- */
QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
QScrollBar::handle:vertical { background: $border_strong; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: $text_muted; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border_strong; border-radius: 4px; min-width: 32px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ---------- menus, splitters, misc ---------- */
QMenu { background: $surface; color: $text; border: 1px solid $border_strong; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 22px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::separator { height: 1px; background: $border; margin: 4px 6px; }
QSplitter::handle { background: transparent; }
QStatusBar { background: $surface; color: $text_muted; border-top: 1px solid $border; }
QFrame#Toast { background: $text; border-radius: 10px; }
QFrame#Toast QLabel { color: $bg; font-weight: 600; }
QFrame#Toast[tone="success"] { background: $success; }
QFrame#Toast[tone="danger"] { background: $danger; }
QFrame#Toast[tone="success"] QLabel, QFrame#Toast[tone="danger"] QLabel { color: #FFFFFF; }
QMessageBox QLabel { color: $text; }
QGroupBox { border: 1px solid $border; border-radius: 10px; margin-top: 14px; padding: 12px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: $text_muted; }
""")


def _arrow(name: str, color: str) -> str:
    from ..core.storage import sub_dir
    from .icons import render_png

    key = f"{name}-{color.strip('#')}"
    if key not in _arrow_paths:
        path = sub_dir("ui-cache") / f"{key}.png"
        if not path.exists():
            render_png(name, color, 32, str(path))
        _arrow_paths[key] = str(path).replace("\\", "/")
    return _arrow_paths[key]


def stylesheet(c: dict) -> str:
    values = dict(c)
    values["chevron_down"] = _arrow("chevron-down", c["text_muted"])
    values["chevron_up"] = _arrow("chevron-up", c["text_muted"])
    return QSS.substitute(values)


def apply(app, new_mode: str) -> None:
    global _mode
    _mode = new_mode if new_mode in PALETTES else "light"
    c = current()
    app.setPalette(_palette(c))
    app.setStyleSheet(stylesheet(c))
