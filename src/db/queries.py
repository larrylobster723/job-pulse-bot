"""Database access functions for TechPulse Jobs Bot.

All functions accept an explicit ``conn: sqlite3.Connection`` parameter so
callers control transaction scope and connection lifetime.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "insert_raw_job",
    "get_unprocessed_raw_jobs",
    "mark_raw_job_processed",
    "insert_job",
    "job_url_exists",
    "get_all_job_titles_companies",
    "get_unscored_jobs",
    "update_pulse_score",
    "get_unposted_jobs",
    "mark_job_posted",
    "insert_pipeline_run",
    "finish_pipeline_run",
    "log_pipeline_run",
    "get_pipeline_status",
]


def _now_utc() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# raw_jobs
# ---------------------------------------------------------------------------


def insert_raw_job(
    conn: sqlite3.Connection,
    source: str,
    external_id: str,
    title: str,
    company: str,
    location_raw: str | None,
    salary_raw: str | None,
    tags_raw: str | None,
    url: str,
) -> bool:
    """Insert a raw job record, ignoring duplicates.

    Args:
        conn: Active SQLite connection.
        source: Source identifier (e.g. "remoteok").
        external_id: Source-specific job ID.
        title: Job title.
        company: Company name.
        location_raw: Raw location string from source.
        salary_raw: Raw salary string from source.
        tags_raw: Comma-separated tags string.
        url: Direct link to the job posting.

    Returns:
        True if a new row was inserted, False if it was a duplicate.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO raw_jobs
            (source, external_id, title, company, location_raw,
             salary_raw, tags_raw, url, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (source, external_id, title, company, location_raw,
         salary_raw, tags_raw, url, _now_utc()),
    )
    return cursor.rowcount > 0


def get_unprocessed_raw_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all raw_jobs rows where processed_at IS NULL.

    Args:
        conn: Active SQLite connection.

    Returns:
        List of row dicts with all raw_jobs columns.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM raw_jobs WHERE processed_at IS NULL ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def mark_raw_job_processed(conn: sqlite3.Connection, raw_job_id: int) -> None:
    """Set processed_at on a raw_jobs row.

    Args:
        conn: Active SQLite connection.
        raw_job_id: Primary key of the raw_jobs row.
    """
    conn.execute(
        "UPDATE raw_jobs SET processed_at = ? WHERE id = ?",
        (_now_utc(), raw_job_id),
    )


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------


def get_all_job_titles_companies(
    conn: sqlite3.Connection,
) -> list[tuple[str, str, int]]:
    """Return (title, company, id) tuples for every row in the jobs table.

    Used by the dedup agent to fuzzy-match incoming jobs against all already-
    seen canonical jobs without loading full row dicts.

    Args:
        conn: Active SQLite connection.

    Returns:
        List of (title, company, id) tuples ordered by id.
    """
    rows = conn.execute(
        "SELECT title, company, id FROM jobs ORDER BY id"
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def job_url_exists(conn: sqlite3.Connection, url: str) -> bool:
    """Check whether a canonical job URL already exists in the jobs table.

    Args:
        conn: Active SQLite connection.
        url: Job posting URL.

    Returns:
        True if a row with this URL exists.
    """
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE url = ? LIMIT 1", (url,)
    ).fetchone()
    return row is not None


