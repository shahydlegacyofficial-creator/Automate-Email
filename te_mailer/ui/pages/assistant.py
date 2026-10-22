"""AI assistant: let Legacy AI (or another MCP-capable assistant) control the app."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QRadioButton, QSpinBox,
    QVBoxLayout,
)

from ..assistant import APPROVAL_CHOICES, AssistantService
from ..widgets import Card, Page, Pill, button, divider, field_label, label, make_table, status_item, table_item

ABILITIES = [
    ("Write emails", "Writes the campaign email (or loads a template) straight into Compose, "
                     "with {first_name} personalisation and your attachments."),
    ("Manage lists", "Creates named recipient lists such as “VIP guests” or “Honeymoon 2026” and adds "
                     "customers to them."),
    ("Run campaigns", "Sends to a whole list one customer at a time, exactly like the Automation page - "
                      "and can pause, resume or stop it."),
    ("Quick emails & tests", "Sends a test to your test address, or a one-off email to a few people."),
    ("Report back", "Tells you progress, failures and what was sent recently."),
]


class AssistantPage(Page):
    def __init__(self, state, service: AssistantService):
        super().__init__("AI assistant",
                         "Let Legacy AI write and send Travel Essence emails for you - by voice or chat - "
                         "through this app.")
        self.state = state
        self.service = service

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        right = QVBoxLayout()
        right.setSpacing(18)
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.content.addLayout(columns)

        # ---- connection
        conn = Card("Connection", "Uses MCP (Model Context Protocol), the open standard for AI tools.")
        self.status_pill = Pill("Off")
        conn.add_action(self.status_pill)
        self.enable = QCheckBox("Allow Legacy AI to control this app")
        self.enable.setStyleSheet("font-weight:600;")
        self.enable.toggled.connect(self._toggle)
        conn.add(self.enable)
        self.status_text = label("", "Hint", wrap=True)
        conn.add(self.status_text)
        conn.add(label("<b>Legacy AI connects by itself</b> (Legacy v3.23 or newer): keep this app open, or "
                       "ask Legacy to “open Email Studio”. Her Tool armory then lists it as "
                       "<i>Legacy AI Email Studio</i>.", "Hint", wrap=True))
        conn.add(divider())
        conn.add(field_label("FOR OTHER AI APPS - ADD AN MCP CONNECTION WITH"))
        url_row = QHBoxLayout()
        self.url_field = QLineEdit()
        self.url_field.setReadOnly(True)
        copy_url = button("Copy", "copy")
        copy_url.clicked.connect(lambda: self._copy(self.url_field.text(), "Address copied"))
        url_row.addWidget(self.url_field, 1)
        url_row.addWidget(copy_url)
        conn.add(url_row)
        token_row = QHBoxLayout()
        self.token_field = QLineEdit()
        self.token_field.setReadOnly(True)
        self.token_field.setEchoMode(QLineEdit.EchoMode.Password)
        show = button("Show", "eye")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.token_field.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        copy_token = button("Copy", "copy")
        copy_token.clicked.connect(lambda: self._copy(self.token_field.text(), "Access token copied"))
        new_token = button("New token", "key", "ghost")
        new_token.setToolTip("Disconnects every AI app until it gets the new token "
                             "(Legacy AI picks it up automatically).")
        new_token.clicked.connect(self._new_token)
        token_row.addWidget(self.token_field, 1)
        token_row.addWidget(show)
        token_row.addWidget(copy_token)
        token_row.addWidget(new_token)
        conn.add(token_row)
        conn.add(label("Send the token as “Authorization: Bearer &lt;token&gt;”. Only programs on this PC can "
                       "connect.", "Hint", wrap=True))
        port_row = QHBoxLayout()
        port_row.addWidget(label("Port", "Muted"))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setMinimumWidth(110)
        port_row.addWidget(self.port)
        apply_port = button("Apply")
        apply_port.clicked.connect(self._apply_port)
        port_row.addWidget(apply_port)
        port_row.addStretch(1)
        conn.add(port_row)
        left.addWidget(conn)

        # ---- activity
        activity = Card("What the AI did", "Every request from the AI assistant since the app opened.")
        self.table = make_table(["Time", "Action", "Details", "Result"], 3)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 240)
        self.table.setMinimumHeight(300)
        activity.add(self.table, 1)
        left.addWidget(activity, 1)

        # ---- safety
        safety = Card("Approval", "Legacy AI already asks you before she sends anything. This adds a second "
                                  "check here, in the app.")
        self.approval_group = QButtonGroup(self)
        self.approval_buttons: dict[str, QRadioButton] = {}
        for key, text in APPROVAL_CHOICES.items():
            radio = QRadioButton(text)
            self.approval_group.addButton(radio)
            self.approval_buttons[key] = radio
            radio.toggled.connect(lambda on, k=key: on and self._set_approval(k))
            safety.add(radio)
        safety.add(label("Test emails to your saved test address never need approval. Unanswered requests "
                         "are declined after 2 minutes.", "Hint", wrap=True))
        right.addWidget(safety)

        abilities = Card("What Legacy can do here")
        for title, text in ABILITIES:
            abilities.add(label(f"<b>{title}</b><br>{text}", wrap=True))
        abilities.add(label("Try: “Legacy, email the VIP guests list about our Eid offer - 20% off "
                            "overwater villas until 30 November.”", "Hint", wrap=True))
        right.addWidget(abilities)
        right.addStretch(1)

        service.server_state.connect(self._show_status)
        service.activity.connect(self._add_activity)
        state.settings_changed.connect(self.load)
        self.load()
        for entry in reversed(service.log):
            self._add_activity(entry)

    # ------------------------------------------------------------ state
    def load(self):
        s = self.state.settings
        for widget in (self.enable, self.port, *self.approval_buttons.values()):
            widget.blockSignals(True)
        self.enable.setChecked(bool(s.get("ai_enabled")))
        self.port.setValue(int(s.get("ai_port", 8765)))
        self.approval_buttons.get(s.get("ai_approval", "campaigns"), self.approval_buttons["campaigns"]).setChecked(True)
        for widget in (self.enable, self.port, *self.approval_buttons.values()):
            widget.blockSignals(False)
        self.url_field.setText(self.service.url)
        self.token_field.setText(s.get("ai_token", ""))
        self._show_status(*self.service.status)

    def _show_status(self, state: str, message: str):
        text, tone = {"on": ("Ready", "success"), "error": ("Problem", "danger")}.get(state, ("Off", None))
        self.status_pill.set(text, tone)
        self.status_text.setText(message)

    def _toggle(self, on: bool):
        self.state.save_settings({"ai_enabled": on})
        if on:
            self.state.notify("AI assistant connection is on", "success")

    def _set_approval(self, key: str):
        if self.state.settings.get("ai_approval") != key:
            self.state.save_settings({"ai_approval": key})

    def _apply_port(self):
        self.state.save_settings({"ai_port": self.port.value()})

    def _new_token(self):
        if QMessageBox.question(self, "New access token",
                                "Create a new access token? AI apps using the old one are disconnected. "
                                "Legacy AI picks up the new one by itself.") != QMessageBox.StandardButton.Yes:
            return
        self.service.regenerate_token()
        self.state.notify("New access token created", "success")

    def _copy(self, text: str, message: str):
        QGuiApplication.clipboard().setText(text)
        self.state.notify(message)

    def _add_activity(self, entry: dict):
        self.table.insertRow(0)
        self.table.setItem(0, 0, table_item(entry["time"]))
        self.table.setItem(0, 1, table_item(entry["tool"].replace("_", " ").capitalize()))
        details = table_item(entry.get("args", ""))
        details.setToolTip(entry.get("args", ""))
        self.table.setItem(0, 2, details)
        result = status_item("sent" if entry["ok"] else "failed")
        result.setText(entry["result"] if entry["ok"] else "Refused: " + entry["result"])
        result.setToolTip(entry["result"])
        self.table.setItem(0, 3, result)
        while self.table.rowCount() > 200:
            self.table.removeRow(self.table.rowCount() - 1)

