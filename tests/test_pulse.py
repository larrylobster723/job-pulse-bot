"""Tests for the pulse agent."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest

from src.agents.pulse import compute_pulse_score, run_pulse
from src.db.init import init_db
from src.db.queries import insert_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn(tmp_path) -> Generator[sqlite3.Connection, None, None]:
    """Provide a schema-initialised SQLite connection.

    Yields:
        An open :class:`sqlite3.Connection`.
    """
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _now_iso(delta_hours: float = 0) -> str:
    """Return a UTC ISO-8601 timestamp offset by delta_hours.

    Args:
        delta_hours: Hours to subtract from now (negative = future).

    Returns:
        ISO-8601 string.
    """
    return (datetime.now(timezone.utc) - timedelta(hours=delta_hours)).isoformat()


def _make_job(
    *,
    title: str = "Software Engineer",
    tags_raw: str | None = None,
    location_country: str | None = None,
    salary_min_usd: int | None = None,
    salary_max_usd: int | None = None,
    first_seen_at: str | None = None,
) -> dict:
    """Build a minimal job dict for compute_pulse_score.

    Args:
        title: Job title.
        tags_raw: Comma-separated tags.
        location_country: Country code or "REMOTE".
        salary_min_usd: Annual minimum salary.
        salary_max_usd: Annual maximum salary.
        first_seen_at: ISO-8601 UTC timestamp.

    Returns:
        A dict compatible with compute_pulse_score input.
    """
    return {
        "title": title,
        "tags_raw": tags_raw,
        "location_country": location_country,
        "salary_min_usd": salary_min_usd,
        "salary_max_usd": salary_max_usd,
        "first_seen_at": first_seen_at or _now_iso(1),
    }


# ---------------------------------------------------------------------------
# compute_pulse_score pure function tests
# ---------------------------------------------------------------------------


def test_maximum_score_remote_high_salary_fresh() -> None:
    """Remote job with above-median salary seen <24h should score near 100."""
    job = _make_job(
        title="Remote Python Engineer",
        location_country="REMOTE",
        salary_min_usd=120_000,
        salary_max_usd=160_000,
        first_seen_at=_now_iso(1),
    )
    score = compute_pulse_score(job)
    # salary(40) + remote(30) + freshness(30) = 100
    assert score == 100


def test_minimum_score_onsite_no_salary_old() -> None:
    """Onsite job with no salary seen >72h ago should score 0."""
    job = _make_job(
        title="Office Assistant",
        location_country="US",
        salary_min_usd=None,
        salary_max_usd=None,
        first_seen_at=_now_iso(80),  # 80 hours ago
    )
    score = compute_pulse_score(job)
    # salary(0) + remote(0) + freshness(0) = 0
    assert score == 0


def test_freshness_boundary_exactly_24h_scores_20() -> None:
    """A job seen exactly 24 hours ago (not < 24h) should get freshness=20."""
    job = _make_job(
        title="Developer",
        first_seen_at=_now_iso(24.01),  # just over 24h
    )
    score = compute_pulse_score(job)
    # No salary(0) + no remote(0) + freshness(20) = 20
    assert score == 20


def test_remote_keyword_in_tags_scores_30() -> None:
    """'remote' in tags_raw should trigger the remote factor."""
    job = _make_job(tags_raw="python,remote,backend")
    score = compute_pulse_score(job)
    assert score >= 30


def test_below_median_salary_scores_20() -> None:
    """A salary below the market median should contribute 20, not 40."""
    job = _make_job(salary_max_usd=50_000, first_seen_at=_now_iso(80))
    score = compute_pulse_score(job)
    # salary(20) + no remote(0) + freshness(0) = 20
    assert score == 20


def test_no_salary_scores_zero_salary_factor() -> None:
    """Absence of salary should contribute 0 to the salary factor."""
    job = _make_job(salary_min_usd=None, salary_max_usd=None, first_seen_at=_now_iso(80))
    score = compute_pulse_score(job)
    assert score == 0


# ---------------------------------------------------------------------------
# run_pulse DB integration tests
# ---------------------------------------------------------------------------


def test_run_pulse_writes_score_and_scored_at(db_conn: sqlite3.Connection) -> None:
    """run_pulse should write pulse_score and scored_at for unscored jobs."""
    insert_job(
        db_conn,
        title="Remote Engineer",
        company="ACME",
        location_country="REMOTE",
        salary_min_usd=120_000,
        salary_max_usd=150_000,
        tags_raw="remote,python",
        url="https://example.com/job/1",
        source="test",
    )
    db_conn.commit()

    scored = run_pulse(db_conn)

    assert scored == 1
    row = db_conn.execute(
        "SELECT pulse_score, scored_at FROM jobs WHERE url = ?",
        ("https://example.com/job/1",),
    ).fetchone()
    assert row["pulse_score"] is not None
    assert row["pulse_score"] > 0
    assert row["scored_at"] is not None


def test_run_pulse_does_not_rescore(db_conn: sqlite3.Connection) -> None:
    """run_pulse should skip jobs that already have a pulse_score."""
    insert_job(
        db_conn,
        title="Already Scored",
        company="Corp",
        location_country=None,
        salary_min_usd=None,
        salary_max_usd=None,
        tags_raw=None,
        url="https://example.com/job/2",
        source="test",
    )
    db_conn.commit()
    db_conn.execute(
        "UPDATE jobs SET pulse_score = 42, scored_at = datetime('now') WHERE url = ?",
        ("https://example.com/job/2",),
    )
    db_conn.commit()

    scored = run_pulse(db_conn)

    assert scored == 0
    row = db_conn.execute(
        "SELECT pulse_score FROM jobs WHERE url = ?",
        ("https://example.com/job/2",),
    ).fetchone()
    assert row["pulse_score"] == 42
