"""Background workers so the window never freezes while Outlook or SMTP is busy."""

from __future__ import annotations

import math
import threading
import time
import traceback
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..core import storage
from ..core.htmlutil import personalize
from ..core.recipients import Recipient
from ..core.senders import BaseSender, OutgoingEmail, SendError

_active: set = set()   # keep threads/handles alive until they finish


class TaskContext:
    def __init__(self, worker: "_TaskWorker"):
        self._worker = worker
        self._cancel = threading.Event()

    def progress(self, current: int, total: int, message: str = "") -> None:
        self._worker.progress.emit(current, total, message)

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()


class _TaskWorker(QObject):
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[TaskContext], object]):
        super().__init__()
        self.fn = fn
        self.ctx = TaskContext(self)

    @Slot()
    def run(self):
        try:
            result = self.fn(self.ctx)
        except SendError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - surface every error to the UI
            traceback.print_exc()
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.done.emit(result)


class TaskHandle(QObject):
    """Lives in the GUI thread so callbacks always run on the GUI thread."""

    def __init__(self, on_done=None, on_error=None, on_progress=None):
        super().__init__()
        self.on_done = on_done
        self.on_error = on_error
        self.on_progress = on_progress
        self.ctx: TaskContext | None = None
        self.thread: QThread | None = None
        self._bundle = None

    def _cleanup(self):
        # Runs on the GUI thread: let the worker thread end before dropping our references.
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
        _active.discard(self._bundle)

    @Slot(object)
    def _done(self, result):
        self._cleanup()
        if self.on_done:
            self.on_done(result)

    @Slot(str)
    def _failed(self, message):
        self._cleanup()
        if self.on_error:
            self.on_error(message)

    @Slot(int, int, str)
    def _progress(self, current, total, message):
        if self.on_progress:
            self.on_progress(current, total, message)

    def cancel(self):
        if self.ctx:
            self.ctx.cancel()

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()


def run_task(fn: Callable[[TaskContext], object], on_done=None, on_error=None,
             on_progress=None) -> TaskHandle:
    handle = TaskHandle(on_done, on_error, on_progress)
    thread = QThread()
    worker = _TaskWorker(fn)
    worker.moveToThread(thread)
    handle.ctx = worker.ctx
    handle.thread = thread

    worker.done.connect(handle._done)
    worker.failed.connect(handle._failed)
    worker.progress.connect(handle._progress)
    thread.started.connect(worker.run)

    handle._bundle = (thread, worker, handle)
    _active.add(handle._bundle)
    thread.start()
    return handle


class CampaignWorker(QObject):
    """Sends one email per recipient, waiting ``interval`` seconds between sends."""

    item_started = Signal(int)
    item_done = Signal(int, str, str)       # index, status (sent|failed), message
    countdown = Signal(int)                 # seconds until the next email
    paused_changed = Signal(bool)
    auto_paused = Signal(str)
    finished = Signal(dict)

    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, sender: BaseSender, recipients: list[Recipient], subject: str, html: str,
                 attachments: list[str], interval: int, fallback: str, session: dict):
        super().__init__()
        self.sender = sender
        self.recipients = recipients
        self.subject = subject
        self.html = html
        self.attachments = attachments
        self.interval = max(1, int(interval))
        self.fallback = fallback
        self.session = session
        self._stop = threading.Event()
        self._pause = threading.Event()

    # thread-safe controls --------------------------------------------------
    def pause(self):
        self._pause.set()
        self.paused_changed.emit(True)

    def resume(self):
        self._pause.clear()
        self.paused_changed.emit(False)

    def stop(self):
        self._stop.set()
        self._pause.clear()

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    # ---------------------------------------------------------------------
    def _wait_while_paused(self):
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(0.1)

    def _wait_interval(self, started_at: float):
        remaining = self.interval - (time.monotonic() - started_at)
        last = time.monotonic()
        shown = None
        while remaining > 0 and not self._stop.is_set():
            now = time.monotonic()
            if not self._pause.is_set():
                remaining -= now - last
            last = now
            seconds = max(0, math.ceil(remaining))
            if seconds != shown:
                self.countdown.emit(seconds)
                shown = seconds
            time.sleep(0.1)
        self.countdown.emit(0)

    def _record(self, recipient: Recipient, status: str, message: str):
        self.session["results"].append({
            "email": recipient.email, "name": recipient.name, "status": status,
            "time": datetime.now().isoformat(timespec="seconds"), "message": message,
        })
        if status == "sent":
            self.session["sent"] += 1
        else:
            self.session["failed"] += 1
        try:
            storage.save_session(self.session)
        except OSError:
            pass

    @Slot()
    def run(self):
        total = len(self.recipients)
        try:
            self.sender.open()
        except Exception as exc:  # noqa: BLE001
            self.session.update(status="error", error=str(exc),
                                finished=datetime.now().isoformat(timespec="seconds"))
            storage.save_session(self.session)
            self.finished.emit(self.session)
            return

        consecutive_failures = 0
        try:
            for index, recipient in enumerate(self.recipients):
                if self._stop.is_set():
                    break
                self._wait_while_paused()
                if self._stop.is_set():
                    break

                started_at = time.monotonic()
                self.item_started.emit(index)
                email = OutgoingEmail(
                    to=[recipient.email],
                    subject=personalize(self.subject, recipient, self.fallback),
                    html=personalize(self.html, recipient, self.fallback, is_html=True),
                    attachments=self.attachments,
                )
                try:
                    self.sender.send(email)
                    status, message = "sent", ""
                    consecutive_failures = 0
                except Exception as exc:  # noqa: BLE001
                    status, message = "failed", str(exc) or type(exc).__name__
                    consecutive_failures += 1
                self._record(recipient, status, message)
                self.item_done.emit(index, status, message)

                if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES and not self._pause.is_set():
                    self._pause.set()
                    self.paused_changed.emit(True)
                    self.auto_paused.emit(message)
                    consecutive_failures = 0

                if index < total - 1:
                    self._wait_interval(started_at)
        finally:
            try:
                self.sender.close()
            except Exception:  # noqa: BLE001
                pass

        done = self.session["sent"] + self.session["failed"]
        self.session["status"] = "stopped" if done < total else "completed"
        self.session["finished"] = datetime.now().isoformat(timespec="seconds")
        storage.save_session(self.session)
        self.finished.emit(self.session)
