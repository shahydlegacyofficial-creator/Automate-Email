"""Application-wide shared state (draft, recipients, settings) with change signals."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ..core import storage
from ..core.recipients import Recipient, is_valid_email, merge
from ..core.senders import BaseSender, create_sender


class AppState(QObject):
    recipients_changed = Signal()
    lists_changed = Signal()          # saved (named) recipient lists
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

    # ------------------------------------------------------------ saved lists
    @staticmethod
    def _list_key(name: str) -> str:
        return " ".join((name or "").split()).casefold()

    def saved_lists(self) -> list[dict]:
        return storage.load_lists()

    def find_list(self, name: str) -> dict | None:
        key = self._list_key(name)
        return next((d for d in storage.load_lists() if self._list_key(d["name"]) == key), None)

    def list_recipients(self, entry: dict) -> list[Recipient]:
        rows = [Recipient.from_dict(r) for r in entry.get("recipients", []) if isinstance(r, dict)]
        return [r for r in rows if is_valid_email(r.email)]

    def save_list(self, name: str, recipients: list[Recipient]) -> dict:
        """Create or overwrite a named list (matched case-insensitively, original spelling kept)."""
        from datetime import datetime

        name = " ".join((name or "").split())
        if not name:
            raise ValueError("A list needs a name.")
        lists = storage.load_lists()
        key = self._list_key(name)
        entry = {"name": name, "updated": datetime.now().isoformat(timespec="seconds"),
                 "recipients": [r.to_dict() for r in recipients]}
        for i, existing in enumerate(lists):
            if self._list_key(existing["name"]) == key:
                entry["name"] = existing["name"]
                lists[i] = entry
                break
        else:
            lists.append(entry)
        lists.sort(key=lambda d: d["name"].casefold())
        storage.save_lists(lists)
        self.lists_changed.emit()
        return entry

    def delete_list(self, name: str) -> bool:
        key = self._list_key(name)
        lists = storage.load_lists()
        kept = [d for d in lists if self._list_key(d["name"]) != key]
        if len(kept) == len(lists):
            return False
        storage.save_lists(kept)
        self.lists_changed.emit()
        return True

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
