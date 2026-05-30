"""Unit tests for the core PK/PD math.

The math layer is the heart of the project, so it gets the most scrutiny. These
tests cover the cases called out in the build spec:

* single-dose peak time and peak value
* superposition of two doses
* decay to a target level
* Widmark BAC reaching (and staying at) zero
* unit handling

plus the numerically awkward bits (ka == ke limit, t < 0, scalar/array shapes).
"""

import math

import numpy as np
import pytest

from pk_tracker.core import models


# --------------------------------------------------------------------------- #
# Rate-constant conversions
# --------------------------------------------------------------------------- #
def test_ke_half_life_round_trip():
    ke = models.ke_from_half_life(5.0)
    assert ke == pytest.approx(math.log(2) / 5.0)
    assert models.half_life_from_ke(ke) == pytest.approx(5.0)


def test_half_life_rejects_nonpositive():
    with pytest.raises(ValueError):
        models.ke_from_half_life(0)
    with pytest.raises(ValueError):
        models.half_life_from_ke(-1)


# --------------------------------------------------------------------------- #
# Bateman single dose: peak time and peak value
# --------------------------------------------------------------------------- #
def test_tmax_matches_analytic_formula():
    ka, ke = 5.0, 0.139
    expected = math.log(ka / ke) / (ka - ke)
    assert models.tmax_single(ka, ke) == pytest.approx(expected)


def test_caffeine_tmax_about_45_minutes():
    # Default caffeine constants from the spec should peak around 0.7-0.75 h.
    tmax = models.tmax_single(ka=5.0, ke=0.139)
    assert 0.65 < tmax < 0.80


def test_peak_value_is_the_curve_maximum():
    # The analytic Cmax must equal the maximum of a finely sampled curve, and it
    # must occur at Tmax.
    dose, f, v, ka, ke = 100.0, 0.99, 36.0, 5.0, 0.139
    tmax = models.tmax_single(ka, ke)
    cmax = models.cmax_single(dose, f, v, ka, ke)

    t = np.linspace(0, 24, 200_000)
    c = models.bateman_single(t, dose, f, v, ka, ke)

    assert cmax == pytest.approx(c.max(), rel=1e-4)
    assert t[np.argmax(c)] == pytest.approx(tmax, abs=1e-3)


def test_concentration_is_zero_before_dose():
    assert models.bateman_single(-1.0, 100, 0.99, 36, 5.0, 0.139) == 0.0
    t = np.array([-5.0, -0.001, 0.0, 1.0])
    c = models.bateman_single(t, 100, 0.99, 36, 5.0, 0.139)
    assert c[0] == 0.0 and c[1] == 0.0
    assert c[3] > 0.0


def test_scalar_in_scalar_out_array_in_array_out():
    val = models.bateman_single(1.0, 100, 0.99, 36, 5.0, 0.139)
    assert isinstance(val, float)
    arr = models.bateman_single(np.array([1.0, 2.0]), 100, 0.99, 36, 5.0, 0.139)
    assert isinstance(arr, np.ndarray) and arr.shape == (2,)


def test_ka_equals_ke_limit_is_continuous():
    # Approaching ka == ke from nearby must match the exact-equality branch.
    dose, f, v, k = 100.0, 1.0, 30.0, 0.7
    t = 1.5
    exact = models.bateman_single(t, dose, f, v, ka=k, ke=k)
    near = models.bateman_single(t, dose, f, v, ka=k + 1e-5, ke=k)
    assert exact == pytest.approx(near, rel=1e-3)
    # And the closed-form limit value itself.
    expected = (f * dose * k / v) * t * math.exp(-k * t)
    assert exact == pytest.approx(expected)


def test_bateman_rejects_bad_params():
    with pytest.raises(ValueError):
        models.bateman_single(1.0, 100, 0.99, v=0, ka=5.0, ke=0.139)
    with pytest.raises(ValueError):
        models.bateman_single(1.0, 100, 0.99, 36, ka=-1, ke=0.139)


# --------------------------------------------------------------------------- #
# Superposition of multiple doses
# --------------------------------------------------------------------------- #
def test_superposition_equals_sum_of_singles():
    f, v, ka, ke = 0.99, 36.0, 5.0, 0.139
    events = [(0.0, 100.0), (3.0, 60.0)]
    t = np.linspace(0, 12, 5000)

    total = models.superpose(t, events, f, v, ka, ke)
    manual = (
        models.bateman_single(t - 0.0, 100.0, f, v, ka, ke)
        + models.bateman_single(t - 3.0, 60.0, f, v, ka, ke)
    )
    assert np.allclose(total, manual)


