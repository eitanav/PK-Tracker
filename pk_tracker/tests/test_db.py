"""Tests for the SQLite persistence layer."""

from datetime import datetime, timedelta, timezone

import pytest

from pk_tracker.core.engine import UserProfile
from pk_tracker.core.substances import Preset, Substance
from pk_tracker.data.db import Database

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.sqlite")
    yield database
    database.close()


def test_seeds_builtin_substances(db):
    subs = db.load_substances()
    assert "caffeine" in subs and "alcohol" in subs and "methylphenidate" in subs
    caf = subs["caffeine"]
    assert caf.is_builtin and caf.redose_eligible
    assert caf.ka == pytest.approx(5.0)
    # Presets came across too.
    assert any(p.label == "Espresso" for p in caf.presets)


def test_seed_is_idempotent(tmp_path):
    path = tmp_path / "seed.sqlite"
    Database(path).close()
    db2 = Database(path)  # second open should not double-seed
    counts = db2.conn.execute("SELECT COUNT(*) FROM substances").fetchone()[0]
    assert counts == len(db2.load_substances())
    db2.close()


def test_dose_crud_round_trip(db):
    dose = db.add_dose("caffeine", 90.0, "mg", NOW, note="morning")
    assert dose.id is not None

    doses = db.list_doses("caffeine")
    assert len(doses) == 1
    assert doses[0].amount == 90.0
    assert doses[0].taken_at == NOW           # tz-aware round trip
    assert doses[0].note == "morning"

    # Edit the timestamp ("I drank this 20 minutes ago").
    db.update_dose(dose.id, taken_at=NOW - timedelta(minutes=20), amount=80.0)
    edited = db.list_doses("caffeine")[0]
    assert edited.amount == 80.0
    assert edited.taken_at == NOW - timedelta(minutes=20)

    db.delete_dose(dose.id)
    assert db.list_doses("caffeine") == []


def test_list_doses_filters_by_substance_and_time(db):
    db.add_dose("caffeine", 90, "mg", NOW - timedelta(hours=5))
    db.add_dose("caffeine", 60, "mg", NOW - timedelta(hours=1))
    db.add_dose("alcohol", 14, "g", NOW - timedelta(hours=2))

    assert len(db.list_doses("caffeine")) == 2
    assert len(db.list_doses()) == 3
    recent = db.list_doses(since=NOW - timedelta(hours=3))
    assert len(recent) == 2  # the 5h-old caffeine is excluded


def test_profile_round_trip_including_tolerance(db):
    profile = UserProfile(body_mass_kg=82.0, sex="female", beta=0.018)
    profile.tolerance = {"caffeine": 1.4, "alcohol": 1.2}
    db.save_profile(profile)

    loaded = db.get_profile()
    assert loaded.body_mass_kg == 82.0
    assert loaded.sex == "female"
    assert loaded.beta == pytest.approx(0.018)
    assert loaded.widmark_r() == loaded.r_female
    assert loaded.tolerance_for("caffeine") == pytest.approx(1.4)
    assert loaded.tolerance_for("unknown") == 1.0  # default


def test_custom_substance_persists(db):
    custom = Substance(
        id="yerba_mate", name="Yerba Mate", model="one_compartment",
        half_life_h=5.0, ka=4.0, ke=0.139, f=0.9, v_l_per_kg=0.6,
        ec50=1.0, redose_eligible=True, is_builtin=False, unit="mg",
        presets=[Preset("Gourd", 70.0, "mg")],
    )
    db.add_substance(custom)
    again = db.get_substance("yerba_mate")
    assert again is not None
    assert again.name == "Yerba Mate"
    assert again.redose_eligible is True
    assert again.is_builtin is False
    assert again.presets[0].label == "Gourd"


def test_deleting_substance_cascades_to_doses(db):
    db.add_dose("methylphenidate", 10, "mg", NOW)
    assert len(db.list_doses("methylphenidate")) == 1
    db.delete_substance("methylphenidate")
    assert db.list_doses("methylphenidate") == []
