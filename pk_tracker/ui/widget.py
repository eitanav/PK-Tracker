"""The floating widget: a small frameless always-on-top status panel.

Shows the active substance's current effect at a glance, a thin live sparkline,
a "+ dose" button, and the next suggested action. Draggable anywhere on its
body; remembers its screen position between launches.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..controller import now_utc
from . import status
from .plots import Sparkline
from .theme import COLORS, mono_font

_POS_KEY = "ui_widget_pos"
_PINNED_KEY = "ui_widget_pinned"


class FloatingWidget(QWidget):
    def __init__(self, controller, sid: str, on_change=None):
        super().__init__(None)
        self.controller = controller
        self.sid = sid
        self.on_change = on_change or (lambda: None)
        self._drag_offset: QPoint | None = None

        # "Pinned to desktop" sits the widget at the desktop level (behind other
        # windows) like a gadget; otherwise it floats on top of everything.
        # Pinned is the default so it feels like part of the desktop, not a popup.
        self.pinned = self.controller.get_setting(_PINNED_KEY, "1") == "1"
        self._apply_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Never steal focus from the user's active window when (re)shown.
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(250, 168)

        panel = QFrame(self)
        panel.setObjectName("Panel")
        panel.setGeometry(0, 0, 250, 168)
        root = QVBoxLayout(panel)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.name_label = QLabel()
        self.name_label.setObjectName("H2")
        top.addWidget(self.name_label)
        top.addStretch(1)
        self.badge = QLabel()
        self.badge.setObjectName("Muted")
        top.addWidget(self.badge)
        root.addLayout(top)

        self.value_label = QLabel("—")
        self.value_label.setFont(mono_font(30, 600))
        root.addWidget(self.value_label)

        self.spark = Sparkline()
        self.spark.setFixedHeight(40)
        root.addWidget(self.spark)

        bottom = QHBoxLayout()
        self.action_label = QLabel("—")
        self.action_label.setObjectName("Sub")
        bottom.addWidget(self.action_label)
        bottom.addStretch(1)

        self.dose_btn = QToolButton()
        self.dose_btn.setText("+ dose")
        self.dose_btn.setPopupMode(QToolButton.InstantPopup)
        self.dose_btn.setCursor(Qt.PointingHandCursor)
        bottom.addWidget(self.dose_btn)
        root.addLayout(bottom)

        self._restore_position()
        self.set_active_substance(sid)

    # ----- window mode (float-on-top vs pinned-to-desktop) -------------------
    def _apply_window_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.pinned:
            # Desktop-gadget style: keep it below normal windows and out of the
            # focus chain so it behaves like part of the desktop, not a popup.
            flags |= Qt.WindowStaysOnBottomHint | Qt.WindowDoesNotAcceptFocus
        else:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_pinned(self, pinned: bool):
        """Switch between float-on-top and pinned-to-desktop, keeping it visible."""
        self.pinned = pinned
        self.controller.set_setting(_PINNED_KEY, "1" if pinned else "0")
        was_visible = self.isVisible()
        self._apply_window_flags()      # changing flags requires re-showing
        self._restore_position()
        if was_visible:
            self.show()                 # showEvent sinks it to the bottom if pinned

    def showEvent(self, e):
        super().showEvent(e)
        # The stays-on-bottom hint alone is unreliable on some Windows setups, so
        # actively push the widget beneath other windows each time it appears.
        if self.pinned:
            self.lower()

    # ----- state -------------------------------------------------------------
    def set_active_substance(self, sid: str):
        self.sid = sid
        self._rebuild_dose_menu()
        self.refresh()

    def _rebuild_dose_menu(self):
        sub = self.controller.substance(self.sid)
        menu = QMenu(self.dose_btn)
        for preset in sub.presets:
            menu.addAction(
                f"{preset.label}  ({preset.amount:g} {preset.unit})",
                lambda p=preset: self._log(p.amount, p.unit),
            )
        if not sub.presets:
            menu.addAction("Log 1 unit", lambda: self._log(1.0, sub.unit))
        self.dose_btn.setMenu(menu)

    def _log(self, amount, unit):
        self.controller.log_dose(self.sid, amount, unit)
        self.on_change()
        self.refresh()

    # ----- refresh -----------------------------------------------------------
    def refresh(self):
        now = now_utc()
        sub = self.controller.substance(self.sid)
        tl = self.controller.timeline(self.sid)
        accent = sub.color

        over = self.controller.overload_info(self.sid, now)
        if over.over:
            accent = COLORS["warn"]

        self.name_label.setText(sub.name)
        readout = status.current_readout(self.controller, self.sid, now)

        if readout["effect_pct"] is not None:
            self.value_label.setText(f"{readout['effect_pct']:.0f}%")
            self.badge.setText("effect")
        else:
            self.value_label.setText(f"{readout['conc_value']:.2f}")
            self.badge.setText(readout["conc_unit"])
        self.value_label.setStyleSheet(f"color: {accent};")

        # Sparkline over a short forward window.
        res = tl.curve(now - timedelta(hours=1), now + timedelta(hours=8), 220)
        if res.effect is not None:
            peak = tl.personal_peak_effect(now=now)
            y = res.effect / peak * 100 if peak > 0 else res.effect * 0
        else:
            y = res.concentration * sub.conc_scale
        self.spark.set_now(now.timestamp())
        self.spark.update_trace(res.x, np.asarray(y), accent)

        action = status.next_action(self.controller, self.sid, now)
        if action is None:
            self.action_label.setText("no active dose" if not readout["has_doses"] else "—")
            self.action_label.setStyleSheet(f"color: {COLORS['subtext']};")
        else:
            label, value, color = action
            self.action_label.setText(f"{label} {value}")
            self.action_label.setStyleSheet(f"color: {color};")

    # ----- right-click menu (mode + hide) ------------------------------------
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        if self.pinned:
            menu.addAction("Float on top", lambda: self.set_pinned(False))
        else:
            menu.addAction("Pin to desktop", lambda: self.set_pinned(True))
        menu.addSeparator()
        menu.addAction("Hide widget", self.hide)
        menu.exec(e.globalPos())

    # ----- dragging + position persistence -----------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        self._save_position()

    def _save_position(self):
        self.controller.set_setting(_POS_KEY, f"{self.x()},{self.y()}")

    def _restore_position(self):
        raw = self.controller.get_setting(_POS_KEY)
        if raw:
            try:
                x, y = (int(v) for v in raw.split(","))
                self.move(x, y)
                return
            except ValueError:
                pass
        self.move(80, 80)

    def closeEvent(self, e):
        self._save_position()
        super().closeEvent(e)
