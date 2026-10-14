"""Compose the campaign email: subject, rich body, attachments, templates."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QMenu, QMessageBox, QToolButton, QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.htmlutil import PLACEHOLDERS, build_email_html, personalize
from ...core.recipients import Recipient, is_valid_email
from ...core.senders import OutgoingEmail, backend_label
from ..editor import AttachmentList, EmailEditor
from ..icons import icon
from ..widgets import Card, Page, Pill, button, field_label, label
from ..signature_assets import signature_html
from ..workers import run_task
from .dialogs import PreviewDialog


def placeholder_button(target: QLineEdit) -> QToolButton:
    btn = QToolButton()
    btn.setObjectName("EditorTool")
    btn.setIcon(icon("braces", "accent"))
    btn.setIconSize(QSize(16, 16))
    btn.setToolTip("Insert a personalised field")
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    menu = QMenu(btn)
    for key, text in PLACEHOLDERS.items():
        menu.addAction(f"{text}   {{{key}}}", lambda k=key: target.insert("{" + k + "}"))
    btn.setMenu(menu)
    return btn


class ComposePage(Page):
    def __init__(self, state):
        super().__init__("Compose email",
                         "Write the message the automation sends to each customer. "
                         "Fields like {first_name} are replaced for every recipient.")
        self.state = state
        self._loading = False
        self._test_task = None

        self.preview_btn = button("Preview", "eye")
        self.preview_btn.clicked.connect(self.preview)
        self.test_btn = button("Send test to me", "flask")
        self.test_btn.clicked.connect(self.send_test)
        self.next_btn = button("Continue to recipients", "users", "primary")
        self.next_btn.clicked.connect(lambda: state.navigate.emit("recipients"))
        for b in (self.preview_btn, self.test_btn, self.next_btn):
            self.header_actions.addWidget(b)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.content.addLayout(body, 1)

        # ---- left: message
        message = Card("Message")
        self.status_pill = Pill("Draft saved", "success")
        message.add_action(self.status_pill)
        message.add(field_label("SUBJECT"))
        subject_row = QHBoxLayout()
        subject_row.setSpacing(6)
        self.subject = QLineEdit()
        self.subject.setProperty("large", True)
        self.subject.setPlaceholderText("e.g. {first_name}, your exclusive Travel Essence holiday offers")
        subject_row.addWidget(self.subject, 1)
        subject_row.addWidget(placeholder_button(self.subject))
        message.add(subject_row)
        message.add(field_label("EMAIL CONTENT"))
        self.editor = EmailEditor(min_height=430)
        message.add(self.editor, 1)
        body.addWidget(message, 1)

        # ---- right column
        side = QVBoxLayout()
        side.setSpacing(18)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(340)
        side.setContentsMargins(0, 0, 0, 0)

        attach_card = Card("Attachments", "JPG, PNG or PDF files sent with every email.")
        self.attachments = AttachmentList()
        attach_card.add(self.attachments)
        side.addWidget(attach_card)

        tpl_card = Card("Templates", "Save and reuse your best emails.")
        self.template_box = QComboBox()
        self.template_box.setPlaceholderText("No saved templates")
        tpl_card.add(self.template_box)
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(6)
        load_btn = button("Load", "folder")
        load_btn.clicked.connect(self.load_template)
        save_btn = button("Save", "save")
        save_btn.clicked.connect(self.save_template)
        del_btn = button("", "trash", "ghost", "Delete selected template")
        del_btn.clicked.connect(self.delete_template)
        tpl_row.addWidget(load_btn)
        tpl_row.addWidget(save_btn)
        tpl_row.addStretch(1)
        tpl_row.addWidget(del_btn)
        tpl_card.add(tpl_row)
        new_btn = button("Start a new blank email", "plus", "ghost")
        new_btn.clicked.connect(self.new_email)
        tpl_card.add(new_btn)
        side.addWidget(tpl_card)

        tips = Card("Personalisation")
        tips.add(label("<b>{first_name}</b> → Sarah<br><b>{name}</b> → Sarah Khan<br>"
                       "<b>{email}</b> → sarah@example.com<br><br>"
                       "If a customer has no name, the fallback from Settings is used "
                       "(e.g. “Valued Customer”).", "Muted", wrap=True))
        side.addWidget(tips)
        side.addStretch(1)
        body.addWidget(side_widget, 0, Qt.AlignmentFlag.AlignTop)

        self.subject.textChanged.connect(self._changed)
        self.editor.changed.connect(self._changed)
        self.attachments.changed.connect(self._changed)
        state.draft_changed.connect(self.load_draft)

        self.load_draft()
        self.reload_templates()

    # ------------------------------------------------------------ draft
    def load_draft(self):
        self._loading = True
        draft = self.state.draft
        self.subject.setText(draft.get("subject", ""))
        self.editor.set_html(draft.get("html", ""))
        self.attachments.set_paths(draft.get("attachments", []))
        self._loading = False
        self._update_status()

    def _changed(self):
        if self._loading:
            return
        self.state.update_draft(self.subject.text(), self.editor.html(), self.attachments.paths())
        self._update_status()

    def _update_status(self):
        if not self.subject.text().strip() or self.editor.is_blank():
            self.status_pill.set("Incomplete", "warning")
        else:
            self.status_pill.set("Ready · auto-saved", "success")

    def new_email(self):
        if (self.subject.text() or not self.editor.is_blank()) and QMessageBox.question(
                self, "New email", "Clear the current subject, content and attachments?") != \
                QMessageBox.StandardButton.Yes:
            return
        self.state.replace_draft("", "", [])

    # ------------------------------------------------------------ templates
    def reload_templates(self):
        self.template_box.clear()
        for tpl in storage.load_templates():
            self.template_box.addItem(tpl.get("name", "Untitled"))

    def save_template(self):
        if self.editor.is_blank() and not self.subject.text().strip():
            QMessageBox.information(self, "Save template", "Write something before saving a template.")
            return
        default = self.template_box.currentText() or self.subject.text()[:60]
        name, ok = QInputDialog.getText(self, "Save template", "Template name:", text=default)
        if not ok or not name.strip():
            return
        name = name.strip()
        templates = [t for t in storage.load_templates() if t.get("name") != name]
        templates.insert(0, {"name": name, "subject": self.subject.text(), "html": self.editor.html(),
                             "attachments": self.attachments.paths(),
                             "saved": datetime.now().isoformat(timespec="seconds")})
        storage.save_templates(templates)
        self.reload_templates()
        self.template_box.setCurrentText(name)
        self.state.notify(f"Template “{name}” saved", "success")

    def load_template(self):
        name = self.template_box.currentText()
        tpl = next((t for t in storage.load_templates() if t.get("name") == name), None)
        if not tpl:
            return
        if (self.subject.text() or not self.editor.is_blank()) and QMessageBox.question(
                self, "Load template", f"Replace the current email with “{name}”?") != \
                QMessageBox.StandardButton.Yes:
            return
        self.state.replace_draft(tpl.get("subject", ""), tpl.get("html", ""), tpl.get("attachments", []))
        self.state.notify(f"Loaded template “{name}”")

    def delete_template(self):
        name = self.template_box.currentText()
        if not name:
            return
        if QMessageBox.question(self, "Delete template", f"Delete the template “{name}”?") != \
                QMessageBox.StandardButton.Yes:
            return
        storage.save_templates([t for t in storage.load_templates() if t.get("name") != name])
        self.reload_templates()

    # ------------------------------------------------------------ preview & test
    def _sample_recipient(self) -> Recipient:
        if self.state.recipients:
            return self.state.recipients[0]
        return Recipient("customer@example.com", "Sarah Khan")

    def preview(self):
        PreviewDialog(self, self.subject.text(), self.editor.html(), self._sample_recipient(),
                      self.state.settings.get("name_fallback", ""), self.attachments.paths(),
                      signature_html(self.state.settings)).exec()

    def send_test(self):
        if not self.subject.text().strip() or self.editor.is_blank():
            QMessageBox.information(self, "Send test", "Add a subject and some content first.")
            return
        address = self.state.settings.get("test_email", "")
        address, ok = QInputDialog.getText(self, "Send test email",
                                           f"Send a test copy using {backend_label(self.state.settings)}\n\n"
                                           "Test address:", text=address)
        if not ok:
            return
        address = address.strip().lower()
        if not is_valid_email(address):
            QMessageBox.warning(self, "Send test", "Please enter a valid email address.")
            return
        if address != self.state.settings.get("test_email"):
            self.state.save_settings({"test_email": address})

        sample = self._sample_recipient()
        recipient = Recipient(address, sample.name)
        fallback = self.state.settings.get("name_fallback", "")
        email = OutgoingEmail(
            to=[address],
            subject="[TEST] " + personalize(self.subject.text(), recipient, fallback),
            html=build_email_html(personalize(self.editor.html(), recipient, fallback, is_html=True),
                                  signature_html(self.state.settings)),
            attachments=self.attachments.paths(),
        )
        sender = self.state.make_sender()

        def work(_ctx):
            with sender:
                sender.send(email)

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Sending test…")

        def finish():
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Send test to me")

        def ok_cb(_):
            finish()
            self.state.notify(f"Test email sent to {address}", "success")

        def err_cb(msg):
            finish()
            QMessageBox.critical(self, "Test email failed", msg)

        self._test_task = run_task(work, ok_cb, err_cb)
