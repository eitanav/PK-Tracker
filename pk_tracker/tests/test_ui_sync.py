"""The Settings dialog's cloud-sync section.

Network and sign-in are faked; what is checked is that each state is reported
honestly, that the buttons cannot be used when they would fail, and that the
work happens off the GUI thread.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication      # noqa: E402

from pk_tracker.controller import AppController  # noqa: E402
from pk_tracker.data.db import Database          # noqa: E402
from pk_tracker.sync.cloudsync import SyncError, SyncResult  # noqa: E402
from pk_tracker.ui.main_window import MainWindow  # noqa: E402
from pk_tracker.ui.settings import SettingsDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def parts(qapp):
    db = Database(None)
    controller = AppController(db)
    window = MainWindow(controller)
    yield controller, window
    db.close()


def _settle(qapp, dialog, timeout_ms=3000):
    """Pump the event loop until the status worker has landed."""
    deadline = timeout_ms
    while deadline > 0:
        qapp.processEvents()
        worker = getattr(dialog, "_status_worker", None)
        if worker is None or worker.isFinished():
            qapp.processEvents()
            return
        QApplication.instance().thread().msleep(10)
        deadline -= 10


def test_unconfigured_points_at_the_setup_docs(parts, qapp):
    controller, window = parts
    dialog = SettingsDialog(controller, window)
    _settle(qapp, dialog)
    assert "docs/SYNC.md" in dialog.sync_status.text()
    # Neither button can do anything useful without config.
    assert not dialog.sync_now_btn.isEnabled()
    assert not dialog.sync_auth_btn.isEnabled()


def test_configured_but_signed_out_offers_sign_in(parts, qapp, monkeypatch):
    controller, window = parts
    monkeypatch.setattr(type(controller), "sync_configured", property(lambda _s: True))
    monkeypatch.setattr(controller, "sync_identity", lambda: None)
    dialog = SettingsDialog(controller, window)
    _settle(qapp, dialog)
    assert dialog.sync_status.text() == "Not signed in."
    assert dialog.sync_auth_btn.text() == "Sign in with Google…"
    assert dialog.sync_auth_btn.isEnabled()
    # Syncing while signed out would only raise; keep it disabled.
    assert not dialog.sync_now_btn.isEnabled()


def test_signed_in_shows_the_account_and_enables_sync(parts, qapp, monkeypatch):
    controller, window = parts
    monkeypatch.setattr(type(controller), "sync_configured", property(lambda _s: True))
    monkeypatch.setattr(controller, "sync_identity", lambda: ("uid-1", "me@example.com"))
    monkeypatch.setattr(
        controller, "sync_last_at", lambda: datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
    )
    dialog = SettingsDialog(controller, window)
    _settle(qapp, dialog)
    assert "me@example.com" in dialog.sync_status.text()
    assert dialog.sync_auth_btn.text() == "Sign out"
    assert dialog.sync_now_btn.isEnabled()


def test_never_synced_says_so(parts, qapp, monkeypatch):
    controller, window = parts
    monkeypatch.setattr(type(controller), "sync_configured", property(lambda _s: True))
    monkeypatch.setattr(controller, "sync_identity", lambda: ("uid-1", "me@example.com"))
    monkeypatch.setattr(controller, "sync_last_at", lambda: None)
    dialog = SettingsDialog(controller, window)
    _settle(qapp, dialog)
    assert "never" in dialog.sync_status.text()


def test_sync_failure_is_reported_not_swallowed(parts, qapp, monkeypatch):
    controller, window = parts
    monkeypatch.setattr(type(controller), "sync_configured", property(lambda _s: True))
    monkeypatch.setattr(controller, "sync_identity", lambda: ("uid-1", "me@example.com"))

    def boom():
        raise SyncError("Firestore rejected the request (403)")

    monkeypatch.setattr(controller, "sync_now", boom)

    seen = {}
    monkeypatch.setattr(
        "pk_tracker.ui.settings.QMessageBox.warning",
        lambda *a, **k: seen.update(title=a[1], text=a[2]),
    )
    dialog = SettingsDialog(controller, window)
    _settle(qapp, dialog)
    dialog._on_sync_now()
    for _ in range(300):
        qapp.processEvents()
        if seen:
            break
    assert seen.get("title") == "Sync failed"
    assert "403" in seen.get("text", "")


def test_successful_sync_reports_and_refreshes(parts, qapp, monkeypatch):
    controller, window = parts
    monkeypatch.setattr(type(controller), "sync_configured", property(lambda _s: True))
    monkeypatch.setattr(controller, "sync_identity", lambda: ("uid-1", "me@example.com"))
    monkeypatch.setattr(
        controller, "sync_now", lambda: SyncResult(inserted=2, updated=0, pushed=1)
    )

    refreshed = []
    monkeypatch.setattr(window, "refresh_all", lambda: refreshed.append(True))
    shown = {}
    monkeypatch.setattr(
        "pk_tracker.ui.settings.QMessageBox.information",
        lambda *a, **k: shown.update(text=a[2]),
    )
    dialog = SettingsDialog(controller, window)
    _settle(qapp, dialog)
    dialog._on_sync_now()
    for _ in range(300):
        qapp.processEvents()
        if shown:
            break
    assert "2 new" in shown.get("text", "")
    assert refreshed, "pulled doses must trigger a UI refresh"
