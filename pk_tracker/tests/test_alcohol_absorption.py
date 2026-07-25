"""Alcohol absorption: the shape of the rising limb, checked against the literature.

Widmark elimination is zero-order, so the *falling* limb is a straight line by
design -- that part is not a bug and these tests pin it down so it is not
"fixed" into an exponential later. What the tests guard is the *rising* limb:
absorption is not instantaneous, and the peak must land roughly half an hour
after the drink rather than at the first sip.

Reference figures for one US standard drink (14 g ethanol) in a 70 kg man:
peak BAC ~0.02-0.03 g/dL reached around 30-45 min on an empty stomach, falling
at ~0.015 g/dL/h, sober after roughly two hours.
"""

from __future__ import annotations

import numpy as np

from pk_tracker.core.engine import DEFAULT_ALCOHOL_RAMP_MIN, UserProfile
from pk_tracker.core.models import widmark_bac

STANDARD_DRINK_G = 14.0
MASS_KG = 70.0
R_MALE = 0.68
BETA = 0.015


def _curve(ramp_h, hours=4.0, step=1 / 60):
    t = np.arange(0, hours + step, step)
    bac = widmark_bac(
        t, [(0.0, STANDARD_DRINK_G)], r=R_MALE, mass_kg=MASS_KG, beta=BETA, ramp_h=ramp_h
    )
    return t, bac


def test_default_absorption_is_not_instantaneous():
    # The whole point of the fix: 0 meant the peak landed at the first sip.
    assert DEFAULT_ALCOHOL_RAMP_MIN > 0
    assert UserProfile().alcohol_ramp_min == DEFAULT_ALCOHOL_RAMP_MIN


def test_peak_arrives_around_half_an_hour_not_immediately():
    t, bac = _curve(DEFAULT_ALCOHOL_RAMP_MIN / 60.0)
    peak_h = t[int(np.argmax(bac))]
    assert 0.25 <= peak_h <= 0.75, f"peak at {peak_h:.2f} h, expected ~0.5 h"


def test_bac_rises_before_it_falls():
    _t, bac = _curve(DEFAULT_ALCOHOL_RAMP_MIN / 60.0)
    peak_i = int(np.argmax(bac))
    assert peak_i > 0, "curve starts at its peak -- absorption is being skipped"
    rising = bac[: peak_i + 1]
    assert np.all(np.diff(rising) >= -1e-12), "the rising limb must not dip"


def test_peak_magnitude_matches_the_literature():
    _t, bac = _curve(DEFAULT_ALCOHOL_RAMP_MIN / 60.0)
    # One standard drink in a 70 kg man: about 0.02-0.03 g/dL.
    assert 0.018 <= bac.max() <= 0.030, f"peak {bac.max():.4f} g/dL out of range"


def test_instant_absorption_overstates_the_first_hour():
    """The behaviour that was wrong, kept as a guard against regressing to it."""
    _t, instant = _curve(0.0)
    _t2, ramped = _curve(DEFAULT_ALCOHOL_RAMP_MIN / 60.0)
    assert instant.max() > ramped.max()
    # ...and the old default peaked immediately, which is what looked wrong.
    assert int(np.argmax(instant)) == 0


def test_elimination_stays_zero_order_and_linear():
    """Zero-order elimination is correct physiology; the decline must stay straight."""
    t, bac = _curve(DEFAULT_ALCOHOL_RAMP_MIN / 60.0)
    peak_i = int(np.argmax(bac))
    # Sample the falling limb while it is still above zero.
    falling = [(ti, b) for ti, b in zip(t[peak_i:], bac[peak_i:]) if b > 1e-6]
    slopes = [
        (b2 - b1) / (t2 - t1)
        for (t1, b1), (t2, b2) in zip(falling, falling[1:])
    ]
    assert slopes, "no falling limb to check"
    assert np.allclose(slopes, -BETA, atol=1e-6), "decline is not a constant rate"


def test_existing_profile_is_migrated_off_the_old_instant_default(tmp_path):
    """A saved profile carries the old 0 explicitly, so the new default alone
    would never reach an existing user."""
    from pk_tracker.data.db import Database

    path = tmp_path / "old.sqlite"
    db = Database(path)
    profile = db.get_profile()
    profile.alcohol_ramp_min = 0.0
    db.save_profile(profile)
    db.conn.execute("DELETE FROM user_profile WHERE key='migrated_alcohol_ramp'")
    db.conn.commit()
    db.close()

    migrated = Database(path)
    assert migrated.get_profile().alcohol_ramp_min == DEFAULT_ALCOHOL_RAMP_MIN
    migrated.close()


def test_migration_does_not_override_a_deliberate_zero(tmp_path):
    """Someone who chooses instantaneous absorption afterwards keeps it."""
    from pk_tracker.data.db import Database

    path = tmp_path / "chosen.sqlite"
    db = Database(path)          # migration marker written on first open
    profile = db.get_profile()
    profile.alcohol_ramp_min = 0.0
    db.save_profile(profile)
    db.close()

    reopened = Database(path)
    assert reopened.get_profile().alcohol_ramp_min == 0.0
    reopened.close()


def test_time_to_sober_is_about_two_hours_per_drink():
    t, bac = _curve(DEFAULT_ALCOHOL_RAMP_MIN / 60.0)
    sober_h = t[int(np.argmax(bac <= 0.0))] if np.any(bac <= 0.0) else None
    # argmax on the boolean finds the first zero *after* the curve has run.
    nonzero = np.nonzero(bac > 0)[0]
    sober_h = t[nonzero[-1] + 1] if nonzero[-1] + 1 < len(t) else t[-1]
    assert 1.5 <= sober_h <= 2.5, f"sober at {sober_h:.2f} h, expected ~2 h"
