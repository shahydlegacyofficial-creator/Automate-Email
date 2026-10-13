"""Rich-text email editor and attachment picker."""

from __future__ import annotations

import os
import uuid

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor, QFont, QImage, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextImageFormat, QTextListFormat,
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from ..core.htmlutil import PLACEHOLDERS, is_blank_html
from ..core.storage import sub_dir
from . import theme
from .icons import icon
from .widgets import FlowLayout, button, human_size, label

FONTS = ["Calibri", "Segoe UI", "Arial", "Aptos", "Cambria", "Georgia", "Helvetica", "Tahoma",
         "Times New Roman", "Trebuchet MS", "Verdana", "Garamond", "Courier New"]
SIZES = ["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "32", "36", "48"]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
MAX_IMAGE_WIDTH = 600

ATTACHMENT_EXTS = (".jpg", ".jpeg", ".png", ".pdf")
ATTACHMENT_FILTER = "Images and PDF (*.jpg *.jpeg *.png *.pdf)"
ATTACHMENT_WARN_BYTES = 20 * 1024 * 1024


def _image_format(path: str, document: QTextDocument) -> QTextImageFormat | None:
    image = QImage(path)
    if image.isNull():
        return None
    url = QUrl.fromLocalFile(os.path.abspath(path))
    document.addResource(QTextDocument.ResourceType.ImageResource, url, image)
    fmt = QTextImageFormat()
    fmt.setName(url.toString())
    width, height = image.width(), image.height()
    if width > MAX_IMAGE_WIDTH:
        height = int(height * MAX_IMAGE_WIDTH / width)
        width = MAX_IMAGE_WIDTH
    fmt.setWidth(width)
    fmt.setHeight(height)
    return fmt


class PaperEdit(QTextEdit):
    """QTextEdit that accepts pasted / dropped images as inline pictures."""

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasUrls():
            images = [u.toLocalFile() for u in source.urls()
                      if u.isLocalFile() and u.toLocalFile().lower().endswith(IMAGE_EXTS)]
            if images:
                for path in images:
                    self.insert_image(path)
                return
        if source.hasImage() and not source.hasHtml():
            image = QImage(source.imageData())
            if not image.isNull():
                path = str(sub_dir("pasted_images") / f"pasted-{uuid.uuid4().hex[:10]}.png")
                image.save(path, "PNG")
                self.insert_image(path)
                return
        super().insertFromMimeData(source)

    def insert_image(self, path: str) -> bool:
        fmt = _image_format(path, self.document())
        if fmt is None:
            return False
        self.textCursor().insertImage(fmt)
        return True


class EmailEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None, min_height: int = 380):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = PaperEdit()
        self.edit.setObjectName("EmailPaper")
        self.edit.setAcceptRichText(True)
        self.edit.setMinimumHeight(min_height)
        self.edit.document().setDefaultFont(QFont("Calibri", 11))
        self.edit.document().setDocumentMargin(4)
        self.edit.setPlaceholderText("Write your email here…  Tip: use Insert field to add the customer's name.")
        self.edit.document().setDefaultStyleSheet("a { color: #0B7A8F; }")

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self.edit, 1)

        self.edit.textChanged.connect(self.changed.emit)
        self.edit.currentCharFormatChanged.connect(self._sync_format)
        self.edit.cursorPositionChanged.connect(self._sync_block)
        self._sync_format(self.edit.currentCharFormat())

    # ------------------------------------------------------------ toolbar
    def _tool(self, icon_name: str, tip: str, slot=None, checkable: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("EditorTool")
        btn.setIcon(icon(icon_name, "text", "accent"))
        btn.setIconSize(QSize(17, 17))
        btn.setToolTip(tip)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        if slot:
            btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _sep() -> QFrame:
        sep = QFrame()
        sep.setObjectName("ToolSep")
        sep.setFixedHeight(22)
        return sep

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("EditorToolbar")
        row = FlowLayout(bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(3)

        row.addWidget(self._tool("undo", "Undo (Ctrl+Z)", self.edit.undo))
        row.addWidget(self._tool("redo", "Redo (Ctrl+Y)", self.edit.redo))
        row.addWidget(self._sep())

        self.font_box = QComboBox()
        self.font_box.addItems(FONTS)
        self.font_box.setToolTip("Font")
        self.font_box.setFixedWidth(150)
        self.font_box.textActivated.connect(self._set_font_family)
        row.addWidget(self.font_box)

        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.addItems(SIZES)
        self.size_box.setToolTip("Font size")
        self.size_box.setFixedWidth(84)
        self.size_box.textActivated.connect(self._set_font_size)
        self.size_box.lineEdit().editingFinished.connect(
            lambda: self._set_font_size(self.size_box.currentText()))
        row.addWidget(self.size_box)
        row.addWidget(self._sep())

        self.bold_btn = self._tool("bold", "Bold (Ctrl+B)", self._toggle_bold, True)
        self.italic_btn = self._tool("italic", "Italic (Ctrl+I)", self._toggle_italic, True)
        self.underline_btn = self._tool("underline", "Underline (Ctrl+U)", self._toggle_underline, True)
        self.strike_btn = self._tool("strike", "Strikethrough", self._toggle_strike, True)
        for b in (self.bold_btn, self.italic_btn, self.underline_btn, self.strike_btn):
            row.addWidget(b)
        row.addWidget(self._tool("text-color", "Text colour", self._pick_text_color))
        row.addWidget(self._tool("highlight", "Highlight colour", self._pick_highlight))
        row.addWidget(self._sep())

        self.align_btns = {}
        for name, flag, tip in (("align-left", Qt.AlignmentFlag.AlignLeft, "Align left"),
                                ("align-center", Qt.AlignmentFlag.AlignHCenter, "Center"),
                                ("align-right", Qt.AlignmentFlag.AlignRight, "Align right"),
                                ("align-justify", Qt.AlignmentFlag.AlignJustify, "Justify")):
            btn = self._tool(name, tip, lambda _=False, f=flag: self._set_alignment(f), True)
            self.align_btns[flag] = btn
            row.addWidget(btn)
        row.addWidget(self._sep())

        row.addWidget(self._tool("list", "Bulleted list",
                                 lambda: self._toggle_list(QTextListFormat.Style.ListDisc)))
        row.addWidget(self._tool("list-ordered", "Numbered list",
                                 lambda: self._toggle_list(QTextListFormat.Style.ListDecimal)))
        row.addWidget(self._sep())
        row.addWidget(self._tool("link", "Insert link (Ctrl+K)", self._insert_link))
        row.addWidget(self._tool("image", "Insert picture into the email body", self._insert_image))
        row.addWidget(self._tool("eraser", "Clear formatting", self._clear_formatting))
        row.addWidget(self._sep())

        fields = QToolButton()
        fields.setObjectName("EditorTool")
        fields.setText(" Insert field")
        fields.setIcon(icon("braces", "accent"))
        fields.setIconSize(QSize(16, 16))
        fields.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        fields.setToolTip("Personalise: inserts a placeholder replaced for every customer")
        fields.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        fields.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(fields)
        for key, text in PLACEHOLDERS.items():
            menu.addAction(f"{text}   {{{key}}}", lambda k=key: self.insert_placeholder(k))
        fields.setMenu(menu)
        row.addWidget(fields)

        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+K"), self.edit, activated=self._insert_link)
        return bar

    # ------------------------------------------------------------ formatting
    def _merge(self, fmt: QTextCharFormat):
        cursor = self.edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if self.bold_btn.isChecked() else QFont.Weight.Normal)
        self._merge(fmt)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.italic_btn.isChecked())
        self._merge(fmt)

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.underline_btn.isChecked())
        self._merge(fmt)

    def _toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(self.strike_btn.isChecked())
        self._merge(fmt)

    def _set_font_family(self, family: str):
        fmt = QTextCharFormat()
        fmt.setFontFamilies([family])
        self._merge(fmt)

    def _set_font_size(self, text: str):
        try:
            size = float(text)
        except ValueError:
            return
        if 4 <= size <= 96:
            fmt = QTextCharFormat()
            fmt.setFontPointSize(size)
            self._merge(fmt)

    def _pick_text_color(self):
        color = QColorDialog.getColor(self.edit.textColor(), self, "Text colour")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._merge(fmt)

    def _pick_highlight(self):
        color = QColorDialog.getColor(QColor("#FFF3B0"), self, "Highlight colour")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self._merge(fmt)

    def _set_alignment(self, flag):
        self.edit.setAlignment(flag)
        self._sync_block()
        self.edit.setFocus()

    def _toggle_list(self, style):
        cursor = self.edit.textCursor()
        current = cursor.currentList()
        cursor.beginEditBlock()
        if current is not None and current.format().style() == style:
            block = cursor.block()
            current.remove(block)
            fmt = block.blockFormat()
            fmt.setIndent(0)
            cursor.setBlockFormat(fmt)
        else:
            fmt = QTextListFormat()
            fmt.setStyle(style)
            cursor.createList(fmt)
        cursor.endEditBlock()
        self.edit.setFocus()

    def _insert_link(self):
        cursor = self.edit.textCursor()
        current_href = cursor.charFormat().anchorHref()
        url, ok = QInputDialog.getText(self, "Insert link", "Web address (URL):",
                                       text=current_href or "https://")
        if not ok or not url.strip() or url.strip() == "https://":
            return
        url = url.strip()
        if "://" not in url and not url.startswith("mailto:"):
            url = ("mailto:" + url) if "@" in url and "/" not in url else "https://" + url
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QColor("#0B7A8F"))
        fmt.setFontUnderline(True)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            text, ok = QInputDialog.getText(self, "Insert link", "Text to display:", text=url)
            if not ok:
                return
            cursor.insertText(text or url, fmt)
            cursor.setCharFormat(QTextCharFormat())
            self.edit.setTextCursor(cursor)
        self.edit.setFocus()

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Insert picture", "",
                                              "Images (*.png *.jpg *.jpeg *.gif *.bmp)")
        if path and not self.edit.insert_image(path):
            QMessageBox.warning(self, "Insert picture", "That image could not be opened.")
        self.edit.setFocus()

    def _clear_formatting(self):
        cursor = self.edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        fmt = QTextCharFormat()
        fmt.setFont(self.edit.document().defaultFont())
        cursor.setCharFormat(fmt)
        block = QTextBlockFormat()
        cursor.setBlockFormat(block)
        self.edit.setFocus()

    def insert_placeholder(self, key: str):
        self.edit.textCursor().insertText("{" + key + "}")
        self.edit.setFocus()

    # ------------------------------------------------------------ toolbar sync
    def _sync_format(self, fmt: QTextCharFormat):
        self.bold_btn.setChecked(fmt.fontWeight() >= QFont.Weight.DemiBold)
        self.italic_btn.setChecked(fmt.fontItalic())
        self.underline_btn.setChecked(fmt.fontUnderline())
        self.strike_btn.setChecked(fmt.fontStrikeOut())
        families = fmt.fontFamilies() or [self.edit.document().defaultFont().family()]
        family = families[0] if isinstance(families, (list, tuple)) and families else str(families)
        self.font_box.blockSignals(True)
        idx = self.font_box.findText(family, Qt.MatchFlag.MatchFixedString)
        if idx < 0:
            self.font_box.addItem(family)
            idx = self.font_box.count() - 1
        self.font_box.setCurrentIndex(idx)
        self.font_box.blockSignals(False)
        size = fmt.fontPointSize() or self.edit.document().defaultFont().pointSizeF()
        self.size_box.blockSignals(True)
        self.size_box.setCurrentText(f"{size:g}")
        self.size_box.blockSignals(False)

    def _sync_block(self):
        alignment = self.edit.alignment()
        for flag, btn in self.align_btns.items():
            btn.setChecked(bool(alignment & flag) if flag != Qt.AlignmentFlag.AlignLeft
                           else not (alignment & (Qt.AlignmentFlag.AlignHCenter
                                                  | Qt.AlignmentFlag.AlignRight
                                                  | Qt.AlignmentFlag.AlignJustify)))

    # ------------------------------------------------------------ public API
    def html(self) -> str:
        return self.edit.toHtml()

    def set_html(self, html: str):
        self.edit.blockSignals(True)
        if html:
            self.edit.setHtml(html)
        else:
            self.edit.clear()
        self.edit.blockSignals(False)
        self._sync_format(self.edit.currentCharFormat())
        self.changed.emit()

    def plain_text(self) -> str:
        return self.edit.toPlainText()

    def is_blank(self) -> bool:
        return is_blank_html(self.html())

    def clear(self):
        self.set_html("")


