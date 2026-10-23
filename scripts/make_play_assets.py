"""Google Play graphics: 512x512 app icon and 1024x500 feature graphic (output: fastlane/metadata/...).

Run:  python scripts/make_play_assets.py [phone-screenshot.png]
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from te_mailer.ui.icons import svg_markup  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "fastlane" / "metadata" / "android" / "en-US" / "images"
TEAL_DARK, TEAL_LIGHT = "#0B7A8F", "#14B8C9"


def gradient(w, h):
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor(TEAL_DARK))
    g.setColorAt(1, QColor(TEAL_LIGHT))
    return g


def glyph(p: QPainter, rect: QRectF, stroke: float = 1.8):
    QSvgRenderer(QByteArray(svg_markup("send", "#FFFFFF", stroke))).render(p, rect)


def icon(size: int = 512) -> QImage:
    """Full-bleed square: Google Play rounds the corners itself."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(0, 0, size, size, gradient(size, size))
    pad = size * 0.24
    glyph(p, QRectF(pad - size * 0.02, pad + size * 0.02, size - 2 * pad, size - 2 * pad))
    p.end()
    return img


def feature(screenshot: str | None) -> QImage:
    w, h = 1024, 500
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.fillRect(0, 0, w, h, gradient(w, h))
    # soft circles for depth
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 18))
    p.drawEllipse(QPointF(880, -40), 260, 260)
    p.drawEllipse(QPointF(60, 520), 220, 220)
    # badge + text
    badge = QPainterPath()
    badge.addRoundedRect(QRectF(64, 92, 88, 88), 22, 22)
    p.fillPath(badge, QColor(255, 255, 255, 40))
    glyph(p, QRectF(80, 110, 56, 56), 2.0)
    p.setPen(QColor("#FFFFFF"))
    f = QFont("DejaVu Sans")
    f.setPixelSize(50)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QPointF(64, 252), "Legacy AI")
    p.drawText(QPointF(64, 312), "Email Studio")
    f2 = QFont("DejaVu Sans")
    f2.setPixelSize(21)
    p.setFont(f2)
    p.setPen(QColor(255, 255, 255, 235))
    p.drawText(QPointF(66, 362), "Personal email campaigns, sent one by one,")
    p.drawText(QPointF(66, 392), "by you or your AI agent, with your approval.")
    if screenshot and Path(screenshot).is_file():
        shot = QImage(screenshot)
        phone_h = 560
        phone_w = phone_h * shot.width() / shot.height()
        x, y = w - phone_w - 70, 40
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(x - 10, y - 10, phone_w + 20, phone_h + 20), 38, 38)
        p.fillPath(frame, QColor("#0F172A"))
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, phone_w, phone_h), 30, 30)
        p.setClipPath(clip)
        p.drawImage(QRectF(x, y, phone_w, phone_h), shot)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 60), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(frame)
    p.end()
    return img


def main():
    QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    icon().save(str(OUT / "icon.png"))
    feature(sys.argv[1] if len(sys.argv) > 1 else None).convertToFormat(QImage.Format.Format_RGB32).save(
        str(OUT / "featureGraphic.png"))
    print("wrote", OUT / "icon.png", OUT / "featureGraphic.png")


if __name__ == "__main__":
    main()
