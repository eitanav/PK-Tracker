"""Entry point: wire up the database, controller, theme, and main window.

Run with:  python -m pk_tracker.app
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .controller import AppController
from .data.db import Database, default_db_path
from .ui.main_window import MainWindow
from .ui.theme import apply_theme

WELCOME = (
    "PK Tracker estimates how psychoactive substances rise and fall in your "
    "body using population-average pharmacokinetic models.\n\n"
    "This is NOT medical advice. Individual metabolism varies widely, and "
    "every constant here is a population average.\n\n"
    "• Prescription medicines (e.g. methylphenidate) are visualised only. "
    "Dosing is your prescriber's decision; this tool never recommends doses.\n"
    "• Alcohol BAC and sober-time figures are rough estimates and must not be "
    "used to decide whether it is safe or legal to drive."
)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PK Tracker")
    # The app lives in the tray; closing the main window must not quit it.
    app.setQuitOnLastWindowClosed(False)

    db = Database(default_db_path())
    controller = AppController(db)
    apply_theme(app, controller.get_setting("ui_theme", "dark"))
    window = MainWindow(controller)

    if controller.get_setting("ui_disclaimer_ack") != "1":
        QMessageBox.information(window, "Welcome to PK Tracker", WELCOME)
        controller.set_setting("ui_disclaimer_ack", "1")

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