def insert_job(
    conn: sqlite3.Connection,
    title: str,
    company: str,
    location_country: str | None,
    salary_min_usd: int | None,
    salary_max_usd: int | None,
    tags_raw: str | None,
    url: str,
    source: str,
) -> bool:
    """Insert a deduplicated, parsed job record, ignoring URL duplicates.

    Args:
        conn: Active SQLite connection.
        title: Normalised job title.
        company: Company name.
        location_country: ISO country code, "REMOTE", or None.
        salary_min_usd: Annual minimum salary in USD, or None.
        salary_max_usd: Annual maximum salary in USD, or None.
        tags_raw: Comma-separated tags string.
        url: Job posting URL (unique key).
        source: Source identifier.

    Returns:
        True if inserted, False if URL was already present.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO jobs
            (title, company, location_country, salary_min_usd, salary_max_usd,
             tags_raw, url, source, first_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title, company, location_country, salary_min_usd, salary_max_usd,
         tags_raw, url, source, _now_utc()),
    )
    return cursor.rowcount > 0


def get_unscored_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all jobs rows where pulse_score IS NULL.

    Args:
        conn: Active SQLite connection.

    Returns:
        List of row dicts with all jobs columns.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM jobs WHERE pulse_score IS NULL ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def update_pulse_score(
    conn: sqlite3.Connection, job_id: int, score: int
) -> None:
    """Write pulse_score and scored_at for a jobs row.

    Args:
        conn: Active SQLite connection.
        job_id: Primary key of the jobs row.
        score: Computed PULSE score (0–100).
    """
    conn.execute(
        "UPDATE jobs SET pulse_score = ?, scored_at = ? WHERE id = ?",
        (score, _now_utc(), job_id),
    )


def get_unposted_jobs(
    conn: sqlite3.Connection, min_score: int
) -> list[dict[str, Any]]:
    """Return scored jobs above threshold that have not been posted yet.

    Args:
        conn: Active SQLite connection.
        min_score: Minimum pulse_score to include.

    Returns:
        List of row dicts ordered by pulse_score DESC.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM jobs
        WHERE posted_at IS NULL
          AND pulse_score >= ?
        ORDER BY pulse_score DESC
        """,
        (min_score,),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_job_posted(conn: sqlite3.Connection, job_id: int) -> None:
    """Set posted_at on a jobs row.

    Args:
        conn: Active SQLite connection.
        job_id: Primary key of the jobs row.
    """
    conn.execute(
        "UPDATE jobs SET posted_at = ? WHERE id = ?",
        (_now_utc(), job_id),
    )


# ---------------------------------------------------------------------------
# pipeline_runs
# ---------------------------------------------------------------------------


def insert_pipeline_run(conn: sqlite3.Connection, agent: str) -> int:
    """Insert a pipeline_runs row and return its id.

    Args:
        conn: Active SQLite connection.
        agent: Agent name (e.g. "recon").

    Returns:
        The new row's primary key.
    """
    cursor = conn.execute(
        "INSERT INTO pipeline_runs (agent, started_at, status) VALUES (?, ?, 'running')",
        (agent, _now_utc()),
    )
    return cursor.lastrowid  # type: ignore[return-value]


def finish_pipeline_run(
    conn: sqlite3.Connection,
    run_id: int,
    jobs_processed: int,
    status: str,
) -> None:
    """Update a pipeline_runs row with completion details.

    Args:
        conn: Active SQLite connection.
        run_id: Primary key of the pipeline_runs row.
        jobs_processed: Number of jobs processed in this run.
        status: Final status string ("success" or "error").
    """
    conn.execute(
        """
        UPDATE pipeline_runs
        SET finished_at = ?, jobs_processed = ?, status = ?
        WHERE id = ?
        """,
        (_now_utc(), jobs_processed, status, run_id),
    )


def log_pipeline_run(
    conn: sqlite3.Connection,
    agent: str,
    jobs_processed: int,
    status: str,
    started_at: str,
) -> None:
    """Insert a completed pipeline_runs record in a single call.

    Convenience function for after-the-fact logging where both the start time
    and outcome are already known. For in-progress tracking use
    :func:`insert_pipeline_run` and :func:`finish_pipeline_run` instead.

    Args:
        conn: Active SQLite connection.
        agent: Agent name (e.g. "recon").
        jobs_processed: Number of jobs processed in this run.
        status: Final status string (e.g. "success" or "error").
        started_at: ISO-8601 UTC timestamp when the run began.
    """
    conn.execute(
        """
        INSERT INTO pipeline_runs
            (agent, started_at, finished_at, jobs_processed, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (agent, started_at, _now_utc(), jobs_processed, status),
    )


def get_pipeline_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aggregate stats for the /pipeline status command.

    Args:
        conn: Active SQLite connection.

    Returns:
        Dict with keys: raw_jobs_last_hour, total_jobs,
        avg_score_last_24h, last_run.
    """
    conn.row_factory = sqlite3.Row

    raw_last_hour = conn.execute(
        """
        SELECT COUNT(*) AS cnt FROM raw_jobs
        WHERE fetched_at >= datetime('now', '-1 hour')
        """
    ).fetchone()["cnt"]

    total_jobs = conn.execute(
        "SELECT COUNT(*) AS cnt FROM jobs"
    ).fetchone()["cnt"]

    avg_score = conn.execute(
        """
        SELECT ROUND(AVG(pulse_score), 1) AS avg FROM jobs
        WHERE scored_at >= datetime('now', '-24 hours')
          AND pulse_score IS NOT NULL
        """
    ).fetchone()["avg"]

    last_run_row = conn.execute(
        """
        SELECT agent, started_at, finished_at, jobs_processed, status
        FROM pipeline_runs
        WHERE finished_at IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    last_run = dict(last_run_row) if last_run_row else None

    return {
        "raw_jobs_last_hour": raw_last_hour,
        "total_jobs": total_jobs,
        "avg_score_last_24h": avg_score,
        "last_run": last_run,
    }
