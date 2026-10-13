"""Application-wide shared state (draft, recipients, settings) with change signals."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ..core import storage
from ..core.recipients import Recipient, is_valid_email, merge
from ..core.senders import BaseSender, create_sender


class AppState(QObject):
    recipients_changed = Signal()
    draft_changed = Signal()          # emitted when the draft is replaced from outside the composer
    settings_changed = Signal()
    history_changed = Signal()
    campaign_status = Signal(str, int, int)   # state text, done, total
    toast = Signal(str, str)                  # message, tone (info | success | danger)
    navigate = Signal(str)                    # page key

    def __init__(self):
        super().__init__()
        self.settings = storage.load_settings()
        self.draft = storage.load_draft()
        self.recipients: list[Recipient] = []
        for row in storage.load_recipients():
            if isinstance(row, dict):
                r = Recipient.from_dict(row)
                if is_valid_email(r.email):
                    self.recipients.append(r)
        self.campaign_running = False

        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(700)
        self._draft_timer.timeout.connect(lambda: storage.save_draft(self.draft))

    # ------------------------------------------------------------ draft
    def update_draft(self, subject: str, html: str, attachments: list[str]) -> None:
        """Called by the composer on every edit (debounced save, no signal)."""
        self.draft = {"subject": subject, "html": html, "attachments": list(attachments)}
        self._draft_timer.start()

    def replace_draft(self, subject: str, html: str, attachments: list[str]) -> None:
        """Replace the draft from elsewhere (templates, Outlook) and notify the composer."""
        self.draft = {"subject": subject, "html": html, "attachments": list(attachments)}
        storage.save_draft(self.draft)
        self.draft_changed.emit()

    def flush(self) -> None:
        if self._draft_timer.isActive():
            self._draft_timer.stop()
        storage.save_draft(self.draft)

    # ------------------------------------------------------------ recipients
    def _persist_recipients(self) -> None:
        storage.save_recipients([r.to_dict() for r in self.recipients])
        self.recipients_changed.emit()

    def add_recipients(self, incoming: list[Recipient]) -> tuple[int, int]:
        self.recipients, added, dupes = merge(self.recipients, incoming)
        self._persist_recipients()
        return added, dupes

    def set_recipients(self, recipients: list[Recipient]) -> None:
        self.recipients = list(recipients)
        self._persist_recipients()

    def remove_emails(self, emails: set[str]) -> int:
        before = len(self.recipients)
        self.recipients = [r for r in self.recipients if r.email not in emails]
        self._persist_recipients()
        return before - len(self.recipients)

    def update_recipient_name(self, email: str, name: str) -> None:
        for r in self.recipients:
            if r.email == email:
                r.name = name.strip()
        storage.save_recipients([r.to_dict() for r in self.recipients])

    # ------------------------------------------------------------ settings
    def save_settings(self, new_settings: dict) -> None:
        self.settings.update(new_settings)
        storage.save_settings(self.settings)
        self.settings_changed.emit()

    def smtp_password(self) -> str:
        return storage.get_password(self.settings.get("smtp_username", ""))

    def make_sender(self) -> BaseSender:
        password = self.smtp_password() if self.settings.get("backend") == "smtp" else ""
        return create_sender(self.settings, password)

    def notify(self, message: str, tone: str = "info") -> None:
        self.toast.emit(message, tone)
