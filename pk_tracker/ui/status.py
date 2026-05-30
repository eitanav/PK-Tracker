"""Formatting helpers that turn engine/scheduler output into UI strings.

Shared by the main window and the floating widget so both present the same
numbers and the same substance-aware "next action" (which respects scope:
caffeine gets a redose nudge, alcohol gets a sober-time, stimulants get a
peak / sleep-safe time — never a redose nudge).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..core import models
from .theme import COLORS


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
    }
    pct = tl.effect_percent_of_peak(now, now=now)
    if pct is not None:
        out["effect_pct"] = pct

    last = tl.last_dose()
    if last is not None:
        out["since_last"] = fmt_delta((now - last.taken_at).total_seconds())
        # Projected peak only makes sense for the absorbing one-compartment model.
        if sub.ka is not None:
            peak_at = last.taken_at.timestamp() + models.tmax_single(sub.ka, sub.ke_value()) * 3600
            peak_dt = datetime.fromtimestamp(peak_at, tz=timezone.utc)
            if peak_dt > now:
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

    # Prescription stimulants: peak, then sleep-safe. No dosing prompt.
    last = tl.last_dose()
    peak_at = last.taken_at.timestamp() + models.tmax_single(sub.ka, sub.ke_value()) * 3600
    peak_dt = datetime.fromtimestamp(peak_at, tz=timezone.utc)
    if peak_dt > now:
        return ("Peak ~", fmt_clock(peak_dt), COLORS["accent"])
    if sub.sleep_threshold is not None:
        conc = float(tl.concentration_at(now))
        if conc > sub.sleep_threshold:
            hrs = models.time_to_decay_to(conc, sub.sleep_threshold, sub.ke_value())
            from datetime import timedelta

            return ("Sleep-safe ~", fmt_clock(now + timedelta(hours=hrs)), COLORS["accent"])
    return ("Clearing", "—", COLORS["subtext"])
