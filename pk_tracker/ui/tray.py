"""System tray icon and menu.

Closing the main window hides to the tray instead of quitting; the tray menu
brings the dashboard back, finds/hides the floating widget, or quits for real.
The icon itself is the brand mark — see :mod:`pk_tracker.ui.brand`.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


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
