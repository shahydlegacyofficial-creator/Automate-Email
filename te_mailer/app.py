"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, ORG_NAME, __version__
from .core import storage


def resource_path(relative: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / relative)


def _setup_logging() -> None:
    log_file = storage.data_dir() / "app.log"
    try:
        if log_file.exists() and log_file.stat().st_size > 2_000_000:
            log_file.unlink()
    except OSError:
        pass
    logging.basicConfig(filename=str(log_file), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Starting %s %s", APP_NAME, __version__)


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    logging.error("Unhandled error:\n%s", text)
    if QApplication.instance() is not None:
        box = QMessageBox(QMessageBox.Icon.Critical, "Unexpected error",
                          f"Something went wrong:\n\n{exc}\n\nDetails were written to the log file in "
                          f"{storage.data_dir()}.")
        box.setDetailedText(text)
        box.exec()


def run() -> int:
    _setup_logging()
    sys.excepthook = _excepthook

    if sys.platform.startswith("win"):
        try:  # own taskbar icon/group instead of python.exe's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{ORG_NAME}.{APP_ID}")
        except Exception:
            pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    icon_path = resource_path(os.path.join("assets", "icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    from .ui import theme
    from .ui.main_window import MainWindow
    from .ui.state import AppState

    state = AppState()
    theme.apply(app, state.settings.get("theme", "light"))
    window = MainWindow(state)
    window.show()
    report = os.environ.get("TE_SMOKE_TEST")
    if report:  # used by CI to prove the packaged exe starts and bundles its dependencies
        from PySide6.QtCore import QTimer

        from .core.senders import outlook_available

        def finish():
            ok, reason = outlook_available()
            Path(report).write_text(f"started=ok\noutlook_com={'ok' if ok else reason}\n", encoding="utf-8")
            app.quit()

        QTimer.singleShot(3000, finish)
    return app.exec()
