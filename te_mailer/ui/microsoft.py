"""Microsoft 365 / new Outlook sign-in card, shared by Settings and Outlook data."""

from __future__ import annotations

import json

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from ..core.graph import GraphClient
from .widgets import Card, Pill, button, field_label, label
from .workers import run_task

SETUP_STEPS = (
    "<b>One-time setup</b> (you or your IT admin, about 5 minutes):<br>"
    "1. Go to <a href='https://entra.microsoft.com'>entra.microsoft.com</a> → App registrations → New registration "
    "(any name, “Accounts in any organizational directory and personal Microsoft accounts”).<br>"
    "2. Authentication → <i>Allow public client flows</i> = <b>Yes</b> → Save.<br>"
    "3. API permissions → Microsoft Graph → Delegated: <b>Mail.Send, Mail.ReadWrite, Contacts.Read, "
    "User.Read</b> (grant admin consent if asked).<br>"
    "4. Copy the <b>Application (client) ID</b> from Overview and paste it below."
)


class SignInDialog(QDialog):
    def __init__(self, parent, user_code: str, url: str, on_cancel):
        super().__init__(parent)
        self.setWindowTitle("Sign in to Microsoft")
        self.setMinimumWidth(460)
        self._on_cancel = on_cancel
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(label("Sign in to Microsoft", "PageTitle"))
        lay.addWidget(label("1. Click the button to open Microsoft's sign-in page (the code is copied for you).<br>"
                            "2. Paste the code and sign in with the Travel Essence mailbox.<br>"
                            "3. Come back here - this finishes automatically.", wrap=True))
        code = QLabel(user_code)
        font = QFont("Consolas", 26)
        font.setBold(True)
        code.setFont(font)
        code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(code)
        open_btn = button("Copy code && open sign-in page", "link", "primary")

        def open_page():
            QGuiApplication.clipboard().setText(user_code)
            QDesktopServices.openUrl(QUrl(url))

        open_btn.clicked.connect(open_page)
        lay.addWidget(open_btn)
        lay.addWidget(label("Waiting for you to approve…", "Hint"))
        cancel = button("Cancel", None, "ghost")
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel, 0, Qt.AlignmentFlag.AlignRight)

    def reject(self):
        self._on_cancel()
        super().reject()


class MicrosoftAccountCard(Card):
    """Client ID / tenant fields, sign-in status and Sign in / Sign out buttons."""

    signed_in_changed = Signal()

    def __init__(self, state, title: str = "Microsoft 365 / new Outlook account"):
        super().__init__(title, "Connects online to your Travel Essence mailbox - works with the new Outlook, "
                                "Outlook on the web and Microsoft 365.")
        self.state = state
        self._task = None
        self._dialog: SignInDialog | None = None
        self.pill = Pill("")
        self.add_action(self.pill)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.client_id = QLineEdit(state.settings.get("ms_client_id", ""))
        self.client_id.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self.tenant = QLineEdit(state.settings.get("ms_tenant", "common") or "common")
        self.tenant.setToolTip("“common” works for most accounts, or use your organisation's tenant ID / domain")
        form.addRow(field_label("APPLICATION (CLIENT) ID"), self.client_id)
        form.addRow(field_label("TENANT"), self.tenant)
        self.add(form)

        row = QHBoxLayout()
        self.sign_in_btn = button("Sign in", "cloud", "primary")
        self.sign_in_btn.clicked.connect(self.sign_in)
        self.sign_out_btn = button("Sign out", None, "ghost")
        self.sign_out_btn.clicked.connect(self.sign_out)
        row.addWidget(self.sign_in_btn)
        row.addWidget(self.sign_out_btn)
        row.addStretch(1)
        self.add(row)
        steps = label(SETUP_STEPS, "Hint", wrap=True)
        steps.setOpenExternalLinks(True)
        self.add(steps)
        self.refresh()

    def client(self) -> GraphClient:
        return GraphClient(self.client_id.text().strip(), self.tenant.text().strip() or "common")

    def is_signed_in(self) -> bool:
        return bool(self.state.settings.get("ms_account")) and self.client().is_signed_in

    def refresh(self):
        account = self.state.settings.get("ms_account", "")
        if account and self.client().is_signed_in:
            self.pill.set(f"Signed in · {account}", "success")
            self.sign_in_btn.setText("Sign in again")
            self.sign_out_btn.setVisible(True)
        else:
            self.pill.set("Not signed in", "warning")
            self.sign_in_btn.setText("Sign in")
            self.sign_out_btn.setVisible(False)

    def _save_fields(self):
        self.state.save_settings({"ms_client_id": self.client_id.text().strip(),
                                  "ms_tenant": self.tenant.text().strip() or "common"})

    def sign_in(self):
        if not self.client_id.text().strip():
            QMessageBox.information(self, "Microsoft sign-in", "Paste the Application (client) ID first "
                                                               "(see the one-time setup steps below).")
            return
        self._save_fields()
        client = self.client()
        self.sign_in_btn.setEnabled(False)

        def work(ctx):
            device = client.start_device_login()
            ctx.progress(0, 0, json.dumps({"code": device["user_code"], "url": device["verification_uri"]}))
            return client.complete_device_login(device, ctx.cancelled)

        def progress(_c, _t, message):
            info = json.loads(message)
            self._dialog = SignInDialog(self, info["code"], info["url"], lambda: self._task and self._task.cancel())
            self._dialog.show()

        def finish():
            self.sign_in_btn.setEnabled(True)
            if self._dialog:
                self._dialog.done(0)
                self._dialog = None

        def done(account):
            finish()
            self.state.save_settings({"ms_account": account})
            self.refresh()
            self.signed_in_changed.emit()
            self.state.notify(f"Signed in as {account}", "success")

        def failed(message):
            finish()
            if message != "Sign-in cancelled":
                QMessageBox.critical(self, "Microsoft sign-in", message)

        self._task = run_task(work, done, failed, progress)

    def sign_out(self):
        self.client().sign_out()
        self.state.save_settings({"ms_account": ""})
        self.refresh()
        self.signed_in_changed.emit()
