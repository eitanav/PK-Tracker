"""Tests for the per-substance accent, the hero gauge, and the Insights view."""

import os
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from PySide6.QtCore import Qt

from pk_tracker.controller import AppController, now_utc
from pk_tracker.data.db import Database
from pk_tracker.ui.gauge import HeroGauge
from pk_tracker.ui.main_window import MainWindow
from pk_tracker.ui.theme import COLORS, apply_theme, set_accent


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def clean_theme(app):
    """Start every test from the stock dark palette with no substance tint.

    The accent is module-level state, so a window built by another test would
    otherwise leak its substance colour into this one.
    """
    set_accent(None)
    apply_theme(app, "dark")
    yield
    set_accent(None)
    apply_theme(app, "dark")


@pytest.fixture
def window(app, tmp_path):
    db = Database(tmp_path / "ui.sqlite")
    controller = AppController(db)
    win = MainWindow(controller)
    yield win
    win.quit_app()
    app.processEvents()


def test_set_accent_derives_the_family_and_restores(app):
    assert set_accent("#d6a04a") is True
    assert COLORS["accent"] == "#d6a04a"
    assert COLORS["accent_text"] == "#06121f"      # dark text on a light amber
    assert COLORS["accent_soft"] != COLORS["accent"]
    assert set_accent("#d6a04a") is False          # no-op when unchanged

    assert set_accent("#c0567a") is True
    assert COLORS["accent_text"] == "#ffffff"      # light text on a dark rose

    assert set_accent(None) is True
    assert COLORS["accent"] == "#4aa3ff"           # back to the palette's own


def test_accent_survives_a_theme_switch(app):
    set_accent("#5ad6b0")
    apply_theme(app, "light")
    assert COLORS["accent"] == "#5ad6b0"
    assert COLORS["bg"] == "#f4f6f9"


def test_effect_colour_is_independent_of_the_accent(app):
    """The level curve wears the substance colour, so the effect trace must not."""
    set_accent("#4aa3ff")
    assert COLORS["effect"] == "#4aa3ff"
    set_accent("#d6a04a")
    assert COLORS["effect"] == "#4aa3ff"


def test_gauge_snaps_when_the_unit_changes(app):
    gauge = HeroGauge(120)
    gauge.set_reading(value=200.0, fraction=0.5, unit="mg", animate=False)
    assert gauge.property("value") == 200.0
    assert gauge.property("fraction") == 0.5

    # A different quantity must not be counted through; it would spell nonsense.
    gauge.set_reading(value=0.014, fraction=0.28, unit="g/dL", decimals=3)
    assert gauge.property("value") == pytest.approx(0.014)
    assert gauge.property("fraction") == pytest.approx(0.28)


def test_gauge_clamps_the_ring(app):
    gauge = HeroGauge(120)
    gauge.set_reading(value=900.0, fraction=3.0, unit="mg", animate=False)
    assert gauge.property("fraction") == 1.0
    gauge.set_reading(value=0.0, fraction=-1.0, unit="mg", animate=False)
    assert gauge.property("fraction") == 0.0


def test_window_tints_itself_to_the_active_substance(window):
    """Switching substance re-derives the accent from that substance's colour."""
    caffeine = window.controller.substance("caffeine")
    assert COLORS["accent"] == caffeine.color

    for row in range(window.sub_list.count()):
        if window.sub_list.item(row).data(Qt.UserRole) == "alcohol":
            window.sub_list.setCurrentRow(row)
            break
    assert window.active_sid == "alcohol"
    assert COLORS["accent"] == window.controller.substance("alcohol").color


def test_insights_page_reports_the_log(window):
    now = now_utc()
    for hours in (1, 25, 49):
        window.controller.log_dose("caffeine", 90.0, "mg", taken_at=now - timedelta(hours=hours))
    window.view_group.button(1).click()

    assert window.pages.currentIndex() == 1
    view = window.insights_view
    assert view.empty.isHidden() is True
    assert view.tiles["day streak"].text() != ""
    assert "Busiest hours" in view.peak_label.text()


def test_insights_page_shows_an_empty_state(window):
    window.view_group.button(1).click()
    assert window.insights_view.empty.isHidden() is False
    assert window.insights_view.when_card.isHidden() is True
