-- TechPulse Jobs Bot — database schema
-- All tables use CREATE TABLE IF NOT EXISTS for idempotent initialisation.

CREATE TABLE IF NOT EXISTS raw_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT    NOT NULL,
    external_id  TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    company      TEXT    NOT NULL,
    location_raw TEXT,
    salary_raw   TEXT,
    tags_raw     TEXT,
    url          TEXT    NOT NULL,
    fetched_at   TEXT    NOT NULL,
    processed_at TEXT,
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    company          TEXT    NOT NULL,
    location_country TEXT,
    salary_min_usd   INTEGER,
    salary_max_usd   INTEGER,
    tags_raw         TEXT,
    url              TEXT    NOT NULL,
    source           TEXT    NOT NULL,
    first_seen_at    TEXT    NOT NULL,
    pulse_score      INTEGER,
    scored_at        TEXT,
    posted_at        TEXT,
    UNIQUE (url)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    agent          TEXT    NOT NULL,
    started_at     TEXT    NOT NULL,
    finished_at    TEXT,
    jobs_processed INTEGER NOT NULL DEFAULT 0,
    status         TEXT    NOT NULL DEFAULT 'running'
);
