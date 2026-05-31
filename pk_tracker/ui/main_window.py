"""The main dashboard window.

Left: substance selector, dose logging, and the dose history.
Centre: the timeline plot (blood level + effect, past solid, future dashed).
Right: status readout, sleep-cutoff solver, alcohol clearance, and access to
calibration / custom substances.

A QTimer fires every few seconds only to redraw and re-check alerts; it does
not advance any simulation. Closing the window hides to the system tray.
"""

from __future__ import annotations

from datetime import timedelta, timezone

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..controller import now_utc
from . import status
from .plots import TimelinePlot
from .settings import CalibrationDialog, CustomSubstanceDialog, SettingsDialog
from .theme import COLORS, apply_theme, mono_font
from .tray import AppTray, make_app_icon
from .widget import FloatingWidget

DISCLAIMER = (
    "Estimates from population-average pharmacokinetic models. Not medical "
    "advice; individual metabolism varies widely."
)


def _dot(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    from PySide6.QtGui import QPainter

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def _panel() -> QFrame:
    f = QFrame()
    f.setObjectName("Panel")
    return f


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("PK Tracker")
        self.resize(1180, 720)
        self.icon = make_app_icon()
        self.setWindowIcon(self.icon)

        subs = controller.ordered_substances()
        self.active_sid = subs[0].id if subs else None
        self._redose_notified: dict[str, bool] = {}
        self._sleep_notified: dict[str, bool] = {}
        self._quitting = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self._build_left(), 0)
        layout.addWidget(self._build_center(), 1)
        layout.addWidget(self._build_right(), 0)

        # Floating widget + tray.
        self.widget = FloatingWidget(controller, self.active_sid, on_change=self.refresh_all)
        self.tray = AppTray(
            self.icon, on_show=self.show_dashboard,
            on_toggle_widget=self.toggle_widget, on_toggle_pin=self.toggle_widget_pin,
            on_settings=self._open_settings, on_quit=self.quit_app, parent=self,
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

        self._sync_substance_widgets()
        self.refresh_all()

        # Show the floating widget automatically unless the user hid it last time
        # (default on, so it appears on first run instead of having to be summoned).
        if self.controller.get_setting("ui_widget_visible", "1") == "1":
            self.widget.show()
            self.widget.refresh()

        self.timer = QTimer(self)
        self.timer.setInterval(20_000)   # redraw + alert check only
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    # ----- layout: left ------------------------------------------------------
    def _build_left(self):
        panel = _panel()
        panel.setFixedWidth(280)
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        title = QLabel("PK Tracker")
        title.setObjectName("H1")
        v.addWidget(title)

        v.addWidget(self._h2("Substance"))
        self.sub_list = QListWidget()
        for sub in self.controller.ordered_substances():
            item = QListWidgetItem(_dot(sub.color), sub.name)
            item.setData(Qt.UserRole, sub.id)
            self.sub_list.addItem(item)
        self.sub_list.setCurrentRow(0)
        self.sub_list.currentItemChanged.connect(self._on_substance_changed)
        self.sub_list.setFixedHeight(150)
        v.addWidget(self.sub_list)

        v.addWidget(self._h2("Log a dose"))
        self.preset_box = QVBoxLayout()
        self.preset_box.setSpacing(6)
        v.addLayout(self.preset_box)

        custom = QHBoxLayout()
        self.custom_amount = QDoubleSpinBox()
        self.custom_amount.setRange(1, 2000)
        self.custom_amount.setValue(90)
        self.mins_ago = QSpinBox()
        self.mins_ago.setRange(0, 1440)
        self.mins_ago.setSuffix(" min ago")
        log_btn = QPushButton("Log")
        log_btn.setObjectName("Accent")
        log_btn.clicked.connect(self._log_custom)
        custom.addWidget(self.custom_amount)
        custom.addWidget(self.mins_ago)
        custom.addWidget(log_btn)
        v.addLayout(custom)
        self.custom_hint = QLabel("")
        self.custom_hint.setObjectName("Muted")
        self.custom_hint.setWordWrap(True)
        v.addWidget(self.custom_hint)

        # Confirmation that a dose was actually logged (otherwise small changes —
        # e.g. a single drink's low BAC — feel like "nothing happened").
        self.log_feedback = QLabel("")
        self.log_feedback.setObjectName("Ok")
        self.log_feedback.setWordWrap(True)
        v.addWidget(self.log_feedback)
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(lambda: self.log_feedback.setText(""))

        v.addWidget(self._h2("History"))
        self.history = QListWidget()
        self.history.itemDoubleClicked.connect(lambda _: self._edit_selected_dose())
        v.addWidget(self.history, 1)
        hrow = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_dose)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete_selected_dose)
        hrow.addWidget(edit_btn)
        hrow.addWidget(del_btn)
        v.addLayout(hrow)
        return panel

    # ----- layout: center ----------------------------------------------------
    def _build_center(self):
        panel = _panel()
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.plot = TimelinePlot()
        v.addWidget(self.plot, 1)

        # Legend so the two traces are never a mystery: which line is blood level,
        # which is effect, and what solid vs dashed means. Updated per substance.
        legend = QHBoxLayout()
        legend.setSpacing(14)
        self.legend_level = QLabel("Blood level")
        self.legend_effect = QLabel("Effect")
        self.legend_hint = QLabel("solid = so far   ·   dashed = projected")
        self.legend_hint.setObjectName("Muted")
        for w in (self.legend_level, self.legend_effect):
            w.setStyleSheet("font-size: 11px; font-weight: 600;")
        legend.addWidget(self.legend_level)
        legend.addWidget(self.legend_effect)
        legend.addStretch(1)
        legend.addWidget(self.legend_hint)
        v.addLayout(legend)

        controls = QHBoxLayout()
        self.overlay_chk = QCheckBox("Overlay all (effect %)")
        self.overlay_chk.stateChanged.connect(self._redraw_plot)
        controls.addWidget(self.overlay_chk)
        controls.addStretch(1)
        controls.addWidget(QLabel("Window"))
        self.window_box = QComboBox()
        self.window_box.addItems(["-2h / +12h", "-6h / +18h", "-1h / +8h", "-12h / +24h"])
        self.window_box.currentIndexChanged.connect(self._redraw_plot)
        controls.addWidget(self.window_box)
        v.addLayout(controls)

        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setObjectName("Disclaimer")
        disclaimer.setWordWrap(True)
        v.addWidget(disclaimer)
        return panel

    # ----- layout: right -----------------------------------------------------
    def _build_right(self):
        panel = _panel()
        panel.setFixedWidth(300)
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(12)

        # Status readout.
        v.addWidget(self._h2("Status"))
        self.status_name = QLabel("—")
        self.status_name.setObjectName("H1")
        v.addWidget(self.status_name)

        self.big_value = QLabel("—")
        self.big_value.setFont(mono_font(34, 700))
        v.addWidget(self.big_value)
        self.big_caption = QLabel("")
        self.big_caption.setObjectName("Sub")
        v.addWidget(self.big_caption)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.readout_labels = {}
        for r, key in enumerate(["Blood level", "Since last", "Projected peak", "In body"]):
            cap = QLabel(key)
            cap.setObjectName("Muted")
            val = QLabel("—")
            val.setFont(mono_font(12))
            grid.addWidget(cap, r, 0)
            grid.addWidget(val, r, 1, alignment=Qt.AlignRight)
            self.readout_labels[key] = val
        v.addLayout(grid)

        self.action_chip = QLabel("—")
        self.action_chip.setFont(mono_font(13, 600))
        v.addWidget(self.action_chip)

        # Sleep cutoff.
        self.sleep_panel = QWidget()
        sv = QVBoxLayout(self.sleep_panel)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(self._h2("Sleep cutoff"))
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Bedtime"))
        self.bedtime = QTimeEdit()
        self.bedtime.setDisplayFormat("HH:mm")
        saved = self.controller.get_setting("ui_bedtime", "23:00")
        hh, mm = (int(x) for x in saved.split(":"))
        self.bedtime.setTime(QTime(hh, mm))
        self.bedtime.timeChanged.connect(self._on_bedtime_changed)
        srow.addWidget(self.bedtime)
        srow.addStretch(1)
        sv.addLayout(srow)

        # How much caffeine you'll tolerate still in your blood at bedtime, as a
        # percentage of one dose's peak. Lower = stricter cutoff + earlier nudge.
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Target by bed"))
        self.sleep_target = QSpinBox()
        self.sleep_target.setRange(5, 90)
        self.sleep_target.setSuffix(" % of peak")
        self.sleep_target.setValue(int(self.controller.get_setting("ui_sleep_target_pct", "15")))
        self.sleep_target.setToolTip(
            "Caffeine left in your blood at bedtime, as % of one dose's peak. "
            "Lower is stricter. You'll get a tray nudge ~30 min before the cutoff."
        )
        self.sleep_target.valueChanged.connect(self._on_sleep_target_changed)
        trow.addWidget(self.sleep_target)
        trow.addStretch(1)
        sv.addLayout(trow)

        self.sleep_result = QLabel("—")
        self.sleep_result.setObjectName("Sub")
        self.sleep_result.setWordWrap(True)
        sv.addWidget(self.sleep_result)
        v.addWidget(self.sleep_panel)

        # Alcohol clearance.
        self.alcohol_panel = QWidget()
        av = QVBoxLayout(self.alcohol_panel)
        av.setContentsMargins(0, 0, 0, 0)
        av.addWidget(self._h2("Clearance"))
        self.alcohol_result = QLabel("—")
        self.alcohol_result.setObjectName("Sub")
        self.alcohol_result.setWordWrap(True)
        av.addWidget(self.alcohol_result)
        v.addWidget(self.alcohol_panel)

        v.addStretch(1)

        for label, slot in [
            ("Settings…", self._open_settings),
            ("Calibration…", self._open_calibration),
            ("New substance…", self._open_custom),
            ("About", self._about),
        ]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            v.addWidget(b)
        return panel

    def _h2(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("H2")
        return lbl

    # ----- substance switching ----------------------------------------------
    def _on_substance_changed(self, current, _prev):
        if current is None:
            return
        self.active_sid = current.data(Qt.UserRole)
        self.widget.set_active_substance(self.active_sid)
        self._sync_substance_widgets()
        self.refresh_all()

    def _sync_substance_widgets(self):
        sub = self.controller.substance(self.active_sid)
        # Rebuild preset buttons. setParent(None) unparents immediately so the
        # old buttons stop rendering at once (deleteLater alone is async and can
        # leave a stale button floating until the next event-loop pass).
        while self.preset_box.count():
            item = self.preset_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for preset in sub.presets:
            b = QPushButton(f"+ {preset.label}  ·  {preset.amount:g} {preset.unit}")
            b.clicked.connect(lambda _=False, p=preset: self._log_preset(p))
            self.preset_box.addWidget(b)
        self.custom_amount.setSuffix(f" {sub.unit}")
        # Seed the custom field with a representative amount for this substance so
        # it is never an absurd default (e.g. 90 g of ethanol = ~7 drinks).
        if sub.presets:
            self.custom_amount.setValue(sub.presets[0].amount)
        if sub.is_alcohol:
            self.custom_hint.setText(
                "Tip: tap a drink above to log it. The box below is grams of pure "
                "ethanol (one standard drink ≈ 14 g)."
            )
        else:
            self.custom_hint.setText("")
        # Show/hide contextual panels. The sleep-cutoff directive ("latest dose
        # at ...") is a dosing suggestion, so it is limited to redose-eligible
        # substances (caffeine, opted-in custom stimulants) — never prescription
        # meds or alcohol, which get no dosing prompts.
        self.sleep_panel.setVisible(sub.redose_eligible)
        self.alcohol_panel.setVisible(sub.is_alcohol)

    # ----- dose logging ------------------------------------------------------
    def _log_preset(self, preset):
        self.controller.log_dose(self.active_sid, preset.amount, preset.unit)
        self.refresh_all()
        self._flash_logged(preset.label)

    def _log_custom(self):
        sub = self.controller.substance(self.active_sid)
        taken = now_utc() - timedelta(minutes=self.mins_ago.value())
        amount = self.custom_amount.value()
        self.controller.log_dose(self.active_sid, amount, sub.unit, taken_at=taken)
        self.mins_ago.setValue(0)
        self.refresh_all()
        self._flash_logged(f"{amount:g} {sub.unit}")

    def _flash_logged(self, label):
        """Show a brief, self-clearing confirmation with the resulting level."""
        r = status.current_readout(self.controller, self.active_sid, now_utc())
        if r["effect_pct"] is not None:
            detail = f"effect {r['effect_pct']:.0f}%"
        else:
            detail = f"{r['conc_value']:.3f} {r['conc_unit']}"
        self.log_feedback.setText(f"✓ Logged {label}  ·  now {detail}")
        self._feedback_timer.start(5000)

    def _selected_dose(self):
        item = self.history.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _edit_selected_dose(self):
        dose = self._selected_dose()
        if dose is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit dose")
        form = QFormLayout(dlg)
        amount = QDoubleSpinBox()
        amount.setRange(0.1, 5000)
        amount.setValue(dose.amount)
        when = QDateTimeEdit()
        when.setDisplayFormat("yyyy-MM-dd HH:mm")
        when.setDateTime(dose.taken_at.astimezone())
        form.addRow("Amount", amount)
        form.addRow("Taken at", when)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.Accepted:
            local_dt = when.dateTime().toPython()
            if local_dt.tzinfo is None:
                local_dt = local_dt.astimezone()
            self.controller.update_dose(
                dose.id, amount=amount.value(), taken_at=local_dt.astimezone(timezone.utc)
            )
            self.refresh_all()

    def _delete_selected_dose(self):
        dose = self._selected_dose()
        if dose is None:
            return
        self.controller.delete_dose(dose.id)
        self.refresh_all()

    # ----- refresh / draw ----------------------------------------------------
    def refresh_all(self):
        self._refresh_history()
        self._redraw_plot()
        self._refresh_status()
        self.widget.refresh()

    def _refresh_history(self):
        self.history.clear()
        for dose in reversed(self.controller.doses(self.active_sid)):
            local = dose.taken_at.astimezone().strftime("%a %H:%M")
            item = QListWidgetItem(f"{local}   ·   {dose.amount:g} {dose.unit}")
            item.setData(Qt.UserRole, dose)
            self.history.addItem(item)

    def _window_hours(self):
        return {0: (2, 12), 1: (6, 18), 2: (1, 8), 3: (12, 24)}[self.window_box.currentIndex()]

    def _redraw_plot(self):
        now = now_utc()
        back_h, fwd_h = self._window_hours()
        start, end = now - timedelta(hours=back_h), now + timedelta(hours=fwd_h)

        self.plot.set_now(now.timestamp())
        self.plot.clear_curves()

        sub = self.controller.substance(self.active_sid)
        tl = self.controller.timeline(self.active_sid)
        res = tl.curve(start, end, 600)
        conc_disp = res.concentration * sub.conc_scale

        effect_pct = None
        if res.effect is not None:
            peak = tl.personal_peak_effect(now=now)
            if peak > 0:
                effect_pct = res.effect / peak * 100.0

        self.plot.add_substance(res.x, conc_disp, effect_pct, sub.color, primary=True)
        self.plot.set_left_label(sub.conc_unit)

        # Keep the legend in step with what is actually drawn.
        level_name = "BAC" if sub.is_alcohol else "Blood level"
        self.legend_level.setText(f"●  {level_name} ({sub.conc_unit})")
        self.legend_level.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {sub.color};")
        self.legend_effect.setVisible(effect_pct is not None)
        self.legend_effect.setText("●  Effect (% of recent peak)")
        self.legend_effect.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {COLORS['accent']};"
        )

        if sub.sleep_threshold is not None:
            self.plot.add_hline(sub.sleep_threshold * sub.conc_scale, COLORS["muted"], "sleep-safe")
        if sub.is_alcohol:
            self.plot.add_hline(self.controller.profile.legal_bac_limit, COLORS["warn"], "limit")

        if self.overlay_chk.isChecked():
            for other in self.controller.ordered_substances():
                if other.id == self.active_sid or other.ec50 is None:
                    continue
                otl = self.controller.timeline(other.id)
                if not otl.doses:
                    continue
                ores = otl.curve(start, end, 400)
                opeak = otl.personal_peak_effect(now=now)
                if ores.effect is not None and opeak > 0:
                    self.plot.add_overlay_effect(ores.x, ores.effect / opeak * 100.0, other.color)

        over = self.controller.overload_info(self.active_sid, now)
        if over.over:
            self.plot.add_banner("jitter zone", COLORS["warn"])

        self.plot.mark_now()
        self.plot.set_x_window(start.timestamp(), end.timestamp())

    def _refresh_status(self):
        now = now_utc()
        sub = self.controller.substance(self.active_sid)
        self.status_name.setText(sub.name)
        self.status_name.setStyleSheet(f"color: {sub.color};")

        r = status.current_readout(self.controller, self.active_sid, now)
        if r["effect_pct"] is not None:
            self.big_value.setText(f"{r['effect_pct']:.0f}%")
            self.big_caption.setText("effect · % of recent peak")
        else:
            self.big_value.setText(f"{r['conc_value']:.3f}")
            self.big_caption.setText(f"current level · {r['conc_unit']}")

        accent = sub.color
        over = self.controller.overload_info(self.active_sid, now)
        if over.over:
            accent = COLORS["warn"]
        self.big_value.setStyleSheet(f"color: {accent};")

        self.readout_labels["Blood level"].setText(f"{r['conc_value']:.3f} {r['conc_unit']}")
        self.readout_labels["Since last"].setText(r["since_last"])
        self.readout_labels["Projected peak"].setText(r["peak_at"])
        if over.has_threshold:
            self.readout_labels["In body"].setText(f"{over.body_amount_mg:.0f} / {over.threshold_mg:.0f} mg")
        else:
            self.readout_labels["In body"].setText("—")

        action = status.next_action(self.controller, self.active_sid, now)
        if action is None:
            self.action_chip.setText("—")
            self.action_chip.setStyleSheet(f"color: {COLORS['subtext']};")
        else:
            label, value, color = action
            self.action_chip.setText(f"{label} {value}")
            self.action_chip.setStyleSheet(f"color: {color};")

        if sub.redose_eligible:
            self._refresh_sleep_cutoff(now)
        if sub.is_alcohol:
            self._refresh_alcohol(now)

        self._check_redose_alert(now)

    _SLEEP_LEAD_MIN = 30   # how long before the cutoff to nudge "stop drinking"

    def _refresh_sleep_cutoff(self, now):
        bt = self.bedtime.time()
        bedtime = self._next_datetime_for(now, bt.hour(), bt.minute())
        pct = float(self.sleep_target.value())
        res = self.controller.sleep_cutoff(self.active_sid, bedtime, target_fraction=pct / 100.0)
        sub = self.controller.substance(self.active_sid)
        if res.feasible and res.cutoff_at is not None:
            self.sleep_result.setText(
                f"Latest {sub.name.lower()} dose: {status.fmt_clock(res.cutoff_at)} "
                f"to stay ≤ {pct:.0f}% (≈ {res.ceiling * sub.conc_scale:.2f} {sub.conc_unit}) "
                f"at {status.fmt_clock(bedtime)}."
            )
        else:
            self.sleep_result.setText(f"No safe dose before bedtime — {res.reason}.")
        self._check_sleep_alert(now, bedtime, res, sub, pct)

    def _on_sleep_target_changed(self):
        self.controller.set_setting("ui_sleep_target_pct", str(self.sleep_target.value()))
        self._sleep_notified.clear()    # new threshold ⇒ allow a fresh nudge
        self._refresh_status()

    def _check_sleep_alert(self, now, bedtime, res, sub, pct):
        """Nudge ~30 min before the latest-coffee time so you stop in advance."""
        sid = self.active_sid
        # Only nudge people who are actually drinking this substance.
        if not res.feasible or res.cutoff_at is None or not self.controller.doses(sid):
            self._sleep_notified[sid] = False
            return
        lead = timedelta(minutes=self._SLEEP_LEAD_MIN)
        if res.cutoff_at - lead <= now <= res.cutoff_at:
            if not self._sleep_notified.get(sid):
                mins = max(0, int((res.cutoff_at - now).total_seconds() // 60))
                self.tray.showMessage(
                    "Coffee curfew",
                    f"Last {sub.name.lower()} by {status.fmt_clock(res.cutoff_at)} "
                    f"(~{mins} min) to stay ≤ {pct:.0f}% at {status.fmt_clock(bedtime)}.",
                    self.icon, 8000,
                )
                self._sleep_notified[sid] = True
        elif now < res.cutoff_at - lead:
            self._sleep_notified[sid] = False   # reset for the next approach

    def _refresh_alcohol(self, now):
        pred = self.controller.alcohol_predictions(self.active_sid, now)
        if pred is None or pred.bac_now <= 0:
            self.alcohol_result.setText("BAC 0.000 g/dL — sober. Estimate, not a legal guarantee.")
            return
        lines = [f"BAC {pred.bac_now:.3f} g/dL."]
        if pred.over_limit:
            lines.append(f"Below {pred.legal_limit:.2f} limit ~ {status.fmt_clock(pred.time_to_limit)}.")
        lines.append(f"Sober (0.00) ~ {status.fmt_clock(pred.time_to_zero)}.")
        lines.append("Rough estimate — never use to decide whether to drive.")
        self.alcohol_result.setText("  ".join(lines))

    def _next_datetime_for(self, now, hour, minute):
        local_now = now.astimezone()
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    def _check_redose_alert(self, now):
        info = self.controller.redose_info(self.active_sid, now)
        if not info.eligible:
            return
        sid = self.active_sid
        if info.overdue:
            if not self._redose_notified.get(sid):
                sub = self.controller.substance(sid)
                self.tray.showMessage(
                    "Redose nudge",
                    f"{sub.name} effect at {info.current_percent:.0f}% — consider a maintenance dose.",
                    self.icon, 6000,
                )
                self._redose_notified[sid] = True
        else:
            self._redose_notified[sid] = False

    # ----- timer -------------------------------------------------------------
    def tick(self):
        self._redraw_plot()
        self._refresh_status()
        self.widget.refresh()

    # ----- dialogs / actions -------------------------------------------------
    def _open_calibration(self):
        if CalibrationDialog(self.controller, self).exec() == QDialog.Accepted:
            self.refresh_all()

    def _open_custom(self):
        dlg = CustomSubstanceDialog(self.controller, self)
        if dlg.exec() == QDialog.Accepted:
            self._reload_substance_list()

    def _reload_substance_list(self):
        self.sub_list.blockSignals(True)
        self.sub_list.clear()
        for sub in self.controller.ordered_substances():
            item = QListWidgetItem(_dot(sub.color), sub.name)
            item.setData(Qt.UserRole, sub.id)
            self.sub_list.addItem(item)
            if sub.id == self.active_sid:
                self.sub_list.setCurrentItem(item)
        self.sub_list.blockSignals(False)
        self.refresh_all()

    def _on_bedtime_changed(self):
        t = self.bedtime.time()
        self.controller.set_setting("ui_bedtime", f"{t.hour():02d}:{t.minute():02d}")
        self._refresh_status()

    def _about(self):
        QMessageBox.information(
            self, "About PK Tracker",
            "PK Tracker models how substances rise and fall in the body using "
            "population-average pharmacokinetic models.\n\n"
            "It is NOT medical advice. Individual metabolism varies widely.\n\n"
            "• Methylphenidate and other prescription medicines are visualised "
            "only — dosing is your prescriber's decision; this tool never "
            "recommends doses.\n"
            "• Alcohol BAC and sober-time figures are rough estimates and must "
            "not be used to decide whether it is safe or legal to drive.",
        )

    # ----- tray / lifecycle --------------------------------------------------
    def show_dashboard(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def set_widget_visible(self, visible: bool):
        if visible:
            self.widget.show()
            self.widget.refresh()
        else:
            self.widget.hide()
        self.controller.set_setting("ui_widget_visible", "1" if visible else "0")

    def toggle_widget(self):
        self.set_widget_visible(not self.widget.isVisible())

    def set_widget_pinned(self, pinned: bool):
        self.widget.set_pinned(pinned)
        if not self.widget.isVisible():           # switching mode also reveals it
            self.set_widget_visible(True)

    def toggle_widget_pin(self):
        self.set_widget_pinned(not self.widget.pinned)

    def set_theme(self, mode: str):
        apply_theme(QApplication.instance(), mode)
        self.controller.set_setting("ui_theme", mode)
        # Refresh chrome that caches colours at construction time.
        self.plot.apply_theme()
        self.widget.spark.apply_theme()
        self.refresh_all()

    def _open_settings(self):
        SettingsDialog(self.controller, self, self).exec()

    def quit_app(self):
        self._quitting = True
        self.widget.close()
        self.controller.db.close()
        QApplication.instance().quit()

    def closeEvent(self, e):
        if self._quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        self.tray.showMessage(
            "PK Tracker", "Still running in the tray. Right-click the tray icon to quit.",
            self.icon, 3000,
        )
