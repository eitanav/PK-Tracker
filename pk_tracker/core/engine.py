"""The engine: dose log + substance model -> concentration and effect over time.

This is where the pure math in :mod:`models` meets real-world inputs — a list of
timestamped doses and a user profile. It deliberately holds **no mutable state
and runs no background loop**. Every query is a fresh evaluation of a closed-form
model at the requested instant, so the app can be killed and reopened a day
later and the curve is simply recomputed from the persisted dose timestamps.

Time handling
-------------
Doses carry timezone-aware UTC timestamps. Internally we evaluate the analytic
models in *hours* using each timestamp's POSIX seconds (``dt.timestamp()/3600``),
so there is never an ambiguous local-time reference. The UI converts to local
time only for display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from . import models
from .substances import MODEL_ONE_COMPARTMENT_ER, MODEL_WIDMARK, Substance

# Default blood-alcohol driving limit used by the sobriety predictor (g/dL).
# Clearly an estimate, not a legal guarantee; user-configurable.
DEFAULT_LEGAL_BAC_LIMIT = 0.05


def to_hours(dt: datetime) -> float:
    """Absolute time in hours (POSIX seconds / 3600) for a tz-aware datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() / 3600.0


@dataclass
class Dose:
    """A single logged dose. ``amount`` is in the substance's native unit
    (mg for stimulants, grams of ethanol for alcohol)."""

    substance_id: str
    amount: float
    unit: str
    taken_at: datetime           # tz-aware, stored UTC
    note: str = ""
    id: int | None = None

    @property
    def hours(self) -> float:
        return to_hours(self.taken_at)


@dataclass
class UserProfile:
    """Per-user calibration. Tolerance is pharmacodynamic and lives here, never
    touching the kinetic constants."""

    body_mass_kg: float = 70.0
    sex: str = "male"                       # 'male' | 'female' -> Widmark r
    r_male: float = 0.68
    r_female: float = 0.55
    beta: float = 0.015                     # alcohol elimination, g/dL/h
    legal_bac_limit: float = DEFAULT_LEGAL_BAC_LIMIT
    alcohol_ramp_min: float = 0.0           # alcohol absorption ramp (min); 0 = instant
    tolerance: dict[str, float] = field(default_factory=dict)   # per substance id

    def widmark_r(self) -> float:
        return self.r_female if str(self.sex).lower().startswith("f") else self.r_male

    def tolerance_for(self, substance_id: str) -> float:
        """Tolerance factor in [0.5, 1.5]; 1.0 if uncalibrated."""
        return float(self.tolerance.get(substance_id, 1.0))


@dataclass
class CurveResult:
    """A sampled timeline ready for plotting. ``x`` is POSIX seconds."""

    x: np.ndarray
    concentration: np.ndarray          # internal units (mg/L, or g/dL for alcohol)
    effect: np.ndarray | None          # raw 0..emax, or None if no PD model
    conc_unit: str
    conc_scale: float


