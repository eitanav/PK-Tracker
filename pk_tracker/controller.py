"""Application service layer between the UI and the core/data layers.

The UI talks to an :class:`AppController`, never to the database or the math
directly. The controller owns the cached substance library and user profile,
builds timelines on demand, and forwards to the scheduler. It runs no loop and
holds no simulation state: every call recomputes from the persisted dose log.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .core import scheduler
from .core.engine import Dose, SubstanceTimeline, UserProfile
from .core.substances import (
    DEFAULT_LIBRARY_PATH,
    Substance,
    load_substances,
    save_substances,
)
from .data.db import Database


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Research-grounded default ceilings for how much caffeine may still be in the
# body at bedtime (mg), by self-reported sleep sensitivity. Derived from dose/
# timing sleep studies (see the Settings "Sleep cutoff" help text).
SLEEP_SENSITIVITY_MG = {"sensitive": 25.0, "average": 50.0, "resistant": 100.0}


class AppController:
    def __init__(self, db: Database):
        self.db = db
        self.substances: dict[str, Substance] = {}
        self.profile = UserProfile()
        self.reload()

    # ----- cache -------------------------------------------------------------
    def reload(self) -> None:
        self.substances = self.db.load_substances()
        self.profile = self.db.get_profile()

    def ordered_substances(self) -> list[Substance]:
        return list(self.substances.values())

    def substance(self, substance_id: str) -> Substance:
        return self.substances[substance_id]

    # ----- doses -------------------------------------------------------------
    def doses(self, substance_id: str) -> list[Dose]:
        return self.db.list_doses(substance_id)

    def log_dose(
        self, substance_id: str, amount: float,
        unit: str | None = None, taken_at: datetime | None = None, note: str = "",
    ) -> Dose:
        sub = self.substances[substance_id]
        return self.db.add_dose(
            substance_id, amount, unit or sub.unit, taken_at or now_utc(), note
        )

    def update_dose(self, dose_id: int, **kw) -> None:
        self.db.update_dose(dose_id, **kw)

    def delete_dose(self, dose_id: int) -> None:
        self.db.delete_dose(dose_id)

    def undo_last_dose(self, substance_id: str | None = None):
        """Delete the most recently logged dose (highest id) and return it."""
        doses = self.db.list_doses(substance_id)
        if not doses:
            return None
        last = max(doses, key=lambda d: d.id or 0)
        self.db.delete_dose(last.id)
        return last

    def daily_total_mg(self, substance_id: str, now: datetime | None = None) -> float:
        """Sum of doses logged since local midnight today (mg)."""
        now = now or now_utc()
        local_midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        doses = self.db.list_doses(substance_id, since=local_midnight.astimezone(timezone.utc))
        return float(sum(d.amount for d in doses))

    # ----- timelines + derived info -----------------------------------------
    def timeline(self, substance_id: str, doses: list[Dose] | None = None) -> SubstanceTimeline:
        if doses is None:
            doses = self.db.list_doses(substance_id)
        return SubstanceTimeline(self.substances[substance_id], doses, self.profile)

    def redose_info(self, substance_id: str, now: datetime | None = None):
        return scheduler.redose_info(self.timeline(substance_id), now or now_utc())

    def sleep_cutoff(self, substance_id, bedtime, *, mode="mg", target_mg=50.0,
                     hours=8.0, amount=None, now=None):
        """Latest sensible dose time before ``bedtime``.

        ``mode`` selects the mental model:
          * ``"mg"`` / ``"preset"`` — keep caffeine in the body at bedtime at or
            below ``target_mg`` mg (dose-aware; accounts for what's already logged).
          * ``"hours"`` — a flat "stop ``hours`` before bed" rule.
        """
        tl = self.timeline(substance_id)
        now = now or now_utc()
        if mode == "hours":
            return scheduler.sleep_cutoff_hours(tl, now, bedtime, hours=hours, amount=amount)
        v = self.substances[substance_id].volume_liters(self.profile.body_mass_kg)
        abs_conc = (target_mg / v) if v else None      # mg in body -> mg/L ceiling
        return scheduler.sleep_cutoff(tl, now, bedtime, amount=amount, absolute_target=abs_conc)

    def _next_local_time(self, now: datetime, hour: int, minute: int) -> datetime:
        local = now.astimezone()
        cand = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cand <= local:
            cand += timedelta(days=1)
        return cand.astimezone(timezone.utc)

    def sleep_cutoff_from_settings(self, substance_id, now=None):
        """Compute the sleep cutoff from the saved UI settings (shared by the
        dashboard and the floating widget so both show the same 'latest coffee')."""
        now = now or now_utc()
        mode = self.get_setting("ui_sleep_mode", "mg")
        hh, mm = (int(x) for x in self.get_setting("ui_bedtime", "23:00").split(":"))
        hours = float(self.get_setting("ui_sleep_hours", "8"))
        if mode == "preset":
            sens = self.get_setting("ui_sleep_sensitivity", "average")
            target_mg = SLEEP_SENSITIVITY_MG.get(sens, 50.0)
        else:
            target_mg = float(self.get_setting("ui_sleep_mg", "50"))
        bedtime = self._next_local_time(now, hh, mm)
        return self.sleep_cutoff(substance_id, bedtime, mode=mode, target_mg=target_mg,
                                 hours=hours, now=now)

    def concentration_to_mg(self, substance_id, conc) -> float:
        """Convert a model concentration to mg in the body, for display."""
        v = self.substances[substance_id].volume_liters(self.profile.body_mass_kg)
        return float(conc) * (v or 0.0)

    def overload_info(self, substance_id, now=None):
        return scheduler.overload_info(self.timeline(substance_id), now or now_utc())

    def perfect_timing(self, substance_id, target_time, amount, now=None):
        return scheduler.perfect_timing(
            self.timeline(substance_id), now or now_utc(), target_time, amount,
        )

    def alcohol_predictions(self, substance_id, now=None):
        return scheduler.alcohol_predictions(self.timeline(substance_id), now or now_utc())

    # ----- profile / substances ---------------------------------------------
    def save_profile(self, profile: UserProfile) -> None:
        self.db.save_profile(profile)
        self.reload()

    def save_substance(self, sub: Substance, *, export_json: bool = True) -> None:
        self.db.update_substance(sub)
        self.reload()
        if export_json:
            # Keep the human-editable JSON library in sync with user additions.
            try:
                library = load_substances(DEFAULT_LIBRARY_PATH)
            except FileNotFoundError:
                library = {}
            library[sub.id] = sub
            save_substances(library, DEFAULT_LIBRARY_PATH)

    # ----- UI settings passthrough ------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self.db.get_setting(key, default)

    def set_setting(self, key: str, value) -> None:
        self.db.set_setting(key, value)
