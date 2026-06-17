"""Lightweight smoke tests for application/UI construction."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from pk_tracker.controller import AppController
from pk_tracker.data.db import Database
from pk_tracker.ui.main_window import MainWindow


def test_main_window_and_widget_construct(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / "smoke.sqlite")
    window = None
    try:
        controller = AppController(db)
        window = MainWindow(controller)
        assert window.widget is not None
        assert window.widget.windowTitle() == "PK Tracker widget"
        assert window.widget.pinned is False
    finally:
        if window is not None:
            window.quit_app()
        else:
            db.close()
        app.processEvents()
