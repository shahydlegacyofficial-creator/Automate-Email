"""Write and send a single email manually."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from ...core import storage
from ...core.htmlutil import build_email_html
from ...core.recipients import EMAIL_FIND_RE, is_valid_email, normalize_email
from ...core.senders import OutgoingEmail, backend_label
from ..editor import AttachmentList, EmailEditor
from ..widgets import Card, Page, button, field_label, label
from ..workers import run_task


def _addresses(text: str) -> tuple[list[str], list[str]]:
    found, bad = [], []
    for token in [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]:
        match = EMAIL_FIND_RE.search(token)
        email = normalize_email(match.group(0)) if match else normalize_email(token)
        (found if is_valid_email(email) else bad).append(email)
    return found, bad


class QuickSendPage(Page):
    def __init__(self, state):
        super().__init__("Write & send",
                         "Compose a one-off email and send it straight away - perfect for replies, "
                         "quotes and individual customer follow-ups.")
        self.state = state
        self._task = None

        load_btn = button("Copy campaign draft", "compose")
        load_btn.setToolTip("Start from the email in Compose")
        load_btn.clicked.connect(self.copy_campaign)
        clear_btn = button("Clear", "trash", "ghost")
        clear_btn.clicked.connect(self.clear)
        self.header_actions.addWidget(load_btn)
        self.header_actions.addWidget(clear_btn)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.content.addLayout(body, 1)

        card = Card("New message")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.to = QLineEdit()
        self.to.setPlaceholderText("customer@example.com, another@example.com")
        self.cc = QLineEdit()
        self.cc.setPlaceholderText("Optional")
        self.bcc = QLineEdit()
        self.bcc.setPlaceholderText("Optional")
        self.subject = QLineEdit()
        self.subject.setProperty("large", True)
        self.subject.setPlaceholderText("Subject")
        for row, (name, widget) in enumerate((("TO", self.to), ("CC", self.cc), ("BCC", self.bcc),
                                              ("SUBJECT", self.subject))):
            lbl = field_label(name)
            lbl.setFixedWidth(64)
            grid.addWidget(lbl, row, 0)
            grid.addWidget(widget, row, 1)
        card.add(grid)
        self.editor = EmailEditor(min_height=400)
        card.add(self.editor, 1)
        body.addWidget(card, 1)

        side = QWidget()
        side.setFixedWidth(340)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(18)
        att_card = Card("Attachments", "JPG, PNG or PDF.")
        self.attachments = AttachmentList()
        att_card.add(self.attachments)
        side_layout.addWidget(att_card)

        send_card = Card("Send")
        self.via = label("", "Muted", wrap=True)
        send_card.add(self.via)
        self.send_btn = button("Send now", "send", "primary", size="large")
        self.send_btn.clicked.connect(self.send)
        send_card.add(self.send_btn)
        send_card.add(label("Sent emails appear in History and in your Outlook Sent Items.", "Hint", wrap=True))
        side_layout.addWidget(send_card)
        side_layout.addStretch(1)
        body.addWidget(side, 0, Qt.AlignmentFlag.AlignTop)

        state.settings_changed.connect(self._refresh_via)
        self._refresh_via()

    def on_show(self):
        self._refresh_via()

    def _refresh_via(self):
        self.via.setText("Sending via " + backend_label(self.state.settings))

    def copy_campaign(self):
        draft = self.state.draft
        self.subject.setText(draft.get("subject", ""))
        self.editor.set_html(draft.get("html", ""))
        self.attachments.set_paths(draft.get("attachments", []))

    def clear(self):
        for field in (self.to, self.cc, self.bcc, self.subject):
            field.clear()
        self.editor.clear()
        self.attachments.set_paths([])

    def send(self):
        to, bad_to = _addresses(self.to.text())
        cc, bad_cc = _addresses(self.cc.text())
        bcc, bad_bcc = _addresses(self.bcc.text())
        bad = bad_to + bad_cc + bad_bcc
        if bad:
            QMessageBox.warning(self, "Check addresses", "These addresses look invalid:\n\n" + "\n".join(bad))
            return
        if not to:
            QMessageBox.information(self, "Send", "Add at least one recipient in the To field.")
            return
        if not self.subject.text().strip():
            if QMessageBox.question(self, "No subject", "Send this email without a subject?") != \
                    QMessageBox.StandardButton.Yes:
                return
        if self.editor.is_blank() and not self.attachments.paths():
            QMessageBox.information(self, "Send", "The email is empty.")
            return

        email = OutgoingEmail(to=to, cc=cc, bcc=bcc, subject=self.subject.text().strip(),
                              html=build_email_html(self.editor.html()), attachments=self.attachments.paths())
        sender = self.state.make_sender()
        settings = self.state.settings

        def work(_ctx):
            with sender:
                sender.send(email)
            session = storage.new_session("manual", email.subject, settings.get("backend", ""), 0,
                                          len(to), email.attachments)
            now = datetime.now().isoformat(timespec="seconds")
            for address in to:
                session["results"].append({"email": address, "name": "", "status": "sent",
                                           "time": now, "message": "Sent manually"})
            session.update(sent=len(to), status="completed", finished=now)
            storage.save_session(session)

        self.send_btn.setEnabled(False)
        self.send_btn.setText("Sending…")

        def finish():
            self.send_btn.setEnabled(True)
            self.send_btn.setText("Send now")

        def done(_):
            finish()
            self.state.notify(f"Email sent to {', '.join(to)}", "success")
            self.state.history_changed.emit()
            self.clear()

        def failed(message):
            finish()
            QMessageBox.critical(self, "Sending failed", message)

        self._task = run_task(work, done, failed)
