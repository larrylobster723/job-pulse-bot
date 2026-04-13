"""Tests for the recon agent."""

from __future__ import annotations

import sqlite3
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.agents.recon import get_enabled_sources, run_recon
from src.db.init import init_db
from src.sources.base import JobSource, RawJob


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn(tmp_path) -> Generator[sqlite3.Connection, None, None]:
    """Provide a fresh in-memory-style SQLite connection backed by a temp file.

    Yields:
        An open :class:`sqlite3.Connection` with the schema applied.
    """
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _make_raw_job(n: int) -> RawJob:
    """Create a deterministic RawJob for testing.

    Args:
        n: Index used to differentiate jobs.

    Returns:
        A unique :class:`RawJob`.
    """
    return RawJob(
        source="test_source",
        external_id=f"job-{n}",
        title=f"Engineer {n}",
        company=f"Acme {n}",
        location_raw="Remote",
        salary_raw="100000-120000",
        tags_raw="python,remote",
        url=f"https://example.com/jobs/{n}",
    )


class _MockSource(JobSource):
    """A mock job source that returns a preset list of RawJobs."""

    def __init__(self, jobs: list[RawJob]) -> None:
        self._jobs = jobs

    @property
    def source_name(self) -> str:
        return "test_source"

    def fetch(self) -> list[RawJob]:
        return self._jobs


class _FailingSource(JobSource):
    """A mock job source that always raises RequestException on fetch."""

    @property
    def source_name(self) -> str:
        return "failing_source"

    def fetch(self) -> list[RawJob]:
        raise requests.RequestException("Network error")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_happy_path_inserts_three_jobs(db_conn: sqlite3.Connection) -> None:
    """Happy path: a source returning 3 jobs should insert 3 raw_jobs rows."""
    jobs = [_make_raw_job(i) for i in range(3)]
    source = _MockSource(jobs)

    count = run_recon(db_conn, [source])

    assert count == 3
    rows = db_conn.execute("SELECT * FROM raw_jobs").fetchall()
    assert len(rows) == 3


def test_idempotency_does_not_duplicate(db_conn: sqlite3.Connection) -> None:
    """Running recon twice with the same jobs should still have 3 rows total."""
    jobs = [_make_raw_job(i) for i in range(3)]
    source = _MockSource(jobs)

    run_recon(db_conn, [source])
    count2 = run_recon(db_conn, [source])

    assert count2 == 0  # all duplicates on second run
    rows = db_conn.execute("SELECT * FROM raw_jobs").fetchall()
    assert len(rows) == 3


def test_source_failure_does_not_crash_pipeline(db_conn: sqlite3.Connection) -> None:
    """A source that raises should not prevent other sources from running."""
    good_jobs = [_make_raw_job(i) for i in range(2)]
    good_source = _MockSource(good_jobs)
    bad_source = _FailingSource()

    # Put failing source first to test that good source still runs.
    count = run_recon(db_conn, [bad_source, good_source])

    assert count == 2
    rows = db_conn.execute("SELECT * FROM raw_jobs").fetchall()
    assert len(rows) == 2


def test_get_enabled_sources_known_names() -> None:
    """get_enabled_sources returns instances for known source names."""
    sources = get_enabled_sources(["remoteok", "arbeitnow"])
    names = [s.source_name for s in sources]
    assert names == ["remoteok", "arbeitnow"]


def test_get_enabled_sources_unknown_skipped() -> None:
    """Unknown source names are silently skipped."""
    sources = get_enabled_sources(["remoteok", "nonexistent"])
    assert len(sources) == 1
    assert sources[0].source_name == "remoteok"
