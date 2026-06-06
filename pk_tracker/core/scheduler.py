"""Alert logic: redose nudges, the sleep-cutoff solver, and alcohol clearance.

Everything here is derived on demand from a :class:`SubstanceTimeline`. The
scheduler never mutates anything; it answers questions like "when does my
caffeine effect fall below 30%?" or "how late can I have a coffee and still
sleep at 23:00?" by root-finding against the analytic curve.

Scope rules (enforced here, not just in the UI):
* Redose nudges are produced **only** for substances flagged ``redose_eligible``
  (caffeine and opted-in custom stimulants). Alcohol and methylphenidate never
  get one, no matter what the caller asks.
* The alcohol helper only ever predicts *clearance* (time to sober / below a
  limit). It never suggests another drink.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from scipy.optimize import brentq

from . import models
from .engine import SubstanceTimeline, to_hours

# Search horizon for forward root-finds (hours). Caffeine/stimulants are gone
# well within a day or two; this is a safe ceiling.
_MAX_HORIZON_H = 72.0


# --------------------------------------------------------------------------- #
# Redose nudge (caffeine and opted-in stimulants only)
# --------------------------------------------------------------------------- #
@dataclass
class RedoseInfo:
    eligible: bool
    threshold_fraction: float
    peak_effect: float
    current_percent: float | None       # current effect as % of recent peak
    redose_at: datetime | None          # when effect crosses below threshold
    overdue: bool                       # already below threshold now


def redose_info(
    timeline: SubstanceTimeline,
    now: datetime,
    threshold_fraction: float | None = None,
) -> RedoseInfo:
    """When will perceived effect fall below ``threshold_fraction`` of the peak?

    Returns an ``eligible=False`` result (and never a time) for substances that
    are not redose-eligible.
    """
    sub = timeline.substance
    frac = threshold_fraction if threshold_fraction is not None else (sub.redose_fraction or 0.30)

    if not sub.redose_eligible or sub.ec50 is None or not timeline.doses:
        return RedoseInfo(False, frac, 0.0, None, None, False)

    peak = timeline.personal_peak_effect(now=now)
    if peak <= 0:
        return RedoseInfo(True, frac, 0.0, None, None, False)

    target_effect = frac * peak
    cur_effect = float(timeline.effect_at(now))
    cur_percent = 100.0 * cur_effect / peak

    if cur_effect <= target_effect:
        return RedoseInfo(True, frac, peak, cur_percent, None, True)

    now_h = to_hours(now)
    g = lambda t_h: float(timeline.effect_at(t_h)) - target_effect  # noqa: E731
    cross_h = _forward_root(g, now_h, _MAX_HORIZON_H)
    redose_at = None if cross_h is None else _hours_to_dt(cross_h)
    return RedoseInfo(True, frac, peak, cur_percent, redose_at, False)


# --------------------------------------------------------------------------- #
# Sleep cutoff solver (caffeine)
# --------------------------------------------------------------------------- #
@dataclass
class SleepCutoff:
    feasible: bool
    cutoff_at: datetime | None          # latest time to take the candidate dose
    bedtime: datetime
    ceiling: float                      # acceptable concentration at bedtime
    existing_at_bedtime: float          # projected level at bedtime from logged doses
    amount: float
    reason: str = ""


def sleep_cutoff(
    timeline: SubstanceTimeline,
    now: datetime,
    bedtime: datetime,
    amount: float | None = None,
    target_fraction: float | None = None,
    absolute_target: float | None = None,
) -> SleepCutoff:
    """Latest time to take a dose of ``amount`` and still sleep at ``bedtime``.

    The bedtime ceiling (max acceptable concentration at lights-out) is, in
    priority order:
      1. ``absolute_target`` if given,
      2. ``target_fraction`` of the candidate dose's own peak if given (this is
         how the user's "≤ X% of peak in the blood by bedtime" setting feeds in),
      3. the substance's physiological ``sleep_threshold`` if defined
         (e.g. caffeine 0.6 mg/L from the literature),
      4. otherwise 15% of the candidate dose's own peak.

    We then find the latest dose time whose contribution at bedtime, on top of
    whatever the already-logged doses project to, stays under the ceiling. The
    candidate dose is only allowed to land at least one Tmax before bedtime, so
    we never "permit" a dose merely because its absorption is unfinished.
    """
    sub = timeline.substance
    if sub.model == "widmark_zero_order" or sub.ka is None:
        return SleepCutoff(False, None, bedtime, 0.0, 0.0, 0.0, "not applicable to this model")

    if amount is None:
        last = timeline.last_dose()
        amount = last.amount if last else (sub.presets[0].amount if sub.presets else 90.0)

    ke = timeline.ke()      # honours the per-user half-life override
    v = sub.volume_liters(timeline.profile.body_mass_kg)
    tmax = models.tmax_single(sub.ka, ke)
    cmax = models.cmax_single(amount, sub.f, v, sub.ka, ke)

    if absolute_target is not None:
        ceiling = absolute_target
    elif target_fraction is not None:
        ceiling = target_fraction * cmax
    elif sub.sleep_threshold is not None:
        ceiling = sub.sleep_threshold
    else:
        ceiling = 0.15 * cmax

    existing_at_bed = float(timeline.concentration_at(bedtime))
    headroom = ceiling - existing_at_bed

    if headroom <= 0:
        return SleepCutoff(
            False, None, bedtime, ceiling, existing_at_bed, amount,
            "already over the sleep ceiling at bedtime from logged doses",
        )

    bed_h = to_hours(bedtime)
    now_h = to_hours(now)
    # Latest physically sensible dose time: one Tmax before bedtime.
    latest_h = bed_h - tmax
    if latest_h <= now_h:
        return SleepCutoff(
            False, None, bedtime, ceiling, existing_at_bed, amount,
            "bedtime is too soon for another dose to peak and clear",
        )

    # added(t_dose) = single-dose contribution at bedtime. On t_dose in
    # [now, latest_h] the dose is post-peak at bedtime, so added increases with
    # t_dose. We want the largest t_dose with added <= headroom.
    def added(t_dose_h: float) -> float:
        return float(models.bateman_single(bed_h - t_dose_h, amount, sub.f, v, sub.ka, ke))

    if added(latest_h) <= headroom:
        cutoff_h = latest_h          # can dose as late as one Tmax before bed
    elif added(now_h) > headroom:
        return SleepCutoff(
            False, None, bedtime, ceiling, existing_at_bed, amount,
            "even a dose now would not have cleared by bedtime",
        )
    else:
        cutoff_h = brentq(lambda th: added(th) - headroom, now_h, latest_h, xtol=1e-4)

    return SleepCutoff(True, _hours_to_dt(cutoff_h), bedtime, ceiling, existing_at_bed, amount)


def sleep_cutoff_hours(
    timeline: SubstanceTimeline,
    now: datetime,
    bedtime: datetime,
    hours: float,
    amount: float | None = None,
) -> SleepCutoff:
    """Flat "stop caffeine N hours before bed" rule — no dose-aware solving.

    A simple alternative to the mg-target model for users who prefer a fixed
    rule. Feasible while the cutoff time is still in the future.
    """
    sub = timeline.substance
    if amount is None:
        last = timeline.last_dose()
        amount = last.amount if last else (sub.presets[0].amount if sub.presets else 90.0)
    cutoff = bedtime - timedelta(hours=hours)
    if cutoff <= now:
        return SleepCutoff(
            False, None, bedtime, 0.0, 0.0, amount,
            "already inside the pre-bed window",
        )
    return SleepCutoff(True, cutoff, bedtime, 0.0, 0.0, amount)


# --------------------------------------------------------------------------- #
# Perfect-timing coach: when to dose so it peaks at a target moment
# --------------------------------------------------------------------------- #
@dataclass
class PerfectTiming:
    feasible: bool
    dose_time: datetime | None          # when to take the dose
    target_time: datetime               # when you want to be at your sharpest
    amount: float
    tmax_h: float                       # lead time (a dose peaks one Tmax later)
    body_mg_at_target: float            # projected mass in body at the target
    reason: str = ""


def perfect_timing(
    timeline: SubstanceTimeline,
    now: datetime,
    target_time: datetime,
    amount: float,
) -> PerfectTiming:
    """When to take a dose of ``amount`` so it peaks right at ``target_time``.

    A single dose peaks one Tmax after it's taken, so the optimal dose time is
    simply ``target_time - Tmax``. Also reports the projected body load at the
    target (already-logged doses + the new one) so the user sees the boost.
    """
    sub = timeline.substance
    if sub.ka is None or sub.model == "widmark_zero_order":
        return PerfectTiming(False, None, target_time, amount, 0.0, 0.0,
                             "not applicable to this substance")
    ke = timeline.ke()      # honours the per-user half-life override
    v = sub.volume_liters(timeline.profile.body_mass_kg)
    tmax = models.tmax_single(sub.ka, ke)
    dose_time = target_time - timedelta(hours=tmax)
    existing = float(timeline.concentration_at(target_time))
    new_peak = float(models.cmax_single(amount, sub.f, v, sub.ka, ke))
    body_mg = (existing + new_peak) * v
    if dose_time <= now:
        return PerfectTiming(False, None, target_time, amount, tmax, body_mg,
                             "that peak is too soon — drink now for the closest")
    return PerfectTiming(True, dose_time, target_time, amount, tmax, body_mg)


# --------------------------------------------------------------------------- #
# Overload / jitter-zone cue (caffeine)
# --------------------------------------------------------------------------- #
@dataclass
class OverloadInfo:
    has_threshold: bool
    body_amount_mg: float
    threshold_mg: float | None
    over: bool


def overload_info(timeline: SubstanceTimeline, now: datetime) -> OverloadInfo:
    """Is the current body burden past the soft 'diminishing returns' threshold?"""
    thr = timeline.substance.overload_amount_mg
    if thr is None:
        return OverloadInfo(False, 0.0, None, False)
    body = timeline.body_amount_at(now)
    return OverloadInfo(True, body, thr, body > thr)


# --------------------------------------------------------------------------- #
# Alcohol clearance predictor (never suggests another drink)
# --------------------------------------------------------------------------- #
@dataclass
class AlcoholPrediction:
    bac_now: float
    over_limit: bool
    time_to_limit: datetime | None      # when BAC drops below the legal limit
    time_to_zero: datetime | None       # when BAC reaches 0.00
    legal_limit: float


def alcohol_predictions(timeline: SubstanceTimeline, now: datetime) -> AlcoholPrediction | None:
    """Projected sober times for alcohol, assuming no further drinks."""
    if timeline.substance.model != "widmark_zero_order":
        return None
    bac_now = float(timeline.concentration_at(now))
    beta = timeline.profile.beta
    limit = timeline.profile.legal_bac_limit

    if bac_now <= 0:
        return AlcoholPrediction(0.0, False, None, None, limit)

    h_to_limit = models.widmark_time_to_target(bac_now, limit, beta)
    h_to_zero = models.widmark_time_to_target(bac_now, 0.0, beta)
    return AlcoholPrediction(
        bac_now=bac_now,
        over_limit=bac_now > limit,
        time_to_limit=now + timedelta(hours=h_to_limit) if bac_now > limit else now,
        time_to_zero=now + timedelta(hours=h_to_zero),
        legal_limit=limit,
    )


# --------------------------------------------------------------------------- #
# Numeric helpers
# --------------------------------------------------------------------------- #
def time_below_level(timeline, now: datetime, level: float,
                     horizon_h: float = 48.0, step_h: float = 0.2) -> datetime | None:
    """First time at/after ``now`` when concentration is at or below ``level``.

    A forward scan against the actual curve, so it is correct even when the
    concentration is still rising (e.g. an extended-release second pulse) rather
    than assuming a simple exponential decay from the current value.
    """
    if float(timeline.concentration_at(now)) <= level:
        return now
    now_h = to_hours(now)
    t = now_h + step_h
    end = now_h + horizon_h
    while t <= end:
        if float(timeline.concentration_at(t)) <= level:
            return _hours_to_dt(t)
        t += step_h
    return None


def _hours_to_dt(t_hours: float) -> datetime:
    return datetime.fromtimestamp(t_hours * 3600.0, tz=timezone.utc)


def _forward_root(g, start_h: float, horizon_h: float, step_h: float = 0.1) -> float | None:
    """First time >= start_h where g changes sign from positive to non-positive.

    g(start) is assumed > 0 (still above threshold). We march forward in small
    steps to bracket the first crossing, then refine with brentq.
    """
    t0 = start_h
    g0 = g(t0)
    if g0 <= 0:
        return start_h
    end = start_h + horizon_h
    t = t0 + step_h
    while t <= end:
        gt = g(t)
        if gt <= 0:
            return float(brentq(g, t0, t, xtol=1e-4))
        t0, g0 = t, gt
        t += step_h
    return None
