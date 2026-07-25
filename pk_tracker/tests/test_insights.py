"""Tests for the dose-log statistics (pk_tracker.core.insights)."""

from datetime import datetime, time, timedelta, timezone

from pk_tracker.core.engine import Dose
from pk_tracker.core.insights import EMPTY, WINDOW_DAYS, compute_insights

# A fixed instant so every test agrees on what "today" means.
NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.astimezone().date()


def dose(days_ago, hour, minute=0, amount=90.0, sid="caffeine"):
    """A dose at a given *local* wall-clock time, stored as UTC.

    Building it naive and calling ``astimezone()`` attaches the offset actually
    in force on that date, so the hour survives a DST boundary intact.
    """
    local = datetime.combine(TODAY - timedelta(days=days_ago), time(hour, minute)).astimezone()
    return Dose(sid, amount, "mg", local.astimezone(timezone.utc))


def test_empty_log_has_no_data():
    ins = compute_insights([], "caffeine", NOW)
    assert ins is EMPTY
    assert ins.has_data is False
    assert ins.hour_counts == [0] * 24
    assert ins.dow_avg_amount == [0.0] * 7
    assert ins.peak_hours == []
    assert ins.first_dose_minutes is None
    assert ins.streak_days == 0
    assert ins.total_doses == 0


def test_other_substances_are_ignored():
    ins = compute_insights([dose(0, 9, sid="alcohol")], "caffeine", NOW)
    assert ins.has_data is False


def test_window_edges():
    """The window is the last WINDOW_DAYS days inclusive of today."""
    inside = compute_insights([dose(WINDOW_DAYS - 1, 9)], "caffeine", NOW)
    outside = compute_insights([dose(WINDOW_DAYS, 9)], "caffeine", NOW)
    assert inside.total_doses == 1
    assert outside.has_data is False


def test_hour_counts_and_peak_hours():
    doses = [dose(0, 8), dose(1, 8), dose(2, 8), dose(0, 14), dose(1, 14), dose(0, 21)]
    ins = compute_insights(doses, "caffeine", NOW)
    assert ins.hour_counts[8] == 3
    assert ins.hour_counts[14] == 2
    assert ins.hour_counts[21] == 1
    assert sum(ins.hour_counts) == 6
    assert ins.peak_hours == [8, 14, 21]     # busiest first


def test_peak_hours_capped_at_three_and_ties_favour_earlier_hours():
    doses = [dose(d, h) for d in range(4) for h in (7, 9, 11, 13)]
    ins = compute_insights(doses, "caffeine", NOW)
    assert ins.peak_hours == [7, 9, 11]      # all tied; stable, so ascending


def test_weekday_averages_use_daily_totals():
    """Two same-weekday dates average their *daily totals*, not their doses."""
    doses = [dose(0, 8, amount=50.0), dose(0, 15, amount=50.0), dose(7, 8, amount=200.0)]
    ins = compute_insights(doses, "caffeine", NOW)
    weekday = TODAY.weekday()
    assert ins.dow_avg_amount[weekday] == 150.0
    assert sum(ins.dow_avg_amount) == 150.0   # every other weekday stays 0


def test_avg_per_day_counts_active_days_only():
    doses = [dose(0, 8), dose(0, 12), dose(0, 17), dose(5, 8), dose(5, 12)]
    ins = compute_insights(doses, "caffeine", NOW)
    assert ins.avg_per_day == 2.5             # 5 doses over 2 active days


def test_week_amount_covers_the_last_seven_days():
    doses = [dose(0, 8, amount=100.0), dose(6, 8, amount=10.0), dose(7, 8, amount=999.0)]
    ins = compute_insights(doses, "caffeine", NOW)
    assert ins.week_amount == 110.0


def test_first_dose_minutes_averages_each_day_first():
    doses = [dose(0, 7, 30), dose(0, 16, 0), dose(1, 8, 30), dose(1, 9, 0)]
    ins = compute_insights(doses, "caffeine", NOW)
    assert ins.first_dose_minutes == 480      # mean of 07:30 and 08:30


def test_streak_counts_consecutive_days_back_from_today():
    ins = compute_insights([dose(d, 9) for d in range(4)], "caffeine", NOW)
    assert ins.streak_days == 4


def test_streak_is_zero_without_a_dose_today():
    ins = compute_insights([dose(d, 9) for d in (1, 2, 3)], "caffeine", NOW)
    assert ins.streak_days == 0
    assert ins.has_data is True


def test_streak_stops_at_the_first_gap():
    ins = compute_insights([dose(d, 9) for d in (0, 1, 3, 4)], "caffeine", NOW)
    assert ins.streak_days == 2
