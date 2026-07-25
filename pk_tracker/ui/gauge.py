"""The hero gauge: one circular readout of where you are right now.

The ring sweeps clockwise from the top to the current fraction of a meaningful
ceiling — mg against the jitter zone, effect against your recent peak, BAC
against the driving limit — and the number in the middle counts up to match.
Both are QPropertyAnimations on the same duration and easing, so the sweep and
the digits arrive together instead of racing.

Drawn with QPainter: no images, so it re-tints with the accent for free.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import COLORS, mono_font

_SWEEP_MS = 900


class HeroGauge(QWidget):
    """A ring + a counting number. Set a reading, it animates there."""

    def __init__(self, diameter: int = 150, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._fraction = 0.0
        self._value = 0.0
        self._decimals = 0
        self._unit = ""
        self._accent: str | None = None

        self._sweep = QPropertyAnimation(self, b"fraction", self)
        self._sweep.setDuration(_SWEEP_MS)
        self._sweep.setEasingCurve(QEasingCurve.OutCubic)
        self._count = QPropertyAnimation(self, b"value", self)
        self._count.setDuration(_SWEEP_MS)
        self._count.setEasingCurve(QEasingCurve.OutCubic)

    # ----- animated properties ----------------------------------------------
    def _get_fraction(self) -> float:
        return self._fraction

    def _set_fraction(self, f: float) -> None:
        self._fraction = max(0.0, min(1.0, float(f)))
        self.update()

    def _get_value(self) -> float:
        return self._value

    def _set_value(self, v: float) -> None:
        self._value = float(v)
        self.update()

    fraction = Property(float, _get_fraction, _set_fraction)
    value = Property(float, _get_value, _set_value)

    # ----- state -------------------------------------------------------------
    def set_reading(
        self, *, value: float, fraction: float, unit: str = "",
        decimals: int = 0, accent: str | None = None, animate: bool = True,
    ) -> None:
        """Point the gauge at a new reading.

        ``fraction`` is clamped to 0..1; ``accent`` overrides the live theme
        accent (used to flash the ring warn-coloured in the jitter zone).
        """
        target_f = max(0.0, min(1.0, float(fraction)))
        target_v = float(value)
        # Counting between two different quantities (300 mg -> 0.014 g/dL) spells
        # out nonsense on the way, so a change of unit snaps instead of sweeping.
        rescaled = unit != self._unit or int(decimals) != self._decimals
        self._decimals = int(decimals)
        self._unit = unit
        self._accent = accent

        # A tick that barely moves should not re-animate; it just looks jittery.
        moved = abs(target_f - self._fraction) > 0.005 or abs(target_v - self._value) > 0.5
        if not animate or rescaled or not moved:
            self._sweep.stop()
            self._count.stop()
            self._set_fraction(target_f)
            self._set_value(target_v)
            return

        for anim, start, end in (
            (self._sweep, self._fraction, target_f),
            (self._count, self._value, target_v),
        ):
            anim.stop()
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.start()

    # ----- painting ----------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self._accent or COLORS["accent"])

        d = float(min(self.width(), self.height()))
        stroke = d * 0.082
        rect = QRectF(stroke / 2, stroke / 2, d - stroke, d - stroke)

        track = QPen(QColor(COLORS["accent_soft"]), stroke)
        track.setCapStyle(Qt.FlatCap)
        p.setPen(track)
        p.drawArc(rect, 0, 360 * 16)

        if self._fraction > 0:
            arc = QPen(accent, stroke)
            arc.setCapStyle(Qt.RoundCap)
            p.setPen(arc)
            # Qt angles: 0 at 3 o'clock, positive counter-clockwise, 1/16 degree.
            p.drawArc(rect, 90 * 16, -int(round(360 * 16 * self._fraction)))

        text = f"{self._value:.{self._decimals}f}"
        p.setPen(QColor(accent))
        p.setFont(mono_font(max(13, int(d * 0.185)), 700))
        num_rect = QRectF(0, d * 0.30, d, d * 0.26)
        p.drawText(num_rect, Qt.AlignHCenter | Qt.AlignVCenter, text)

        if self._unit:
            p.setPen(QColor(COLORS["subtext"]))
            p.setFont(mono_font(max(8, int(d * 0.072)), 500))
            p.drawText(
                QRectF(0, d * 0.56, d, d * 0.14),
                Qt.AlignHCenter | Qt.AlignVCenter, self._unit,
            )
        p.end()
