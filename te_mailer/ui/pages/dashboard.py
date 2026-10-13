"""Home dashboard: status at a glance and the 3-step workflow."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ...core import storage
from ...core.htmlutil import is_blank_html
from ...core.senders import backend_label, outlook_available
from ..widgets import Card, IconBadge, Page, Pill, StatCard, button, divider, label


class StepRow(QWidget):
    def __init__(self, number: int, title: str, text: str, action_text: str, icon_name: str, callback):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(14)
        self.badge = IconBadge(icon_name, "accent", 42)
        row.addWidget(self.badge)
        col = QVBoxLayout()
        col.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label(f"{number}. {title}", "CardTitle"))
        self.pill = Pill("")
        head.addWidget(self.pill)
        head.addStretch(1)
        col.addLayout(head)
        self.text = label(text, "Muted", wrap=True)
        col.addWidget(self.text)
        row.addLayout(col, 1)
        self.btn = button(action_text)
        self.btn.clicked.connect(callback)
        row.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_status(self, text: str, tone: str | None):
        self.pill.set(text, tone)


class DashboardPage(Page):
    def __init__(self, state):
        super().__init__("Welcome back", "Travel Essence email automation - compose once, then let the "
                                         "app send it to each customer one by one.")
        self.state = state

        stats = QHBoxLayout()
        stats.setSpacing(16)
        self.stat_recipients = StatCard("Recipients ready", "0", "users", "accent", "in your list")
        self.stat_sent = StatCard("Emails sent", "0", "send", "success", "all time")
        self.stat_campaigns = StatCard("Campaigns run", "0", "zap", "warning", "automation sessions")
        self.stat_failed = StatCard("Failed sends", "0", "x-circle", "danger", "all time")
        for card in (self.stat_recipients, self.stat_sent, self.stat_campaigns, self.stat_failed):
            stats.addWidget(card)
        self.content.addLayout(stats)

        grid = QHBoxLayout()
        grid.setSpacing(18)

        steps = Card("Get a campaign out in 3 steps")
        nav = state.navigate.emit
        self.step1 = StepRow(1, "Write your email", "Subject, message, attachments and personal fields.",
                             "Compose", "compose", lambda: nav("compose"))
        self.step2 = StepRow(2, "Add recipients", "Paste addresses, import a spreadsheet or collect them "
                                                  "from Outlook.", "Recipients", "users", lambda: nav("recipients"))
        self.step3 = StepRow(3, "Start the automation", "One email per customer, one minute apart, with a "
                                                        "live progress bar.", "Automation", "zap",
                             lambda: nav("automation"))
        steps.add(self.step1)
        steps.add(divider())
        steps.add(self.step2)
        steps.add(divider())
        steps.add(self.step3)
        steps.body.addStretch(1)
        grid.addWidget(steps, 3)

        side = QVBoxLayout()
        side.setSpacing(18)
        self.status_card = Card("Sending status")
        self.backend_text = label("", wrap=True)
        self.status_card.add(self.backend_text)
        self.backend_hint = label("", "Hint", wrap=True)
        self.status_card.add(self.backend_hint)
        settings_btn = button("Change in Settings", "settings", "ghost")
        settings_btn.clicked.connect(lambda: nav("settings"))
        self.status_card.add(settings_btn)
        side.addWidget(self.status_card)

        self.last_card = Card("Last campaign")
        self.last_text = label("No campaigns yet.", "Muted", wrap=True)
        self.last_card.add(self.last_text)
        hist_btn = button("View history", "history", "ghost")
        hist_btn.clicked.connect(lambda: nav("history"))
        self.last_card.add(hist_btn)
        side.addWidget(self.last_card)

        quick = Card("Quick actions")
        qgrid = QGridLayout()
        qgrid.setSpacing(8)
        for i, (text, icon_name, key) in enumerate((("Write && send", "mail", "quick"),
                                                     ("Outlook data", "database", "outlook"))):
            b = button(text, icon_name)
            b.clicked.connect(lambda _=False, k=key: nav(k))
            qgrid.addWidget(b, 0, i)
        quick.add(qgrid)
        side.addWidget(quick)
        side.addStretch(1)
        grid.addLayout(side, 2)
        self.content.addLayout(grid)
        self.content.addStretch(1)

        for sig in (state.recipients_changed, state.draft_changed, state.settings_changed, state.history_changed):
            sig.connect(self.refresh)
        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self):
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        self.title_label.setText(greeting)

        stats = storage.all_time_stats()
        count = len(self.state.recipients)
        self.stat_recipients.set_value(f"{count:,}")
        self.stat_sent.set_value(f"{stats['sent']:,}")
        self.stat_campaigns.set_value(f"{stats['campaigns']:,}")
        self.stat_failed.set_value(f"{stats['failed']:,}")

        draft = self.state.draft
        ready = bool(draft.get("subject", "").strip()) and not is_blank_html(draft.get("html", ""))
        self.step1.set_status("Ready" if ready else "To do", "success" if ready else "warning")
        self.step2.set_status(f"{count:,} added" if count else "To do", "success" if count else "warning")
        if self.state.campaign_running:
            self.step3.set_status("Running", "accent")
        else:
            self.step3.set_status("Ready to start" if ready and count else "Waiting",
                                  "accent" if ready and count else None)

        settings = self.state.settings
        self.backend_text.setText(f"<b>{backend_label(settings)}</b>")
        backend = settings.get("backend")
        if backend == "outlook":
            ok, reason = outlook_available()
            self.backend_hint.setText("Emails go out from Outlook and are saved in Sent Items." if ok else
                                      f"⚠ {reason}")
        elif backend == "simulate":
            self.backend_hint.setText("Practice mode: nothing is actually sent.")
        else:
            self.backend_hint.setText("Emails are delivered directly through your SMTP server.")

        sessions = [s for s in storage.load_sessions() if s.get("kind") == "campaign"]
        if sessions:
            s = sessions[0]
            try:
                when = datetime.fromisoformat(s["started"]).strftime("%d %b %Y, %H:%M")
            except (KeyError, ValueError):
                when = ""
            self.last_text.setText(f"<b>{s.get('subject', '')}</b><br>{when}<br>"
                                   f"{s.get('sent', 0)} sent · {s.get('failed', 0)} failed · "
                                   f"{s.get('status', '').title()}")
        else:
            self.last_text.setText("No campaigns yet.")
