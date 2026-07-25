-- SQLite schema for the PK tracker.
--
-- The dose log is the single source of truth. Substances carry their model
-- constants; presets are one-tap dose buttons; user_profile is a simple
-- key/value store for calibration. All timestamps are ISO 8601 in UTC.

PRAGMA foreign_keys = ON;
-- App-level schema version is stored in PRAGMA user_version by the Python migration layer.

CREATE TABLE IF NOT EXISTS substances (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    model              TEXT NOT NULL,            -- 'one_compartment' | 'widmark_zero_order'
    half_life_h        REAL,
    ka                 REAL,
    ke                 REAL,
    f                  REAL,
    v_l_per_kg         REAL,
    frac_ir            REAL,
    lag_h              REAL,
    ka2                REAL,
    ec50               REAL,
    emax               REAL NOT NULL DEFAULT 1.0,
    redose_eligible    INTEGER NOT NULL DEFAULT 0,
    is_builtin         INTEGER NOT NULL DEFAULT 0,
    unit               TEXT NOT NULL DEFAULT 'mg',
    conc_unit          TEXT NOT NULL DEFAULT 'mg/L',
    conc_scale         REAL NOT NULL DEFAULT 1.0,
    color              TEXT NOT NULL DEFAULT '#4aa3ff',
    note               TEXT NOT NULL DEFAULT '',
    sleep_threshold    REAL,
    redose_fraction    REAL,
    overload_amount_mg REAL,
    toxicity_threshold REAL
);

CREATE TABLE IF NOT EXISTS doses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    substance_id TEXT NOT NULL REFERENCES substances(id) ON DELETE CASCADE,
    amount       REAL NOT NULL,
    unit         TEXT NOT NULL,                  -- 'mg' | 'g' (ethanol) | 'ml' ...
    taken_at     TEXT NOT NULL,                  -- ISO 8601, UTC
    note         TEXT,
    -- Sync-ready columns (match the Android app's Firestore model so the log
    -- can merge across devices): a global uid, a soft-delete tombstone, and a
    -- last-modified stamp for last-write-wins.
    uid          TEXT,                           -- UUID, globally unique across devices
    deleted      INTEGER NOT NULL DEFAULT 0,     -- soft-delete tombstone
    updated_at   TEXT                            -- ISO 8601, UTC; last local change
);

CREATE INDEX IF NOT EXISTS idx_doses_substance_time ON doses(substance_id, taken_at);
-- Indexes on the sync columns (uid, updated_at) are created by the Python
-- migration layer, after those columns are guaranteed to exist on legacy DBs.

CREATE TABLE IF NOT EXISTS user_profile (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS presets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    substance_id TEXT NOT NULL REFERENCES substances(id) ON DELETE CASCADE,
    label        TEXT NOT NULL,
    amount       REAL NOT NULL,
    unit         TEXT NOT NULL,
    volume_ml    REAL,
    abv_percent  REAL
);