def test_superposition_second_dose_inactive_before_it_is_taken():
    f, v, ka, ke = 0.99, 36.0, 5.0, 0.139
    events = [(0.0, 100.0), (3.0, 100.0)]
    # At t = 2 h only the first dose contributes.
    at_two = models.superpose(2.0, events, f, v, ka, ke)
    only_first = models.bateman_single(2.0, 100.0, f, v, ka, ke)
    assert at_two == pytest.approx(only_first)


def test_superposition_is_additive_in_dose():
    # Two 50 mg doses at the same instant == one 100 mg dose.
    f, v, ka, ke = 0.99, 36.0, 5.0, 0.139
    t = np.linspace(0, 10, 1000)
    two_halves = models.superpose(t, [(0.0, 50.0), (0.0, 50.0)], f, v, ka, ke)
    one_full = models.bateman_single(t, 100.0, f, v, ka, ke)
    assert np.allclose(two_halves, one_full)


# --------------------------------------------------------------------------- #
# Extended-release: two superposed Bateman pulses
# --------------------------------------------------------------------------- #
def test_er_is_sum_of_two_pulses():
    f, v, ka, ke = 0.30, 175.0, 1.3, 0.198
    frac, lag, ka2 = 0.4, 5.0, 0.6
    t = np.linspace(0, 24, 4000)
    er = models.bateman_er_single(t, 36.0, f, v, ka, ke, frac, lag, ka2)
    manual = (
        models.bateman_single(t, frac * 36.0, f, v, ka, ke)
        + models.bateman_single(t - lag, (1 - frac) * 36.0, f, v, ka2, ke)
    )
    assert np.allclose(er, manual)


def test_er_second_pulse_inactive_before_its_lag():
    f, v, ka, ke = 0.30, 175.0, 1.3, 0.198
    frac, lag = 0.4, 5.0
    # Before the lag, only the immediate fraction contributes.
    early = models.bateman_er_single(2.0, 36.0, f, v, ka, ke, frac, lag)
    only_ir = models.bateman_single(2.0, frac * 36.0, f, v, ka, ke)
    assert early == pytest.approx(only_ir)


def test_er_plateau_outlasts_an_equivalent_immediate_dose():
    # Same total dose: ER holds a higher level late in the day than pure IR,
    # because part of it is released later.
    f, v, ka, ke = 0.30, 175.0, 1.3, 0.198
    late = 9.0
    er = models.bateman_er_single(late, 36.0, f, v, ka, ke, frac_ir=0.4, lag_h=5.0)
    ir = models.bateman_single(late, 36.0, f, v, ka, ke)
    assert er > ir


def test_superpose_er_matches_single_when_one_dose():
    f, v, ka, ke = 0.30, 175.0, 1.3, 0.198
    t = np.linspace(0, 24, 1000)
    multi = models.superpose_er(t, [(0.0, 36.0)], f, v, ka, ke, 0.4, 5.0)
    single = models.bateman_er_single(t, 36.0, f, v, ka, ke, 0.4, 5.0)
    assert np.allclose(multi, single)


# --------------------------------------------------------------------------- #
# Decay to a target level (sleep-cutoff primitive)
# --------------------------------------------------------------------------- #
def test_time_to_decay_to_matches_exponential():
    ke = models.ke_from_half_life(5.0)
    # One half-life to halve the concentration.
    assert models.time_to_decay_to(2.0, 1.0, ke) == pytest.approx(5.0)
    # Two half-lives to quarter it.
    assert models.time_to_decay_to(4.0, 1.0, ke) == pytest.approx(10.0)


def test_time_to_decay_round_trips_through_decay():
    ke = 0.139
    c0, target = 8.0, 1.2
    t = models.time_to_decay_to(c0, target, ke)
    # Applying pure exponential decay for that long must land on the target.
    assert c0 * math.exp(-ke * t) == pytest.approx(target)


def test_time_to_decay_edge_cases():
    assert models.time_to_decay_to(1.0, 2.0, 0.139) == 0.0   # already below
    assert models.time_to_decay_to(1.0, 1.0, 0.139) == 0.0   # already at
    assert models.time_to_decay_to(5.0, 0.0, 0.139) == float("inf")  # never zero


# --------------------------------------------------------------------------- #
# Pharmacodynamics: Emax effect and tolerance shift
# --------------------------------------------------------------------------- #
def test_emax_half_maximal_at_ec50():
    # At C == EC50 (tolerance 1.0) the effect is exactly half of Emax.
    eff = models.emax_effect(2.0, emax=1.0, ec50=2.0, tolerance_factor=1.0)
    assert eff == pytest.approx(0.5)


def test_tolerance_shifts_curve_right():
    # A habituated user (tolerance 1.5) feels less from the same concentration
    # than a naive user (tolerance 0.5).
    c = 2.0
    naive = models.emax_effect(c, 1.0, 2.0, tolerance_factor=0.5)
    habituated = models.emax_effect(c, 1.0, 2.0, tolerance_factor=1.5)
    assert naive > habituated


