"""Main window: sidebar navigation + page stack."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from . import theme
from .icons import icon
from .pages.automation import AutomationPage
from .pages.compose import ComposePage
from .pages.dashboard import DashboardPage
from .pages.history import HistoryPage
from .pages.outlook import OutlookPage
from .pages.quick_send import QuickSendPage
from .pages.recipients import RecipientsPage
from .pages.settings import SettingsPage
from .pages.signature import SignaturePage
from .state import AppState
from .widgets import IconLabel, Toast, label

NAV = [
    ("WORKSPACE", [
        ("dashboard", "Dashboard", "dashboard"),
        ("compose", "Compose email", "compose"),
        ("recipients", "Recipients", "users"),
        ("automation", "Automation", "zap"),
    ]),
    ("TOOLS", [
        ("quick", "Write & send", "mail"),
        ("signature", "Signature", "id-card"),
        ("outlook", "Outlook data", "database"),
        ("history", "History", "history"),
        ("settings", "Settings", "settings"),
    ]),
]


class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1180, 740)
        self.resize(1460, 920)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        root_layout.addWidget(self.stack, 1)

        self.pages = {
            "dashboard": DashboardPage(state),
            "compose": ComposePage(state),
            "recipients": RecipientsPage(state),
            "automation": AutomationPage(state),
            "quick": QuickSendPage(state),
            "signature": SignaturePage(state),
            "outlook": OutlookPage(state),
            "history": HistoryPage(state),
            "settings": SettingsPage(state, self.set_theme),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.toast = Toast(self)
        state.toast.connect(self.toast.show_message)
        state.navigate.connect(self.navigate)
        state.campaign_status.connect(self._campaign_status)
        self.navigate("dashboard")

    # ------------------------------------------------------------ sidebar
    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(250)
        col = QVBoxLayout(bar)
        col.setContentsMargins(16, 20, 16, 16)
        col.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = label("", "BrandLogo")
        logo.setFixedSize(42, 42)
        inner = QVBoxLayout(logo)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(IconLabel("plane", "on_accent", 22), 0, Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Travel Essence", "BrandTitle"))
        names.addWidget(label("EMAIL STUDIO", "BrandSubtitle"))
        brand.addLayout(names, 1)
        col.addLayout(brand)
        col.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for section, items in NAV:
            col.addWidget(label(section, "NavSection"))
            for key, text, icon_name in items:
                btn = QPushButton("  " + text.replace("&", "&&"))
                btn.setObjectName("NavButton")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setIcon(icon(icon_name, "text_muted", "on_accent"))
                btn.setIconSize(QSize(18, 18))
                btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
                self.nav_group.addButton(btn)
                self.nav_buttons[key] = btn
                col.addWidget(btn)
            col.addSpacing(8)
        col.addStretch(1)

        self.campaign_box = QFrame()
        self.campaign_box.setObjectName("SidebarStatus")
        box = QVBoxLayout(self.campaign_box)
        box.setContentsMargins(12, 10, 12, 12)
        box.setSpacing(6)
        self.campaign_text = label("", "SidebarStatusText", wrap=True)
        box.addWidget(self.campaign_text)
        self.campaign_bar = QProgressBar()
        self.campaign_bar.setObjectName("ThinProgress")
        self.campaign_bar.setTextVisible(False)
        box.addWidget(self.campaign_bar)
        self.campaign_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.campaign_box.mousePressEvent = lambda _e: self.navigate("automation")
        self.campaign_box.hide()
        col.addWidget(self.campaign_box)
        col.addSpacing(8)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeToggle")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setIconSize(QSize(18, 18))
        self.theme_btn.clicked.connect(self.toggle_theme)
        col.addWidget(self.theme_btn)
        col.addSpacing(6)
        version = label(f"v{__version__}", "Hint")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(version)
        self._update_theme_button()
        return bar

    def _update_theme_button(self):
        dark = theme.mode() == "dark"
        self.theme_btn.setText("  Light mode" if dark else "  Dark mode")
        self.theme_btn.setIcon(icon("sun" if dark else "moon", "text"))
        self.theme_btn.setToolTip("Switch between light and dark theme")

    # ------------------------------------------------------------ actions
    def navigate(self, key: str):
        page = self.pages.get(key)
        if page is None:
            return
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(page)
        page.on_show()

    def set_theme(self, mode: str):
        if mode == theme.mode():
            return
        theme.apply(QApplication.instance(), mode)
        self._update_theme_button()
        if self.state.settings.get("theme") != mode:
            self.state.save_settings({"theme": mode})

    def toggle_theme(self):
        self.set_theme("light" if theme.mode() == "dark" else "dark")

    def _campaign_status(self, text: str, done: int, total: int):
        if not text:
            self.campaign_box.hide()
            return
        self.campaign_box.show()
        self.campaign_text.setText(f"<b>Campaign {text.lower()}</b><br>{done:,} of {total:,} processed")
        self.campaign_bar.setRange(0, max(1, total))
        self.campaign_bar.setValue(done)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, event):
        automation: AutomationPage = self.pages["automation"]
        if automation.is_running():
            answer = QMessageBox.question(
                self, "Campaign in progress",
                "A campaign is still sending. Closing the app will stop it.\n\n"
                "Customers not yet emailed can be re-queued later from History.\n\nClose anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            automation.shutdown()
        self.state.flush()
        event.accept()
