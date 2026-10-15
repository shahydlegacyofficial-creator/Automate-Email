"""Recipient list management: paste in bulk, import files, edit, export."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLineEdit,
    QMessageBox, QPlainTextEdit, QTableWidgetItem, QWidget, QVBoxLayout,
)

from ...core.recipients import (
    ParseResult, is_suppressed, parse_file, parse_suppression, parse_text, write_csv,
)
from .. import theme
from ..widgets import Card, Page, Pill, button, field_label, label, make_table


class RecipientsPage(Page):
    def __init__(self, state):
        super().__init__("Recipients",
                         "Paste addresses in bulk or import a CSV / Excel / TXT file. "
                         "Duplicates and invalid addresses are removed automatically.")
        self.state = state
        self._populating = False

        export_btn = button("Export CSV", "download")
        export_btn.clicked.connect(self.export_csv)
        next_btn = button("Continue to automation", "zap", "primary")
        next_btn.clicked.connect(lambda: state.navigate.emit("automation"))
        self.header_actions.addWidget(export_btn)
        self.header_actions.addWidget(next_btn)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.content.addLayout(body, 1)

        # ---- left: add
        add_card = Card("Add recipients", "One per line, or separated by commas / semicolons. "
                                          "“Name <email>” and copied spreadsheet rows work too.")
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("sarah.khan@gmail.com\nJohn Smith <john@outlook.com>\n"
                                      "Ali Raza, ali.raza@yahoo.com\nmaria@hotmail.com; leo@icloud.com")
        self.paste.setMinimumHeight(260)
        add_card.add(self.paste, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        add_btn = button("Add to list", "plus", "primary")
        add_btn.clicked.connect(self.add_from_text)
        clip_btn = button("Paste clipboard", "clipboard")
        clip_btn.clicked.connect(self.paste_clipboard)
        row.addWidget(add_btn)
        row.addWidget(clip_btn)
        row.addStretch(1)
        add_card.add(row)
        add_card.add(field_label("OR IMPORT A FILE"))
        import_btn = button("Import CSV, Excel or TXT…", "upload")
        import_btn.clicked.connect(self.import_file)
        add_card.add(import_btn)
        add_card.add(label("Files with an “Email” column (and optionally “Name” or “First name”) "
                           "are matched automatically.", "Hint", wrap=True))
        outlook_btn = button("Collect from Outlook…", "database", "ghost")
        outlook_btn.clicked.connect(lambda: state.navigate.emit("outlook"))
        add_card.add(outlook_btn)
        self.result_label = label("", "Hint", wrap=True)
        add_card.add(self.result_label)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(add_card)

        lists_card = Card("Saved lists", "Name a list (e.g. “VIP guests”) to reuse it later - "
                                         "Legacy AI can send to saved lists by name.")
        self.lists_box = QComboBox()
        self.lists_box.setPlaceholderText("No saved lists yet")
        lists_card.add(self.lists_box)
        lists_row = QHBoxLayout()
        lists_row.setSpacing(6)
        load_btn = button("Load", "upload")
        load_btn.setToolTip("Replace the recipient list with the saved list")
        load_btn.clicked.connect(self.load_saved_list)
        save_btn = button("Save as…", "save", "primary")
        save_btn.setToolTip("Save the recipient list under a name")
        save_btn.clicked.connect(self.save_as_list)
        delete_btn = button("", "trash", "ghost")
        delete_btn.setToolTip("Delete the selected saved list")
        delete_btn.clicked.connect(self.delete_saved_list)
        lists_row.addWidget(load_btn)
        lists_row.addWidget(save_btn, 1)
        lists_row.addWidget(delete_btn)
        lists_card.add(lists_row)
        left_layout.addWidget(lists_card)
        left.setFixedWidth(380)
        body.addWidget(left)

        # ---- right: list
        list_card = Card("Recipient list")
        self.count_pill = Pill("0 recipients", "accent")
        list_card.add_action(self.count_pill)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search email or name…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        tools.addWidget(self.search, 1)
        remove_btn = button("Remove selected", "trash")
        remove_btn.clicked.connect(self.remove_selected)
        self.suppressed_btn = button("Remove do-not-email", "x-circle")
        self.suppressed_btn.clicked.connect(self.remove_suppressed)
        clear_btn = button("Clear all", "trash", "danger")
        clear_btn.clicked.connect(self.clear_all)
        tools.addWidget(remove_btn)
        tools.addWidget(self.suppressed_btn)
        tools.addWidget(clear_btn)
        list_card.add(tools)

        self.table = make_table(["#", "Email address", "Name (double-click to edit)", "Note"], 1)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 170)
        self.table.setMinimumHeight(420)
        self.table.itemChanged.connect(self._name_edited)
        list_card.add(self.table, 1)
        body.addWidget(list_card, 1)

        state.recipients_changed.connect(self.populate)
        state.settings_changed.connect(self.populate)
        state.lists_changed.connect(self.reload_lists)
        self.populate()
        self.reload_lists()

    # ------------------------------------------------------------ saved lists
    def reload_lists(self):
        current = self.lists_box.currentData()
        self.lists_box.clear()
        for entry in self.state.saved_lists():
            count = len(entry["recipients"])
            self.lists_box.addItem(f"{entry['name']}  ·  {count:,} recipient{'s' if count != 1 else ''}",
                                   entry["name"])
        index = self.lists_box.findData(current)
        self.lists_box.setCurrentIndex(index if index >= 0 else (0 if self.lists_box.count() else -1))

    def load_saved_list(self):
        name = self.lists_box.currentData()
        entry = self.state.find_list(name) if name else None
        if entry is None:
            QMessageBox.information(self, "Saved lists", "Choose a saved list first.")
            return
        people = self.state.list_recipients(entry)
        if self.state.recipients and QMessageBox.question(
                self, "Load list", f"Replace the current {len(self.state.recipients):,} recipients with "
                                   f"“{entry['name']}” ({len(people):,})?") != QMessageBox.StandardButton.Yes:
            return
        self.state.set_recipients(people)
        self.state.notify(f"Loaded “{entry['name']}”", "success")

    def save_as_list(self):
        if not self.state.recipients:
            QMessageBox.information(self, "Save list", "Add some recipients first.")
            return
        name, ok = QInputDialog.getText(self, "Save list", "Name for this list:",
                                        text=self.lists_box.currentData() or "")
        name = " ".join(name.split())
        if not ok or not name:
            return
        if self.state.find_list(name) and QMessageBox.question(
                self, "Save list", f"Replace the saved list “{name}”?") != QMessageBox.StandardButton.Yes:
            return
        entry = self.state.save_list(name, self.state.recipients)
        self.lists_box.setCurrentIndex(self.lists_box.findData(entry["name"]))
        self.state.notify(f"Saved “{entry['name']}” ({len(entry['recipients']):,} recipients)", "success")

    def delete_saved_list(self):
        name = self.lists_box.currentData()
        if not name:
            return
        if QMessageBox.question(self, "Delete list", f"Delete the saved list “{name}”? "
                                "The recipients on this page are not affected.") == QMessageBox.StandardButton.Yes:
            self.state.delete_list(name)

    # ------------------------------------------------------------ list
    def populate(self):
        self._populating = True
        suppression = parse_suppression(self.state.settings.get("suppression_list", ""))
        colors = theme.current()
        recipients = self.state.recipients
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(recipients))
        suppressed_count = 0
        for row, r in enumerate(recipients):
            num = QTableWidgetItem(str(row + 1))
            num.setFlags(num.flags() & ~Qt.ItemFlag.ItemIsEditable)
            num.setForeground(QColor(colors["text_muted"]))
            email = QTableWidgetItem(r.email)
            email.setFlags(email.flags() & ~Qt.ItemFlag.ItemIsEditable)
            email.setData(Qt.ItemDataRole.UserRole, r.email)
            name = QTableWidgetItem(r.name)
            note = QTableWidgetItem("")
            note.setFlags(note.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if suppression and is_suppressed(r.email, suppression):
                suppressed_count += 1
                note.setText("Do-not-email list")
                note.setForeground(QColor(colors["danger"]))
            self.table.setItem(row, 0, num)
            self.table.setItem(row, 1, email)
            self.table.setItem(row, 2, name)
            self.table.setItem(row, 3, note)
        self._populating = False
        count = len(recipients)
        self.count_pill.set(f"{count:,} recipient{'s' if count != 1 else ''}", "accent")
        self.suppressed_btn.setEnabled(suppressed_count > 0)
        self.suppressed_btn.setText(f"Remove do-not-email ({suppressed_count})" if suppressed_count
                                    else "Remove do-not-email")
        self.apply_filter()

    def apply_filter(self):
        needle = self.search.text().strip().lower()
        for row in range(self.table.rowCount()):
            email = self.table.item(row, 1).text().lower()
            name = (self.table.item(row, 2).text() if self.table.item(row, 2) else "").lower()
            self.table.setRowHidden(row, bool(needle) and needle not in email and needle not in name)

    def _name_edited(self, item: QTableWidgetItem):
        if self._populating or item.column() != 2:
            return
        email = self.table.item(item.row(), 1).data(Qt.ItemDataRole.UserRole)
        self.state.update_recipient_name(email, item.text())

    def _selected_emails(self) -> set[str]:
        rows = {i.row() for i in self.table.selectedItems()}
        return {self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in rows}

    def remove_selected(self):
        emails = self._selected_emails()
        if emails:
            removed = self.state.remove_emails(emails)
            self.state.notify(f"Removed {removed} recipient{'s' if removed != 1 else ''}")

    def remove_suppressed(self):
        suppression = parse_suppression(self.state.settings.get("suppression_list", ""))
        emails = {r.email for r in self.state.recipients if is_suppressed(r.email, suppression)}
        if emails:
            removed = self.state.remove_emails(emails)
            self.state.notify(f"Removed {removed} address{'es' if removed != 1 else ''} on the do-not-email list")

    def clear_all(self):
        if not self.state.recipients:
            return
        if QMessageBox.question(self, "Clear recipients",
                                f"Remove all {len(self.state.recipients):,} recipients from the list?") \
                == QMessageBox.StandardButton.Yes:
            self.state.set_recipients([])

    # ------------------------------------------------------------ adding
    def _report(self, result: ParseResult, source: str):
        added, dupes = self.state.add_recipients(result.recipients)
        dupes += result.duplicates
        parts = [f"<b>{added:,}</b> added from {source}"]
        if dupes:
            parts.append(f"{dupes:,} duplicate{'s' if dupes != 1 else ''} skipped")
        if result.invalid:
            sample = ", ".join(result.invalid[:5]) + ("…" if len(result.invalid) > 5 else "")
            parts.append(f"<span style='color:{theme.current()['danger']}'>{len(result.invalid)} invalid: "
                         f"{sample}</span>")
        self.result_label.setText(" · ".join(parts))
        tone = "success" if added else "info"
        self.state.notify(f"{added:,} recipient{'s' if added != 1 else ''} added", tone)

    def add_from_text(self):
        text = self.paste.toPlainText()
        if not text.strip():
            return
        result = parse_text(text)
        if not result.recipients and not result.invalid:
            self.result_label.setText("No email addresses were found in the text.")
            return
        self._report(result, "pasted text")
        self.paste.clear()

    def paste_clipboard(self):
        text = QGuiApplication.clipboard().text()
        if text:
            self.paste.setPlainText(text)
            self.add_from_text()

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import recipients", "",
                                              "Recipient files (*.csv *.xlsx *.xlsm *.txt *.tsv);;All files (*)")
        if not path:
            return
        try:
            result = parse_file(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", f"Could not read the file:\n{exc}")
            return
        import os
        self._report(result, os.path.basename(path))

    def export_csv(self):
        if not self.state.recipients:
            QMessageBox.information(self, "Export", "The recipient list is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export recipients", "recipients.csv", "CSV (*.csv)")
        if path:
            write_csv(path, self.state.recipients)
            self.state.notify("Recipient list exported", "success")
