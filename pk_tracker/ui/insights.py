"""The Insights view: the dose log read back as patterns.

Three cards over the same statistics the Android app shows, so the two agree
number for number: the hours you actually reach for it, your weekly rhythm, and
the flat averages (doses per active day, this week's total, usual first dose,
logging streak). The maths lives in :mod:`pk_tracker.core.insights`; this file
only draws it.

Bars grow in once per refresh — enough motion to show the shape assembling,
short enough to stay out of the way.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..controller import now_utc
from ..core.insights import WINDOW_DAYS, compute_insights
from .theme import COLORS, card_frame, mono_font, stat_tile

_GROW_MS = 800
_WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"]


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class BarStrip(QWidget):
    """A row of bars, sized to the largest value, that grows in on demand.

    Highlighted indices are drawn in the accent; the rest stay chrome-coloured,
    so the eye lands on the peak hours (or on today) without a legend.
    """

    def __init__(self, spacing: int = 3, radius: int = 3, parent=None):
        super().__init__(parent)
        self._values: list[float] = []
        self._highlight: set[int] = set()
        self._spacing = spacing
        self._radius = radius
        self._grow = 0.0
        self._anim = QPropertyAnimation(self, b"grow_factor", self)
        self._anim.setDuration(_GROW_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_grow(self) -> float:
        return self._grow

    def _set_grow(self, v: float) -> None:
        self._grow = float(v)
        self.update()

    grow_factor = Property(float, _get_grow, _set_grow)

    def set_values(self, values, highlight=()) -> None:
        self._values = [float(v) for v in values]
        self._highlight = set(highlight)
        self.update()

    def grow(self) -> None:
        """Replay the grow-in. Call once per refresh, after set_values."""
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, _e):
        if not self._values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)

        n = len(self._values)
        top = max(self._values) or 1.0
        h = float(self.height())
        total_gap = self._spacing * (n - 1)
        w = max(1.0, (self.width() - total_gap) / n)
        accent = QColor(COLORS["accent"])
        dim = QColor(COLORS["border"])

        for i, value in enumerate(self._values):
            # A stub for empty buckets, so the axis still reads as a full row.
            bar = 3.0 + (h - 3.0) * (value / top) * self._grow
            x = i * (w + self._spacing)
            p.setBrush(accent if i in self._highlight else dim)
            p.drawRoundedRect(QRectF(x, h - bar, w, bar), self._radius, self._radius)
        p.end()


class InsightsView(QWidget):
    """The Insights page of the centre panel, for one substance at a time."""

    def __init__(self, controller, sid: str, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.sid = sid

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Insights")
        title.setObjectName("H1")
        self.sub_name = QLabel("")
        self.sub_name.setObjectName("Accented")
        window = QLabel(f"last {WINDOW_DAYS} days")
        window.setObjectName("Muted")
        header.addWidget(title)
        header.addWidget(self.sub_name)
        header.addStretch(1)
        header.addWidget(window)
        root.addLayout(header)

        self.empty = QLabel(
            "No doses logged yet — log a few and your patterns show up here."
        )
        self.empty.setObjectName("Sub")
        self.empty.setWordWrap(True)
        root.addWidget(self.empty)

        root.addWidget(self._build_when())
        root.addWidget(self._build_weekly())
        root.addWidget(self._build_averages())
        root.addStretch(1)

    # ----- cards -------------------------------------------------------------
    def _build_when(self):
        self.when_card = card_frame("When you have it")
        v = self.when_card.layout()
        self.hours = BarStrip(spacing=3)
        self.hours.setMinimumHeight(104)
        v.addWidget(self.hours)

        axis = QHBoxLayout()
        axis.setContentsMargins(0, 0, 0, 0)
        for i, text in enumerate(("00", "06", "12", "18", "23")):
            lbl = QLabel(text)
            lbl.setObjectName("Muted")
            lbl.setFont(mono_font(9))
            axis.addWidget(lbl)
            if i < 4:
                axis.addStretch(1)
        v.addLayout(axis)

        self.peak_label = QLabel("")
        self.peak_label.setObjectName("Accented")
        self.peak_label.setFont(mono_font(11, 600))
        v.addWidget(self.peak_label)
        return self.when_card

    def _build_weekly(self):
        self.weekly_card = card_frame("Weekly rhythm")
        v = self.weekly_card.layout()
        self.weekly = BarStrip(spacing=10, radius=4)
        self.weekly.setMinimumHeight(84)
        v.addWidget(self.weekly)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.weekday_labels = []
        for name in _WEEKDAYS:
            lbl = QLabel(name)
            lbl.setFont(mono_font(9))
            lbl.setAlignment(Qt.AlignCenter)
            row.addWidget(lbl, 1)
            self.weekday_labels.append(lbl)
        v.addLayout(row)
        return self.weekly_card

    def _build_averages(self):
        self.avg_card = card_frame("Averages")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.tiles = {}
        cells = [
            ("per active day", 0, 0), ("this week", 0, 1),
            ("usual first", 1, 0), ("day streak", 1, 1),
        ]
        for caption, r, c in cells:
            tile, value = stat_tile(caption)
            grid.addWidget(tile, r, c)
            self.tiles[caption] = value
        self.avg_card.layout().addLayout(grid)
        return self.avg_card

    # ----- refresh -----------------------------------------------------------
    def set_substance(self, sid: str) -> None:
        self.sid = sid
        self.refresh()

    def refresh(self, now: datetime | None = None) -> None:
        now = now or now_utc()
        sub = self.controller.substance(self.sid)
        ins = compute_insights(self.controller.doses(self.sid), self.sid, now)

        self.sub_name.setText(f"· {sub.name}")
        self.empty.setVisible(not ins.has_data)
        for card in (self.when_card, self.weekly_card, self.avg_card):
            card.setVisible(ins.has_data)
        if not ins.has_data:
            return

        self.hours.set_values(ins.hour_counts, ins.peak_hours)
        self.hours.grow()
        if ins.peak_hours:
            busiest = "  ·  ".join(f"{h:02d}:00" for h in sorted(ins.peak_hours))
            self.peak_label.setText(f"Busiest hours: {busiest}")
        else:
            self.peak_label.setText("")

        today = now.astimezone().weekday()
        self.weekly.set_values(ins.dow_avg_amount, [today])
        self.weekly.grow()
        for i, lbl in enumerate(self.weekday_labels):
            colour = COLORS["accent"] if i == today else COLORS["muted"]
            lbl.setStyleSheet(f"color: {colour};")

        first = _hhmm(ins.first_dose_minutes) if ins.first_dose_minutes is not None else "—"
        self.tiles["per active day"].setText(f"{ins.avg_per_day:.1f}")
        self.tiles["this week"].setText(f"{ins.week_amount:.0f} {sub.unit}")
        self.tiles["usual first"].setText(first)
        self.tiles["day streak"].setText(str(ins.streak_days))
