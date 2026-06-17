"""Validation and migration guardrails for persistence-layer inputs."""

from datetime import datetime, timezone

import pytest

from pk_tracker.core.engine import UserProfile
from pk_tracker.core.substances import Substance
from pk_tracker.data.db import Database, SCHEMA_VERSION

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def test_schema_version_is_recorded(tmp_path):
    db = Database(tmp_path / "version.sqlite")
    try:
        assert db.schema_version() == SCHEMA_VERSION
    finally:
        db.close()


def test_rejects_nonpositive_dose(tmp_path):
    db = Database(tmp_path / "dose.sqlite")
    try:
        with pytest.raises(ValueError, match="dose amount"):
            db.add_dose("caffeine", 0, "mg", NOW)
    finally:
        db.close()


def test_rejects_naive_dose_timestamp(tmp_path):
    db = Database(tmp_path / "time.sqlite")
    try:
        with pytest.raises(ValueError, match="timezone-aware"):
            db.add_dose("caffeine", 90, "mg", datetime(2026, 5, 30, 12, 0))
    finally:
        db.close()


def test_rejects_invalid_profile_values(tmp_path):
    db = Database(tmp_path / "profile.sqlite")
    try:
        with pytest.raises(ValueError, match="body_mass_kg"):
            db.save_profile(UserProfile(body_mass_kg=5))
        profile = UserProfile()
        profile.tolerance = {"caffeine": 2.0}
        with pytest.raises(ValueError, match="tolerance"):
            db.save_profile(profile)
    finally:
        db.close()


def test_rejects_invalid_custom_substance(tmp_path):
    db = Database(tmp_path / "substance.sqlite")
    try:
        bad = Substance(
            id="bad", name="Bad", model="one_compartment",
            half_life_h=5.0, ka=0.0, ke=0.1, f=0.9, v_l_per_kg=0.6,
            ec50=1.0,
        )
        with pytest.raises(ValueError, match="ka"):
            db.add_substance(bad)
    finally:
        db.close()
