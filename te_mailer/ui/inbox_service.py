"""Checks the watched mailboxes in the background and tells the rest of the app what arrived."""

from __future__ import annotations

import json
import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from ..core import storage
from ..core.inbox import Inbox, InboxMessage, build_sources, watched
from ..core.senders import create_sender

log = logging.getLogger(__name__)


def record_reply(msg: InboxMessage, result: dict, attachments: list[str], started_by: str = "") -> None:
    """Put a sent reply in History, like any other email."""
    from datetime import datetime

    session = storage.new_session("reply", result.get("subject", ""), msg.source, 0,
                                  len(result.get("to", [])), attachments)
    now = datetime.now().isoformat(timespec="seconds")
    for address in result.get("to", []) + result.get("cc", []):
        session["results"].append({"email": address, "name": msg.from_name if address == msg.from_email else "",
                                   "status": "sent", "time": now, "message": f"Reply to “{msg.subject}”"})
    session.update(sent=len(result.get("to", [])), status="completed", finished=now)
    if started_by:
        session["started_by"] = started_by
    storage.save_session(session)


class InboxService(QObject):
    changed = Signal()          # the list or the unread count changed
    arrived = Signal(list)      # [InboxMessage] that are new since the last check
    checking = Signal(bool)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.inbox = Inbox(self._sources)
        self._thread: threading.Thread | None = None
        self._signature = self._watch_signature()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        state.settings_changed.connect(self._settings_changed)

    # ------------------------------------------------------------ mailboxes
    def _sources(self):
        settings = dict(self.state.settings)

        def sender():
            password = storage.get_password(settings.get("smtp_username", "")) if settings.get("backend") == "smtp" else ""
            return create_sender(settings, password)

        return build_sources(settings, storage.get_password, sender)

    def _watch_signature(self) -> str:
        s = self.state.settings
        return json.dumps([s.get("inbox_enabled"), watched(s), s.get("backend")], sort_keys=True, default=str)

    def watching(self) -> list[str]:
        return [src.label for src in self._sources()]

    # ------------------------------------------------------------ schedule
    def start(self) -> None:
        self._reschedule()
        QTimer.singleShot(2500, self.check)

    def stop(self) -> None:
        self._timer.stop()

    def _reschedule(self) -> None:
        minutes = max(1, int(self.state.settings.get("inbox_interval_minutes", 2) or 2))
        if self.state.settings.get("inbox_enabled", True):
            self._timer.start(minutes * 60_000)
        else:
            self._timer.stop()

    def _settings_changed(self) -> None:
        self._reschedule()
        signature = self._watch_signature()
        if signature != self._signature:
            self._signature = signature
            QTimer.singleShot(300, self.check)

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------ checking
    def check(self) -> None:
        """Check now, in the background (does nothing if a check is already running)."""
        if self.busy:
            return
        self._thread = threading.Thread(target=self._run, name="inbox-check", daemon=True)
        self.checking.emit(True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._publish(self.inbox.refresh())
        except Exception:
            log.exception("Inbox check failed")
        finally:
            self.checking.emit(False)

    def check_now(self) -> list[InboxMessage]:
        """Check and wait (used by the AI assistant from its own thread)."""
        fresh = self.inbox.refresh()
        self._publish(fresh)
        return fresh

    def _publish(self, fresh: list[InboxMessage]) -> None:
        self.changed.emit()
        if fresh:
            self.arrived.emit(fresh)

    # ------------------------------------------------------------ acting
    def set_read(self, msg: InboxMessage, read: bool) -> None:
        self.inbox.set_read(msg, read)
        self.changed.emit()

    def reply(self, msg: InboxMessage, editor_html: str, signature: str, attachments: list[str],
              reply_all: bool, started_by: str = "") -> dict:
        result = self.inbox.reply(msg, editor_html, signature, attachments, reply_all)
        record_reply(msg, result, attachments, started_by)
        self.changed.emit()
        return result
