"""Shared dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout

from ...core.htmlutil import build_email_html, personalize
from ...core.recipients import Recipient
from ..widgets import label


class PreviewDialog(QDialog):
    """Shows the email exactly as one customer will receive it."""

    def __init__(self, parent, subject: str, html: str, recipient: Recipient, fallback: str,
                 attachments: list[str], signature: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Email preview")
        self.resize(820, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        layout.addWidget(label("Preview", "PageTitle"))
        meta = QVBoxLayout()
        meta.setSpacing(4)
        meta.addWidget(self._meta_row("To", f"{recipient.name} <{recipient.email}>" if recipient.name
                                      else recipient.email))
        meta.addWidget(self._meta_row("Subject", personalize(subject, recipient, fallback)))
        if attachments:
            import os
            meta.addWidget(self._meta_row("Attachments", ", ".join(os.path.basename(a) for a in attachments)))
        layout.addLayout(meta)

        browser = QTextBrowser()
        browser.setObjectName("EmailPaper")
        browser.setOpenExternalLinks(True)
        browser.setHtml(build_email_html(personalize(html, recipient, fallback, is_html=True), signature))
        layout.addWidget(browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _meta_row(name: str, value: str):
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        key = label(name, "FieldLabel")
        key.setFixedWidth(90)
        row.addWidget(key)
        val = QLabel(value)
        val.setWordWrap(True)
        row.addWidget(val, 1)
        return w
