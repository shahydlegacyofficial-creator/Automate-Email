"""Generate assets/icon.png and assets/icon.ico (run once; output is committed)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from te_mailer.ui.icons import svg_markup  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#0B7A8F"))
    grad.setColorAt(1, QColor("#14B8C9"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    p.fillPath(path, grad)
    pad = size * 0.2
    QSvgRenderer(QByteArray(svg_markup("plane", "#FFFFFF", 1.8))).render(
        p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return img


def main():
    QGuiApplication(sys.argv)
    ASSETS.mkdir(exist_ok=True)
    big = render(512)
    png = ASSETS / "icon.png"
    big.save(str(png), "PNG")
    Image.open(png).save(ASSETS / "icon.ico",
                         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", png, ASSETS / "icon.ico")


if __name__ == "__main__":
    main()
