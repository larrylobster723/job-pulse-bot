"""Integration tests for the TechPulse Jobs Bot pipeline.

Tests INT-1 through INT-6 exercise the full pipeline end-to-end using
in-memory SQLite and mocked HTTP / Discord calls.  No agent logic is mocked —
only external calls (HTTP via requests.RequestException, Discord channel.send).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio  # noqa: F401 — activates pytest-asyncio plugin
import requests

from src.agents.dedup import run_dedup
from src.agents.herald import run_herald
from src.agents.pulse import run_pulse
from src.agents.recon import run_recon
from src.sources.base import JobSource, RawJob


# ---------------------------------------------------------------------------
# Helper: fresh in-memory DB
# ---------------------------------------------------------------------------


def make_db() -> sqlite3.Connection:
    """Create a fresh in-memory DB with schema applied.

    Returns:
        An open :class:`sqlite3.Connection` with the full schema applied.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Read and apply schema.sql
    schema_path = Path(__file__).parent.parent / "src" / "db" / "schema.sql"
    conn.executescript(schema_path.read_text())
    return conn


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_channel() -> AsyncMock:
    """Create a mock Discord TextChannel with an async send method.

    Returns:
        An :class:`unittest.mock.AsyncMock` simulating a TextChannel.
    """
    channel = AsyncMock(spec=discord.TextChannel)
    channel.send = AsyncMock(return_value=MagicMock())
    return channel


class _MockSource(JobSource):
    """A JobSource that returns a preset list of RawJob objects."""

    def __init__(self, name: str, jobs: list[RawJob]) -> None:
        self._name = name
        self._jobs = jobs

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self) -> list[RawJob]:
        return self._jobs


class _FailingSource(JobSource):
    """A JobSource that always raises requests.RequestException on fetch."""

    @property
    def source_name(self) -> str:
        return "failing"

    def fetch(self) -> list[RawJob]:
        raise requests.RequestException("simulated network error")


def _insert_scored_job(
    conn: sqlite3.Connection,
    *,
    score: int,
    url: str,
    title: str = "Engineer",
    company: str = "Corp",
    location_country: str | None = None,
    salary_max_usd: int | None = None,
) -> None:
    """Insert a job directly into the jobs table with a pre-set pulse_score.

    Bypasses recon/dedup/pulse so herald tests can start from a known state.

    Args:
        conn: Active SQLite connection.
        score: Pulse score to assign immediately.
        url: Unique URL for this job.
        title: Job title.
        company: Company name.
        location_country: Parsed location country code or "REMOTE".
        salary_max_usd: Optional annual max salary in USD.
    """
    conn.execute(
        """
        INSERT INTO jobs
            (title, company, location_country, salary_min_usd, salary_max_usd,
             tags_raw, url, source, first_seen_at, pulse_score, scored_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'test', datetime('now'), ?, datetime('now'))
        """,
        (title, company, location_country, None, salary_max_usd, None, url, score),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# INT-1: Full pipeline end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_int1_full_pipeline() -> None:
    """INT-1: recon → dedup → pulse → herald processes 3 distinct jobs.

    Score breakdown (all jobs fresh, so freshness = +30):
      A1 — Remote title + salary $100k (>=80k) → remote 30 + salary 40 + fresh 30 = 100 (posted)
      A2 — Remote title + no salary             → remote 30 + salary 0  + fresh 30 = 60  (posted)
      B1 — No remote + no salary                → remote 0  + salary 0  + fresh 30 = 30  (not posted)
    """
    conn = make_db()

    job_a1 = RawJob(
        source="source_a",
        external_id="a1",
        title="Remote Software Engineer",
        company="Acme Inc",
        location_raw="Remote",
        salary_raw="$100k",
        tags_raw="python,remote",
        url="https://example.com/a1",
    )
    job_a2 = RawJob(
        source="source_a",
        external_id="a2",
        title="Remote Data Analyst",
        company="Beta Corp",
        location_raw="Remote",
        salary_raw=None,
        tags_raw=None,
        url="https://example.com/a2",
    )
    job_b1 = RawJob(
        source="source_b",
        external_id="b1",
        title="Office Manager",
        company="Gamma Ltd",
        location_raw="New York, US",
        salary_raw=None,
        tags_raw=None,
        url="https://example.com/b1",
    )

    sources = [
        _MockSource("source_a", [job_a1, job_a2]),
        _MockSource("source_b", [job_b1]),
    ]
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        run_recon(conn, sources)
        run_dedup(conn)
        run_pulse(conn)
        await run_herald(conn, channel)

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
    assert raw_count == 3

    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert job_count == 3

    unscored = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE pulse_score IS NULL"
    ).fetchone()[0]
    assert unscored == 0

    # channel.send call count must match the number of jobs scoring >= 60
    qualifying = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE pulse_score >= 60"
    ).fetchone()[0]
    assert channel.send.call_count == qualifying

    # Jobs below threshold must not be posted
    not_posted_low = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE pulse_score < 60 AND posted_at IS NOT NULL"
    ).fetchone()[0]
    assert not_posted_low == 0

    conn.close()


