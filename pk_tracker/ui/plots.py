"""pyqtgraph wrappers: the main timeline plot and the widget sparkline.

The timeline shows two traces on two y-axes — objective **blood level** on the
left (in the substance's own units) and subjective **effect** on the right
(percent of the user's recent peak). The part of each curve that has already
happened is drawn solid; the future projection is dashed. A vertical marker
shows "now". This is the conceptual centrepiece, so the two traces are kept
visually distinct and never collapsed into one.
"""

from __future__ import annotations

from datetime import datetime

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


class AdaptiveDateAxisItem(pg.DateAxisItem):
    """Date axis with denser, zoom-aware time labels for the timeline."""

    def tickStrings(self, values, scale, spacing):
        if spacing < 60:
            fmt = "%H:%M:%S"
        elif spacing < 6 * 3600:
            fmt = "%H:%M"
        elif spacing < 36 * 3600:
            fmt = "%a %H:%M"
        else:
            fmt = "%d %b\n%H:%M"
        return [datetime.fromtimestamp(v).astimezone().strftime(fmt) for v in values]


class TimelinePlot(pg.PlotWidget):
    """Blood-level (left axis) + effect-% (right axis) over time."""

    def __init__(self, parent=None):
        super().__init__(parent, axisItems={"bottom": AdaptiveDateAxisItem()})
        self._now_ts = 0.0
        self._items: list = []        # everything we add, so we can clear cleanly
        self._hover_x: np.ndarray | None = None
        self._hover_series: list[tuple[str, np.ndarray, str]] = []

        self.p1 = self.getPlotItem()
        self.p1.showGrid(x=True, y=True, alpha=0.12)
        self.p1.setMenuEnabled(False)
        self.p1.setMouseEnabled(x=True, y=False)
        self.p1.hideButtons()
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
        self.p1.getAxis("right").setLabel("Effect", units="%", color=COLORS["effect"])
        self.p1.getAxis("bottom").setStyle(tickTextOffset=8, autoExpandTextSpace=True)
        self.p1.getAxis("right").setTextPen(COLORS["effect"])
        self.vb2.setYRange(0, 105, padding=0)
        self.vb2.setMouseEnabled(x=False, y=False)
        self.p1.vb.sigResized.connect(self._sync_views)

        self._hover_line = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(color=COLORS["subtext"], width=1, style=Qt.DotLine),
        )
        self._hover_label = pg.TextItem("", color=COLORS["text"], anchor=(0, 1),
                                        fill=COLORS["panel"])
        self._hover_line.hide()
        self._hover_label.hide()
        self.p1.addItem(self._hover_line, ignoreBounds=True)
        self.p1.addItem(self._hover_label, ignoreBounds=True)
        self._hover_proxy = pg.SignalProxy(
            self.scene().sigMouseMoved, rateLimit=30, slot=self._on_mouse_moved,
        )

    def _sync_views(self):
        self.vb2.setGeometry(self.p1.vb.sceneBoundingRect())
        self.vb2.linkedViewChanged(self.p1.vb, self.vb2.XAxis)

    def resizeEvent(self, ev):
        # The effect (right-axis) ViewBox must track the main plot's geometry, or
        # the blue trace drifts/clips and stops following pans. sigResized alone
        # can miss the initial layout and some resizes, so sync here too.
        super().resizeEvent(ev)
        if getattr(self, "vb2", None) is not None:
            self._sync_views()

    def apply_theme(self):
        """Refresh static chrome (background, axes) after a theme switch.

        Curves themselves are redrawn from scratch on the next refresh, so only
        the persistent background and axis colours need updating here.
        """
        self.setBackground(COLORS["bg"])
        self.p1.getAxis("left").setTextPen(COLORS["subtext"])
        self.p1.getAxis("bottom").setTextPen(COLORS["subtext"])
        self.p1.getAxis("right").setTextPen(COLORS["effect"])
        self.p1.getAxis("right").setLabel("Effect", units="%", color=COLORS["effect"])
        self.p1.getAxis("bottom").setStyle(tickTextOffset=8, autoExpandTextSpace=True)

    # ----- lifecycle ---------------------------------------------------------
    def set_now(self, now_ts: float):
        self._now_ts = now_ts

    def clear_curves(self):
        for it, target in self._items:
            target.removeItem(it)
        self._items = []
        self._hover_x = None
        self._hover_series = []
        self._hover_line.hide()
        self._hover_label.hide()
        self.vb2.setYRange(0, 105, padding=0)   # reset; _grow_effect_axis expands it

    def set_normalized_y_ranges(self, concentration, effect_pct=None):
        """Normalize vertical scale after every redraw and lock mouse panning to X."""
        conc = np.asarray(concentration, float)
        c_top = 1.0
        if conc.size and np.isfinite(conc).any():
            c_top = max(1.0, float(np.nanmax(conc)) * 1.15)
        self.p1.setYRange(0, c_top, padding=0)

        e_top = 105.0
        if effect_pct is not None:
            eff = np.asarray(effect_pct, float)
            if eff.size and np.isfinite(eff).any():
                e_top = max(105.0, float(np.nanmax(eff)) * 1.08)
        self.vb2.setYRange(0, e_top, padding=0)

    def set_hover_data(self, x, series):
        self._hover_x = np.asarray(x, float)
        self._hover_series = [
            (label, np.asarray(y, float), suffix)
            for label, y, suffix in series
            if y is not None
        ]

    def _on_mouse_moved(self, evt):
        if self._hover_x is None or not self._hover_series:
            return
        pos = evt[0]
        if not self.p1.sceneBoundingRect().contains(pos):
            self._hover_line.hide()
            self._hover_label.hide()
            return
        mouse = self.p1.vb.mapSceneToView(pos)
        x = float(mouse.x())
        if x < self._hover_x[0] or x > self._hover_x[-1]:
            self._hover_line.hide()
            self._hover_label.hide()
            return
        local = datetime.fromtimestamp(x).astimezone().strftime("%a %H:%M")
        lines = [local]
        for label, y, suffix in self._hover_series:
            val = float(np.interp(x, self._hover_x, y))
            lines.append(f"{label}: {val:.1f}{suffix}")
        self._hover_line.setPos(x)
        yr = self.p1.vb.viewRange()[1]
        self._hover_label.setText("\n".join(lines))
        self._hover_label.setPos(x, yr[1])
        self._hover_line.show()
        self._hover_label.show()

    def _grow_effect_axis(self, y):
        """Expand the right (effect) axis so a curve peaking above the recent peak
        — e.g. a just-logged dose still rising past 100% — stays fully visible
        instead of clipping at the top."""
        arr = np.asarray(y, float)
        if arr.size:
            top = max(105.0, float(np.nanmax(arr)) * 1.08)
            self.vb2.setYRange(0, top, padding=0)

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
            self._split_line(x, effect_pct, COLORS["effect"], 1.8, right=True, fill=False)
            self._grow_effect_axis(effect_pct)

    def add_overlay_effect(self, x, effect_pct, color):
        """In overlay mode, compare substances by effect-% on the right axis."""
        self._split_line(x, effect_pct, color, 1.4, right=True, fill=False)
        self._grow_effect_axis(effect_pct)

    def add_simulation(self, x, concentration, effect_pct, color):
        """Draw a hypothetical future-dose curve in a distinct colour."""
        self._split_line(x, concentration, color, 2.1, right=False, fill=False)
        if effect_pct is not None:
            self._split_line(x, effect_pct, color, 1.5, right=True, fill=False)
            self._grow_effect_axis(effect_pct)

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
        self._sync_views()   # keep the effect ViewBox aligned after every redraw


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
