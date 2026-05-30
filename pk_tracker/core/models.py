"""Pure pharmacokinetic / pharmacodynamic math.

This module is the heart of the project. It contains *only* math: closed-form
analytic models evaluated at arbitrary times. There is no UI, no database, no
global state, and no background loop. Everything here is a pure function of its
arguments, which makes it trivially unit-testable and means the rest of the app
can recompute the world from scratch at any moment.

Conventions
-----------
* Time is in **hours** unless stated otherwise.
* Concentration is in **mg/L** for the one-compartment model.
* Blood alcohol concentration (BAC) is in **g/dL** (the Widmark convention).
* All public functions accept either a Python scalar or a NumPy array for the
  time argument and return the same shape back (scalar in -> scalar out).

The two model families
----------------------
1. Linear one-compartment model with first-order absorption (the *Bateman*
   function). Used for caffeine and methylphenidate. Because it is linear,
   multiple doses combine by **superposition**.
2. Widmark zero-order elimination for alcohol. The metabolising enzyme
   saturates after the first drink, so elimination is a constant rate (a
   straight line down) rather than exponential. Superposition does **not**
   hold, so alcohol gets its own accumulation routine.
"""

from __future__ import annotations

import numpy as np

# Below this absolute difference between ka and ke we treat them as equal and
# use the analytic limit of the Bateman function (which otherwise has a
# removable 0/0 singularity at ka == ke).
_KA_KE_EPS = 1e-6

LN2 = float(np.log(2.0))


# --------------------------------------------------------------------------- #
# Small shape helpers
# --------------------------------------------------------------------------- #
def _as_array(t):
    """Return (1-D float array, was_scalar) for a scalar or array-like input."""
    arr = np.asarray(t, dtype=float)
    return np.atleast_1d(arr), arr.ndim == 0


def _restore(values: np.ndarray, was_scalar: bool):
    """Collapse a length-1 array back to a Python float if the input was scalar."""
    return float(values[0]) if was_scalar else values


# --------------------------------------------------------------------------- #
# Rate-constant conversions
# --------------------------------------------------------------------------- #
def ke_from_half_life(half_life_h: float) -> float:
    """Elimination rate constant (1/h) from an elimination half-life (h)."""
    if half_life_h <= 0:
        raise ValueError("half_life_h must be positive")
    return LN2 / half_life_h


def half_life_from_ke(ke: float) -> float:
    """Elimination half-life (h) from an elimination rate constant (1/h)."""
    if ke <= 0:
        raise ValueError("ke must be positive")
    return LN2 / ke


# --------------------------------------------------------------------------- #
# One-compartment model, first-order absorption (the Bateman function)
# --------------------------------------------------------------------------- #
def bateman_single(t, dose, f, v, ka, ke):
    """Single-dose blood concentration (mg/L) at time ``t`` hours post-ingestion.

    C(t) = (F*D*ka) / (V*(ka-ke)) * (exp(-ke*t) - exp(-ka*t))      for t >= 0

    For t < 0 (before the dose) the contribution is 0. When ``ka`` and ``ke``
    are numerically equal the formula above is 0/0, so we fall back to its
    analytic limit C(t) = (F*D*ka/V) * t * exp(-ka*t).

    Parameters
    ----------
    t     : scalar or array, hours since ingestion.
    dose  : dose amount in mg.
    f     : bioavailability (fraction absorbed, 0..1).
    v     : volume of distribution in L.
    ka    : absorption rate constant (1/h).
    ke    : elimination rate constant (1/h).
    """
    if v <= 0:
        raise ValueError("volume of distribution v must be positive")
    if ka <= 0 or ke <= 0:
        raise ValueError("ka and ke must be positive")

    t_arr, scalar = _as_array(t)
    c = np.zeros_like(t_arr)
    pos = t_arr >= 0.0
    tp = t_arr[pos]

    if abs(ka - ke) < _KA_KE_EPS:
        k = ka
        c[pos] = (f * dose * k / v) * tp * np.exp(-k * tp)
    else:
        coef = (f * dose * ka) / (v * (ka - ke))
        c[pos] = coef * (np.exp(-ke * tp) - np.exp(-ka * tp))

    # Guard against tiny negative values from floating-point cancellation.
    np.maximum(c, 0.0, out=c)
    return _restore(c, scalar)


def tmax_single(ka, ke) -> float:
    """Time of peak concentration (hours) for a single dose.

    Tmax = ln(ka/ke) / (ka - ke), with the limit 1/ka when ka == ke.
    """
    if ka <= 0 or ke <= 0:
        raise ValueError("ka and ke must be positive")
    if abs(ka - ke) < _KA_KE_EPS:
        return 1.0 / ka
    return float(np.log(ka / ke) / (ka - ke))


def cmax_single(dose, f, v, ka, ke) -> float:
    """Peak concentration (mg/L) for a single dose (value of C at Tmax)."""
    return float(bateman_single(tmax_single(ka, ke), dose, f, v, ka, ke))


def superpose(t, dose_events, f, v, ka, ke):
    """Total concentration (mg/L) from many doses of one linear substance.

    Linear kinetics means doses do not interact: the total is just the sum of
    each single-dose curve shifted to its own ingestion time.

        C_total(t) = sum_i  C_single(t - t_i)

    Parameters
    ----------
    t           : scalar or array, absolute time in hours (same clock as t_i).
    dose_events : iterable of (t_i_hours, amount_mg) pairs.
    f, v, ka, ke: shared substance parameters.
    """
    t_arr, scalar = _as_array(t)
    total = np.zeros_like(t_arr)
    for t_i, amount in dose_events:
        total += np.atleast_1d(bateman_single(t_arr - t_i, amount, f, v, ka, ke))
    return _restore(total, scalar)