class SubstanceTimeline:
    """Concentration / effect for one substance given its dose history.

    Construct it with the substance definition, the doses for that substance,
    and the user profile. All methods are pure reads.
    """

    def __init__(self, substance: Substance, doses: list[Dose], profile: UserProfile):
        self.substance = substance
        self.profile = profile
        # Only the doses for this substance, sorted by time.
        self.doses = sorted(
            (d for d in doses if d.substance_id == substance.id),
            key=lambda d: d.taken_at,
        )
        self.tolerance_factor = profile.tolerance_for(substance.id)

    # ----- core evaluation ---------------------------------------------------
    def _dose_events(self) -> list[tuple[float, float]]:
        return [(d.hours, d.amount) for d in self.doses]

    def concentration_at(self, when: datetime | float):
        """Concentration (internal units) at an instant or array of POSIX-hour values."""
        t = when if not isinstance(when, datetime) else to_hours(when)
        events = self._dose_events()
        if not events:
            return 0.0 if np.isscalar(t) else np.zeros_like(np.asarray(t, float))

        sub = self.substance
        if sub.model == MODEL_WIDMARK:
            return models.widmark_bac(
                t, events, r=self.profile.widmark_r(),
                mass_kg=self.profile.body_mass_kg, beta=self.profile.beta,
                ramp_h=self.profile.alcohol_ramp_min / 60.0,
            )
        v = sub.volume_liters(self.profile.body_mass_kg)
        ke = sub.ke_value()
        if sub.model == MODEL_ONE_COMPARTMENT_ER:
            return models.superpose_er(
                t, events, f=sub.f, v=v, ka=sub.ka, ke=ke,
                frac_ir=sub.frac_ir if sub.frac_ir is not None else 0.5,
                lag_h=sub.lag_h if sub.lag_h is not None else 4.0,
                ka2=sub.ka2,
            )
        return models.superpose(t, events, f=sub.f, v=v, ka=sub.ka, ke=ke)

    def effect_at(self, when: datetime | float):
        """Raw perceived effect (0..emax) at an instant. None if no PD model."""
        if self.substance.ec50 is None:
            return None
        c = self.concentration_at(when)
        return models.emax_effect(
            c, emax=self.substance.emax, ec50=self.substance.ec50,
            tolerance_factor=self.tolerance_factor,
        )

    def body_amount_at(self, when: datetime | float) -> float:
        """Drug mass currently in the body (mg) = concentration * volume.

        Used for the caffeine 'jitter zone' overload cue. Meaningless for the
        Widmark model, which returns 0.
        """
        if self.substance.model == MODEL_WIDMARK or self.substance.v_l_per_kg is None:
            return 0.0
        c = self.concentration_at(when)
        v = self.substance.volume_liters(self.profile.body_mass_kg)
        return float(c * v)

    # ----- sampled curves ----------------------------------------------------
    def curve(self, start: datetime, end: datetime, n: int = 600) -> CurveResult:
        """Sample concentration and effect on a uniform grid from start to end."""
        x_hours = np.linspace(to_hours(start), to_hours(end), n)
        conc = np.atleast_1d(self.concentration_at(x_hours)).astype(float)
        if self.substance.ec50 is None:
            effect = None
        else:
            effect = models.emax_effect(
                conc, emax=self.substance.emax, ec50=self.substance.ec50,
                tolerance_factor=self.tolerance_factor,
            )
        x_posix = x_hours * 3600.0
        return CurveResult(
            x=x_posix, concentration=conc, effect=effect,
            conc_unit=self.substance.conc_unit, conc_scale=self.substance.conc_scale,
        )

    # ----- summary statistics ------------------------------------------------
    def personal_peak_effect(self, now: datetime | None = None) -> float:
        """Max raw effect across the dose history up to ``now`` (for % display).

        Returns 0 if there is no effect model or no doses. Sampled densely
        enough to catch sharp caffeine peaks.
        """
        if self.substance.ec50 is None or not self.doses:
            return 0.0
        now = now or datetime.now(timezone.utc)
        start_h = self.doses[0].hours
        end_h = max(to_hours(now), self.doses[-1].hours + 0.1)
        grid = np.linspace(start_h, end_h, 2000)
        eff = models.emax_effect(
            np.atleast_1d(self.concentration_at(grid)).astype(float),
            emax=self.substance.emax, ec50=self.substance.ec50,
            tolerance_factor=self.tolerance_factor,
        )
        return float(np.max(eff)) if eff.size else 0.0

    def effect_percent_of_peak(self, when: datetime, now: datetime | None = None) -> float | None:
        """Current effect expressed as a percentage of the personal recent peak."""
        peak = self.personal_peak_effect(now=now or when)
        if peak <= 0:
            return None
        cur = self.effect_at(when)
        if cur is None:
            return None
        return 100.0 * float(cur) / peak

    def last_dose(self) -> Dose | None:
        return self.doses[-1] if self.doses else None
