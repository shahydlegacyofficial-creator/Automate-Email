import threading
import time

from te_mailer.core import storage
from te_mailer.core.recipients import Recipient
from te_mailer.core.senders import BaseSender, SendError


class RecordingSender(BaseSender):
    def __init__(self, fail_for=()):
        self.sent = []
        self.times = []
        self.fail_for = set(fail_for)
        self.opened = self.closed = False

    def open(self):
        self.opened = True

    def send(self, email):
        self.times.append(time.monotonic())
        if email.to[0] in self.fail_for:
            raise SendError("mailbox unavailable")
        self.sent.append(email)

    def close(self):
        self.closed = True


def make_worker(sender, recipients, interval=1):
    from te_mailer.ui.workers import CampaignWorker

    session = storage.new_session("campaign", "Hi {first_name}", "test", interval, len(recipients), [])
    return CampaignWorker(sender, recipients, "Hi {first_name}", "<p>Dear {name}</p>", [], interval,
                          "Valued Customer", session)


def test_sends_one_by_one_with_interval(qapp):
    recipients = [Recipient("a@x.com", "Ann Lee"), Recipient("b@x.com", ""), Recipient("c@x.com", "Cy")]
    sender = RecordingSender(fail_for={"b@x.com"})
    worker = make_worker(sender, recipients, interval=1)
    results, finished = [], []
    worker.item_done.connect(lambda i, s, m: results.append((i, s)))
    worker.finished.connect(finished.append)
    worker.run()

    assert sender.opened and sender.closed
    assert [e.to for e in sender.sent] == [["a@x.com"], ["c@x.com"]]
    assert sender.sent[0].subject == "Hi Ann"
    assert "Dear Ann Lee" in sender.sent[0].html
    assert results == [(0, "sent"), (1, "failed"), (2, "sent")]
    gaps = [b - a for a, b in zip(sender.times, sender.times[1:])]
    assert all(0.9 <= g <= 1.5 for g in gaps), gaps
    session = finished[0]
    assert (session["sent"], session["failed"], session["status"]) == (2, 1, "completed")
    assert storage.load_sessions()[0]["id"] == session["id"]


def test_stop_during_wait(qapp):
    recipients = [Recipient(f"r{i}@x.com") for i in range(5)]
    sender = RecordingSender()
    worker = make_worker(sender, recipients, interval=30)
    finished = []
    worker.finished.connect(finished.append)
    threading.Timer(0.5, worker.stop).start()
    started = time.monotonic()
    worker.run()
    assert time.monotonic() - started < 3
    assert len(sender.sent) == 1
    assert finished[0]["status"] == "stopped"


def test_pause_freezes_countdown(qapp):
    recipients = [Recipient("a@x.com"), Recipient("b@x.com")]
    sender = RecordingSender()
    worker = make_worker(sender, recipients, interval=1)
    worker.item_done.connect(lambda i, s, m: (worker.pause(), threading.Timer(1.0, worker.resume).start())
                             if i == 0 else None)
    worker.run()
    gap = sender.times[1] - sender.times[0]
    assert gap >= 1.8, gap  # 1s interval + ~1s paused


def test_auto_pause_after_repeated_failures(qapp):
    recipients = [Recipient(f"r{i}@x.com") for i in range(4)]
    sender = RecordingSender(fail_for={r.email for r in recipients})
    worker = make_worker(sender, recipients, interval=1)
    reasons = []
    worker.auto_paused.connect(reasons.append)
    worker.auto_paused.connect(lambda _m: threading.Timer(0.3, worker.stop).start())
    worker.run()
    assert reasons == ["mailbox unavailable"]
    assert len(sender.times) == 3