class AttachmentList(QWidget):
    """Attachment picker limited to JPG / PNG / PDF, with drag & drop."""

    changed = Signal()

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.list = QListWidget()
        self.list.setObjectName("AttachmentList")
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(20, 20))
        self.list.setMinimumHeight(70 if compact else 110)
        self.list.setMaximumHeight(120 if compact else 220)
        layout.addWidget(self.list)

        self.summary = label("No attachments · drag files here", "Hint")
        layout.addWidget(self.summary)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.add_btn = button("Add files", "paperclip")
        self.add_btn.clicked.connect(self.browse)
        self.remove_btn = button("Remove", "trash", "ghost")
        self.remove_btn.clicked.connect(self.remove_selected)
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self._paths: list[str] = []

    def paths(self) -> list[str]:
        return list(self._paths)

    def set_paths(self, paths: list[str]):
        self._paths = []
        self._add([p for p in paths if p], notify=False, quiet=True)
        self._refresh()

    def browse(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Attach files", "", ATTACHMENT_FILTER)
        if files:
            self._add(files)

    def _add(self, files: list[str], notify: bool = True, quiet: bool = False):
        rejected = []
        for path in files:
            path = os.path.abspath(path)
            if not path.lower().endswith(ATTACHMENT_EXTS):
                rejected.append(os.path.basename(path))
                continue
            if path not in self._paths:
                self._paths.append(path)
        self._refresh()
        if rejected and not quiet:
            QMessageBox.information(self, "Attachments",
                                    "Only JPG, PNG and PDF files can be attached.\n\nSkipped: "
                                    + ", ".join(rejected))
        if self.total_bytes() > ATTACHMENT_WARN_BYTES and not quiet:
            QMessageBox.warning(self, "Large attachments",
                                f"Attachments total {human_size(self.total_bytes())}. Many mail servers "
                                "reject messages over 20 MB - consider compressing the files.")
        if notify:
            self.changed.emit()

    def remove_selected(self):
        rows = sorted((self.list.row(i) for i in self.list.selectedItems()), reverse=True)
        if not rows and self.list.count():
            rows = [self.list.count() - 1]
        for r in rows:
            del self._paths[r]
        self._refresh()
        self.changed.emit()

    def total_bytes(self) -> int:
        return sum(os.path.getsize(p) for p in self._paths if os.path.isfile(p))

    def missing(self) -> list[str]:
        return [p for p in self._paths if not os.path.isfile(p)]

    def _refresh(self):
        self.list.clear()
        colors = theme.current()
        for path in self._paths:
            exists = os.path.isfile(path)
            name = os.path.basename(path)
            size = human_size(os.path.getsize(path)) if exists else "missing"
            item = QListWidgetItem(icon("image" if not path.lower().endswith(".pdf") else "file",
                                        "accent"), f"{name}   ·   {size}")
            item.setToolTip(path)
            if not exists:
                item.setForeground(QColor(colors["danger"]))
            self.list.addItem(item)
        if self._paths:
            self.summary.setText(f"{len(self._paths)} file{'s' if len(self._paths) != 1 else ''} · "
                                 f"{human_size(self.total_bytes())}")
        else:
            self.summary.setText("No attachments · JPG, PNG or PDF · drag files here")
        self.remove_btn.setEnabled(bool(self._paths))

    # drag & drop ------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if files:
            self._add(files)
            event.acceptProposedAction()
