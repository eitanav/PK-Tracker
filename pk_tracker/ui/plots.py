"""pyqtgraph wrappers: the main timeline plot and the widget sparkline.

The timeline shows two traces on two y-axes — objective **blood level** on the
left (in the substance's own units) and subjective **effect** on the right
(percent of the user's recent peak). The part of each curve that has already
happened is drawn solid; the future projection is dashed. A vertical marker
shows "now". This is the conceptual centrepiece, so the two traces are kept
visually distinct and never collapsed into one.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .theme import COLORS

pg.setConfigOption("background", COLORS["bg"])
pg.setConfigOption("foreground", COLORS["subtext"])
pg.setConfigOptions(antialias=True)


def _with_alpha(hex_color: str, alpha: int) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


class TimelinePlot(pg.PlotWidget):
    """Blood-level (left axis) + effect-% (right axis) over time."""

    def __init__(self, parent=None):
        super().__init__(parent, axisItems={"bottom": pg.DateAxisItem()})
        self._now_ts = 0.0
        self._items: list = []        # everything we add, so we can clear cleanly

        self.p1 = self.getPlotItem()
        self.p1.showGrid(x=True, y=True, alpha=0.12)
        self.p1.setMenuEnabled(False)
        self.p1.setLabel("left", "Blood level")
        self.p1.getAxis("left").setTextPen(COLORS["subtext"])
        self.p1.getAxis("bottom").setTextPen(COLORS["subtext"])
        # Keep the axis unit exactly as set (e.g. g/dL), matching the readout,
        # rather than pyqtgraph silently re-prefixing it to mg/dL.
        self.p1.getAxis("left").enableAutoSIPrefix(False)

        # Second ViewBox for the effect axis (right).
        self.vb2 = pg.ViewBox()
        self.p1.showAxis("right")
        self.p1.scene().addItem(self.vb2)
        self.p1.getAxis("right").linkToView(self.vb2)
        self.vb2.setXLink(self.p1)
        self.p1.getAxis("right").setLabel("Effect", units="%", color=COLORS["accent"])
        self.p1.getAxis("right").setTextPen(COLORS["accent"])
        self.vb2.setYRange(0, 105, padding=0)
        self.vb2.setMouseEnabled(x=False, y=False)
        self.p1.vb.sigResized.connect(self._sync_views)

    def _sync_views(self):
        self.vb2.setGeometry(self.p1.vb.sceneBoundingRect())
        self.vb2.linkedViewChanged(self.p1.vb, self.vb2.XAxis)

    def apply_theme(self):
        """Refresh static chrome (background, axes) after a theme switch.

        Curves themselves are redrawn from scratch on the next refresh, so only
        the persistent background and axis colours need updating here.
        """
        self.setBackground(COLORS["bg"])
        self.p1.getAxis("left").setTextPen(COLORS["subtext"])
        self.p1.getAxis("bottom").setTextPen(COLORS["subtext"])
        self.p1.getAxis("right").setTextPen(COLORS["accent"])
        self.p1.getAxis("right").setLabel("Effect", units="%", color=COLORS["accent"])

    # ----- lifecycle ---------------------------------------------------------
    def set_now(self, now_ts: float):
        self._now_ts = now_ts

    def clear_curves(self):
        for it, target in self._items:
            target.removeItem(it)
        self._items = []

    def _add(self, item, right: bool = False):
        target = self.vb2 if right else self.p1
        target.addItem(item)
        self._items.append((item, target))
        return item

    # ----- drawing -----------------------------------------------------------
    def _split_line(self, x, y, color, width, right, fill):
        """Add a curve split into a solid (past) and dashed (future) segment."""
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        past = x <= self._now_ts
        fut = x >= self._now_ts
        solid = pg.mkPen(color=color, width=width)
        dashed = pg.mkPen(color=color, width=width, style=Qt.DashLine)

        if past.any():
            kw = {}
            if fill:
                kw = dict(fillLevel=0.0, fillBrush=_with_alpha(color, 38))
            self._add(pg.PlotDataItem(x[past], y[past], pen=solid, **kw), right=right)
        if fut.any():
            self._add(pg.PlotDataItem(x[fut], y[fut], pen=dashed), right=right)

    def add_substance(self, x, concentration, effect_pct, color, *, primary=True):
        """Plot one substance. Primary substances get a filled concentration and
        their effect trace; overlays get a thin concentration line only."""
        width = 2.4 if primary else 1.4
        self._split_line(x, concentration, color, width, right=False, fill=primary)
        if primary and effect_pct is not None:
            self._split_line(x, effect_pct, COLORS["accent"], 1.8, right=True, fill=False)

    def add_overlay_effect(self, x, effect_pct, color):
        """In overlay mode, compare substances by effect-% on the right axis."""
        self._split_line(x, effect_pct, color, 1.4, right=True, fill=False)

    def add_hline(self, level, color, label):
        line = pg.InfiniteLine(
            pos=level, angle=0, movable=False,
            pen=pg.mkPen(color=color, width=1, style=Qt.DotLine),
            label=label, labelOpts={"color": color, "position": 0.04, "fill": COLORS["panel"]},
        )
        self._add(line)

    def mark_now(self):
        line = pg.InfiniteLine(
            pos=self._now_ts, angle=90, movable=False,
            pen=pg.mkPen(color=COLORS["muted"], width=1, style=Qt.DashLine),
            label="now", labelOpts={"color": COLORS["subtext"], "position": 0.96},
        )
        self._add(line)

    def add_banner(self, text, color):
        item = pg.TextItem(text, color=color, anchor=(0, 0))
        item.setPos(self._now_ts, self.vb2.viewRange()[1][1])
        # Banner is informational; pin near the top-left of the view in effect space.
        self._add(item, right=True)

    def set_left_label(self, unit: str):
        self.p1.setLabel("left", "Blood level", units=unit)

    def set_x_window(self, start_ts, end_ts):
        self.p1.setXRange(start_ts, end_ts, padding=0.02)


class Sparkline(pg.PlotWidget):
    """A tiny, axis-free effect trace for the floating widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMenuEnabled(False)
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.setMouseEnabled(x=False, y=False)
        self.setBackground(COLORS["panel"])
        self.getPlotItem().setContentsMargins(0, 0, 0, 0)
        self._now_ts = 0.0

    def set_now(self, ts):
        self._now_ts = ts

    def apply_theme(self):
        self.setBackground(COLORS["panel"])

    def update_trace(self, x, y, color):
        self.clear()
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        past, fut = x <= self._now_ts, x >= self._now_ts
        if past.any():
            self.plot(
                x[past], y[past], pen=pg.mkPen(color=color, width=2),
                fillLevel=0.0, fillBrush=_with_alpha(color, 50),
            )
        if fut.any():
            self.plot(x[fut], y[fut], pen=pg.mkPen(color=color, width=1.5, style=Qt.DashLine))
        self.addItem(pg.InfiniteLine(
            pos=self._now_ts, angle=90,
            pen=pg.mkPen(color=COLORS["muted"], width=1, style=Qt.DashLine),
        ))
        if y.size:
            self.setYRange(0, max(1.0, float(np.nanmax(y)) * 1.15), padding=0)
