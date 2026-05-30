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
from datetime import datetime, timezone
from pathlib import Path

from ..core.engine import Dose, UserProfile
from ..core.substances import (
    DEFAULT_LIBRARY_PATH,
    Preset,
    Substance,
    load_substances,
)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

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
        if seed:
            self.seed_builtins()

    # ----- schema / seeding --------------------------------------------------
    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a DB was first created (idempotent)."""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(substances)")}
        for col, col_type in _MIGRATION_COLUMNS.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE substances ADD COLUMN {col} {col_type}")
        self.conn.commit()

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
        cur = self.conn.execute(
            "INSERT INTO doses (substance_id, amount, unit, taken_at, note)"
            " VALUES (?, ?, ?, ?, ?)",
            (substance_id, amount, unit, _to_iso(taken_at), note),
        )
        self.conn.commit()
        return Dose(substance_id, amount, unit, taken_at, note, id=cur.lastrowid)

    def list_doses(
        self, substance_id: str | None = None, since: datetime | None = None,
    ) -> list[Dose]:
        sql = "SELECT * FROM doses"
        clauses, params = [], []
        if substance_id is not None:
            clauses.append("substance_id = ?")
            params.append(substance_id)
        if since is not None:
            clauses.append("taken_at >= ?")
            params.append(_to_iso(since))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY taken_at"
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
        params.append(dose_id)
        self.conn.execute(f"UPDATE doses SET {', '.join(sets)} WHERE id = ?", params)
        self.conn.commit()

    def delete_dose(self, dose_id: int) -> None:
        self.conn.execute("DELETE FROM doses WHERE id = ?", (dose_id,))
        self.conn.commit()

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
        for r in rows:
            key, raw = r["key"], r["value"]
            if key in _PROFILE_SCALARS:
                setattr(profile, key, _PROFILE_SCALARS[key](raw))
            elif key.startswith(_TOLERANCE_PREFIX):
                tolerance[key[len(_TOLERANCE_PREFIX):]] = float(raw)
        profile.tolerance = tolerance
        return profile

    def save_profile(self, profile: UserProfile) -> None:
        for key in _PROFILE_SCALARS:
            self.set_profile_value(key, getattr(profile, key))
        for sub_id, factor in profile.tolerance.items():
            self.set_profile_value(f"{_TOLERANCE_PREFIX}{sub_id}", factor)

    # ----- generic settings (UI prefs: widget position, bedtime, ...) --------
    # These live in the same key/value table; get_profile ignores unknown keys.
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM user_profile WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value) -> None:
        self.set_profile_value(key, value)

    # ----- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self.conn.close()
