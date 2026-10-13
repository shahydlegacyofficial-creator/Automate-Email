"""History of campaigns and manual sends."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QSplitter

from ...core import storage
from ...core.recipients import Recipient
from ..widgets import Card, Page, Pill, button, make_table, status_item, table_item

KIND_LABELS = {"campaign": "Automation", "manual": "Manual", "test": "Test"}
STATUS_TONES = {"completed": "success", "stopped": "warning", "error": "danger", "running": "accent"}


def _fmt(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return iso


class HistoryPage(Page):
    def __init__(self, state):
        super().__init__("History", "Every automation session and manual email, with per-customer results.")
        self.state = state
        self.sessions: list[dict] = []

        folder_btn = button("Open data folder", "folder")
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(storage.data_dir()))))
        refresh_btn = button("Refresh", "refresh")
        refresh_btn.clicked.connect(self.reload)
        self.header_actions.addWidget(folder_btn)
        self.header_actions.addWidget(refresh_btn)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        sessions_card = Card("Sessions")
        self.total_pill = Pill("")
        sessions_card.add_action(self.total_pill)
        self.sessions_table = make_table(["Started", "Type", "Subject", "Recipients", "Sent", "Failed",
                                          "Status"], 2)
        self.sessions_table.setColumnWidth(0, 160)
        self.sessions_table.setColumnWidth(1, 100)
        for col in (3, 4, 5):
            self.sessions_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.sessions_table.setColumnWidth(6, 120)
        self.sessions_table.setMinimumHeight(240)
        self.sessions_table.itemSelectionChanged.connect(self.show_details)
        sessions_card.add(self.sessions_table, 1)
        splitter.addWidget(sessions_card)

        details_card = Card("Session details")
        self.details_pill = Pill("Select a session")
        details_card.add_action(self.details_pill)
        actions = QHBoxLayout()
        self.requeue_btn = button("Re-queue unsent && failed", "refresh", "primary")
        self.requeue_btn.setToolTip("Add customers who did not receive this email back to the recipient list")
        self.requeue_btn.clicked.connect(self.requeue)
        self.export_btn = button("Export CSV", "download")
        self.export_btn.clicked.connect(self.export)
        self.delete_btn = button("Delete", "trash", "danger")
        self.delete_btn.clicked.connect(self.delete)
        actions.addWidget(self.requeue_btn)
        actions.addWidget(self.export_btn)
        actions.addStretch(1)
        actions.addWidget(self.delete_btn)
        details_card.add(actions)
        self.details_table = make_table(["Time", "Email", "Name", "Status", "Details"], 4)
        self.details_table.setColumnWidth(0, 150)
        self.details_table.setColumnWidth(1, 250)
        self.details_table.setColumnWidth(2, 160)
        self.details_table.setColumnWidth(3, 110)
        self.details_table.setMinimumHeight(260)
        details_card.add(self.details_table, 1)
        splitter.addWidget(details_card)
        splitter.setSizes([320, 360])
        self.content.addWidget(splitter, 1)

        state.history_changed.connect(self.reload)
        self.reload()

    def on_show(self):
        self.reload()

    def reload(self):
        selected = self.current_session()
        selected_id = selected["id"] if selected else None
        self.sessions = storage.load_sessions()
        t = self.sessions_table
        t.setRowCount(len(self.sessions))
        reselect = -1
        for row, s in enumerate(self.sessions):
            t.setItem(row, 0, table_item(_fmt(s.get("started")), data=s["id"]))
            t.setItem(row, 1, table_item(KIND_LABELS.get(s.get("kind"), s.get("kind", ""))))
            t.setItem(row, 2, table_item(s.get("subject", "")))
            t.setItem(row, 3, table_item(s.get("total", 0), True))
            t.setItem(row, 4, table_item(s.get("sent", 0), True))
            t.setItem(row, 5, table_item(s.get("failed", 0), True))
            status = s.get("status", "")
            item = status_item({"completed": "sent", "error": "failed", "stopped": "skipped",
                                "running": "sending"}.get(status, status))
            item.setText(status.title())
            t.setItem(row, 6, item)
            if s["id"] == selected_id:
                reselect = row
        stats = storage.all_time_stats()
        self.total_pill.set(f"{stats['sent']:,} emails sent all-time", "accent")
        if reselect < 0 and self.sessions:
            reselect = 0
        if reselect >= 0:
            t.selectRow(reselect)
        else:
            self.show_details()

    def current_session(self) -> dict | None:
        rows = {i.row() for i in self.sessions_table.selectedItems()}
        if not rows:
            return None
        row = min(rows)
        return self.sessions[row] if row < len(self.sessions) else None

    def show_details(self):
        s = self.current_session()
        for b in (self.requeue_btn, self.export_btn, self.delete_btn):
            b.setEnabled(s is not None)
        self.details_table.setRowCount(0)
        if not s:
            self.details_pill.set("Select a session")
            return
        self.details_pill.set(f"{s.get('status', '').title()} · {_fmt(s.get('started'))}",
                              STATUS_TONES.get(s.get("status")))
        results = s.get("results", [])
        self.details_table.setRowCount(len(results))
        for row, r in enumerate(results):
            self.details_table.setItem(row, 0, table_item(_fmt(r.get("time"))))
            self.details_table.setItem(row, 1, table_item(r.get("email", "")))
            self.details_table.setItem(row, 2, table_item(r.get("name", "")))
            self.details_table.setItem(row, 3, status_item(r.get("status", "")))
            details = table_item(r.get("message", ""))
            details.setToolTip(r.get("message", ""))
            self.details_table.setItem(row, 4, details)
        self.requeue_btn.setEnabled(s.get("kind") == "campaign" and s.get("status") != "running")

    def requeue(self):
        s = self.current_session()
        if not s:
            return
        queue = s.get("queue") or [{"email": r["email"], "name": r.get("name", "")}
                                   for r in s.get("results", [])]
        sent = {r["email"] for r in s.get("results", []) if r.get("status") == "sent"}
        pending = [Recipient(q["email"], q.get("name", "")) for q in queue if q["email"] not in sent]
        if not pending:
            QMessageBox.information(self, "Re-queue", "Every customer in this session received the email.")
            return
        if QMessageBox.question(
                self, "Re-queue",
                f"Replace the current recipient list with the {len(pending):,} customer(s) who did not "
                "receive this email (failed or never reached)?") != QMessageBox.StandardButton.Yes:
            return
        self.state.set_recipients(pending)
        self.state.notify(f"{len(pending):,} customer(s) queued for the next campaign", "success")
        self.state.navigate.emit("automation")

    def export(self):
        s = self.current_session()
        if not s:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export session", f"session-{s['id']}.csv", "CSV (*.csv)")
        if path:
            storage.export_session_csv(path, s)
            self.state.notify("Session exported", "success")

    def delete(self):
        s = self.current_session()
        if not s:
            return
        if s.get("status") == "running" and self.state.campaign_running:
            QMessageBox.information(self, "Delete", "This campaign is still running.")
            return
        if QMessageBox.question(self, "Delete session", "Delete this session from history?") == \
                QMessageBox.StandardButton.Yes:
            storage.delete_session(s["id"])
            self.sessions_table.clearSelection()
            self.reload()
