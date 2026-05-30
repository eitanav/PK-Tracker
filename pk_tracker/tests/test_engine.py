"""Tests for the engine: dose log + models -> concentration / effect."""

from datetime import datetime, timedelta, timezone

import pytest

from pk_tracker.core import models
from pk_tracker.core.engine import Dose, SubstanceTimeline, UserProfile, to_hours
from pk_tracker.core.substances import load_substances

LIB = load_substances()
NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def _profile(**kw):
    kw.setdefault("body_mass_kg", 70.0)
    kw.setdefault("sex", "male")
    return UserProfile(**kw)


def test_concentration_matches_raw_superposition():
    caf = LIB["caffeine"]
    doses = [
        Dose("caffeine", 90.0, "mg", NOW - timedelta(hours=2)),
        Dose("caffeine", 70.0, "mg", NOW - timedelta(hours=0.5)),
    ]
    tl = SubstanceTimeline(caf, doses, _profile())

    v = caf.volume_liters(70.0)
    events = [(to_hours(d.taken_at), d.amount) for d in doses]
    expected = models.superpose(to_hours(NOW), events, caf.f, v, caf.ka, caf.ke)
    assert tl.concentration_at(NOW) == pytest.approx(expected)


def test_only_matching_substance_doses_count():
    caf = LIB["caffeine"]
    doses = [
        Dose("caffeine", 90.0, "mg", NOW - timedelta(hours=1)),
        Dose("alcohol", 14.0, "g", NOW - timedelta(hours=1)),  # ignored here
    ]
    tl = SubstanceTimeline(caf, doses, _profile())
    assert len(tl.doses) == 1


def test_effect_is_none_without_pd_model():
    alcohol = LIB["alcohol"]
    doses = [Dose("alcohol", 14.0, "g", NOW)]
    tl = SubstanceTimeline(alcohol, doses, _profile())
    assert tl.effect_at(NOW) is None


def test_effect_within_zero_to_emax():
    caf = LIB["caffeine"]
    doses = [Dose("caffeine", 200.0, "mg", NOW - timedelta(hours=1))]
    tl = SubstanceTimeline(caf, doses, _profile())
    eff = tl.effect_at(NOW)
    assert 0.0 < eff < caf.emax


def test_tolerance_lowers_effect_not_concentration():
    caf = LIB["caffeine"]
    doses = [Dose("caffeine", 120.0, "mg", NOW - timedelta(hours=1))]
    naive = SubstanceTimeline(caf, doses, _profile(tolerance={"caffeine": 0.5}))
    habituated = SubstanceTimeline(caf, doses, _profile(tolerance={"caffeine": 1.5}))
    # Same concentration...
    assert naive.concentration_at(NOW) == pytest.approx(habituated.concentration_at(NOW))
    # ...different felt effect.
    assert naive.effect_at(NOW) > habituated.effect_at(NOW)


def test_body_amount_tracks_concentration_times_volume():
    caf = LIB["caffeine"]
    doses = [Dose("caffeine", 100.0, "mg", NOW - timedelta(hours=1))]
    tl = SubstanceTimeline(caf, doses, _profile())
    c = tl.concentration_at(NOW)
    assert tl.body_amount_at(NOW) == pytest.approx(c * caf.volume_liters(70.0))


def test_curve_shapes_and_now_marker():
    caf = LIB["caffeine"]
    doses = [Dose("caffeine", 90.0, "mg", NOW)]
    tl = SubstanceTimeline(caf, doses, _profile())
    res = tl.curve(NOW - timedelta(hours=2), NOW + timedelta(hours=10), n=300)
    assert res.x.shape == (300,)
    assert res.concentration.shape == (300,)
    assert res.effect is not None and res.effect.shape == (300,)
    # Concentration is zero before the dose, positive after.
    assert res.concentration[0] == pytest.approx(0.0, abs=1e-9)
    assert res.concentration.max() > 0


def test_personal_peak_and_percent_of_peak():
    caf = LIB["caffeine"]
    doses = [Dose("caffeine", 90.0, "mg", NOW - timedelta(hours=6))]
    tl = SubstanceTimeline(caf, doses, _profile())
    peak = tl.personal_peak_effect(now=NOW)
    assert peak > 0
    pct = tl.effect_percent_of_peak(NOW, now=NOW)
    # Six hours later the effect has fallen from its peak but, because the Emax
    # response saturates, it is still a meaningful fraction of it.
    assert 0 < pct < 100


def test_alcohol_uses_widmark_and_sex_ratio():
    alcohol = LIB["alcohol"]
    grams = 28.0
    doses = [Dose("alcohol", grams, "g", NOW)]
    male = SubstanceTimeline(alcohol, doses, _profile(sex="male"))
    female = SubstanceTimeline(alcohol, doses, _profile(sex="female"))
    # Same dose hits a smaller-r body (female default) harder.
    assert female.concentration_at(NOW) > male.concentration_at(NOW)
    assert male.concentration_at(NOW) == pytest.approx(grams / (0.68 * 70 * 10))
