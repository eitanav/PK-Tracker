"""Dose-log statistics: the log turned into patterns.

Pure functions over a list of :class:`Dose` objects. No database, no UI, and no
clock of its own — ``now`` is always passed in — so this is trivially testable
and can be called from anywhere without a controller.

Deliberately mirrors the Android app's ``computeInsights`` so both apps report
the same numbers from the same log: same 30-day window, same weekday indexing
(Mon=0), same tie-breaking for the busiest hours.

Everything is bucketed in **local time**. "The hours you actually reach for it"
and "your weekly rhythm" are questions about a person's day, not about UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .engine import Dose

# How far back the patterns look, and how many hours count as "busiest".
WINDOW_DAYS = 30
PEAK_HOUR_COUNT = 3


@dataclass(frozen=True)
class Insights:
    """Summary statistics for one substance over the recent window."""

    has_data: bool
    hour_counts: list[int] = field(default_factory=lambda: [0] * 24)
    # Mean amount taken on a given weekday, over the days that had any dose.
    dow_avg_amount: list[float] = field(default_factory=lambda: [0.0] * 7)
    avg_per_day: float = 0.0        # doses per *active* day
    week_amount: float = 0.0        # total amount over the last 7 days
    first_dose_minutes: int | None = None   # mean minute-of-day of the day's first dose
    streak_days: int = 0            # consecutive days up to today with at least one dose
    total_doses: int = 0            # doses inside the window
    peak_hours: list[int] = field(default_factory=list)   # busiest first


EMPTY = Insights(has_data=False)


def compute_insights(
    doses: list[Dose], substance_id: str,
    now: datetime | None = None, window_days: int = WINDOW_DAYS,
) -> Insights:
    """Summarise one substance's dose log over the last ``window_days`` days.

    ``doses`` may contain every substance; only ``substance_id`` is counted.
    Returns :data:`EMPTY` when nothing falls inside the window.
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone().date()
    window_start = today - timedelta(days=window_days - 1)

    rows: list[tuple[Dose, datetime]] = []
    for dose in doses:
        if dose.substance_id != substance_id:
            continue
        local = dose.taken_at.astimezone()
        if local.date() >= window_start:
            rows.append((dose, local))
    if not rows:
        return EMPTY

    hour_counts = [0] * 24
    by_date: dict[date, float] = {}
    first_of_date: dict[date, int] = {}
    for dose, local in rows:
        hour_counts[local.hour] += 1
        day = local.date()
        by_date[day] = by_date.get(day, 0.0) + dose.amount
        minute = local.hour * 60 + local.minute
        if minute < first_of_date.get(day, 24 * 60):
            first_of_date[day] = minute

    # Weekday rhythm: average the *daily totals*, not the raw doses, so a day
    # with three coffees counts once at its full amount.
    dow_sum = [0.0] * 7
    dow_days = [0] * 7
    for day, amount in by_date.items():
        i = day.weekday()                       # Mon=0 .. Sun=6
        dow_sum[i] += amount
        dow_days[i] += 1
    dow_avg = [dow_sum[i] / dow_days[i] if dow_days[i] else 0.0 for i in range(7)]

    week_start = today - timedelta(days=6)
    week_amount = float(sum(d.amount for d, local in rows if local.date() >= week_start))

    streak = 0
    day = today
    while day in by_date:
        streak += 1
        day -= timedelta(days=1)

    active_hours = [h for h in range(24) if hour_counts[h]]
    peak_hours = sorted(active_hours, key=lambda h: -hour_counts[h])[:PEAK_HOUR_COUNT]

    return Insights(
        has_data=True,
        hour_counts=hour_counts,
        dow_avg_amount=dow_avg,
        avg_per_day=len(rows) / max(len(by_date), 1),
        week_amount=week_amount,
        first_dose_minutes=int(sum(first_of_date.values()) / len(first_of_date)),
        streak_days=streak,
        total_doses=len(rows),
        peak_hours=peak_hours,
    )