def test_emax_saturates_below_emax():
    big = models.emax_effect(1e6, emax=1.0, ec50=2.0, tolerance_factor=1.0)
    assert big < 1.0 and big > 0.99
    assert models.emax_effect(0.0, 1.0, 2.0, 1.0) == 0.0


# --------------------------------------------------------------------------- #
# Alcohol: unit handling and the Widmark curve
# --------------------------------------------------------------------------- #
def test_grams_ethanol_for_a_standard_beer():
    # 330 ml at 5% ABV.
    grams = models.grams_ethanol(330.0, 5.0)
    assert grams == pytest.approx(330 * 0.05 * 0.789)
    assert grams == pytest.approx(13.02, abs=0.02)


def test_widmark_peak_height_matches_hand_calc():
    grams = models.grams_ethanol(330.0, 5.0)
    # 70 kg male, r = 0.68, peak right at the drink.
    bac0 = models.widmark_bac(0.0, [(0.0, grams)], r=0.68, mass_kg=70.0, beta=0.015)
    assert bac0 == pytest.approx(grams / (0.68 * 70.0 * 10.0))
    assert bac0 == pytest.approx(0.0273, abs=0.001)


def test_widmark_reaches_zero_and_stays_there():
    grams = 28.0  # roughly two strong drinks
    r, mass, beta = 0.68, 70.0, 0.015
    bac0 = models.widmark_bac(0.0, [(0.0, grams)], r, mass, beta)
    t_zero = bac0 / beta  # straight-line descent to zero

    just_before = models.widmark_bac(t_zero - 0.01, [(0.0, grams)], r, mass, beta)
    at_zero = models.widmark_bac(t_zero, [(0.0, grams)], r, mass, beta)
    well_after = models.widmark_bac(t_zero + 50.0, [(0.0, grams)], r, mass, beta)

    assert just_before > 0.0
    assert at_zero == pytest.approx(0.0, abs=1e-9)
    assert well_after == 0.0  # floored, never negative


def test_widmark_two_drinks_do_not_naively_superpose():
    # Zero-order elimination means two spaced drinks accumulate less than the
    # naive sum of two independent peaks would suggest, because elimination
    # keeps chewing through the first drink while the second is consumed.
    r, mass, beta = 0.68, 70.0, 0.015
    drinks = [(0.0, 14.0), (2.0, 14.0)]
    bac_at_second = models.widmark_bac(2.0, drinks, r, mass, beta)

    single_bump = 14.0 / (r * mass * 10.0)
    # First drink has been eliminating for 2 h before the second lands.
    expected = max(0.0, single_bump - beta * 2.0) + single_bump
    assert bac_at_second == pytest.approx(expected)
    assert bac_at_second < 2 * single_bump  # strictly less than naive doubling


def test_widmark_ramp_softens_the_peak_but_conserves_clearance():
    r, mass, beta = 0.68, 70.0, 0.015
    drinks = [(0.0, 28.0)]
    instant_peak = models.widmark_bac(0.0, drinks, r, mass, beta)            # ramp 0
    ramped_at_zero = models.widmark_bac(0.0, drinks, r, mass, beta, ramp_h=0.5)
    ramped_after = models.widmark_bac(0.5, drinks, r, mass, beta, ramp_h=0.5)

    # At t=0 only a sliver has been absorbed, so the ramped curve starts lower.
    assert ramped_at_zero < instant_peak
    # By the end of the ramp almost all of it is on board (minus a little
    # elimination), approaching the instantaneous peak.
    assert ramped_after == pytest.approx(instant_peak - beta * 0.5, rel=0.05)


def test_widmark_ramp_zero_equals_default():
    r, mass, beta = 0.68, 70.0, 0.015
    drinks = [(0.0, 20.0), (1.5, 14.0)]
    t = np.linspace(0, 8, 200)
    assert np.allclose(
        models.widmark_bac(t, drinks, r, mass, beta),
        models.widmark_bac(t, drinks, r, mass, beta, ramp_h=0.0),
    )


def test_widmark_time_to_target():
    beta = 0.015
    assert models.widmark_time_to_target(0.08, 0.05, beta) == pytest.approx(0.03 / beta)
    assert models.widmark_time_to_target(0.02, 0.05, beta) == 0.0  # already below


def test_widmark_empty_and_scalar_shapes():
    assert models.widmark_bac(5.0, [], r=0.68, mass_kg=70, beta=0.015) == 0.0
    arr = models.widmark_bac(np.array([0.0, 1.0]), [(0.0, 14.0)], 0.68, 70, 0.015)
    assert isinstance(arr, np.ndarray) and arr.shape == (2,)
