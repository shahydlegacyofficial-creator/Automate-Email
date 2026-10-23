"""Inbox: emails arriving at the Travel Essence mailboxes - read, reply, mark, add to recipients."""

from __future__ import annotations

import html as html_lib
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QSpinBox, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.inbox import ImapSource, InboxMessage, imap_password_key, reply_subject, watched
from ...core.recipients import Recipient
from ..editor import AttachmentList, EmailEditor
from ..signature_assets import signature_html
from ..widgets import Banner, Card, Page, Pill, button, field_label, label, make_table, table_item
from ..workers import run_task

IMAP_HINT = ("Common servers: Microsoft 365 outlook.office365.com · Gmail imap.gmail.com (use an app password) · "
             "Zoho imap.zoho.com · most web hosts mail.yourdomain.com. Port 993 with SSL.")


def when_text(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.year == now.year:
        return dt.strftime("%d %b, %H:%M")
    return dt.strftime("%d %b %Y")


# ====================================================================== dialogs
class ImapAccountDialog(QDialog):
    def __init__(self, parent, account: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("IMAP mailbox")
        self.setMinimumWidth(480)
        account = account or {}
        self._task = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(account.get("name", ""))
        self.name.setPlaceholderText("e.g. Sales mailbox")
        self.host = QLineEdit(account.get("host", ""))
        self.host.setPlaceholderText("mail.travelessence.mv")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(account.get("port") or 993))
        self.security = QComboBox()
        for key, text in (("ssl", "SSL (port 993)"), ("starttls", "STARTTLS (port 143)"), ("none", "None")):
            self.security.addItem(text, key)
        self.security.setCurrentIndex(max(0, self.security.findData(account.get("security", "ssl"))))
        self.security.currentIndexChanged.connect(
            lambda: self.port.setValue({"ssl": 993, "starttls": 143}.get(self.security.currentData(), self.port.value())))
        self.username = QLineEdit(account.get("username", ""))
        self.username.setPlaceholderText("sales.marketing@travelessence.mv")
        self.password = QLineEdit(storage.get_password(imap_password_key(account)) if account else "")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Name", self.name)
        form.addRow("Server", self.host)
        form.addRow("Security", self.security)
        form.addRow("Port", self.port)
        form.addRow("Email / username", self.username)
        form.addRow("Password", self.password)
        lay.addLayout(form)
        lay.addWidget(label(IMAP_HINT, "Hint", wrap=True))
        self.result = label("", "Hint", wrap=True)
        lay.addWidget(self.result)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.test_btn = button("Test connection", "refresh")
        buttons.addButton(self.test_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.test_btn.clicked.connect(self.test)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def account(self) -> dict:
        return {"name": self.name.text().strip(), "host": self.host.text().strip(), "port": self.port.value(),
                "security": self.security.currentData(), "username": self.username.text().strip()}

    def test(self):
        account, password = self.account(), self.password.text()
        self.test_btn.setEnabled(False)
        self.result.setText("Connecting…")

        def done(rows):
            self.test_btn.setEnabled(True)
            self.result.setText(f"✓ Connected - the newest email is “{rows[0].subject}”." if rows else
                                "✓ Connected - the Inbox is empty.")

        def failed(message):
            self.test_btn.setEnabled(True)
            self.result.setText(f"✕ {message}")

        self._task = run_task(lambda _ctx: ImapSource(account, password).fetch(1, {}), done, failed)

    def _accept(self):
        account = self.account()
        if not account["host"] or not account["username"]:
            QMessageBox.information(self, "IMAP mailbox", "Enter the server and the username.")
            return
        storage.set_password(imap_password_key(account), self.password.text())
        self.accept()


class MailboxesDialog(QDialog):
    """Which Travel Essence mailboxes the inbox watches."""

    def __init__(self, parent, state):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Inbox mailboxes")
        self.setMinimumWidth(560)
        s = state.settings
        w = watched(s)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.enabled = QCheckBox("Check for new emails")
        self.enabled.setChecked(bool(s.get("inbox_enabled", True)))
        lay.addWidget(self.enabled)
        lay.addWidget(field_label("MAILBOXES"))
        self.outlook = QCheckBox("Outlook app on this PC - every account in classic Outlook")
        self.outlook.setChecked(w["outlook"])
        lay.addWidget(self.outlook)
        account = s.get("ms_account")
        self.graph = QCheckBox(f"Microsoft 365 / new Outlook - {account}" if account else
                               "Microsoft 365 / new Outlook (sign in under Settings first)")
        self.graph.setChecked(w["graph_wanted"])
        lay.addWidget(self.graph)
        lay.addWidget(label("IMAP mailboxes (any other email account - add as many as you need):", "Muted"))
        self.imap = QListWidget()
        self.imap.setMinimumHeight(110)
        self.accounts = [dict(a) for a in s.get("inbox_imap_accounts") or []]
        self._fill()
        lay.addWidget(self.imap)
        row = QHBoxLayout()
        for text, icon_name, slot in (("Add…", "plus", self.add), ("Edit…", "compose", self.edit),
                                      ("Remove", "trash", self.remove)):
            btn = button(text, icon_name)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(field_label("CHECKING"))
        every = QHBoxLayout()
        every.addWidget(label("Check every"))
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setSuffix(" min")
        self.interval.setValue(int(s.get("inbox_interval_minutes", 2) or 2))
        every.addWidget(self.interval)
        every.addStretch(1)
        lay.addLayout(every)
        self.notify = QCheckBox("Show a Windows notification when an email arrives")
        self.notify.setChecked(bool(s.get("inbox_notify", True)))
        lay.addWidget(self.notify)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _fill(self):
        self.imap.clear()
        for a in self.accounts:
            QListWidgetItem(f"{a.get('name') or a.get('username')}  ·  {a.get('username')} @ {a.get('host')}", self.imap)

    def add(self):
        dlg = ImapAccountDialog(self)
        if dlg.exec():
            self.accounts.append(dlg.account())
            self._fill()

    def edit(self):
        row = self.imap.currentRow()
        if row < 0:
            return
        dlg = ImapAccountDialog(self, self.accounts[row])
        if dlg.exec():
            self.accounts[row] = dlg.account()
            self._fill()

    def remove(self):
        row = self.imap.currentRow()
        if row >= 0:
            storage.set_password(imap_password_key(self.accounts[row]), "")
            del self.accounts[row]
            self._fill()

    def _save(self):
        self.state.save_settings({
            "inbox_enabled": self.enabled.isChecked(), "inbox_outlook": self.outlook.isChecked(),
            "inbox_graph": self.graph.isChecked(), "inbox_imap_accounts": self.accounts,
            "inbox_interval_minutes": self.interval.value(), "inbox_notify": self.notify.isChecked()})
        self.accept()


class ReplyDialog(QDialog):
    def __init__(self, parent, state, service, msg: InboxMessage, reply_all: bool):
        super().__init__(parent)
        self.state, self.service, self.msg, self.reply_all = state, service, msg, reply_all
        self._task = None
        self.setWindowTitle("Reply all" if reply_all else "Reply")
        self.resize(820, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        to = msg.reply_to or msg.from_email
        cc = [a for a in msg.to + msg.cc if a != to] if reply_all else []
        meta = f"<b>To:</b> {html_lib.escape(msg.from_name + ' <' + to + '>' if msg.from_name else to)}"
        if cc:
            meta += f"<br><b>Cc:</b> {html_lib.escape(', '.join(cc))} <span style='color:#888'>(your own " \
                    "Travel Essence addresses are left out)</span>"
        meta += f"<br><b>Subject:</b> {html_lib.escape(reply_subject(msg.subject))}" \
                f"<br><b>From:</b> {html_lib.escape(msg.account)}"
        lay.addWidget(label(meta, wrap=True))
        self.editor = EmailEditor(min_height=320)
        first = (msg.from_name or "").split()[0] if (msg.from_name or "").strip() else ""
        self.editor.set_html(f"<p>Dear {html_lib.escape(first)},</p><p><br></p>" if first else "<p><br></p>")
        lay.addWidget(self.editor, 1)
        self.attachments = AttachmentList(compact=True)
        lay.addWidget(self.attachments)
        lay.addWidget(label("The Travel Essence signature and the customer's original email are added "
                            "below your reply.", "Hint", wrap=True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.send_btn = button("Send reply", "send", "primary")
        buttons.addButton(self.send_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.send_btn.clicked.connect(self.send)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def send(self):
        if self.editor.is_blank():
            QMessageBox.information(self, "Reply", "Write your reply first.")
            return
        html, attachments = self.editor.html(), self.attachments.paths()
        signature = signature_html(self.state.settings)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("Sending…")

        def done(result):
            self.state.notify(f"Reply sent to {', '.join(result['to'])}", "success")
            self.state.history_changed.emit()
            self.accept()

        def failed(message):
            self.send_btn.setEnabled(True)
            self.send_btn.setText("Send reply")
            QMessageBox.critical(self, "Reply not sent", message)

        self._task = run_task(lambda _ctx: self.service.reply(self.msg, html, signature, attachments,
                                                              self.reply_all), done, failed)


# ====================================================================== page
class InboxPage(Page):
    def __init__(self, state, service):
        super().__init__("Inbox", "Emails arriving at your Travel Essence mailboxes. Legacy AI can watch this "
                                  "inbox too and tell you when something arrives.", scroll=False)
        self.state = state
        self.service = service
        self.current: InboxMessage | None = None
        self._tasks = []

        self.status = label("", "Muted")
        self.header_actions.addWidget(self.status)
        self.check_btn = button("Check now", "refresh")
        self.check_btn.clicked.connect(service.check)
        boxes_btn = button("Mailboxes…", "settings")
        boxes_btn.clicked.connect(self.edit_mailboxes)
        self.header_actions.addWidget(self.check_btn)
        self.header_actions.addWidget(boxes_btn)

        self.banner = Banner("")
        self.banner.hide()
        self.content.addWidget(self.banner)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.content.addLayout(body, 1)

        # ---- list
        list_card = Card("Messages")
        self.count_pill = Pill("0 unread", "accent")
        list_card.add_action(self.count_pill)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sender or subject…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.populate)
        self.unread_only = QCheckBox("Unread only")
        self.unread_only.toggled.connect(self.populate)
        self.mailbox = QComboBox()
        self.mailbox.currentIndexChanged.connect(self.populate)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.mailbox)
        tools.addWidget(self.unread_only)
        list_card.add(tools)
        self.table = make_table(["", "From", "Subject", "Received"], 2)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(3, 100)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._selected)
        list_card.add(self.table, 1)
        list_wrap = QWidget()
        lw = QVBoxLayout(list_wrap)
        lw.setContentsMargins(0, 0, 0, 0)
        lw.addWidget(list_card)
        list_wrap.setMinimumWidth(520)
        body.addWidget(list_wrap, 5)

        # ---- reading pane
        self.pane = Card("")
        self.subject = label("Select an email to read it", "CardTitle", wrap=True)
        self.subject.setStyleSheet("font-size:15pt; font-weight:600;")
        self.pane.add(self.subject)
        self.meta = label("", "Muted", wrap=True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pane.add(self.meta)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.reply_btn = button("Reply", "reply", "primary")
        self.reply_btn.clicked.connect(lambda: self.reply(False))
        self.reply_all_btn = button("Reply all", "reply-all")
        self.reply_all_btn.clicked.connect(lambda: self.reply(True))
        self.read_btn = button("Mark as unread", "mail-open")
        self.read_btn.clicked.connect(self.toggle_read)
        self.add_btn = button("Add to recipients", "user-plus", "ghost")
        self.add_btn.clicked.connect(self.add_sender)
        for b in (self.reply_btn, self.reply_all_btn, self.read_btn, self.add_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        self.pane.add(actions)
        self.viewer = QTextBrowser()
        self.viewer.setObjectName("EmailPaper")
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setMinimumHeight(300)
        self.pane.add(self.viewer, 1)
        self.attach_label = label("", "Hint", wrap=True)
        self.pane.add(self.attach_label)
        body.addWidget(self.pane, 6)

        service.changed.connect(self.refresh)
        service.checking.connect(self._checking)
        state.settings_changed.connect(self.refresh)
        self._enable_actions(False)
        self.refresh()

    # ------------------------------------------------------------ list
    def on_show(self):
        self.refresh()

    def _checking(self, busy: bool):
        self.check_btn.setEnabled(not busy)
        self.check_btn.setText("Checking…" if busy else "Check now")

    def refresh(self):
        inbox = self.service.inbox
        current = self.mailbox.currentData()
        self.mailbox.blockSignals(True)
        self.mailbox.clear()
        self.mailbox.addItem("All mailboxes", "")
        for name in sorted({m.account for m in inbox.messages()}):
            self.mailbox.addItem(name, name)
        self.mailbox.setCurrentIndex(max(0, self.mailbox.findData(current)))
        self.mailbox.blockSignals(False)

        watching = self.service.watching()
        checked = when_text(inbox.last_checked) if inbox.last_checked else "not yet"
        every = int(self.state.settings.get("inbox_interval_minutes", 2) or 2)
        self.status.setText(f"Checked {checked} · every {every} min" if watching else "")
        problems = list(inbox.errors.values())
        if not self.state.settings.get("inbox_enabled", True):
            self._banner("<b>Checking for new emails is off.</b> Turn it on under <i>Mailboxes…</i>.")
        elif not watching:
            w = watched(self.state.settings)
            extra = (" Microsoft 365 is ticked but not signed in - sign in under Settings." if w["graph_wanted"]
                     and not w["graph"] else "")
            self._banner("<b>No mailbox is connected yet.</b> Click <i>Mailboxes…</i> to choose the Outlook app, "
                         "Microsoft 365 or an IMAP mailbox." + extra)
        elif problems:
            self._banner("<b>Some mailboxes could not be checked:</b><br>" +
                         "<br>".join(html_lib.escape(p) for p in problems))
        else:
            self.banner.hide()
        self.populate()

    def _banner(self, text: str):
        self.banner.text.setText(text)
        self.banner.show()

    def populate(self):
        inbox = self.service.inbox
        rows = inbox.messages()
        unread = sum(1 for m in rows if m.unread)
        self.count_pill.set(f"{unread} unread" if unread else "All read", "accent" if unread else "success")
        needle = self.search.text().strip().lower()
        box = self.mailbox.currentData() or ""
        if needle:
            rows = [m for m in rows if needle in f"{m.from_name} {m.from_email} {m.subject}".lower()]
        if box:
            rows = [m for m in rows if m.account == box]
        if self.unread_only.isChecked():
            rows = [m for m in rows if m.unread]
        selected = self.current.key if self.current else None
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        bold = QFont()
        bold.setBold(True)
        select_row = -1
        for i, m in enumerate(rows):
            dot = table_item("●" if m.unread else "", data=m.key)
            sender = table_item(m.from_name or m.from_email)
            sender.setToolTip(m.sender)
            subject = table_item((m.subject or "(no subject)") + (f"  —  {m.preview}" if m.preview else ""))
            subject.setToolTip(m.subject)
            received = table_item(when_text(m.received))
            received.setToolTip(f"{m.received.replace('T', ' ')} · {m.account}")
            for item in (dot, sender, subject, received):
                if m.unread:
                    item.setFont(bold)
            for col, item in enumerate((dot, sender, subject, received)):
                self.table.setItem(i, col, item)
            if m.key == selected:
                select_row = i
        self.table.blockSignals(False)
        if select_row >= 0:
            self.table.selectRow(select_row)

    # ------------------------------------------------------------ reading
    def _enable_actions(self, on: bool):
        for b in (self.reply_btn, self.reply_all_btn, self.read_btn, self.add_btn):
            b.setEnabled(on)

    def _selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        key = self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        msg = self.service.inbox.find(key)
        if msg is None or (self.current and self.current.key == key):
            return
        self.open(msg)

    def open(self, msg: InboxMessage):
        self.current = msg
        self._enable_actions(True)
        self.subject.setText(html_lib.escape(msg.subject or "(no subject)"))
        to = ", ".join(msg.to) or "—"
        meta = (f"<b>{html_lib.escape(msg.from_name or msg.from_email)}</b> &lt;{html_lib.escape(msg.from_email)}&gt;"
                f"<br>To: {html_lib.escape(to)}")
        if msg.cc:
            meta += f"<br>Cc: {html_lib.escape(', '.join(msg.cc))}"
        meta += f"<br>{html_lib.escape(msg.received.replace('T', ' ')[:16])} · {html_lib.escape(msg.account)}"
        self.meta.setText(meta)
        self.read_btn.setText("Mark as unread")
        self.viewer.setHtml(f"<p style='color:#888'>{html_lib.escape(msg.preview)}</p><p style='color:#888'>Loading…</p>")
        self.attach_label.setText("")

        def work(_ctx):
            body = self.service.inbox.body(msg)
            if msg.unread:
                self.service.set_read(msg, True)
            return body

        def done(body):
            if self.current is None or self.current.key != msg.key:
                return
            self.viewer.setHtml(body["html"])
            names = body.get("attachments") or []
            self.attach_label.setText(("📎 " + ", ".join(names) +
                                       " - open the email in your mail app to save attachments") if names else "")

        def failed(message):
            if self.current is not None and self.current.key == msg.key:
                self.viewer.setHtml(f"<p style='color:#c0392b'>Could not open this email: {html_lib.escape(message)}</p>")

        self._tasks.append(run_task(work, done, failed))
        self._tasks = [t for t in self._tasks if t.is_running()][-5:]

    def toggle_read(self):
        msg = self.current and self.service.inbox.find(self.current.key)
        if not msg:
            return
        read = msg.unread   # unread -> mark read, read -> mark unread
        self.read_btn.setText("Mark as unread" if read else "Mark as read")
        self._tasks.append(run_task(lambda _ctx: self.service.set_read(msg, read), None,
                                    lambda m: QMessageBox.warning(self, "Inbox", m)))

    def reply(self, reply_all: bool):
        msg = self.current and self.service.inbox.find(self.current.key)
        if msg:
            ReplyDialog(self, self.state, self.service, msg, reply_all).exec()

    def add_sender(self):
        msg = self.current
        if msg and msg.from_email:
            added, _ = self.state.add_recipients([Recipient(msg.from_email, msg.from_name)])
            self.state.notify(f"{msg.from_name or msg.from_email} added to recipients" if added else
                              "Already on the recipient list", "success" if added else "info")

    def edit_mailboxes(self):
        MailboxesDialog(self, self.state).exec()
