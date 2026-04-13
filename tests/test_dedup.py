"""Tests for the dedup agent including parse_salary and parse_location."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Generator

import pytest

from src.agents.dedup import parse_location, parse_salary, run_dedup
from src.db.init import init_db
from src.db.queries import insert_raw_job


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


def _insert(
    conn: sqlite3.Connection,
    *,
    title: str = "Software Engineer",
    company: str = "Acme Corp",
    n: int = 0,
    salary_raw: str | None = None,
    location_raw: str | None = None,
    tags_raw: str | None = None,
) -> None:
    """Helper to insert a raw_job row for testing.

    Args:
        conn: Open SQLite connection.
        title: Job title.
        company: Company name.
        n: Disambiguator appended to external_id and url.
        salary_raw: Optional raw salary string.
        location_raw: Optional raw location string.
        tags_raw: Optional tags string.
    """
    insert_raw_job(
        conn,
        source="test",
        external_id=f"job-{n}",
        title=title,
        company=company,
        location_raw=location_raw,
        salary_raw=salary_raw,
        tags_raw=tags_raw,
        url=f"https://example.com/{n}",
    )
    conn.commit()


# ---------------------------------------------------------------------------
# parse_salary tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_min, expected_max",
    [
        ("$100k", 100_000, 100_000),
        ("80000-120000", 80_000, 120_000),
        (None, None, None),
        ("90000", 90_000, 90_000),
        ("100K-150K", 100_000, 150_000),
        ("$80,000", 80_000, 80_000),
    ],
)
def test_parse_salary(
    raw: str | None,
    expected_min: int | None,
    expected_max: int | None,
) -> None:
    """parse_salary should extract (min, max) from various salary formats."""
    salary_min, salary_max = parse_salary(raw)
    assert salary_min == expected_min
    assert salary_max == expected_max


# ---------------------------------------------------------------------------
# parse_location tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Remote", "REMOTE"),
        ("Worldwide", "REMOTE"),
        ("Anywhere", "REMOTE"),
        ("New York, US", "US"),
        ("United Kingdom", "GB"),
        (None, None),
        ("Mars Colony", None),
    ],
)
def test_parse_location(raw: str | None, expected: str | None) -> None:
    """parse_location should map location strings to country codes or REMOTE."""
    assert parse_location(raw) == expected


# ---------------------------------------------------------------------------
# run_dedup tests
# ---------------------------------------------------------------------------


def test_three_unique_jobs_inserted(db_conn: sqlite3.Connection) -> None:
    """3 unique raw jobs should all be promoted to the jobs table."""
    # Use completely different titles so token_sort_ratio stays well below
    # DEDUP_THRESHOLD (85) — the titles share no meaningful tokens.
    _insert(db_conn, title="Python Developer", company="Acme Inc", n=0)
    _insert(db_conn, title="DevOps Engineer", company="Beta Corp", n=1)
    _insert(db_conn, title="Data Scientist", company="Gamma LLC", n=2)

    count = run_dedup(db_conn)

    assert count == 3
    rows = db_conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert rows == 3


def test_duplicate_title_company_skipped(db_conn: sqlite3.Connection) -> None:
    """A near-identical title+company (>= 85 similarity) should be skipped."""
    # Insert original
    _insert(db_conn, title="Senior Python Engineer", company="TechCorp", n=0)
    run_dedup(db_conn)

    # Insert near-duplicate (different URL, same conceptual role)
    _insert(db_conn, title="Python Engineer Senior", company="TechCorp", n=1)
    second_count = run_dedup(db_conn)

    assert second_count == 0
    total = db_conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert total == 1


def test_similar_but_different_company_inserted(db_conn: sqlite3.Connection) -> None:
    """Same title but sufficiently different company should be a distinct job.

    token_sort_ratio scores "software engineer google" vs
    "software engineer facebook" well below 85, so both should be inserted.
    """
    _insert(db_conn, title="Software Engineer", company="Google", n=0)
    run_dedup(db_conn)

    _insert(db_conn, title="Software Engineer", company="Facebook", n=1)
    second_count = run_dedup(db_conn)

    assert second_count == 1
    total = db_conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert total == 2


def test_salary_and_location_parsed_on_insert(db_conn: sqlite3.Connection) -> None:
    """Salary and location should be parsed and stored when promoting to jobs."""
    _insert(
        db_conn,
        title="Backend Engineer",
        company="PayCo",
        n=0,
        salary_raw="100K-150K",
        location_raw="Remote",
    )
    run_dedup(db_conn)

    row = db_conn.execute("SELECT * FROM jobs LIMIT 1").fetchone()
    assert row["salary_min_usd"] == 100_000
    assert row["salary_max_usd"] == 150_000
    assert row["location_country"] == "REMOTE"
