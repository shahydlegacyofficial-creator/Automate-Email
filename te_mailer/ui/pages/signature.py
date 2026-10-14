"""Signature editor: Travel Essence contact details, social links and logo, with live preview."""

from __future__ import annotations

import base64
import os
import re
import shutil

from PySide6.QtCore import QMimeData, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QTextBrowser, QVBoxLayout, QWidget,
)

from ...core.signature import DEFAULT_SIGNATURE, SOCIALS, build_signature_html, normalized
from ...core.storage import sub_dir
from ..signature_assets import icon_file, render_signature
from ..widgets import Card, Page, Pill, button, field_label, label


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(10)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return form


class SignaturePage(Page):
    def __init__(self, state):
        super().__init__("Email signature",
                         "Your Travel Essence contact details, social links and logo - added below every email.")
        self.state = state
        self._loading = False

        self.saved_pill = Pill("Saved", "success")
        copy_btn = button("Copy for Outlook", "clipboard",
                          tooltip="Copy the signature so you can paste it into Outlook's own signature settings")
        copy_btn.clicked.connect(self.copy_for_outlook)
        reset_btn = button("Reset to Travel Essence details", "refresh", "ghost")
        reset_btn.clicked.connect(self.reset)
        self.header_actions.addWidget(self.saved_pill)
        self.header_actions.addWidget(reset_btn)
        self.header_actions.addWidget(copy_btn)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.content.addLayout(body, 1)

        # ---- left: form
        left = QVBoxLayout()
        left.setSpacing(18)
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(470)
        left.setContentsMargins(0, 0, 0, 0)

        style = Card("Style")
        self.enabled = QCheckBox("Add this signature to every email (campaigns, tests, Write && send)")
        style.add(self.enabled)
        form = _form()
        self.theme = QComboBox()
        self.theme.addItem("Dark card", "dark")
        self.theme.addItem("Light (white)", "light")
        form.addRow(field_label("BACKGROUND"), self.theme)
        accent_row = QHBoxLayout()
        self.accent_btn = QPushButton()
        self.accent_btn.setFixedSize(44, 30)
        self.accent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accent_btn.clicked.connect(self.pick_accent)
        self.accent_text = QLineEdit()
        self.accent_text.setMaxLength(7)
        self.accent_text.setFixedWidth(100)
        accent_row.addWidget(self.accent_btn)
        accent_row.addWidget(self.accent_text)
        accent_row.addStretch(1)
        form.addRow(field_label("ICON & LINK COLOUR"), accent_row)
        style.add(form)
        left.addWidget(style)

        details = Card("Contact details", "Leave a field empty to hide it.")
        form = _form()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Optional - e.g. Aisha Ibrahim")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Optional - e.g. Sales & Marketing")
        self.email = QLineEdit()
        self.phone = QLineEdit()
        self.address = QPlainTextEdit()
        self.address.setFixedHeight(64)
        self.website = QLineEdit()
        for caption, widget in (("NAME", self.name), ("JOB TITLE", self.title), ("EMAIL", self.email),
                                ("PHONE", self.phone), ("ADDRESS", self.address), ("WEBSITE", self.website)):
            form.addRow(field_label(caption), widget)
        details.add(form)
        left.addWidget(details)

        logo = Card("Logo", "PNG or JPG. A transparent PNG looks best on the dark card.")
        logo_row = QHBoxLayout()
        choose = button("Choose logo…", "image")
        choose.clicked.connect(self.choose_logo)
        self.remove_logo_btn = button("Remove", "trash", "ghost")
        self.remove_logo_btn.clicked.connect(self.remove_logo)
        logo_row.addWidget(choose)
        logo_row.addWidget(self.remove_logo_btn)
        logo_row.addStretch(1)
        logo.add(logo_row)
        self.logo_name = label("No logo selected", "Hint")
        logo.add(self.logo_name)
        form = _form()
        self.logo_width = QSpinBox()
        self.logo_width.setRange(80, 360)
        self.logo_width.setSingleStep(10)
        self.logo_width.setSuffix("  px")
        form.addRow(field_label("LOGO WIDTH"), self.logo_width)
        logo.add(form)
        left.addWidget(logo)

        social = Card("Social media", "Paste a full link or just the page name / handle. WhatsApp takes a phone number.")
        form = _form()
        self.social_fields: dict[str, QLineEdit] = {}
        hints = {"facebook": "travelessence", "instagram": "@travelessence", "whatsapp": "+960 7978580",
                 "tiktok": "@travelessence", "linkedin": "travel-essence", "youtube": "@travelessence",
                 "x": "@travelessence"}
        for key, caption, _ in SOCIALS:
            field = QLineEdit()
            field.setPlaceholderText(hints.get(key, ""))
            self.social_fields[key] = field
            form.addRow(field_label(caption.upper()), field)
        social.add(form)
        left.addWidget(social)
        left.addStretch(1)
        body.addWidget(left_widget, 0, Qt.AlignmentFlag.AlignTop)

        # ---- right: preview
        preview = Card("Preview", "How the signature appears under your emails.")
        self.preview = QTextBrowser()
        self.preview.setObjectName("EmailPaper")
        self.preview.setOpenExternalLinks(True)
        self.preview.setMinimumHeight(520)
        preview.add(self.preview, 1)
        preview.add(label("Icons and the logo are attached inside each email, so recipients see them "
                          "without downloading pictures from the internet.", "Hint", wrap=True))
        body.addWidget(preview, 1)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save)

        for widget in [self.name, self.title, self.email, self.phone, self.website, self.accent_text,
                       *self.social_fields.values()]:
            widget.textChanged.connect(self._changed)
        self.address.textChanged.connect(self._changed)
        self.enabled.toggled.connect(self._changed)
        self.theme.currentIndexChanged.connect(self._changed)
        self.logo_width.valueChanged.connect(self._changed)
        self.load()

    # ------------------------------------------------------------ state
    def config(self) -> dict:
        cfg = normalized(self.state.settings.get("signature"))
        accent = self.accent_text.text().strip()
        cfg.update(
            enabled=self.enabled.isChecked(),
            theme=self.theme.currentData(),
            accent=accent if QColor(accent).isValid() and accent.startswith("#") else cfg["accent"],
            name=self.name.text().strip(), title=self.title.text().strip(),
            email=self.email.text().strip(), phone=self.phone.text().strip(),
            address=self.address.toPlainText().strip(), website=self.website.text().strip(),
            logo_width=self.logo_width.value(),
            socials={key: field.text().strip() for key, field in self.social_fields.items()},
        )
        return cfg

    def load(self):
        self._loading = True
        cfg = normalized(self.state.settings.get("signature"))
        self.enabled.setChecked(bool(cfg["enabled"]))
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg["theme"])))
        self.accent_text.setText(cfg["accent"])
        self.name.setText(cfg["name"])
        self.title.setText(cfg["title"])
        self.email.setText(cfg["email"])
        self.phone.setText(cfg["phone"])
        self.address.setPlainText(cfg["address"])
        self.website.setText(cfg["website"])
        self.logo_width.setValue(int(cfg["logo_width"] or 200))
        for key, field in self.social_fields.items():
            field.setText(cfg["socials"].get(key, ""))
        self._loading = False
        self._refresh()

    def _changed(self, *_):
        if self._loading:
            return
        self.saved_pill.set("Saving…", "warning")
        self._refresh()
        self._save_timer.start()

    def save(self):
        self.state.save_settings({"signature": self.config()})
        self.saved_pill.set("Saved", "success")

    def _refresh(self):
        cfg = self.config()
        color = QColor(cfg["accent"])
        self.accent_btn.setStyleSheet(f"background:{color.name()}; border:1px solid #94A3B8; border-radius:6px;")
        logo = cfg.get("logo_path") or ""
        self.logo_name.setText(os.path.basename(logo) if logo and os.path.isfile(logo) else "No logo selected")
        self.remove_logo_btn.setEnabled(bool(logo))
        sig = render_signature(cfg)
        note = "" if cfg["enabled"] else (
            "<p style='color:#B45309;font-family:Segoe UI,Arial;font-size:10pt'>"
            "The signature is switched off - tick “Add this signature to every email” to use it.</p>")
        self.preview.setHtml(
            "<p style='font-family:Calibri,Arial;font-size:11pt;color:#1F2937'>Dear Sarah,<br><br>"
            "Thank you for choosing Travel Essence…<br><br>Kind regards,</p>" + sig + note)

    # ------------------------------------------------------------ actions
    def pick_accent(self):
        color = QColorDialog.getColor(QColor(self.accent_text.text() or "#1E88E5"), self, "Icon & link colour")
        if color.isValid():
            self.accent_text.setText(color.name().upper())

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose logo", "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower() or ".png"
        target = sub_dir("signature") / f"logo{ext}"
        for old in sub_dir("signature").glob("logo.*"):
            old.unlink(missing_ok=True)
        shutil.copyfile(path, target)
        cfg = self.config()
        cfg["logo_path"] = str(target)
        self.state.save_settings({"signature": cfg})
        self._refresh()
        self.state.notify("Logo added to the signature", "success")

    def remove_logo(self):
        cfg = self.config()
        cfg["logo_path"] = ""
        self.state.save_settings({"signature": cfg})
        self._refresh()

    def reset(self):
        cfg = normalized(self.state.settings.get("signature"))
        defaults = {k: v for k, v in DEFAULT_SIGNATURE.items() if k not in ("logo_path", "socials")}
        cfg.update(defaults)
        self.state.save_settings({"signature": cfg})
        self.load()
        self.state.notify("Signature reset to the Travel Essence details")

    def copy_for_outlook(self):
        """Copy as rich HTML with embedded pictures, ready to paste into Outlook's signature editor."""
        cfg = self.config()

        def data_uri(path) -> str:
            with open(path, "rb") as fh:
                return "data:image/png;base64," + base64.b64encode(fh.read()).decode()

        logo = cfg.get("logo_path") or ""
        logo_src = ""
        if logo and os.path.isfile(logo):
            mime = "image/jpeg" if re.search(r"\.jpe?g$", logo, re.I) else "image/png"
            with open(logo, "rb") as fh:
                logo_src = f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
        html = build_signature_html(cfg, lambda kind, name: data_uri(icon_file(kind, name, cfg["accent"])), logo_src)
        mime_data = QMimeData()
        mime_data.setHtml(html)
        mime_data.setText(" | ".join(v for v in (cfg["email"], cfg["phone"], cfg["website"]) if v))
        QGuiApplication.clipboard().setMimeData(mime_data)
        self.state.notify("Signature copied - paste it into Outlook → Settings → Signatures", "success")
