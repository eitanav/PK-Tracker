"""Tests for the scheduler: redose nudges, sleep cutoff, alcohol clearance.

These also pin down the safety scope rules: only caffeine-like substances get
redose nudges; alcohol and methylphenidate never do.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pk_tracker.core import models, scheduler
from pk_tracker.core.engine import Dose, SubstanceTimeline, UserProfile
from pk_tracker.core.substances import load_substances

LIB = load_substances()
NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def _tl(sub_id, doses, **profile_kw):
    return SubstanceTimeline(LIB[sub_id], doses, UserProfile(body_mass_kg=70.0, **profile_kw))


# --------------------------------------------------------------------------- #
# Redose scope + timing
# --------------------------------------------------------------------------- #
def test_redose_eligible_only_for_caffeine_like():
    caf = _tl("caffeine", [Dose("caffeine", 90, "mg", NOW)])
    mph = _tl("methylphenidate", [Dose("methylphenidate", 10, "mg", NOW)])
    alc = _tl("alcohol", [Dose("alcohol", 14, "g", NOW)])
    assert scheduler.redose_info(caf, NOW).eligible is True
    assert scheduler.redose_info(mph, NOW).eligible is False
    assert scheduler.redose_info(alc, NOW).eligible is False


def test_redose_time_is_in_the_future_after_a_fresh_dose():
    # Dosed an hour ago, so the curve is near its peak (not zero as it would be
    # at the exact instant of dosing).
    tl = _tl("caffeine", [Dose("caffeine", 120, "mg", NOW - timedelta(hours=1))])
    info = scheduler.redose_info(tl, NOW, threshold_fraction=0.30)
    assert info.overdue is False
    assert info.redose_at is not None and info.redose_at > NOW


def test_redose_marked_overdue_when_effect_already_low():
    # A dose taken a full day ago: effect is well below 30% of peak.
    tl = _tl("caffeine", [Dose("caffeine", 90, "mg", NOW - timedelta(hours=24))])
    info = scheduler.redose_info(tl, NOW, threshold_fraction=0.30)
    assert info.overdue is True
    assert info.redose_at is None


def test_redose_crossing_actually_sits_at_the_threshold():
    tl = _tl("caffeine", [Dose("caffeine", 120, "mg", NOW - timedelta(hours=1))])
    info = scheduler.redose_info(tl, NOW, threshold_fraction=0.30)
    eff_at_cross = float(tl.effect_at(info.redose_at))
    assert eff_at_cross == pytest.approx(0.30 * info.peak_effect, rel=1e-2)


# --------------------------------------------------------------------------- #
# Sleep cutoff
# --------------------------------------------------------------------------- #
def test_sleep_cutoff_feasible_with_a_distant_bedtime():
    tl = _tl("caffeine", [])
    bedtime = NOW + timedelta(hours=14)
    res = scheduler.sleep_cutoff(tl, NOW, bedtime, amount=90.0)
    assert res.feasible is True
    assert NOW < res.cutoff_at < bedtime


def test_sleep_cutoff_contribution_lands_on_the_ceiling():
    # A dose taken exactly at the cutoff should bring the bedtime level right up
    # to the ceiling (here the substance's absolute sleep threshold).
    tl = _tl("caffeine", [])
    bedtime = NOW + timedelta(hours=14)
    res = scheduler.sleep_cutoff(tl, NOW, bedtime, amount=90.0)

    caf = LIB["caffeine"]
    v = caf.volume_liters(70.0)
    dt_hours = (bedtime - res.cutoff_at).total_seconds() / 3600.0
    added = models.bateman_single(dt_hours, 90.0, caf.f, v, caf.ka, caf.ke)
    assert added == pytest.approx(res.ceiling - res.existing_at_bedtime, rel=1e-2)


def test_sleep_cutoff_infeasible_when_bedtime_too_soon():
    tl = _tl("caffeine", [])
    bedtime = NOW + timedelta(minutes=20)
    res = scheduler.sleep_cutoff(tl, NOW, bedtime, amount=90.0)
    assert res.feasible is False


def test_sleep_cutoff_not_applicable_to_alcohol():
    tl = _tl("alcohol", [Dose("alcohol", 14, "g", NOW)])
    res = scheduler.sleep_cutoff(tl, NOW, NOW + timedelta(hours=8))
    assert res.feasible is False


# --------------------------------------------------------------------------- #
# Overload cue
# --------------------------------------------------------------------------- #
def test_overload_triggers_past_threshold():
    # A large recent caffeine load should put body burden over 400 mg.
    doses = [Dose("caffeine", 300, "mg", NOW), Dose("caffeine", 300, "mg", NOW)]
    tl = _tl("caffeine", doses)
    info = scheduler.overload_info(tl, NOW + timedelta(minutes=45))
    assert info.has_threshold is True
    assert info.over is True


def test_overload_not_triggered_by_a_single_coffee():
    tl = _tl("caffeine", [Dose("caffeine", 90, "mg", NOW)])
    info = scheduler.overload_info(tl, NOW + timedelta(minutes=45))
    assert info.over is False


# --------------------------------------------------------------------------- #
# Alcohol clearance predictor
# --------------------------------------------------------------------------- #
def test_alcohol_predictions_clear_over_time():
    grams = 28.0
    tl = _tl("alcohol", [Dose("alcohol", grams, "g", NOW)], sex="male")
    # Absorption takes ~30 min by default; read the curve once it has peaked.
    peak = NOW + timedelta(minutes=30)
    pred = scheduler.alcohol_predictions(tl, peak)
    assert pred is not None
    # Widmark height, less the elimination that ran during absorption.
    expected = grams / (0.68 * 70 * 10) - 0.015 * 0.5
    assert pred.bac_now == pytest.approx(expected, abs=1e-6)
    assert pred.over_limit is True
    # Sober (zero) comes strictly after dropping below the legal limit.
    assert pred.time_to_zero > pred.time_to_limit > peak


def test_alcohol_predictions_when_already_sober():
    tl = _tl("alcohol", [Dose("alcohol", 14, "g", NOW - timedelta(hours=20))])
    pred = scheduler.alcohol_predictions(tl, NOW)
    assert pred.bac_now == pytest.approx(0.0, abs=1e-9)
    assert pred.over_limit is False


def test_alcohol_predictions_none_for_caffeine():
    tl = _tl("caffeine", [Dose("caffeine", 90, "mg", NOW)])
    assert scheduler.alcohol_predictions(tl, NOW) is None
