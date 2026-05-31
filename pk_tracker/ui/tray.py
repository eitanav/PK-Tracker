"""System tray icon and menu, plus a generated application icon.

Closing the main window hides to the tray instead of quitting; the tray menu
brings the dashboard back, toggles the floating widget, or quits for real.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import COLORS


def make_app_icon(accent: str = COLORS["accent"], size: int = 64) -> QIcon:
    """Draw a simple 'rise and fall' curve mark on a dark rounded tile."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Rounded dark tile.
    p.setBrush(QBrush(QColor(COLORS["panel"])))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)

    # A little Bateman-ish hump.
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor(accent))
    grad.setColorAt(1.0, QColor(COLORS["panel"]))
    pen = p.pen()
    pen.setColor(QColor(accent))
    pen.setWidthF(size * 0.07)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)

    pts = []
    import math

    for i in range(0, 101):
        t = i / 100.0
        # rise then exponential-ish decay, normalised to the tile
        val = (1 - math.exp(-6 * t)) * math.exp(-1.7 * t)
        x = size * (0.16 + 0.68 * t)
        y = size * (0.74 - 0.50 * val / 0.62)
        pts.append(QPointF(x, y))
    for a, b in zip(pts, pts[1:]):
        p.drawLine(a, b)

    p.end()
    return QIcon(pm)


class AppTray(QSystemTrayIcon):
    def __init__(self, icon: QIcon, *, on_show, on_toggle_widget, on_toggle_pin, on_quit, parent=None):
        super().__init__(icon, parent)
        self.setToolTip("PK Tracker")
        menu = QMenu()
        menu.addAction("Show dashboard", on_show)
        menu.addAction("Toggle widget", on_toggle_widget)
        menu.addAction("Pin widget to desktop", on_toggle_pin)
        menu.addSeparator()
        menu.addAction("Quit", on_quit)
        self.setContextMenu(menu)
        self.activated.connect(lambda reason: on_show() if reason == QSystemTrayIcon.Trigger else None)
