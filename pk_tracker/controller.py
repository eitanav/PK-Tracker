"""Application service layer between the UI and the core/data layers.

The UI talks to an :class:`AppController`, never to the database or the math
directly. The controller owns the cached substance library and user profile,
builds timelines on demand, and forwards to the scheduler. It runs no loop and
holds no simulation state: every call recomputes from the persisted dose log.
"""

from __future__ import annotations

from datetime import datetime, timezone

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

    # ----- timelines + derived info -----------------------------------------
    def timeline(self, substance_id: str, doses: list[Dose] | None = None) -> SubstanceTimeline:
        if doses is None:
            doses = self.db.list_doses(substance_id)
        return SubstanceTimeline(self.substances[substance_id], doses, self.profile)

    def redose_info(self, substance_id: str, now: datetime | None = None):
        return scheduler.redose_info(self.timeline(substance_id), now or now_utc())

    def sleep_cutoff(self, substance_id, bedtime, amount=None, now=None):
        return scheduler.sleep_cutoff(
            self.timeline(substance_id), now or now_utc(), bedtime, amount=amount
        )

    def overload_info(self, substance_id, now=None):
        return scheduler.overload_info(self.timeline(substance_id), now or now_utc())

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
