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

import numpy as np
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..controller import SLEEP_SENSITIVITY_MG, now_utc
from ..core.engine import Dose
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
        self._sleep_cutoff_at = None      # last computed coffee curfew, for the timing check
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
        self.widget = FloatingWidget(
            controller, self.active_sid,
            on_change=self.refresh_all, on_close=self._on_widget_hidden,
        )
        self.tray = AppTray(
            self.icon, on_show=self.show_dashboard,
            on_show_widget=self.show_widget, on_hide_widget=self.hide_widget,
            on_toggle_pin=self.toggle_widget_pin,
            on_settings=self._open_settings, on_quit=self.quit_app, parent=self,
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

        self._sync_substance_widgets()
        self.refresh_all()

        # Show the floating widget automatically unless the user hid it last time
        # (default on, so it appears on first run instead of having to be summoned).
        # ui_widget_enabled (new key, default on) is the persistent show/hide. The
        # old ui_widget_visible key is intentionally not read: the ✕ button used to
        # write it to "0", which could leave the widget stuck hidden across upgrades.
        if self.controller.get_setting("ui_widget_enabled", "1") == "1":
            self.widget.show()
            self.widget.refresh()
        if hasattr(self, "widget_toggle"):
            self.widget_toggle.setChecked(self.widget.isVisible())

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
        self.mins_ago.setSingleStep(15)
        self.mins_ago.setKeyboardTracking(False)
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
        undo_btn = QPushButton("↩ Undo last")
        undo_btn.setToolTip("Remove the most recently logged dose")
        undo_btn.clicked.connect(self._undo_last_dose)
        hrow.addWidget(edit_btn)
        hrow.addWidget(del_btn)
        hrow.addWidget(undo_btn)
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
        self.sim_chk = QCheckBox("Sim dose")
        self.sim_chk.setToolTip("Preview a hypothetical dose without logging it")
        self.sim_chk.stateChanged.connect(self._redraw_plot)
        controls.addWidget(self.sim_chk)
        self.sim_amount = QSpinBox()
        self.sim_amount.setRange(1, 1000)
        self.sim_amount.setSingleStep(10)
        self.sim_amount.setSuffix(" mg")
        self.sim_amount.setValue(90)
        self.sim_amount.valueChanged.connect(self._redraw_plot)
        controls.addWidget(self.sim_amount)
        self.sim_in_label = QLabel("in")
        controls.addWidget(self.sim_in_label)
        self.sim_in_min = QSpinBox()
        self.sim_in_min.setRange(0, 24 * 60)
        self.sim_in_min.setSingleStep(15)
        self.sim_in_min.setKeyboardTracking(False)
        self.sim_in_min.setSuffix(" min")
        self.sim_in_min.setValue(60)
        self.sim_in_min.valueChanged.connect(self._redraw_plot)
        controls.addWidget(self.sim_in_min)
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
        for r, key in enumerate(["Blood level", "Since last", "Projected peak", "Effect", "Today"]):
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

        # Sleep cutoff readout. The method (mg / sensitivity / hours) and bedtime
        # are configured in Settings → Sleep cutoff; this just shows the answer.
        self.sleep_panel = QWidget()
        sv = QVBoxLayout(self.sleep_panel)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(self._h2("Sleep cutoff"))

        self.sleep_headline = QLabel("—")
        self.sleep_headline.setObjectName("H2")
        self.sleep_headline.setStyleSheet(f"color: {COLORS['accent']};")
        self.sleep_headline.setWordWrap(True)
        sv.addWidget(self.sleep_headline)

        self.sleep_result = QLabel("—")
        self.sleep_result.setObjectName("Sub")
        self.sleep_result.setWordWrap(True)
        sv.addWidget(self.sleep_result)

        self.sleep_config = QLabel("")
        self.sleep_config.setObjectName("Muted")
        self.sleep_config.setWordWrap(True)
        sv.addWidget(self.sleep_config)
        v.addWidget(self.sleep_panel)

        # Perfect timing (caffeine): when to dose so it peaks at a target moment.
        self.timing_panel = QWidget()
        pv = QVBoxLayout(self.timing_panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(self._h2("🎯 Perfect timing"))
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Be sharp at"))
        self.timing_time = QTimeEdit()
        self.timing_time.setDisplayFormat("HH:mm")
        th, tm = (int(x) for x in self.controller.get_setting("ui_timing_target", "18:00").split(":"))
        self.timing_time.setTime(QTime(th, tm))
        self.timing_time.timeChanged.connect(self._on_timing_changed)
        prow.addWidget(self.timing_time)
        self.timing_mg = QSpinBox()
        self.timing_mg.setRange(10, 400)
        self.timing_mg.setSingleStep(10)
        self.timing_mg.setSuffix(" mg")
        self.timing_mg.setValue(int(float(self.controller.get_setting("ui_timing_mg", "90"))))
        self.timing_mg.valueChanged.connect(self._on_timing_changed)
        prow.addWidget(self.timing_mg)
        prow.addStretch(1)
        pv.addLayout(prow)
        self.timing_headline = QLabel("—")
        self.timing_headline.setObjectName("H2")
        self.timing_headline.setStyleSheet(f"color: {COLORS['accent']};")
        self.timing_headline.setWordWrap(True)
        pv.addWidget(self.timing_headline)
        self.timing_note = QLabel("")
        self.timing_note.setObjectName("Muted")
        self.timing_note.setWordWrap(True)
        pv.addWidget(self.timing_note)
        v.addWidget(self.timing_panel)

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

        bottom = QHBoxLayout()
        self.widget_toggle = QToolButton()
        self.widget_toggle.setText("Widget")
        self.widget_toggle.setCheckable(True)
        self.widget_toggle.setToolTip("Show/hide the floating widget. Pin/float mode lives in Settings.")
        self.widget_toggle.clicked.connect(lambda checked: self.set_widget_visible(bool(checked)))
        bottom.addWidget(self.widget_toggle)
        settings_btn = QPushButton("Settings…")
        settings_btn.clicked.connect(self._open_settings)
        bottom.addWidget(settings_btn, 1)
        v.addLayout(bottom)
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
        self.sim_amount.setSuffix(f" {sub.unit}")
        # Seed the custom field with a representative amount for this substance so
        # it is never an absurd default (e.g. 90 g of ethanol = ~7 drinks).
        if sub.presets:
            self.custom_amount.setValue(sub.presets[0].amount)
            self.sim_amount.setValue(int(sub.presets[0].amount))
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
        self.timing_panel.setVisible(sub.redose_eligible)
        self.alcohol_panel.setVisible(sub.is_alcohol)
        self.sim_chk.setVisible(sub.redose_eligible)
        self.sim_amount.setVisible(sub.redose_eligible)
        self.sim_in_label.setVisible(sub.redose_eligible)
        self.sim_in_min.setVisible(sub.redose_eligible)

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

    def _undo_last_dose(self):
        dose = self.controller.undo_last_dose(self.active_sid)
        if dose is None:
            self.log_feedback.setText("Nothing to undo.")
        else:
            sub = self.controller.substance(self.active_sid)
            self.log_feedback.setText(f"↩ Removed {dose.amount:g} {dose.unit} {sub.name.lower()}")
            self.refresh_all()
        self._feedback_timer.start(4000)

    def _export_data(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export dose log", "pk_tracker_doses.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if not path:
            return
        doses = self.controller.db.list_doses()
        if path.lower().endswith(".json"):
            import json
            payload = [
                {"substance": d.substance_id, "amount": d.amount, "unit": d.unit,
                 "taken_at": d.taken_at.isoformat(), "note": d.note}
                for d in doses
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        else:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["substance", "amount", "unit", "taken_at", "note"])
                for d in doses:
                    w.writerow([d.substance_id, d.amount, d.unit, d.taken_at.isoformat(), d.note])
        self.tray.showMessage("Export complete", f"Saved {len(doses)} doses to {path}", self.icon, 5000)

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
        hover_series = [("Level", conc_disp, f" {sub.conc_unit}")]
        if effect_pct is not None:
            hover_series.append(("Effect", effect_pct, "%"))
        y_norm_conc = conc_disp
        y_norm_eff = effect_pct

        if self.sim_chk.isChecked() and sub.redose_eligible:
            sim_taken = now + timedelta(minutes=self.sim_in_min.value())
            sim_dose = Dose(self.active_sid, float(self.sim_amount.value()), sub.unit, sim_taken)
            sim_tl = self.controller.timeline(self.active_sid, self.controller.doses(self.active_sid) + [sim_dose])
            sim_res = sim_tl.curve(start, end, 600)
            sim_conc = sim_res.concentration * sub.conc_scale
            sim_effect_pct = None
            if sim_res.effect is not None:
                sim_peak = max(tl.personal_peak_effect(now=now), sim_tl.personal_peak_effect(now=end))
                if sim_peak > 0:
                    sim_effect_pct = sim_res.effect / sim_peak * 100.0
            sim_color = COLORS["warn"]
            self.plot.add_simulation(sim_res.x, sim_conc, sim_effect_pct, sim_color)
            hover_series.append(("Sim level", sim_conc, f" {sub.conc_unit}"))
            if sim_effect_pct is not None:
                hover_series.append(("Sim effect", sim_effect_pct, "%"))
                y_norm_eff = sim_effect_pct if y_norm_eff is None else np.maximum(y_norm_eff, sim_effect_pct)
            y_norm_conc = np.maximum(y_norm_conc, sim_conc)

        self.plot.set_hover_data(res.x, hover_series)
        self.plot.set_normalized_y_ranges(y_norm_conc, y_norm_eff)
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
        over = self.controller.overload_info(self.active_sid, now)
        # Primary metric: concrete mass in the body (mg). Effect % is secondary.
        if r["body_mg"] is not None:
            self.big_value.setText(f"{r['body_mg']:.0f} mg")
            if over.has_threshold:
                self.big_caption.setText(f"{sub.name.lower()} in body · jitter zone ~{over.threshold_mg:.0f} mg")
            else:
                self.big_caption.setText(f"{sub.name.lower()} in body")
        else:
            self.big_value.setText(f"{r['conc_value']:.3f}")
            self.big_caption.setText(f"current level · {r['conc_unit']}")

        accent = sub.color
        if over.over:
            accent = COLORS["warn"]
        self.big_value.setStyleSheet(f"color: {accent};")

        self.readout_labels["Blood level"].setText(f"{r['conc_value']:.3f} {r['conc_unit']}")
        self.readout_labels["Since last"].setText(r["since_last"])
        self.readout_labels["Projected peak"].setText(r["peak_at"])
        if r["effect_pct"] is not None:
            self.readout_labels["Effect"].setText(f"{r['effect_pct']:.0f}% of recent peak")
        else:
            self.readout_labels["Effect"].setText("—")

        dm, gl = r["daily_mg"], r["daily_guideline"]
        today = self.readout_labels["Today"]
        if dm and dm > 0:
            today.setText(f"{dm:.0f} / {gl:.0f} mg" if gl else f"{dm:.0f} mg")
            col = ""
            if gl and dm >= gl:
                col = COLORS["danger"]
            elif gl and dm >= 0.8 * gl:
                col = COLORS["warn"]
            today.setStyleSheet(f"color: {col};" if col else "")
        else:
            today.setText("—")
            today.setStyleSheet("")

        action = status.next_action(self.controller, self.active_sid, now)
        if action is None:
            self.action_chip.setText("—")
            self.action_chip.setStyleSheet(f"color: {COLORS['subtext']};")
        else:
            label, value, color = action
            self.action_chip.setText(f"{label} {value}")
            self.action_chip.setStyleSheet(f"color: {color};")

        if sub.redose_eligible:
            self._refresh_sleep_cutoff(now)     # sets self._sleep_cutoff_at
            self._refresh_timing(now)
        if sub.is_alcohol:
            self._refresh_alcohol(now)

        self._check_redose_alert(now)

    _SLEEP_LEAD_MIN = 30   # how long before the cutoff to nudge "stop drinking"

    def _sleep_config(self):
        """Read the sleep-cutoff preferences (set in Settings) into a tuple."""
        c = self.controller
        mode = c.get_setting("ui_sleep_mode", "mg")
        hh, mm = (int(x) for x in c.get_setting("ui_bedtime", "23:00").split(":"))
        hours = float(c.get_setting("ui_sleep_hours", "8"))
        if mode == "preset":
            sens = c.get_setting("ui_sleep_sensitivity", "average")
            target_mg = SLEEP_SENSITIVITY_MG.get(sens, 50.0)
        else:
            target_mg = float(c.get_setting("ui_sleep_mg", "50"))
        return mode, (hh, mm), target_mg, hours

    def _refresh_sleep_cutoff(self, now):
        mode, (hh, mm), target_mg, hours = self._sleep_config()
        bedtime = self._next_datetime_for(now, hh, mm)
        res = self.controller.sleep_cutoff(
            self.active_sid, bedtime, mode=mode, target_mg=target_mg, hours=hours,
        )
        sub = self.controller.substance(self.active_sid)
        self._sleep_cutoff_at = res.cutoff_at    # for the perfect-timing sleep check
        self._render_sleep(res, sub, mode, bedtime, target_mg, hours)
        self._check_sleep_alert(now, bedtime, res, sub)

    def _refresh_timing(self, now):
        tt = self.timing_time.time()
        target = self._next_datetime_for(now, tt.hour(), tt.minute())
        amount = float(self.timing_mg.value())
        res = self.controller.perfect_timing(self.active_sid, target, amount, now=now)
        clk = status.fmt_clock
        if res.feasible and res.dose_time is not None:
            lead = res.dose_time - now
            self.timing_headline.setText(
                f"☕ Drink {amount:.0f} mg at {clk(res.dose_time)}  ·  in {status.fmt_delta(lead.total_seconds())}"
            )
            note = f"Peaks right at {clk(target)} (~{res.body_mg_at_target:.0f} mg in body then)."
            cutoff = self._sleep_cutoff_at
            if cutoff is not None:
                if res.dose_time <= cutoff:
                    note += "  ✓ within your sleep cutoff."
                else:
                    note += f"  ⚠ after your {clk(cutoff)} curfew — may cost you sleep."
            self.timing_note.setText(note)
        else:
            self.timing_headline.setText(f"☕ Drink {amount:.0f} mg now")
            self.timing_note.setText(
                f"{res.reason.capitalize()} — for a {clk(target)} peak you'd need to dose "
                f"~{res.tmax_h*60:.0f} min ahead."
            )

    def _on_timing_changed(self):
        t = self.timing_time.time()
        self.controller.set_setting("ui_timing_target", f"{t.hour():02d}:{t.minute():02d}")
        self.controller.set_setting("ui_timing_mg", str(self.timing_mg.value()))
        self._refresh_status()

    def _render_sleep(self, res, sub, mode, bedtime, target_mg, hours):
        clk = status.fmt_clock
        name = sub.name.lower()
        if mode == "hours":
            self.sleep_config.setText(f"Bedtime {clk(bedtime)} · stop {hours:.0f} h before · change in Settings")
        else:
            self.sleep_config.setText(f"Bedtime {clk(bedtime)} · target ≤ {target_mg:.0f} mg by bed · change in Settings")

        if res.feasible and res.cutoff_at is not None:
            self.sleep_headline.setText(f"☕ Latest {name}: {clk(res.cutoff_at)}")
            if mode == "hours":
                self.sleep_result.setText(f"A flat cutoff {hours:.0f} h before your {clk(bedtime)} bedtime.")
            else:
                existing = self.controller.concentration_to_mg(self.active_sid, res.existing_at_bedtime)
                self.sleep_result.setText(
                    f"Keeps {name} at or below ~{target_mg:.0f} mg in your body at "
                    f"{clk(bedtime)} (already logged → ~{existing:.0f} mg by then)."
                )
        else:
            self.sleep_headline.setText(f"☕ No more {name} before bed")
            if mode == "hours":
                self.sleep_result.setText(f"You're already within {hours:.0f} h of {clk(bedtime)}.")
            else:
                existing = self.controller.concentration_to_mg(self.active_sid, res.existing_at_bedtime)
                if existing > target_mg:
                    self.sleep_result.setText(
                        f"What you've already had projects to ~{existing:.0f} mg at {clk(bedtime)}, "
                        f"over your ~{target_mg:.0f} mg target."
                    )
                else:
                    self.sleep_result.setText(
                        f"Even a {name} now likely wouldn't clear to ~{target_mg:.0f} mg by "
                        f"{clk(bedtime)} — {res.reason}."
                    )

    def refresh_sleep_settings(self):
        """Called by the Settings dialog when any sleep preference changes."""
        self._sleep_notified.clear()
        self._refresh_status()

    def _check_sleep_alert(self, now, bedtime, res, sub):
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
                    f"(~{mins} min) for better sleep at {status.fmt_clock(bedtime)}.",
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
            self.widget.reveal()        # on-screen + raised, even in pinned mode
            self.widget.refresh()
        else:
            self.widget.hide()
        self.controller.set_setting("ui_widget_enabled", "1" if visible else "0")
        if hasattr(self, "widget_toggle"):
            self.widget_toggle.blockSignals(True)
            self.widget_toggle.setChecked(bool(visible))
            self.widget_toggle.blockSignals(False)

    def show_widget(self):
        self.set_widget_visible(True)

    def hide_widget(self):
        self.set_widget_visible(False)

    def toggle_widget(self):
        self.set_widget_visible(not self.widget.isVisible())

    def _on_widget_hidden(self):
        """The widget's ✕ dismisses it for the session (it reopens next launch).
        Nudge once so people know where to bring it back or turn it off for good."""
        self.tray.showMessage(
            "Widget hidden for now",
            "It'll be back next time you open PK Tracker. Bring it back now from the "
            "tray menu (Show / find widget), or turn it off for good in Settings.",
            self.icon, 6000,
        )

    def set_widget_pinned(self, pinned: bool):
        self.widget.set_pinned(pinned)
        if not self.widget.isVisible():           # switching mode also reveals it
            self.set_widget_visible(True)

    def set_widget_close_button(self, visible: bool):
        self.widget.set_close_button_visible(visible)

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
