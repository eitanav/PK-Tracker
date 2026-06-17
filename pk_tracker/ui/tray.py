"""System tray icon and menu, plus a generated application icon.

Closing the main window hides to the tray instead of quitting; the tray menu
brings the dashboard back, finds/hides the floating widget, or quits for real.
"""

from __future__ import annotations

import math

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
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

# Brand colours for the logo, fixed (theme-independent) so the app mark looks the
# same in light or dark mode and when embedded as the .exe / installer icon.
_TILE = "#13212b"
_ACCENT = "#4aa3ff"
_STEAM = "#7fc0ff"


def _paint_icon(p: QPainter, size: int, accent: str = _ACCENT, tile: str = _TILE) -> None:
    """Draw the app mark: a steaming coffee cup with a little clock on it.

    Coffee + time — the app tracks how a substance (often caffeine) rises and
    falls over the clock. Pure QPainter so it scales crisply to any size.
    """
    s = float(size)
    p.setRenderHint(QPainter.Antialiasing)

    # Rounded dark tile.
    p.setBrush(QBrush(QColor(tile)))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(s * 0.03, s * 0.03, s * 0.94, s * 0.94), s * 0.22, s * 0.22)

    acc = QColor(accent)

    # Steam: two soft wavy wisps rising from the cup.
    steam = QPen(QColor(_STEAM))
    steam.setWidthF(s * 0.045)
    steam.setCapStyle(Qt.RoundCap)
    p.setPen(steam)
    p.setBrush(Qt.NoBrush)
    for x0 in (0.42, 0.55):
        path = QPainterPath(QPointF(s * x0, s * 0.42))
        path.cubicTo(s * (x0 + 0.06), s * 0.36, s * (x0 - 0.06), s * 0.31, s * x0, s * 0.25)
        p.drawPath(path)

    # Cup body: a rounded trapezoid (wider at the rim).
    cup = QPainterPath()
    cup.moveTo(s * 0.30, s * 0.46)
    cup.lineTo(s * 0.62, s * 0.46)
    cup.lineTo(s * 0.585, s * 0.70)
    cup.quadTo(s * 0.575, s * 0.745, s * 0.535, s * 0.745)
    cup.lineTo(s * 0.385, s * 0.745)
    cup.quadTo(s * 0.345, s * 0.745, s * 0.335, s * 0.70)
    cup.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(acc))
    p.drawPath(cup)

    # Handle: a C-shaped stroke on the right of the cup.
    handle = QPen(acc)
    handle.setWidthF(s * 0.055)
    handle.setCapStyle(Qt.RoundCap)
    p.setPen(handle)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(s * 0.585, s * 0.47, s * 0.16, s * 0.17), -72 * 16, 144 * 16)

    # Saucer line under the cup.
    p.drawLine(QPointF(s * 0.30, s * 0.78), QPointF(s * 0.62, s * 0.78))

    # Clock face on the cup: dark disc, accent rim, two hands.
    cx, cy, r = s * 0.46, s * 0.585, s * 0.115
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(tile)))
    p.drawEllipse(QPointF(cx, cy), r, r)
    rim = QPen(acc)
    rim.setWidthF(s * 0.022)
    p.setPen(rim)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), r, r)

    hands = QPen(acc)
    hands.setWidthF(s * 0.03)
    hands.setCapStyle(Qt.RoundCap)
    p.setPen(hands)
    # Hour hand up-left, minute hand up-right (classic readable pose).
    p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.55 * math.cos(math.radians(122)),
                                        cy - r * 0.55 * math.sin(math.radians(122))))
    p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.80 * math.cos(math.radians(58)),
                                        cy - r * 0.80 * math.sin(math.radians(58))))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(acc))
    p.drawEllipse(QPointF(cx, cy), s * 0.018, s * 0.018)


def make_app_icon(accent: str = _ACCENT, size: int = 64) -> QIcon:
    """The application icon: a steaming coffee cup with a clock, on a dark tile."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    _paint_icon(p, size, accent)
    p.end()
    return QIcon(pm)


class AppTray(QSystemTrayIcon):
    def __init__(self, icon: QIcon, *, on_show, on_show_widget, on_hide_widget, on_toggle_pin,
                 on_settings, on_quit, parent=None):
        super().__init__(icon, parent)
        self.setToolTip("PK Tracker")
        menu = QMenu()
        menu.addAction("Show dashboard", on_show)
        menu.addAction("Show / find widget", on_show_widget)
        menu.addAction("Hide widget", on_hide_widget)
        menu.addAction("Pin / float widget", on_toggle_pin)
        menu.addSeparator()
        menu.addAction("Settings…", on_settings)
        menu.addAction("Quit", on_quit)
        self.setContextMenu(menu)
        self.activated.connect(lambda reason: on_show() if reason == QSystemTrayIcon.Trigger else None)