# ---------------------------------------------------------------------------
# INT-2: Duplicate across sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_int2_duplicate_across_sources() -> None:
    """INT-2: identical title+company from two sources → dedup keeps 1 in jobs."""
    conn = make_db()

    # Same title + company, different URLs (and different source/external_id pairs
    # so the raw_jobs UNIQUE constraint is not triggered).
    job_1 = RawJob(
        source="source_a",
        external_id="dup1",
        title="Senior Python Developer",
        company="Duplicate Co",
        location_raw="Remote",
        salary_raw=None,
        tags_raw=None,
        url="https://example.com/dup1",
    )
    job_2 = RawJob(
        source="source_b",
        external_id="dup2",
        title="Senior Python Developer",
        company="Duplicate Co",
        location_raw="Remote",
        salary_raw=None,
        tags_raw=None,
        url="https://example.com/dup2",
    )

    sources = [
        _MockSource("source_a", [job_1]),
        _MockSource("source_b", [job_2]),
    ]
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        run_recon(conn, sources)
        run_dedup(conn)
        run_pulse(conn)
        await run_herald(conn, channel)

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
    assert raw_count == 2  # both raw records stored

    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert job_count == 1  # duplicate removed by dedup

    # The surviving job is remote + fresh → score 60, so exactly 1 embed sent
    assert channel.send.call_count == 1

    conn.close()


# ---------------------------------------------------------------------------
# INT-3: Source failure resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_int3_source_failure_resilience() -> None:
    """INT-3: failing source is skipped; good source jobs flow through."""
    conn = make_db()

    # job_1: Remote + salary $90k → score 40+30+30 = 100 (posted)
    job_1 = RawJob(
        source="good_source",
        external_id="g1",
        title="Remote Backend Engineer",
        company="AlphaCorp",
        location_raw="Remote",
        salary_raw="$90k",
        tags_raw="python,remote",
        url="https://example.com/g1",
    )
    # job_2: Remote + no salary → score 0+30+30 = 60 (posted)
    job_2 = RawJob(
        source="good_source",
        external_id="g2",
        title="Remote Frontend Engineer",
        company="BetaCorp",
        location_raw="Remote",
        salary_raw=None,
        tags_raw="javascript,remote",
        url="https://example.com/g2",
    )

    sources = [
        _FailingSource(),
        _MockSource("good_source", [job_1, job_2]),
    ]
    channel = _make_channel()

    # Pipeline must complete without raising
    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        run_recon(conn, sources)
        run_dedup(conn)
        run_pulse(conn)
        await run_herald(conn, channel)

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
    assert raw_count == 2  # only good source contributed

    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert job_count == 2

    qualifying = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE pulse_score >= 60"
    ).fetchone()[0]
    assert channel.send.call_count == qualifying

    conn.close()


# ---------------------------------------------------------------------------
# INT-4: HOT badge threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_int4_hot_badge_threshold() -> None:
    """INT-4: score >= 80 → gold embed (HOT); 60–79 → blue embed (normal)."""
    conn = make_db()

    # HOT job: score 100
    _insert_scored_job(
        conn,
        score=100,
        url="https://example.com/hot",
        title="Remote Staff Engineer",
        company="HotCo",
        location_country="REMOTE",
        salary_max_usd=120_000,
    )
    # Normal job: score 60
    _insert_scored_job(
        conn,
        score=60,
        url="https://example.com/normal",
        title="Remote Junior Engineer",
        company="NormalCo",
        location_country="REMOTE",
        salary_max_usd=None,
    )

    channel = _make_channel()
    captured_embeds: list[discord.Embed] = []

    async def _capture_send(**kwargs: object) -> MagicMock:
        embed = kwargs.get("embed")
        if embed is not None:
            captured_embeds.append(embed)  # type: ignore[arg-type]
        return MagicMock()

    channel.send.side_effect = _capture_send

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        await run_herald(conn, channel)

    # Both jobs qualify (score >= 60)
    assert channel.send.call_count == 2
    assert len(captured_embeds) == 2

    # Herald fetches jobs ORDER BY pulse_score DESC → HOT first, normal second
    hot_embed = captured_embeds[0]
    normal_embed = captured_embeds[1]

    assert hot_embed.color.value == 0xFFD700    # Gold
    assert normal_embed.color.value == 0x3498DB  # Blue

    conn.close()


# ---------------------------------------------------------------------------
# INT-5: No re-post guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_int5_no_repost_guard() -> None:
    """INT-5: running herald twice sends each eligible job exactly once."""
    conn = make_db()

    _insert_scored_job(
        conn,
        score=75,
        url="https://example.com/once",
        title="Remote Platform Engineer",
        company="OnceCo",
    )
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        await run_herald(conn, channel)
        await run_herald(conn, channel)

    # Second run must not re-post
    assert channel.send.call_count == 1

    # posted_at should be set after the first run
    row = conn.execute(
        "SELECT posted_at FROM jobs WHERE url = ?",
        ("https://example.com/once",),
    ).fetchone()
    assert row["posted_at"] is not None

    conn.close()


# ---------------------------------------------------------------------------
# INT-6: Empty pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_int6_empty_pipeline() -> None:
    """INT-6: zero-job source runs the full pipeline without errors."""
    conn = make_db()

    sources = [_MockSource("empty_source", [])]
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        run_recon(conn, sources)
        run_dedup(conn)
        run_pulse(conn)
        await run_herald(conn, channel)

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_jobs").fetchone()[0]
    assert raw_count == 0

    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert job_count == 0

    channel.send.assert_not_called()

    conn.close()
