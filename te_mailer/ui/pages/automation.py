"""Automated campaign: one email to one customer, then wait, then the next."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from PySide6.QtCore import QThread, Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QHeaderView, QMessageBox, QProgressBar, QSpinBox, QVBoxLayout, QWidget,
)

from ...core import storage
from ...core.htmlutil import build_email_html, is_blank_html
from ...core.recipients import is_suppressed, parse_suppression
from ...core.senders import backend_label, outlook_available
from .. import theme
from ..icons import icon
from ..widgets import (
    Banner, Card, Page, Pill, StatCard, button, divider, field_label, format_duration, label,
    make_table, status_item, table_item,
)
from ..signature_assets import signature_html
from ..workers import CampaignWorker


class AutomationPage(Page):
    def __init__(self, state):
        super().__init__("Automation",
                         "Sends your email to one customer at a time, waiting between each one "
                         "(default: 1 email every minute).")
        self.state = state
        self.thread: QThread | None = None
        self.worker: CampaignWorker | None = None
        self.session: dict | None = None
        self.total = 0
        self.done = 0
        self.failed = 0
        self.interval = 60
        self.countdown_value = 0
        self.started_at: datetime | None = None

        edit_btn = button("Edit email", "compose")
        edit_btn.clicked.connect(lambda: state.navigate.emit("compose"))
        rec_btn = button("Edit recipients", "users")
        rec_btn.clicked.connect(lambda: state.navigate.emit("recipients"))
        self.header_actions.addWidget(edit_btn)
        self.header_actions.addWidget(rec_btn)

        self.mode_banner = Banner("")
        self.mode_banner.hide()
        self.content.addWidget(self.mode_banner)

        # ---- stats
        stats = QHBoxLayout()
        stats.setSpacing(16)
        self.stat_total = StatCard("Recipients", "0", "users", "accent")
        self.stat_sent = StatCard("Sent", "0", "check", "success")
        self.stat_failed = StatCard("Failed", "0", "x-circle", "danger")
        self.stat_left = StatCard("Remaining", "0", "history", "warning")
        for card in (self.stat_total, self.stat_sent, self.stat_failed, self.stat_left):
            stats.addWidget(card)
        self.content.addLayout(stats)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.content.addLayout(row)

        # ---- campaign setup card
        setup = Card("Campaign", "Review before starting.")
        setup.add(field_label("SUBJECT"))
        self.subject_label = label("", wrap=True)
        self.subject_label.setStyleSheet("font-weight:600;")
        setup.add(self.subject_label)
        self.attach_label = label("", "Muted", wrap=True)
        setup.add(self.attach_label)
        setup.add(field_label("SENDING VIA"))
        self.backend_label = label("", "Muted", wrap=True)
        setup.add(self.backend_label)
        setup.add(divider())
        setup.add(field_label("TIME BETWEEN EMAILS"))
        interval_row = QHBoxLayout()
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 3600)
        self.interval_spin.setSingleStep(10)
        self.interval_spin.setSuffix("  seconds")
        self.interval_spin.setValue(int(state.settings.get("interval_seconds", 60)))
        self.interval_spin.setMinimumWidth(150)
        self.interval_spin.valueChanged.connect(self._interval_changed)
        interval_row.addWidget(self.interval_spin)
        interval_row.addStretch(1)
        setup.add(interval_row)
        self.interval_hint = label("", "Hint", wrap=True)
        setup.add(self.interval_hint)
        setup.add(divider())

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.start_btn = button("Start sending", "play", "primary", size="large")
        self.start_btn.clicked.connect(self.start)
        self.pause_btn = button("Pause", "pause", size="large")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn = button("Stop", "stop", "danger", size="large")
        self.stop_btn.clicked.connect(self.stop)
        controls.addWidget(self.start_btn, 1)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.stop_btn)
        setup.add(controls)
        setup_wrap = QWidget()
        sw = QVBoxLayout(setup_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.addWidget(setup)
        sw.addStretch(1)
        setup_wrap.setFixedWidth(400)
        row.addWidget(setup_wrap)

        # ---- progress card
        progress = Card("Session progress")
        self.state_pill = Pill("Ready", None)
        progress.add_action(self.state_pill)

        counter_row = QHBoxLayout()
        counter_col = QVBoxLayout()
        counter_col.setSpacing(0)
        self.counter = label("0 / 0", "BigCounter")
        counter_col.addWidget(self.counter)
        counter_col.addWidget(label("emails sent this session", "Muted"))
        counter_row.addLayout(counter_col, 1)
        countdown_col = QVBoxLayout()
        countdown_col.setSpacing(0)
        self.countdown_label = label("--:--", "Countdown")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        countdown_col.addWidget(self.countdown_label)
        self.countdown_caption = label("next email in", "Muted")
        self.countdown_caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        countdown_col.addWidget(self.countdown_caption)
        counter_row.addLayout(countdown_col)
        progress.add(counter_row)

        self.bar = QProgressBar()
        self.bar.setObjectName("BigProgress")
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        progress.add(self.bar)

        info = QGridLayout()
        info.setHorizontalSpacing(24)
        info.setVerticalSpacing(6)
        self.current_label = label("—")
        self.started_label = label("—")
        self.eta_label = label("—")
        self.rate_label = label("—")
        for i, (caption, widget) in enumerate((("NOW SENDING TO", self.current_label),
                                                ("STARTED", self.started_label),
                                                ("ESTIMATED FINISH", self.eta_label),
                                                ("SUCCESS RATE", self.rate_label))):
            info.addWidget(field_label(caption), 0 if i < 2 else 2, i % 2)
            info.addWidget(widget, 1 if i < 2 else 3, i % 2)
        progress.add(info)
        progress.body.addStretch(1)
        row.addWidget(progress, 1)

        # ---- log
        log = Card("Activity log", "Every email in this session and its delivery status.")
        self.table = make_table(["#", "Time", "Recipient", "Name", "Status", "Details"], 5)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 170)
        self.table.setColumnWidth(4, 110)
        self.table.setMinimumHeight(320)
        log.add(self.table, 1)
        self.content.addWidget(log, 1)

        state.draft_changed.connect(self.refresh_summary)
        state.recipients_changed.connect(self.refresh_summary)
        state.settings_changed.connect(self._settings_changed)
        self._set_running(False)
        self.refresh_summary()

    # ------------------------------------------------------------ summary
    def on_show(self):
        self.refresh_summary()

    def _settings_changed(self):
        if not self.is_running():
            self.interval_spin.setValue(int(self.state.settings.get("interval_seconds", 60)))
        self.refresh_summary()

    def _interval_changed(self, _value: int):
        if not self.is_running():
            self.refresh_summary()

    def _eligible(self):
        return self.eligible_from(self.state.recipients)

    def refresh_summary(self):
        draft = self.state.draft
        subject = draft.get("subject", "").strip()
        self.subject_label.setText(subject or "<i>No subject yet - write your email first</i>")
        atts = draft.get("attachments", [])
        self.attach_label.setText(
            ("📎 " + ", ".join(os.path.basename(a) for a in atts)) if atts else "No attachments")
        self.backend_label.setText(backend_label(self.state.settings))
        self._update_interval_hint()

        backend = self.state.settings.get("backend")
        if backend == "simulate":
            self.mode_banner.text.setText("<b>Simulation mode is on</b> - campaigns run normally but no "
                                          "emails are actually sent. Change it in Settings.")
            self.mode_banner.show()
        elif backend == "outlook" and not outlook_available()[0]:
            self.mode_banner.text.setText("<b>Outlook is not available on this computer.</b> "
                                          + outlook_available()[1] + " Use SMTP or Simulation in Settings.")
            self.mode_banner.show()
        else:
            self.mode_banner.hide()

        if self.is_running():
            return
        eligible, skipped = self._eligible()
        count = len(eligible)
        self.stat_total.set_value(f"{count:,}", f"{skipped} on do-not-email list skipped" if skipped else "")
        self.stat_left.set_value(f"{count:,}")
        self.stat_sent.set_value("0")
        self.stat_failed.set_value("0")
        duration = max(0, count - 1) * self.interval_spin.value()
        self.eta_label.setText(f"≈ {format_duration(duration)} for {count:,} emails" if count else "—")
        self.counter.setText(f"0 / {count:,}")

    def _update_interval_hint(self):
        value = self.interval_spin.value()
        minutes = value / 60
        every = f"{minutes:g} minute{'s' if minutes != 1 else ''}" if value % 60 == 0 else f"{value} seconds"
        self.interval_hint.setText(f"1 email every {every} · about {3600 / value:.0f} emails per hour")

    # ------------------------------------------------------------ running state
    def is_running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)
        self.interval_spin.setEnabled(not running)
        if not running:
            self.pause_btn.setText("Pause")
            self.pause_btn.setIcon(icon("pause"))

    def readiness_problem(self, subject: str, html: str, attachments: list[str]) -> tuple[str, str] | None:
        """Why a campaign can't start right now, as (message, page to fix it on), or None."""
        if self.is_running():
            return "A campaign is already running. Wait for it to finish or stop it first.", "automation"
        if not subject.strip() or is_blank_html(html):
            return "Please write a subject and email content first.", "compose"
        missing = [a for a in attachments if not os.path.isfile(a)]
        if missing:
            return "These attachments can no longer be found:\n\n" + "\n".join(missing), "compose"
        backend = self.state.settings.get("backend")
        if backend == "outlook":
            ok, reason = outlook_available()
            if not ok:
                return reason, "settings"
        if backend == "graph" and not self.state.settings.get("ms_account"):
            return "Sign in to Microsoft 365 / new Outlook in Settings first.", "settings"
        return None

    def eligible_from(self, recipients) -> tuple[list, int]:
        suppression = parse_suppression(self.state.settings.get("suppression_list", ""))
        eligible = [r for r in recipients if not is_suppressed(r.email, suppression)]
        return eligible, len(recipients) - len(eligible)

    def start(self):
        if self.is_running():
            return
        draft = self.state.draft
        subject = draft.get("subject", "").strip()
        html = draft.get("html", "")
        attachments = draft.get("attachments", [])
        problem = self.readiness_problem(subject, html, attachments)
        if problem:
            QMessageBox.information(self, "Not ready", problem[0])
            if problem[1] in ("compose", "settings"):
                self.state.navigate.emit(problem[1])
            return
        eligible, skipped = self._eligible()
        if not eligible:
            QMessageBox.information(self, "Not ready", "Add at least one recipient first.")
            self.state.navigate.emit("recipients")
            return

        interval = self.interval_spin.value()
        count = len(eligible)
        duration = format_duration(max(0, count - 1) * interval)
        text = (f"<p>Send <b>“{subject}”</b> to <b>{count:,}</b> customer{'s' if count != 1 else ''}, "
                f"one email every <b>{interval} seconds</b>.</p>"
                f"<p>Sending via: {backend_label(self.state.settings)}<br>"
                f"Estimated duration: about {duration}</p>")
        if skipped:
            text += f"<p>{skipped} address(es) on the do-not-email list will be skipped.</p>"
        text += "<p>Keep this app (and Outlook) open until the campaign finishes.</p>"
        if QMessageBox.question(self, "Start campaign", text) != QMessageBox.StandardButton.Yes:
            return
        if interval != self.state.settings.get("interval_seconds"):
            self.state.save_settings({"interval_seconds": interval})
        self.launch(subject, html, list(attachments), eligible, interval)

    def launch(self, subject: str, html: str, attachments: list[str], eligible: list, interval: int,
               started_by: str = "") -> dict:
        """Start sending without any questions - callers have already checked and confirmed."""
        backend = self.state.settings.get("backend")
        count = len(eligible)
        self.interval_spin.setValue(interval)
        self.total = count
        self.done = 0
        self.failed = 0
        self.interval = interval
        self.countdown_value = 0
        self.started_at = datetime.now()
        self.session = storage.new_session("campaign", subject, backend, interval, count, attachments)
        self.session["queue"] = [r.to_dict() for r in eligible]
        if started_by:
            self.session["started_by"] = started_by
        storage.save_session(self.session)

        self.table.setRowCount(0)
        self.table.setRowCount(count)
        muted = QColor(theme.current()["text_muted"])
        for i, r in enumerate(eligible):
            num = table_item(i + 1)
            num.setForeground(muted)
            self.table.setItem(i, 0, num)
            self.table.setItem(i, 1, table_item(""))
            self.table.setItem(i, 2, table_item(r.email))
            self.table.setItem(i, 3, table_item(r.name))
            self.table.setItem(i, 4, status_item("pending"))
            self.table.setItem(i, 5, table_item(""))
        self.recipients = [r for r in eligible]

        self.bar.setRange(0, count)
        self.bar.setValue(0)
        self.started_label.setText(self.started_at.strftime("%d %b %Y, %H:%M"))
        self.subject_label.setText(subject)

        self.worker = CampaignWorker(self.state.make_sender(), self.recipients, subject,
                                     build_email_html(html, signature_html(self.state.settings)), list(attachments), interval,
                                     self.state.settings.get("name_fallback", ""), self.session)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.item_started.connect(self._on_item_started)
        self.worker.item_done.connect(self._on_item_done)
        self.worker.countdown.connect(self._on_countdown)
        self.worker.paused_changed.connect(self._on_paused)
        self.worker.auto_paused.connect(self._on_auto_paused)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self._on_finished)
        self.state.campaign_running = True
        self._set_running(True)
        self._update_counts()
        self.state_pill.set("Running", "accent")
        self.state.campaign_status.emit("Sending", 0, count)
        self.thread.start()
        return self.session

    def status(self) -> dict:
        """A snapshot of the current (or last) campaign for the AI assistant."""
        running = self.is_running()
        info: dict = {"running": running}
        if self.session is None:
            info["message"] = "No campaign has been started since the app opened."
            return info
        sent = self.done - self.failed
        info.update({
            "subject": self.session.get("subject", ""),
            "started": self.session.get("started"),
            "total": self.total,
            "processed": self.done,
            "sent": sent,
            "failed": self.failed,
            "remaining": self.total - self.done,
            "interval_seconds": self.interval,
            "paused": bool(running and self.worker is not None and self.worker.is_paused),
            "state": self.state_pill.text(),
        })
        if running and info["remaining"] > 0:
            seconds = self.countdown_value + max(0, info["remaining"] - 1) * self.interval
            info["estimated_finish"] = (datetime.now() + timedelta(seconds=seconds)).strftime("%H:%M")
        else:
            info["finished_status"] = self.session.get("status")
        failures = [r for r in self.session.get("results", []) if r.get("status") != "sent"][-5:]
        if failures:
            info["recent_failures"] = [{"email": r.get("email"), "error": r.get("message", "")} for r in failures]
        return info

    def pause_campaign(self) -> None:
        if self.worker and not self.worker.is_paused:
            self.worker.pause()

    def resume_campaign(self) -> None:
        if self.worker and self.worker.is_paused:
            self.worker.resume()

    def stop_campaign(self) -> None:
        if self.worker:
            self.worker.stop()
            self.state_pill.set("Stopping…", "warning")

    def toggle_pause(self):
        if not self.worker:
            return
        if self.worker.is_paused:
            self.worker.resume()
        else:
            self.worker.pause()

    def stop(self):
        if not self.worker:
            return
        if QMessageBox.question(self, "Stop campaign",
                                "Stop sending? Customers not yet emailed will not receive it. "
                                "You can re-queue them later from History.") == QMessageBox.StandardButton.Yes:
            self.stop_campaign()

    def shutdown(self, timeout_ms: int = 8000) -> None:
        """Stop the campaign when the app closes."""
        if self.worker:
            self.worker.stop()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(timeout_ms)

    # ------------------------------------------------------------ worker slots
    def _update_counts(self):
        sent = self.done - self.failed
        remaining = self.total - self.done
        self.stat_total.set_value(f"{self.total:,}", "")
        self.stat_sent.set_value(f"{sent:,}")
        self.stat_failed.set_value(f"{self.failed:,}")
        self.stat_left.set_value(f"{remaining:,}")
        self.counter.setText(f"{sent:,} / {self.total:,}")
        self.bar.setValue(self.done)
        self.bar.setFormat(f"{self.done:,} of {self.total:,} processed  ·  %p%")
        self.rate_label.setText(f"{(sent / self.done * 100):.0f}%" if self.done else "—")
        self._update_eta()

    def _update_eta(self):
        remaining = self.total - self.done
        if remaining <= 0 or not self.is_running():
            return
        seconds = self.countdown_value + max(0, remaining - 1) * self.interval
        finish = datetime.now() + timedelta(seconds=seconds)
        self.eta_label.setText(f"{finish.strftime('%H:%M')}  ({format_duration(seconds)} left)")

    @Slot(int)
    def _on_item_started(self, index: int):
        self.table.setItem(index, 4, status_item("sending"))
        self.table.scrollToItem(self.table.item(index, 2))
        r = self.recipients[index]
        self.current_label.setText(f"{r.name} <{r.email}>" if r.name else r.email)
        self.countdown_label.setText("Now")
        self.countdown_caption.setText("sending…")

    @Slot(int, str, str)
    def _on_item_done(self, index: int, status: str, message: str):
        self.done += 1
        if status != "sent":
            self.failed += 1
        self.table.setItem(index, 1, table_item(datetime.now().strftime("%H:%M:%S")))
        self.table.setItem(index, 4, status_item(status))
        details = table_item(message or "Delivered to outbox")
        details.setToolTip(message)
        self.table.setItem(index, 5, details)
        self._update_counts()
        self.state.campaign_status.emit("Sending", self.done, self.total)

    @Slot(int)
    def _on_countdown(self, seconds: int):
        self.countdown_value = seconds
        if seconds > 0:
            m, s = divmod(seconds, 60)
            self.countdown_label.setText(f"{m:02d}:{s:02d}")
            paused = self.worker is not None and self.worker.is_paused
            self.countdown_caption.setText("paused" if paused else "next email in")
            self.current_label.setText("Waiting for the next send…")
        self._update_eta()

    @Slot(bool)
    def _on_paused(self, paused: bool):
        if paused:
            self.pause_btn.setText("Resume")
            self.pause_btn.setIcon(icon("play"))
            self.state_pill.set("Paused", "warning")
            self.countdown_caption.setText("paused")
            self.state.campaign_status.emit("Paused", self.done, self.total)
        else:
            self.pause_btn.setText("Pause")
            self.pause_btn.setIcon(icon("pause"))
            self.state_pill.set("Running", "accent")
            self.countdown_caption.setText("next email in")
            self.state.campaign_status.emit("Sending", self.done, self.total)

    @Slot(str)
    def _on_auto_paused(self, message: str):
        QMessageBox.warning(self, "Campaign paused",
                            "Sending was paused after several failures in a row.\n\n"
                            f"Last error: {message}\n\nFix the problem (e.g. open Outlook) and press Resume.")

    @Slot(dict)
    def _on_finished(self, session: dict):
        self.thread.quit()
        self.thread.wait(5000)
        self.worker = None
        self.thread = None
        self.state.campaign_running = False
        self._set_running(False)
        self.countdown_label.setText("--:--")
        self.countdown_caption.setText("next email in")
        self.current_label.setText("—")
        status = session.get("status")
        sent, failed = session.get("sent", 0), session.get("failed", 0)
        if status == "error":
            self.state_pill.set("Could not start", "danger")
            self.state.campaign_status.emit("", 0, 0)
            QMessageBox.critical(self, "Campaign could not start", session.get("error", "Unknown error"))
        elif status == "stopped":
            self.state_pill.set("Stopped", "warning")
            self.eta_label.setText("—")
            self.state.campaign_status.emit("", 0, 0)
            self.state.notify(f"Campaign stopped · {sent} sent, {failed} failed")
        else:
            self.state_pill.set("Completed", "success")
            self.eta_label.setText(datetime.now().strftime("Finished %H:%M"))
            self.state.campaign_status.emit("", 0, 0)
            self.state.notify(f"Campaign complete · {sent} sent, {failed} failed", "success")
        self.state.history_changed.emit()
