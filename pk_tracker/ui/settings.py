"""Calibration and custom-substance dialogs.

Calibration is per-user and entirely pharmacodynamic plus body parameters: it
never edits a substance's kinetic constants. The guided flow is transparent —
it maps a couple of plain questions to a starting tolerance factor and shows
the user the resulting number.

The custom builder adds a new one-compartment substance to the library (DB +
JSON) without any code change. Only caffeine-like custom stimulants may opt into
redose nudges; that checkbox is the gate.
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.engine import UserProfile
from ..core.substances import Preset, Substance
from .theme import COLORS


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "substance"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class CalibrationDialog(QDialog):
    """Body parameters + per-substance tolerance, with a guided helper."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Calibration")
        self.setMinimumWidth(440)
        profile = controller.profile

        root = QVBoxLayout(self)

        body = QFormLayout()
        self.mass = QDoubleSpinBox()
        self.mass.setRange(30, 250)
        self.mass.setSuffix(" kg")
        self.mass.setValue(profile.body_mass_kg)
        body.addRow("Body mass", self.mass)

        self.sex = QComboBox()
        self.sex.addItems(["male", "female"])
        self.sex.setCurrentText(profile.sex)
        body.addRow("Sex (alcohol r)", self.sex)

        self.beta = QDoubleSpinBox()
        self.beta.setRange(0.008, 0.030)
        self.beta.setSingleStep(0.001)
        self.beta.setDecimals(3)
        self.beta.setSuffix(" g/dL/h")
        self.beta.setValue(profile.beta)
        body.addRow("Alcohol elimination", self.beta)

        self.limit = QDoubleSpinBox()
        self.limit.setRange(0.0, 0.15)
        self.limit.setSingleStep(0.01)
        self.limit.setDecimals(2)
        self.limit.setSuffix(" g/dL")
        self.limit.setValue(profile.legal_bac_limit)
        body.addRow("Driving limit (estimate)", self.limit)

        self.ramp = QDoubleSpinBox()
        self.ramp.setRange(0, 90)
        self.ramp.setSingleStep(5)
        self.ramp.setSuffix(" min")
        self.ramp.setValue(profile.alcohol_ramp_min)
        self.ramp.setToolTip("Linear alcohol absorption window. 0 = instantaneous (default).")
        body.addRow("Alcohol absorption ramp", self.ramp)
        root.addLayout(body)

        # Per-substance tolerance.
        root.addWidget(self._h2("Tolerance  (0.5 sensitive · 1.0 baseline · 1.5 habituated)"))
        self.tol_spins: dict[str, QDoubleSpinBox] = {}
        tol_form = QFormLayout()
        for sub in controller.ordered_substances():
            if sub.ec50 is None:
                continue
            spin = QDoubleSpinBox()
            spin.setRange(0.5, 1.5)
            spin.setSingleStep(0.05)
            spin.setValue(profile.tolerance_for(sub.id))
            self.tol_spins[sub.id] = spin
            tol_form.addRow(sub.name, spin)
        root.addLayout(tol_form)

        # Guided helper (caffeine).
        root.addWidget(self._h2("Guided (caffeine)"))
        guided = QFormLayout()
        self.daily = QComboBox()
        self.daily.addItems(["none", "1-2 cups", "3-4 cups", "5+ cups"])
        guided.addRow("Typical daily intake", self.daily)
        self.sensitivity = QComboBox()
        self.sensitivity.addItems(["hits me hard", "normal", "barely notice"])
        self.sensitivity.setCurrentText("normal")
        guided.addRow("A coffee affects me", self.sensitivity)
        row = QHBoxLayout()
        apply_btn = QPushButton("Compute → caffeine tolerance")
        apply_btn.clicked.connect(self._apply_guided)
        self.guided_out = QLabel("—")
        self.guided_out.setStyleSheet(f"color: {COLORS['accent']};")
        row.addWidget(apply_btn)
        row.addWidget(self.guided_out)
        row.addStretch(1)
        guided.addRow(row)
        root.addLayout(guided)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _h2(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("H2")
        return lbl

    def _apply_guided(self):
        base = {0: 0.7, 1: 0.9, 2: 1.1, 3: 1.4}[self.daily.currentIndex()]
        adj = {0: -0.2, 1: 0.0, 2: 0.2}[self.sensitivity.currentIndex()]
        tol = round(_clamp(base + adj, 0.5, 1.5), 2)
        self.guided_out.setText(f"tolerance = {tol}")
        if "caffeine" in self.tol_spins:
            self.tol_spins["caffeine"].setValue(tol)

    def _save(self):
        profile = UserProfile(
            body_mass_kg=self.mass.value(),
            sex=self.sex.currentText(),
            beta=self.beta.value(),
            legal_bac_limit=self.limit.value(),
            alcohol_ramp_min=self.ramp.value(),
        )
        profile.tolerance = {sid: spin.value() for sid, spin in self.tol_spins.items()}
        self.controller.save_profile(profile)
        self.accept()


class CustomSubstanceDialog(QDialog):
    """Build a new one-compartment substance and persist it."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("New custom substance")
        self.setMinimumWidth(440)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Yerba Mate")
        form.addRow("Name", self.name)

        self.half_life = self._spin(0.1, 72, 5.0, " h", 0.1)
        form.addRow("Elimination half-life", self.half_life)
        self.ka = self._spin(0.05, 20, 4.0, " 1/h", 0.05)
        form.addRow("Absorption rate ka", self.ka)
        self.f = self._spin(0.05, 1.0, 0.9, "", 0.01)
        form.addRow("Bioavailability F", self.f)
        self.v = self._spin(0.1, 10, 0.6, " L/kg", 0.05)
        form.addRow("Volume of distribution", self.v)
        self.ec50 = self._spin(0.0, 100, 1.0, " mg/L", 0.1)
        form.addRow("EC50 (effect, 0 = none)", self.ec50)

        self.conc_unit = QLineEdit("mg/L")
        form.addRow("Concentration unit", self.conc_unit)
        self.conc_scale = self._spin(0.0001, 1000, 1.0, "", 1.0)
        form.addRow("Display scale (×mg/L)", self.conc_scale)
        self.color = QLineEdit("#7ad1c7")
        form.addRow("Accent colour (hex)", self.color)

        self.redose = QCheckBox("Eligible for redose nudges (stimulant-like only)")
        form.addRow("", self.redose)
        root.addLayout(form)

        root.addWidget(self._label("Presets"))
        self.presets = QTableWidget(0, 2)
        self.presets.setHorizontalHeaderLabels(["Label", "Amount"])
        self.presets.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.presets)
        prow = QHBoxLayout()
        add = QPushButton("Add preset")
        add.clicked.connect(lambda: self._add_preset_row("Dose", 50.0))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(self._remove_preset_row)
        prow.addWidget(add)
        prow.addWidget(rm)
        prow.addStretch(1)
        root.addLayout(prow)
        self._add_preset_row("Standard", 50.0)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _spin(self, lo, hi, val, suffix, step):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setSuffix(suffix)
        s.setSingleStep(step)
        s.setDecimals(4 if step < 0.01 else 2)
        return s

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("H2")
        return lbl

    def _add_preset_row(self, label, amount):
        r = self.presets.rowCount()
        self.presets.insertRow(r)
        self.presets.setItem(r, 0, QTableWidgetItem(label))
        self.presets.setItem(r, 1, QTableWidgetItem(str(amount)))

    def _remove_preset_row(self):
        r = self.presets.currentRow()
        if r >= 0:
            self.presets.removeRow(r)

    def _save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Please give the substance a name.")
            return
        sid = _slug(name)
        if sid in self.controller.substances:
            QMessageBox.warning(self, "Already exists", f"A substance with id '{sid}' already exists.")
            return

        unit = "mg"
        presets = []
        for r in range(self.presets.rowCount()):
            label_item = self.presets.item(r, 0)
            amount_item = self.presets.item(r, 1)
            if not label_item or not amount_item:
                continue
            try:
                amount = float(amount_item.text())
            except ValueError:
                continue
            presets.append(Preset(label_item.text(), amount, unit))

        from ..core.models import ke_from_half_life

        ec50 = self.ec50.value() or None
        sub = Substance(
            id=sid, name=name, model="one_compartment",
            half_life_h=self.half_life.value(),
            ka=self.ka.value(), ke=ke_from_half_life(self.half_life.value()),
            f=self.f.value(), v_l_per_kg=self.v.value(),
            ec50=ec50, emax=1.0,
            redose_eligible=self.redose.isChecked(), is_builtin=False,
            unit=unit, conc_unit=self.conc_unit.text() or "mg/L",
            conc_scale=self.conc_scale.value(), color=self.color.text() or "#7ad1c7",
            note="User-defined substance.",
            redose_fraction=0.30 if self.redose.isChecked() else None,
            presets=presets,
        )
        self.controller.save_substance(sub)
        self.new_substance_id = sid
        self.accept()
