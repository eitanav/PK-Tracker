"""Formatting helpers that turn engine/scheduler output into UI strings.

Shared by the main window and the floating widget so both present the same
numbers and the same substance-aware "next action" (which respects scope:
caffeine gets a redose nudge, alcohol gets a sober-time, stimulants get a
peak / sleep-safe time — never a redose nudge).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from ..core import scheduler
from .theme import COLORS


def _forward_peak(tl, now: datetime, hours: float = 16.0) -> datetime | None:
    """Time of the next concentration maximum ahead of ``now``, if it is still
    climbing to one (handles the extended-release second pulse). None if the
    curve is already past its peak and only declining."""
    res = tl.curve(now, now + timedelta(hours=hours), 160)
    conc = res.concentration
    if conc.size == 0:
        return None
    imax = int(np.argmax(conc))
    if imax > 1 and conc[imax] > float(conc[0]) * 1.02:
        return datetime.fromtimestamp(res.x[imax], tz=timezone.utc)
    return None


def fmt_clock(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone().strftime("%H:%M")


def fmt_delta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def current_readout(controller, sid: str, now: datetime) -> dict:
    """Concentration, effect %, time-since-last, projected peak for the readout."""
    sub = controller.substance(sid)
    tl = controller.timeline(sid)
    conc = float(tl.concentration_at(now))
    out = {
        "conc_value": conc * sub.conc_scale,
        "conc_unit": sub.conc_unit,
        "effect_pct": None,
        "since_last": "—",
        "peak_at": "—",
        "has_doses": bool(tl.doses),
        # Caffeine/stimulant mass in the body (mg) — the primary, concrete metric.
        # None for alcohol (Widmark) and any substance with no distribution volume.
        "body_mg": None if (sub.is_alcohol or sub.v_l_per_kg is None) else float(tl.body_amount_at(now)),
    }
    pct = tl.effect_percent_of_peak(now, now=now)
    if pct is not None:
        out["effect_pct"] = pct

    last = tl.last_dose()
    if last is not None:
        out["since_last"] = fmt_delta((now - last.taken_at).total_seconds())
        # Projected peak only makes sense for the absorbing one-compartment
        # models; scan the curve so it is right for IR and ER (bimodal) alike.
        if sub.ka is not None:
            peak_dt = _forward_peak(tl, now)
            if peak_dt is not None:
                out["peak_at"] = fmt_clock(peak_dt)
    return out


def next_action(controller, sid: str, now: datetime):
    """Return (label, value, color) for the single most relevant upcoming event."""
    sub = controller.substance(sid)
    tl = controller.timeline(sid)
    if not tl.doses:
        return None

    # Caffeine / opted-in stimulants: redose nudge.
    if sub.redose_eligible:
        ri = controller.redose_info(sid, now)
        if ri.overdue:
            return ("Redose", "now", COLORS["warn"])
        if ri.redose_at is not None:
            return ("Redose ~", fmt_clock(ri.redose_at), COLORS["accent"])
        return None

    # Alcohol: clearance only, never a "drink" prompt.
    if sub.is_alcohol:
        pred = controller.alcohol_predictions(sid, now)
        if pred is None or pred.bac_now <= 0:
            return ("Sober", "yes", COLORS["good"])
        if pred.over_limit:
            return ("Under limit ~", fmt_clock(pred.time_to_limit), COLORS["warn"])
        return ("Sober ~", fmt_clock(pred.time_to_zero), COLORS["accent"])

    # Prescription stimulants: peak, then sleep-safe. No dosing prompt. Both are
    # read off the actual curve so the extended-release second pulse is handled.
    peak_dt = _forward_peak(tl, now)
    if peak_dt is not None:
        return ("Peak ~", fmt_clock(peak_dt), COLORS["accent"])
    if sub.sleep_threshold is not None and float(tl.concentration_at(now)) > sub.sleep_threshold:
        dt = scheduler.time_below_level(tl, now, sub.sleep_threshold)
        if dt is not None:
            return ("Sleep-safe ~", fmt_clock(dt), COLORS["accent"])
    return ("Clearing", "—", COLORS["subtext"])
