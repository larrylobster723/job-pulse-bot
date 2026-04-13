"""Pulse agent — scores jobs with the PULSE algorithm.

PULSE score (0–100) has three components:
  - Salary factor  (0–40): no salary → 0, below median → 20, at/above → 40
  - Remote factor  (0–30): remote keywords in title or tags → 30, else 0
  - Freshness      (0–30): <24 h → 30, <48 h → 20, <72 h → 10, older → 0
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from src.db.queries import (
    finish_pipeline_run,
    get_unscored_jobs,
    insert_pipeline_run,
    update_job_pulse_score,
)

try:
    from src.config import (
        PULSE_HOT_THRESHOLD,
        SALARY_MARKET_MEDIAN_USD,
    )
except RuntimeError:
    PULSE_HOT_THRESHOLD = 80
    SALARY_MARKET_MEDIAN_USD = 80_000

__all__ = ["compute_pulse_score", "run_pulse"]

_log = logging.getLogger(__name__)

# Factor ceilings
_SALARY_MAX = 40
_REMOTE_MAX = 30
_FRESHNESS_MAX = 30

# Freshness hour thresholds
_FRESH_24H = 24
_FRESH_48H = 48
_FRESH_72H = 72

# Remote keywords (lower-cased)
_REMOTE_KEYWORDS = frozenset({"remote", "wfh", "work from home", "anywhere"})


def _freshness_score(first_seen_at: str) -> int:
    """Compute the freshness component of the PULSE score.

    Args:
        first_seen_at: ISO-8601 UTC timestamp string from the jobs table.

    Returns:
        30 if <24 h old, 20 if <48 h, 10 if <72 h, 0 otherwise.
    """
    try:
        seen_dt = datetime.fromisoformat(first_seen_at)
        if seen_dt.tzinfo is None:
            seen_dt = seen_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0

    age_hours = (datetime.now(timezone.utc) - seen_dt).total_seconds() / 3600

    if age_hours < _FRESH_24H:
        return _FRESHNESS_MAX
    if age_hours < _FRESH_48H:
        return 20
    if age_hours < _FRESH_72H:
        return 10
    return 0


def compute_pulse_score(job: dict) -> int:  # noqa: D401
    """Compute the PULSE score for a single job dict (pure function, no DB).

    Args:
        job: A dict with keys matching the jobs table columns, specifically:
             salary_min_usd, salary_max_usd, location_country, tags_raw,
             title, first_seen_at.

    Returns:
        An integer PULSE score in the range [0, 100].
    """
    # --- Salary factor (0-40) ---
    salary_min: int | None = job.get("salary_min_usd")
    salary_max: int | None = job.get("salary_max_usd")
    has_salary = salary_min is not None or salary_max is not None
    if not has_salary:
        salary_score = 0
    else:
        representative = salary_max if salary_max is not None else salary_min
        assert representative is not None
        salary_score = _SALARY_MAX if representative >= SALARY_MARKET_MEDIAN_USD else 20

    # --- Remote factor (0-30) ---
    title_lower = (job.get("title") or "").lower()
    tags_lower = (job.get("tags_raw") or "").lower()
    location_lower = (job.get("location_country") or "").lower()

    is_remote = (
        any(kw in title_lower for kw in _REMOTE_KEYWORDS)
        or any(kw in tags_lower for kw in _REMOTE_KEYWORDS)
        or location_lower == "remote"
    )
    remote_score = _REMOTE_MAX if is_remote else 0

    # --- Freshness factor (0-30) ---
    freshness_score = _freshness_score(job.get("first_seen_at") or "")

    total = salary_score + remote_score + freshness_score
    # Clamp to [0, 100] as a safety measure.
    return max(0, min(100, total))


def run_pulse(conn: sqlite3.Connection) -> int:
    """Score all unscored jobs and persist results to the DB.

    Logs total scored count, average score, and HOT count
    (score >= PULSE_HOT_THRESHOLD).

    Args:
        conn: Active SQLite connection.

    Returns:
        Number of jobs scored in this run.
    """
    run_id = insert_pipeline_run(conn, "pulse")
    conn.commit()

    unscored = get_unscored_jobs(conn)
    _log.info("Pulse: %d unscored jobs to evaluate", len(unscored))

    scores: list[int] = []
    for job in unscored:
        score = compute_pulse_score(job)
        update_job_pulse_score(conn, job["id"], score)
        scores.append(score)

    conn.commit()

    if scores:
        avg = sum(scores) / len(scores)
        hot_count = sum(1 for s in scores if s >= PULSE_HOT_THRESHOLD)
        _log.info(
            "Pulse complete — scored %d jobs, avg=%.1f, HOT=%d",
            len(scores),
            avg,
            hot_count,
        )
    else:
        _log.info("Pulse complete — no new jobs to score")

    finish_pipeline_run(conn, run_id, len(scores), "success")
    conn.commit()
    return len(scores)
