"""Desktop side of the email signature: recoloured icon PNGs and the final HTML."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF, QUrl, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from ..app import resource_path
from ..core.signature import build_signature_html, normalized
from ..core.storage import sub_dir

SIZE = 96


def _master(name: str) -> QImage:
    return QImage(resource_path(os.path.join("assets", "signature_icons", f"{name}.png")))


def icon_file(kind: str, name: str, color: str) -> Path:
    """PNG for a contact icon (glyph in the accent colour) or social icon (white glyph on a
    filled accent circle). Cached per colour in the data folder."""
    color = QColor(color if QColor(color).isValid() else "#1E88E5")
    path = sub_dir("signature_icons") / f"{kind}-{name}-{color.name()[1:]}.png"
    if path.exists():
        return path
    master = _master(name)
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if kind == "social":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QRectF(0, 0, SIZE, SIZE))
        p.drawImage(QRectF(SIZE * 0.2, SIZE * 0.2, SIZE * 0.6, SIZE * 0.6), master)
    else:
        p.drawImage(QRectF(0, 0, SIZE, SIZE), master)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(img.rect(), color)
    p.end()
    img.save(str(path), "PNG")
    return path


def file_url(path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def render_signature(config: dict) -> str:
    cfg = normalized(config)
    logo = cfg.get("logo_path") or ""
    logo_src = file_url(logo) if logo and os.path.isfile(logo) else ""
    return build_signature_html(cfg, lambda kind, name: file_url(icon_file(kind, name, cfg["accent"])), logo_src)


def signature_html(settings: dict) -> str:
    """Signature to append to outgoing emails, or "" when switched off."""
    cfg = normalized(settings.get("signature"))
    return render_signature(cfg) if cfg.get("enabled") else ""
