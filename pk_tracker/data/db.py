"""SQLite access layer.

Thin, explicit wrapper around sqlite3. It owns the schema, seeds the built-in
substances/presets from ``substances.json`` on first run, and provides typed
CRUD that hands back the same dataclasses the engine consumes (``Dose``,
``Substance``, ``UserProfile``). No ORM, no magic — the data model is small and
the SQL is easy to read.

All timestamps are stored as ISO 8601 in UTC and returned as tz-aware
``datetime`` objects.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core.engine import Dose, UserProfile
from ..core.substances import (
    DEFAULT_LIBRARY_PATH,
    Preset,
    Substance,
    load_substances,
)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 3

# Columns of the substances table, in order, used for round-tripping.
_SUBSTANCE_COLUMNS = [
    "id", "name", "model", "half_life_h", "ka", "ke", "f", "v_l_per_kg",
    "frac_ir", "lag_h", "ka2", "ec50", "emax", "redose_eligible", "is_builtin",
    "unit", "conc_unit", "conc_scale", "color", "note", "sleep_threshold",
    "redose_fraction", "overload_amount_mg", "toxicity_threshold",
]

# Columns added after the first release; auto-added to pre-existing databases.
_MIGRATION_COLUMNS = {"frac_ir": "REAL", "lag_h": "REAL", "ka2": "REAL"}

# Profile keys that are plain scalars (everything else is a tolerance_<id> key).
_PROFILE_SCALARS = {
    "body_mass_kg": float,
    "sex": str,
    "r_male": float,
    "r_female": float,
    "beta": float,
    "legal_bac_limit": float,
    "alcohol_ramp_min": float,
}
_TOLERANCE_PREFIX = "tolerance_"
_HALFLIFE_PREFIX = "halflife_"


def default_db_path() -> Path:
    """Per-user database location. Local only, never synced."""
    return Path.home() / ".pk_tracker" / "pk_tracker.sqlite"


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class Database:
    """Owns one SQLite connection and all persistence operations."""

    def __init__(self, path: str | Path = None, *, seed: bool = True):
        self.path = ":memory:" if path is None else str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()
        self._migrate()
        self._set_schema_version()
        if seed:
            self.seed_builtins()

    # ----- schema / seeding --------------------------------------------------
    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.conn.commit()

    def _migrate(self) -> None:
        """Apply lightweight, idempotent migrations for existing user databases."""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(substances)")}
        for col, col_type in _MIGRATION_COLUMNS.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE substances ADD COLUMN {col} {col_type}")
        self._migrate_doses_sync_columns()
        self.conn.commit()

    def _migrate_doses_sync_columns(self) -> None:
        """Add the sync columns (uid/deleted/updated_at) to pre-existing dose
        logs and backfill them, so an old local database becomes mergeable with
        the cloud without losing or duplicating anything. Idempotent."""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(doses)")}
        added = []
        if "uid" not in existing:
            self.conn.execute("ALTER TABLE doses ADD COLUMN uid TEXT")
            added.append("uid")
        if "deleted" not in existing:
            self.conn.execute("ALTER TABLE doses ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        if "updated_at" not in existing:
            self.conn.execute("ALTER TABLE doses ADD COLUMN updated_at TEXT")
            added.append("updated_at")
        if "uid" in added:
            # Give every legacy row a stable global uid.
            for row in self.conn.execute("SELECT id FROM doses WHERE uid IS NULL").fetchall():
                self.conn.execute(
                    "UPDATE doses SET uid = ? WHERE id = ?", (str(uuid.uuid4()), row[0])
                )
        if "updated_at" in added:
            # Seed the stamp from taken_at so ordering is sensible until edited.
            self.conn.execute(
                "UPDATE doses SET updated_at = taken_at WHERE updated_at IS NULL"
            )
        # Index the sync columns now that they are guaranteed to exist (fresh or
        # migrated). CREATE INDEX IF NOT EXISTS keeps this idempotent.
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_doses_uid ON doses(uid)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_doses_updated ON doses(updated_at)")

    def _set_schema_version(self) -> None:
        """Persist the app-level schema version for future migrations/support."""
        self.conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        self.conn.commit()

    def schema_version(self) -> int:
        """Current app-level SQLite schema version."""
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def seed_builtins(self, library_path: str | Path = DEFAULT_LIBRARY_PATH) -> None:
        """Seed substances + presets from the JSON library if the DB is empty."""
        count = self.conn.execute("SELECT COUNT(*) FROM substances").fetchone()[0]
        if count:
            return
        library = load_substances(library_path)
        for sub in library.values():
            self.add_substance(sub, commit=False)
        self.conn.commit()

    # ----- substances --------------------------------------------------------
    def add_substance(self, sub: Substance, *, commit: bool = True) -> None:
        self._validate_substance(sub)
        values = {
            "id": sub.id, "name": sub.name, "model": sub.model,
            "half_life_h": sub.half_life_h, "ka": sub.ka, "ke": sub.ke,
            "f": sub.f, "v_l_per_kg": sub.v_l_per_kg,
            "frac_ir": sub.frac_ir, "lag_h": sub.lag_h, "ka2": sub.ka2,
            "ec50": sub.ec50,
            "emax": sub.emax, "redose_eligible": int(sub.redose_eligible),
            "is_builtin": int(sub.is_builtin), "unit": sub.unit,
            "conc_unit": sub.conc_unit, "conc_scale": sub.conc_scale,
            "color": sub.color, "note": sub.note,
            "sleep_threshold": sub.sleep_threshold,
            "redose_fraction": sub.redose_fraction,
            "overload_amount_mg": sub.overload_amount_mg,
            "toxicity_threshold": sub.toxicity_threshold,
        }
        cols = ", ".join(values)
        placeholders = ", ".join(f":{c}" for c in values)
        self.conn.execute(
            f"INSERT OR REPLACE INTO substances ({cols}) VALUES ({placeholders})", values
        )
        # Reset this substance's presets to match the definition.
        self.conn.execute("DELETE FROM presets WHERE substance_id = ?", (sub.id,))
        for p in sub.presets:
            self.conn.execute(
                "INSERT INTO presets (substance_id, label, amount, unit, volume_ml, abv_percent)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sub.id, p.label, p.amount, p.unit, p.volume_ml, p.abv_percent),
            )
        if commit:
            self.conn.commit()

    def update_substance(self, sub: Substance) -> None:
        self.add_substance(sub)  # INSERT OR REPLACE handles updates

    def delete_substance(self, substance_id: str) -> None:
        self.conn.execute("DELETE FROM substances WHERE id = ?", (substance_id,))
        self.conn.commit()

    def get_substance(self, substance_id: str) -> Substance | None:
        row = self.conn.execute(
            "SELECT * FROM substances WHERE id = ?", (substance_id,)
        ).fetchone()
        return self._row_to_substance(row) if row else None

    def load_substances(self) -> dict[str, Substance]:
        # Built-ins first, each group in insertion (JSON / creation) order so the
        # library reads caffeine, methylphenidate, alcohol, ... and custom ones last.
        rows = self.conn.execute(
            "SELECT * FROM substances ORDER BY is_builtin DESC, rowid"
        ).fetchall()
        return {row["id"]: self._row_to_substance(row) for row in rows}

    def _row_to_substance(self, row: sqlite3.Row) -> Substance:
        presets = [
            Preset(
                label=p["label"], amount=p["amount"], unit=p["unit"],
                volume_ml=p["volume_ml"], abv_percent=p["abv_percent"],
            )
            for p in self.conn.execute(
                "SELECT * FROM presets WHERE substance_id = ? ORDER BY id", (row["id"],)
            ).fetchall()
        ]
        return Substance(
            id=row["id"], name=row["name"], model=row["model"],
            half_life_h=row["half_life_h"], ka=row["ka"], ke=row["ke"],
            f=row["f"], v_l_per_kg=row["v_l_per_kg"],
            frac_ir=row["frac_ir"], lag_h=row["lag_h"], ka2=row["ka2"],
            ec50=row["ec50"],
            emax=row["emax"], redose_eligible=bool(row["redose_eligible"]),
            is_builtin=bool(row["is_builtin"]), unit=row["unit"],
            conc_unit=row["conc_unit"], conc_scale=row["conc_scale"],
            color=row["color"], note=row["note"],
            sleep_threshold=row["sleep_threshold"],
            redose_fraction=row["redose_fraction"],
            overload_amount_mg=row["overload_amount_mg"],
            toxicity_threshold=row["toxicity_threshold"],
            presets=presets,
        )

    # ----- doses -------------------------------------------------------------
    def add_dose(
        self, substance_id: str, amount: float, unit: str,
        taken_at: datetime, note: str = "",
    ) -> Dose:
        self._validate_dose(amount, taken_at)
        now = _to_iso(datetime.now(timezone.utc))
        cur = self.conn.execute(
            "INSERT INTO doses (substance_id, amount, unit, taken_at, note, uid, deleted, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (substance_id, amount, unit, _to_iso(taken_at), note, str(uuid.uuid4()), now),
        )
        self.conn.commit()
        return Dose(substance_id, amount, unit, taken_at, note, id=cur.lastrowid)

    def _bumped_updated_at(self, dose_id: int) -> str:
        """A stamp guaranteed to outrank this row's current one.

        Last-write-wins compares timestamps at the wire format's resolution
        (epoch milliseconds). Two changes to the same row inside one millisecond
        -- log then immediately undo, say -- would otherwise tie, and the second
        change would look no newer than the copy already in the cloud and never
        be pushed. Keeping ``updated_at`` strictly increasing per row makes an
        edit always outrank the version it was derived from.
        """
        now = datetime.now(timezone.utc)
        row = self.conn.execute(
            "SELECT updated_at FROM doses WHERE id = ?", (dose_id,)
        ).fetchone()
        if row and row[0]:
            try:
                floor = _from_iso(row[0]) + timedelta(milliseconds=1)
                now = max(now, floor)
            except ValueError:
                pass
        return _to_iso(now)

    def list_doses(
        self, substance_id: str | None = None, since: datetime | None = None,
    ) -> list[Dose]:
        # Soft-deleted rows are tombstones for sync; never surface them here.
        clauses, params = ["deleted = 0"], []
        if substance_id is not None:
            clauses.append("substance_id = ?")
            params.append(substance_id)
        if since is not None:
            clauses.append("taken_at >= ?")
            params.append(_to_iso(since))
        sql = "SELECT * FROM doses WHERE " + " AND ".join(clauses) + " ORDER BY taken_at"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            Dose(
                substance_id=r["substance_id"], amount=r["amount"], unit=r["unit"],
                taken_at=_from_iso(r["taken_at"]), note=r["note"] or "", id=r["id"],
            )
            for r in rows
        ]

    def update_dose(
        self, dose_id: int, *, amount: float | None = None,
        taken_at: datetime | None = None, note: str | None = None,
    ) -> None:
        if amount is not None or taken_at is not None:
            self._validate_dose(1.0 if amount is None else amount, taken_at or datetime.now(timezone.utc))
        sets, params = [], []
        if amount is not None:
            sets.append("amount = ?")
            params.append(amount)
        if taken_at is not None:
            sets.append("taken_at = ?")
            params.append(_to_iso(taken_at))
        if note is not None:
            sets.append("note = ?")
            params.append(note)
        if not sets:
            return
        # Any edit bumps updated_at so last-write-wins picks it up on sync.
        sets.append("updated_at = ?")
        params.append(self._bumped_updated_at(dose_id))
        params.append(dose_id)
        self.conn.execute(f"UPDATE doses SET {', '.join(sets)} WHERE id = ?", params)
        self.conn.commit()

    def delete_dose(self, dose_id: int) -> None:
        # Soft delete: keep the row as a tombstone so the deletion propagates
        # to other devices instead of the row resurrecting on the next sync.
        self.conn.execute(
            "UPDATE doses SET deleted = 1, updated_at = ? WHERE id = ?",
            (self._bumped_updated_at(dose_id), dose_id),
        )
        self.conn.commit()

    # ----- sync support ------------------------------------------------------
    # These deal in raw rows (including tombstones) rather than ``Dose`` objects,
    # because the sync layer needs the columns ``Dose`` deliberately hides:
    # uid, deleted and updated_at.
    def all_for_sync(self) -> list[dict]:
        """Every dose row, tombstones included, as plain dicts for the sync layer."""
        rows = self.conn.execute(
            "SELECT id, uid, substance_id, amount, unit, taken_at, note, deleted,"
            " updated_at FROM doses WHERE uid IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]

    def dose_row_by_uid(self, uid: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, uid, substance_id, amount, unit, taken_at, note, deleted,"
            " updated_at FROM doses WHERE uid = ?",
            (uid,),
        ).fetchone()
        return dict(row) if row else None

    def known_substance_ids(self) -> set[str]:
        """Substance ids this install knows about. ``doses.substance_id`` is a
        foreign key, so a remote dose naming an unknown substance cannot be
        inserted; the sync layer checks against this and reports what it skipped
        instead of failing the whole merge."""
        return {r[0] for r in self.conn.execute("SELECT id FROM substances")}

    def upsert_synced_dose(
        self, uid: str, substance_id: str, amount: float, unit: str,
        taken_at: datetime, note: str, deleted: bool, updated_at: datetime,
    ) -> str:
        """Apply a remote dose locally, last-write-wins on ``updated_at``.

        Returns ``"inserted"``, ``"updated"`` or ``"skipped"`` (local copy is the
        same age or newer). Values arrive already validated by the device that
        wrote them, so this deliberately bypasses ``_validate_dose``: rejecting a
        peer's row here would silently desynchronise the two logs.
        """
        existing = self.dose_row_by_uid(uid)
        updated_iso = _to_iso(updated_at)
        if existing is not None and (existing["updated_at"] or "") >= updated_iso:
            return "skipped"
        params = (
            substance_id, amount, unit, _to_iso(taken_at), note,
            1 if deleted else 0, updated_iso,
        )
        if existing is None:
            self.conn.execute(
                "INSERT INTO doses (substance_id, amount, unit, taken_at, note,"
                " deleted, updated_at, uid) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                params + (uid,),
            )
            result = "inserted"
        else:
            self.conn.execute(
                "UPDATE doses SET substance_id = ?, amount = ?, unit = ?, taken_at = ?,"
                " note = ?, deleted = ?, updated_at = ? WHERE uid = ?",
                params + (uid,),
            )
            result = "updated"
        self.conn.commit()
        return result

    # ----- presets -----------------------------------------------------------
    def list_presets(self, substance_id: str) -> list[Preset]:
        rows = self.conn.execute(
            "SELECT * FROM presets WHERE substance_id = ? ORDER BY id", (substance_id,)
        ).fetchall()
        return [
            Preset(
                label=r["label"], amount=r["amount"], unit=r["unit"],
                volume_ml=r["volume_ml"], abv_percent=r["abv_percent"],
            )
            for r in rows
        ]

    # ----- user profile ------------------------------------------------------
    def set_profile_value(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO user_profile (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        self.conn.commit()

    def get_profile(self) -> UserProfile:
        rows = self.conn.execute("SELECT key, value FROM user_profile").fetchall()
        profile = UserProfile()
        tolerance: dict[str, float] = {}
        half_lives: dict[str, float] = {}
        for r in rows:
            key, raw = r["key"], r["value"]
            if key in _PROFILE_SCALARS:
                setattr(profile, key, _PROFILE_SCALARS[key](raw))
            elif key.startswith(_TOLERANCE_PREFIX):
                tolerance[key[len(_TOLERANCE_PREFIX):]] = float(raw)
            elif key.startswith(_HALFLIFE_PREFIX):
                half_lives[key[len(_HALFLIFE_PREFIX):]] = float(raw)
        profile.tolerance = tolerance
        profile.half_life_overrides = half_lives
        return profile

    def save_profile(self, profile: UserProfile) -> None:
        self._validate_profile(profile)
        for key in _PROFILE_SCALARS:
            self.set_profile_value(key, getattr(profile, key))
        for sub_id, factor in profile.tolerance.items():
            self.set_profile_value(f"{_TOLERANCE_PREFIX}{sub_id}", factor)
        for sub_id, hl in profile.half_life_overrides.items():
            self.set_profile_value(f"{_HALFLIFE_PREFIX}{sub_id}", hl)

    # ----- generic settings (UI prefs: widget position, bedtime, ...) --------
    # These live in the same key/value table; get_profile ignores unknown keys.
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM user_profile WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value) -> None:
        self.set_profile_value(key, value)

    # ----- validation --------------------------------------------------------
    def _validate_dose(self, amount: float, taken_at: datetime) -> None:
        if amount <= 0:
            raise ValueError("dose amount must be positive")
        if taken_at.tzinfo is None:
            raise ValueError("taken_at must be timezone-aware")

    def _validate_profile(self, profile: UserProfile) -> None:
        if not 30 <= profile.body_mass_kg <= 250:
            raise ValueError("body_mass_kg must be between 30 and 250")
        if profile.beta <= 0:
            raise ValueError("alcohol beta must be positive")
        if not 0 <= profile.legal_bac_limit <= 0.20:
            raise ValueError("legal_bac_limit must be between 0 and 0.20 g/dL")
        if profile.alcohol_ramp_min < 0:
            raise ValueError("alcohol_ramp_min must be non-negative")
        for sid, factor in profile.tolerance.items():
            if not 0.5 <= float(factor) <= 1.5:
                raise ValueError(f"tolerance for {sid} must be between 0.5 and 1.5")
        for sid, half_life in profile.half_life_overrides.items():
            if float(half_life) <= 0:
                raise ValueError(f"half-life override for {sid} must be positive")

    def _validate_substance(self, sub: Substance) -> None:
        if not sub.id or not sub.name:
            raise ValueError("substance id and name are required")
        if sub.model != "widmark_zero_order":
            for field_name in ("ka", "f", "v_l_per_kg"):
                value = getattr(sub, field_name)
                if value is None or value <= 0:
                    raise ValueError(f"{field_name} must be positive for {sub.id}")
            if sub.half_life_h is not None and sub.half_life_h <= 0:
                raise ValueError(f"half_life_h must be positive for {sub.id}")
            if sub.ke is not None and sub.ke <= 0:
                raise ValueError(f"ke must be positive for {sub.id}")
        if sub.ec50 is not None and sub.ec50 <= 0:
            raise ValueError(f"ec50 must be positive for {sub.id}")
        if sub.conc_scale <= 0:
            raise ValueError(f"conc_scale must be positive for {sub.id}")
        for preset in sub.presets:
            if preset.amount <= 0:
                raise ValueError(f"preset amount must be positive for {sub.id}")

    # ----- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self.conn.close()
