"""Settings: sending method, Outlook account, SMTP, defaults, do-not-email list, theme."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox,
    QPlainTextEdit, QRadioButton, QSpinBox, QVBoxLayout,
)

from ... import __version__
from ...core import outlook_data, storage
from ...core.recipients import is_valid_email
from ...core.senders import SmtpSender, outlook_available
from ..microsoft import MicrosoftAccountCard
from ..widgets import Card, Page, button, field_label, label
from ..workers import run_task

SMTP_PRESETS = {
    "Microsoft 365 / Outlook.com (if SMTP AUTH is allowed)": ("smtp.office365.com", 587, "starttls"),
    "Gmail / Google Workspace": ("smtp.gmail.com", 587, "starttls"),
    "Custom server": None,
}


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(10)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return form


class SettingsPage(Page):
    def __init__(self, state, on_theme_change):
        super().__init__("Settings", "Choose how emails are sent and set your campaign defaults.")
        self.state = state
        self.on_theme_change = on_theme_change
        self._task = None

        save_btn = button("Save settings", "save", "primary")
        save_btn.clicked.connect(self.save)
        self.header_actions.addWidget(save_btn)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        right = QVBoxLayout()
        right.setSpacing(18)
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.content.addLayout(columns)

        # ---- sending method
        method = Card("Sending method")
        self.method_group = QButtonGroup(self)
        self.radio_outlook = QRadioButton("Outlook app on this PC (classic Outlook)")
        self.radio_graph = QRadioButton("Microsoft 365 / new Outlook (sign in online)")
        self.radio_smtp = QRadioButton("SMTP server")
        self.radio_sim = QRadioButton("Simulation - practise without sending anything")
        descriptions = {
            self.radio_outlook: "Sends through the classic Outlook desktop app on this PC, from your Travel "
                                "Essence mailbox. Emails appear in Outlook's Sent Items.",
            self.radio_graph: "For the new Outlook, Outlook on the web or any Microsoft 365 mailbox. Signs in "
                              "online once; emails are sent from your mailbox and saved in Sent Items.",
            self.radio_smtp: "Sends directly through a mail server that allows SMTP sign-in (e.g. Gmail, "
                             "Zoho or your web host).",
            self.radio_sim: "Runs campaigns exactly as normal (timer, progress, history) but no email "
                            "leaves this computer.",
        }
        for radio in (self.radio_outlook, self.radio_graph, self.radio_smtp, self.radio_sim):
            self.method_group.addButton(radio)
            method.add(radio)
            hint = label(descriptions[radio], "Hint", wrap=True)
            hint.setContentsMargins(26, 0, 0, 4)
            method.add(hint)
        left.addWidget(method)

        # ---- outlook
        self.outlook_card = Card("Outlook account")
        ok, reason = outlook_available()
        if not ok:
            self.outlook_card.add(label(f"⚠ {reason}", "Hint", wrap=True))
        form = _form()
        acc_row = QHBoxLayout()
        self.account_box = QComboBox()
        self.account_box.setEditable(True)
        self.account_box.setMinimumWidth(260)
        self.account_box.lineEdit().setPlaceholderText("Default Outlook account")
        load_acc = button("Load accounts", "refresh")
        load_acc.clicked.connect(self.load_accounts)
        acc_row.addWidget(self.account_box, 1)
        acc_row.addWidget(load_acc)
        form.addRow(field_label("SEND FROM"), acc_row)
        self.signature = QCheckBox("Also add the signature saved in the Outlook app")
        form.addRow("", self.signature)
        self.outlook_card.add(form)
        left.addWidget(self.outlook_card)

        # ---- microsoft 365 / new outlook
        self.graph_card = MicrosoftAccountCard(state)
        left.addWidget(self.graph_card)

        # ---- smtp
        self.smtp_card = Card("SMTP server")
        form = _form()
        self.preset = QComboBox()
        self.preset.addItems(list(SMTP_PRESETS))
        self.preset.textActivated.connect(self._apply_preset)
        form.addRow(field_label("PROVIDER"), self.preset)
        host_row = QHBoxLayout()
        self.smtp_host = QLineEdit()
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setFixedWidth(110)
        host_row.addWidget(self.smtp_host, 1)
        host_row.addWidget(self.smtp_port)
        form.addRow(field_label("SERVER / PORT"), host_row)
        self.smtp_security = QComboBox()
        self.smtp_security.addItem("STARTTLS (port 587)", "starttls")
        self.smtp_security.addItem("SSL/TLS (port 465)", "ssl")
        self.smtp_security.addItem("None (not recommended)", "none")
        form.addRow(field_label("SECURITY"), self.smtp_security)
        self.smtp_user = QLineEdit()
        self.smtp_user.setPlaceholderText("info@travelessence.com")
        form.addRow(field_label("USERNAME"), self.smtp_user)
        self.smtp_pass = QLineEdit()
        self.smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_pass.setPlaceholderText("Password or app password")
        form.addRow(field_label("PASSWORD"), self.smtp_pass)
        self.remember = QCheckBox("Remember password securely (Windows Credential Manager)")
        form.addRow("", self.remember)
        self.from_email = QLineEdit()
        self.from_email.setPlaceholderText("info@travelessence.com")
        form.addRow(field_label("FROM EMAIL"), self.from_email)
        self.from_name = QLineEdit()
        form.addRow(field_label("FROM NAME"), self.from_name)
        self.smtp_card.add(form)
        test_row = QHBoxLayout()
        self.test_btn = button("Test connection", "check")
        self.test_btn.clicked.connect(self.test_smtp)
        test_row.addWidget(self.test_btn)
        test_row.addStretch(1)
        self.smtp_card.add(test_row)
        left.addWidget(self.smtp_card)
        left.addStretch(1)

        # ---- defaults
        defaults = Card("Campaign defaults")
        form = _form()
        self.interval = QSpinBox()
        self.interval.setRange(10, 3600)
        self.interval.setSingleStep(10)
        self.interval.setSuffix("  seconds")
        form.addRow(field_label("TIME BETWEEN EMAILS"), self.interval)
        self.fallback = QLineEdit()
        self.fallback.setPlaceholderText("Valued Customer")
        form.addRow(field_label("NAME IF UNKNOWN"), self.fallback)
        self.test_email = QLineEdit()
        self.test_email.setPlaceholderText("you@travelessence.com")
        form.addRow(field_label("TEST EMAIL TO"), self.test_email)
        defaults.add(form)
        right.addWidget(defaults)

        dne = Card("Do-not-email list", "Addresses or whole domains (e.g. @competitor.com) that campaigns "
                                        "always skip - use it for unsubscribe requests.")
        self.suppression = QPlainTextEdit()
        self.suppression.setPlaceholderText("unsubscribed@example.com\n@competitor.com")
        self.suppression.setMinimumHeight(150)
        dne.add(self.suppression)
        right.addWidget(dne)

        appearance = Card("Appearance")
        form = _form()
        self.theme_box = QComboBox()
        self.theme_box.addItem("Light", "light")
        self.theme_box.addItem("Dark", "dark")
        self.theme_box.currentIndexChanged.connect(
            lambda: self.on_theme_change(self.theme_box.currentData()))
        form.addRow(field_label("THEME"), self.theme_box)
        appearance.add(form)
        right.addWidget(appearance)

        about = Card("About")
        about.add(label(f"Travel Essence Email Studio v{__version__}<br>"
                        f"Data folder: {storage.data_dir()}", "Hint", wrap=True))
        right.addWidget(about)
        right.addStretch(1)

        self.method_group.buttonToggled.connect(self._method_changed)
        state.settings_changed.connect(self._sync_theme)
        self.load()

    # ------------------------------------------------------------
    def _sync_theme(self):
        idx = self.theme_box.findData(self.state.settings.get("theme", "light"))
        if idx >= 0 and idx != self.theme_box.currentIndex():
            self.theme_box.blockSignals(True)
            self.theme_box.setCurrentIndex(idx)
            self.theme_box.blockSignals(False)

    def _method_changed(self, *_):
        self.outlook_card.setVisible(self.radio_outlook.isChecked())
        self.graph_card.setVisible(self.radio_graph.isChecked())
        self.smtp_card.setVisible(self.radio_smtp.isChecked())

    def _apply_preset(self, name: str):
        preset = SMTP_PRESETS.get(name)
        if preset:
            host, port, security = preset
            self.smtp_host.setText(host)
            self.smtp_port.setValue(port)
            self.smtp_security.setCurrentIndex(self.smtp_security.findData(security))

    def load(self):
        s = self.state.settings
        {"smtp": self.radio_smtp, "simulate": self.radio_sim, "graph": self.radio_graph}.get(
            s.get("backend"), self.radio_outlook).setChecked(True)
        self.account_box.clear()
        self.account_box.addItem("")
        if s.get("outlook_account"):
            self.account_box.addItem(s["outlook_account"])
        self.account_box.setCurrentText(s.get("outlook_account", ""))
        self.signature.setChecked(bool(s.get("include_signature")))
        self.smtp_host.setText(s.get("smtp_host", ""))
        self.smtp_port.setValue(int(s.get("smtp_port", 587) or 587))
        self.smtp_security.setCurrentIndex(max(0, self.smtp_security.findData(s.get("smtp_security", "starttls"))))
        preset_name = next((n for n, p in SMTP_PRESETS.items() if p and p[0] == s.get("smtp_host")), "Custom server")
        self.preset.setCurrentText(preset_name)
        self.smtp_user.setText(s.get("smtp_username", ""))
        self.smtp_pass.setText(self.state.smtp_password())
        self.remember.setChecked(bool(s.get("smtp_remember_password", True)))
        self.from_email.setText(s.get("smtp_from_email", ""))
        self.from_name.setText(s.get("smtp_from_name", ""))
        self.interval.setValue(int(s.get("interval_seconds", 60)))
        self.fallback.setText(s.get("name_fallback", ""))
        self.test_email.setText(s.get("test_email", ""))
        self.suppression.setPlainText(s.get("suppression_list", ""))
        self._sync_theme()
        self._method_changed()

    def _collect(self) -> dict:
        backend = ("smtp" if self.radio_smtp.isChecked() else "simulate" if self.radio_sim.isChecked()
                   else "graph" if self.radio_graph.isChecked() else "outlook")
        return {
            "backend": backend,
            "ms_client_id": self.graph_card.client_id.text().strip(),
            "ms_tenant": self.graph_card.tenant.text().strip() or "common",
            "outlook_account": self.account_box.currentText().strip(),
            "include_signature": self.signature.isChecked(),
            "smtp_host": self.smtp_host.text().strip(),
            "smtp_port": self.smtp_port.value(),
            "smtp_security": self.smtp_security.currentData(),
            "smtp_username": self.smtp_user.text().strip(),
            "smtp_remember_password": self.remember.isChecked(),
            "smtp_from_email": self.from_email.text().strip(),
            "smtp_from_name": self.from_name.text().strip(),
            "interval_seconds": self.interval.value(),
            "name_fallback": self.fallback.text().strip(),
            "test_email": self.test_email.text().strip(),
            "suppression_list": self.suppression.toPlainText(),
            "theme": self.theme_box.currentData(),
        }

    def save(self):
        values = self._collect()
        if self.state.campaign_running and values["backend"] != self.state.settings.get("backend"):
            QMessageBox.information(self, "Settings", "Changes to the sending method apply to the next campaign.")
        if values["test_email"] and not is_valid_email(values["test_email"]):
            QMessageBox.warning(self, "Settings", "The test email address is not valid.")
            return
        if values["backend"] == "smtp":
            stored = storage.set_password(values["smtp_username"],
                                          self.smtp_pass.text() if values["smtp_remember_password"] else "")
            if values["smtp_remember_password"] and not stored and self.smtp_pass.text():
                QMessageBox.warning(self, "Settings", "The password could not be stored securely on this "
                                                      "computer; you may need to enter it again.")
        self.state.save_settings(values)
        self.state.notify("Settings saved", "success")

    def load_accounts(self):
        def done(info):
            current = self.account_box.currentText()
            self.account_box.clear()
            self.account_box.addItem("")
            for acc in info.get("accounts", []):
                self.account_box.addItem(acc["smtp"] or acc["name"])
            self.account_box.setCurrentText(current)
            self.state.notify(f"Found {len(info.get('accounts', []))} Outlook account(s)", "success")

        self._task = run_task(lambda _ctx: outlook_data.list_accounts(), done,
                              lambda msg: QMessageBox.critical(self, "Outlook", msg))

    def test_smtp(self):
        v = self._collect()
        sender = SmtpSender(v["smtp_host"], v["smtp_port"], v["smtp_security"], v["smtp_username"],
                            self.smtp_pass.text(), v["smtp_from_email"], v["smtp_from_name"], timeout=20)

        def work(_ctx):
            sender.open()
            sender.close()

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing…")

        def finish():
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test connection")

        def ok(_):
            finish()
            QMessageBox.information(self, "SMTP", "Connection and login succeeded.")

        def failed(msg):
            finish()
            QMessageBox.critical(self, "SMTP", msg)

        self._task = run_task(work, ok, failed)
