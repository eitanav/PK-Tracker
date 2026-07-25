"""The PK Tracker brand mark: the pharmacokinetic curve itself.

Absorption, peak, clearance — the shape the whole app is about — inside a
rounded badge. Drawn with QPainter on a 48-unit grid so it stays crisp from a
16 px tray icon up to the dashboard header, and re-tints to whatever accent it
is handed. Matches the Android app's ``PkLogo``, so the two look like one
product.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from .theme import COLORS

# Fixed brand colours for the shipped icon (tray, taskbar, .exe): the mark must
# look the same in light or dark mode and against any desktop wallpaper.
BRAND_TILE = "#13212b"
BRAND_BORDER = "#22384a"
BRAND_ACCENT = "#4aa3ff"


def paint_mark(
    p: QPainter, size: float, accent: str = BRAND_ACCENT, *,
    badge: bool = True, tile: str = BRAND_TILE, border: str = BRAND_BORDER,
) -> None:
    """Draw the mark filling a ``size`` x ``size`` square at the origin."""
    k = float(size) / 48.0

    def u(v: float) -> float:
        return v * k

    p.setRenderHint(QPainter.Antialiasing)
    acc = QColor(accent)

    if badge:
        rect = QRectF(u(0.5), u(0.5), u(47), u(47))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(tile)))
        p.drawRoundedRect(rect, u(12), u(12))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(border), max(1.0, u(1))))
        p.drawRoundedRect(rect, u(12), u(12))

    # The curve: a flat baseline, a steep absorption climb to Cmax, then the
    # long clearance tail.
    curve = QPainterPath(QPointF(u(8), u(35)))
    curve.cubicTo(u(14), u(35), u(16), u(15), u(23), u(14))
    curve.cubicTo(u(31), u(13), u(35), u(26), u(41), u(30))

    area = QPainterPath(curve)
    area.lineTo(u(41), u(39))
    area.lineTo(u(8), u(39))
    area.closeSubpath()

    fill = QColor(acc)
    fill.setAlpha(51)                       # ~20%, the area under the curve
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(fill))
    p.drawPath(area)

    stroke = QPen(acc, u(2.6))
    stroke.setCapStyle(Qt.RoundCap)
    stroke.setJoinStyle(Qt.RoundJoin)
    p.setPen(stroke)
    p.setBrush(Qt.NoBrush)
    p.drawPath(curve)

    # The peak itself, marked.
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(acc))
    p.drawEllipse(QPointF(u(23), u(14)), u(3.1), u(3.1))


def make_app_icon(accent: str = BRAND_ACCENT, size: int = 64) -> QIcon:
    """The application icon: the PK curve on a dark tile."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_mark(p, size, accent)
    p.end()
    return QIcon(pm)


class PkLogo(QWidget):
    """The mark as an in-app widget, badged in the current panel colours.

    Follows the live accent by default, so switching substance re-tints it along
    with the rest of the UI; ``set_accent`` pins it to an explicit colour.
    """

    def __init__(self, size: int = 30, parent=None):
        super().__init__(parent)
        self._accent: str | None = None
        self.setFixedSize(size, size)

    def set_accent(self, color: str | None) -> None:
        self._accent = color
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_mark(
            p, min(self.width(), self.height()), self._accent or COLORS["accent"],
            tile=COLORS["panel_alt"], border=COLORS["border"],
        )
        p.end()
