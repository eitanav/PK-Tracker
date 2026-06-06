"""The floating widget: a small frameless always-on-top status panel.

Shows the active substance's current mass in the body (mg) at a glance, with the
effect % as a secondary badge, a thin live sparkline, a "+ dose" button, and the
next suggested action. Draggable anywhere on its body; remembers its screen
position between launches.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication
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
_CLOSE_BTN_KEY = "ui_widget_close_btn"


class FloatingWidget(QWidget):
    def __init__(self, controller, sid: str, on_change=None, on_close=None):
        super().__init__(None)
        self.controller = controller
        self.sid = sid
        self.on_change = on_change or (lambda: None)
        self._on_close_cb = on_close or (lambda: None)
        self._drag_offset: QPoint | None = None

        # "Pinned to desktop" sits the widget at the desktop level (behind other
        # windows) like a gadget; otherwise it floats on top of everything.
        # Pinned is the default so it feels like part of the desktop, not a popup.
        self.pinned = self.controller.get_setting(_PINNED_KEY, "1") == "1"
        self._apply_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Never steal focus from the user's active window when (re)shown.
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(250, 196)

        panel = QFrame(self)
        panel.setObjectName("Panel")
        panel.setGeometry(0, 0, 250, 196)
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
        # A small close (✕) button to hide the widget directly. Optional — it can
        # be turned off in Settings for a cleaner, gadget-like look.
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setObjectName("WidgetClose")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("Hide widget (bring it back from Settings or the tray)")
        self.close_btn.clicked.connect(self._on_close)
        top.addWidget(self.close_btn)
        root.addLayout(top)

        self.value_label = QLabel("—")
        self.value_label.setFont(mono_font(30, 600))
        root.addWidget(self.value_label)

        info = QHBoxLayout()
        self.today_label = QLabel("")           # daily total vs guideline
        self.today_label.setObjectName("Muted")
        info.addWidget(self.today_label)
        info.addStretch(1)
        self.curfew_label = QLabel("")          # latest coffee for sleep
        self.curfew_label.setObjectName("Muted")
        info.addWidget(self.curfew_label)
        root.addLayout(info)

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

        self.close_btn.setVisible(self.controller.get_setting(_CLOSE_BTN_KEY, "1") == "1")
        self._restore_position()
        self.set_active_substance(sid)

    # ----- close button ------------------------------------------------------
    def _on_close(self):
        """Dismiss the widget for now. It reopens next launch; to turn it off for
        good, use Settings or the tray. (Session-only so the ✕ can never 'lose'
        the widget permanently in a way that's hard to undo.)"""
        self._save_position()
        self.hide()
        self._on_close_cb()

    def set_close_button_visible(self, visible: bool):
        self.close_btn.setVisible(visible)
        self.controller.set_setting(_CLOSE_BTN_KEY, "1" if visible else "0")

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
        # actively push the widget beneath other windows each time it appears —
        # except when the user explicitly asked to see it via reveal().
        if self.pinned and not getattr(self, "_suppress_lower", False):
            self.lower()

    def reveal(self):
        """Bring the widget somewhere the user can definitely see it: on a visible
        screen and raised to the front, even in pinned (stays-on-bottom) mode.
        Used by the dashboard button, tray toggle, and Settings."""
        self._restore_position()          # re-clamps onto a connected screen
        self._suppress_lower = True
        self.show()
        self._suppress_lower = False
        self.raise_()
        if not self.pinned:          # pinned widget refuses focus; raise_ is enough
            self.activateWindow()

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

        # Primary metric is the concrete mass in the body (mg); effect % is the
        # secondary badge. Alcohol (no body-mass concept) falls back to its level.
        if readout["body_mg"] is not None:
            self.value_label.setText(f"{readout['body_mg']:.0f} mg")
            if readout["effect_pct"] is not None:
                self.badge.setText(f"{readout['effect_pct']:.0f}% effect")
            else:
                self.badge.setText("in body")
        else:
            self.value_label.setText(f"{readout['conc_value']:.2f}")
            self.badge.setText(readout["conc_unit"])
        self.value_label.setStyleSheet(f"color: {accent};")

        # Daily total vs guideline (left) + latest-coffee curfew (right).
        dm, gl = readout["daily_mg"], readout["daily_guideline"]
        if dm and dm > 0:
            self.today_label.setText(f"Today {dm:.0f}/{gl:.0f} mg" if gl else f"Today {dm:.0f} mg")
            if gl and dm >= gl:
                self.today_label.setStyleSheet(f"color: {COLORS['danger']};")
            elif gl and dm >= 0.8 * gl:
                self.today_label.setStyleSheet(f"color: {COLORS['warn']};")
            else:
                self.today_label.setStyleSheet("")
        else:
            self.today_label.setText("")
            self.today_label.setStyleSheet("")

        if sub.redose_eligible:
            sc = self.controller.sleep_cutoff_from_settings(self.sid, now)
            clk = status.fmt_clock
            self.curfew_label.setText(f"☕ {clk(sc.cutoff_at)}" if (sc.feasible and sc.cutoff_at) else "☕ —")
            self.curfew_label.setToolTip("Latest coffee to protect your sleep")
        else:
            self.curfew_label.setText("")

        # Sparkline tracks the blood level (∝ mg in body), matching the headline.
        res = tl.curve(now - timedelta(hours=1), now + timedelta(hours=8), 220)
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
                self.move(self._on_screen_point(x, y))
                return
            except ValueError:
                pass
        self.move(self._default_point())

    def _default_point(self) -> QPoint:
        ag = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(ag.right() - (self.width() or 250) - 24, ag.top() + 60)

    def _on_screen_point(self, x: int, y: int) -> QPoint:
        """Keep the saved position visible: nudge it fully inside whatever screen
        it lands on, or fall back to a default corner if it is off every screen
        (e.g. a monitor that is no longer connected). This is what stops a stale
        off-screen position from making the widget 'not open' at all."""
        w, h = self.width() or 250, self.height() or 168
        rect = QRect(x, y, w, h)
        for s in QGuiApplication.screens():
            ag = s.availableGeometry()
            if ag.intersects(rect):
                nx = min(max(x, ag.left()), ag.right() - w)
                ny = min(max(y, ag.top()), ag.bottom() - h)
                return QPoint(nx, ny)
        return self._default_point()

    def closeEvent(self, e):
        self._save_position()
        super().closeEvent(e)