def time_to_decay_to(c_current: float, c_target: float, ke: float) -> float:
    """Hours for a concentration to decay from ``c_current`` to ``c_target``.

    Pure first-order elimination only (the absorption phase is assumed over):

        t = (1/ke) * ln(c_current / c_target)

    Returns 0.0 if already at or below the target. Returns +inf if the target
    is zero (an exponential never actually reaches zero).
    """
    if ke <= 0:
        raise ValueError("ke must be positive")
    if c_current <= 0 or c_target >= c_current:
        return 0.0
    if c_target <= 0:
        return float("inf")
    return float((1.0 / ke) * np.log(c_current / c_target))


# --------------------------------------------------------------------------- #
# Pharmacodynamics: perceived effect (Emax with a tolerance-shifted EC50)
# --------------------------------------------------------------------------- #
def emax_effect(concentration, emax: float, ec50: float, tolerance_factor: float):
    """Perceived effect from a blood concentration (a saturating Emax curve).

        Effect = Emax * C / (EC50 * tolerance_factor + C)

    ``tolerance_factor`` shifts the half-maximal concentration EC50:
        * 0.5  -> sensitive / naive user (a little goes a long way)
        * 1.0  -> baseline
        * 1.5  -> habituated user (needs more for the same effect)

    Tolerance is a *pharmacodynamic* phenomenon: it changes how concentration
    maps to felt effect. It must never touch ke or the concentration curve.
    """
    if ec50 <= 0:
        raise ValueError("ec50 must be positive")
    if tolerance_factor <= 0:
        raise ValueError("tolerance_factor must be positive")
    c = np.asarray(concentration, dtype=float)
    denom = ec50 * tolerance_factor + c
    eff = np.where(denom > 0, emax * c / denom, 0.0)
    if c.ndim == 0:
        return float(eff)
    return eff


# --------------------------------------------------------------------------- #
# Alcohol: Widmark zero-order model
# --------------------------------------------------------------------------- #
# Density of ethanol at room temperature, g/mL. Used to convert a drink's
# volume and ABV into grams of pure ethanol.
ETHANOL_DENSITY_G_PER_ML = 0.789


def grams_ethanol(volume_ml: float, abv_percent: float) -> float:
    """Grams of pure ethanol in a drink.

        A = volume_ml * (abv% / 100) * 0.789
    """
    if volume_ml < 0 or abv_percent < 0:
        raise ValueError("volume and abv must be non-negative")
    return volume_ml * (abv_percent / 100.0) * ETHANOL_DENSITY_G_PER_ML


def widmark_bac(t, drink_events, r: float, mass_kg: float, beta: float = 0.015):
    """Blood alcohol concentration (g/dL) under the Widmark model.

    Elimination is zero-order: BAC falls along a straight line at ``beta`` g/dL
    per hour, floored at zero. Each drink is modelled as instantaneous
    absorption (a step up in BAC). Because elimination saturates, drinks do not
    superpose the way linear doses do, so this walks the piecewise-linear
    trajectory forward through the drink timeline.

    Single-drink height: A / (r * M * 10), where the factor of 10 converts the
    classic g/kg (~g/L) Widmark result into g/dL.

    Parameters
    ----------
    t            : scalar or array, absolute time in hours (same clock as t_i).
    drink_events : iterable of (t_i_hours, grams_ethanol) pairs.
    r            : Widmark distribution ratio (~0.68 male, ~0.55 female).
    mass_kg      : body mass in kg.
    beta         : elimination rate in g/dL/h (default 0.015).
    """
    if r <= 0 or mass_kg <= 0:
        raise ValueError("r and mass_kg must be positive")
    if beta <= 0:
        raise ValueError("beta must be positive")

    t_arr, scalar = _as_array(t)
    events = sorted(drink_events, key=lambda d: d[0])
    if not events:
        return _restore(np.zeros_like(t_arr), scalar)

    event_t = np.array([e[0] for e in events], dtype=float)
    bumps = np.array([e[1] for e in events], dtype=float) / (r * mass_kg * 10.0)

    # BAC immediately *after* each drink, walking the trajectory forward and
    # flooring at zero between drinks.
    bac_after = np.empty(len(events))
    prev_t = None
    prev_b = 0.0
    for i, (te, bump) in enumerate(zip(event_t, bumps)):
        if prev_t is None:
            b = bump
        else:
            b = max(0.0, prev_b - beta * (te - prev_t)) + bump
        bac_after[i] = b
        prev_t, prev_b = te, b

    out = np.zeros_like(t_arr)
    # For each query time, find the most recent drink at or before it, then
    # decay from that drink's post-level (floored at zero).
    idx = np.searchsorted(event_t, t_arr, side="right") - 1
    valid = idx >= 0
    j = idx[valid]
    out[valid] = np.maximum(0.0, bac_after[j] - beta * (t_arr[valid] - event_t[j]))
    return _restore(out, scalar)


def widmark_time_to_target(bac_now: float, target: float, beta: float = 0.015) -> float:
    """Hours from now for BAC to fall to ``target`` g/dL, assuming no more drinks.

    Zero-order elimination is a straight line, so this is just the vertical drop
    divided by the slope. Returns 0.0 if already at or below the target.
    """
    if beta <= 0:
        raise ValueError("beta must be positive")
    if bac_now <= target:
        return 0.0
    return float((bac_now - target) / beta)
