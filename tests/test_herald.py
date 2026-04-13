"""Tests for the herald agent."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from src.agents.herald import run_herald
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


def _insert_scored_job(
    conn: sqlite3.Connection,
    *,
    score: int,
    url: str,
    title: str = "Engineer",
    company: str = "Corp",
    is_remote: bool = False,
    salary_max: int | None = None,
) -> None:
    """Insert a job and immediately set its pulse_score.

    Args:
        conn: Open SQLite connection.
        score: Pulse score to assign.
        url: Unique URL for this job.
        title: Job title.
        company: Company name.
        is_remote: Whether to set location_country="REMOTE".
        salary_max: Optional max salary in USD.
    """
    location = "REMOTE" if is_remote else None
    insert_job(
        conn,
        title=title,
        company=company,
        location_country=location,
        salary_min_usd=None,
        salary_max_usd=salary_max,
        tags_raw=None,
        url=url,
        source="test",
    )
    conn.execute(
        "UPDATE jobs SET pulse_score = ?, scored_at = datetime('now') WHERE url = ?",
        (score, url),
    )
    conn.commit()


def _make_channel() -> AsyncMock:
    """Create a mock Discord TextChannel with an async send method.

    Returns:
        An :class:`unittest.mock.AsyncMock` simulating a TextChannel.
    """
    channel = AsyncMock(spec=discord.TextChannel)
    channel.send = AsyncMock(return_value=MagicMock())
    return channel


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_herald_posts_high_score_job(db_conn: sqlite3.Connection) -> None:
    """Jobs with score >= 60 should be sent to the channel."""
    _insert_scored_job(db_conn, score=75, url="https://example.com/job/75")
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        posted = await run_herald(db_conn, channel)

    assert posted == 1
    channel.send.assert_called_once()


@pytest.mark.asyncio
async def test_herald_does_not_post_low_score_job(db_conn: sqlite3.Connection) -> None:
    """Jobs with score < 60 should NOT be sent to the channel."""
    _insert_scored_job(db_conn, score=50, url="https://example.com/job/50")
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        posted = await run_herald(db_conn, channel)

    assert posted == 0
    channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_herald_sets_posted_at_on_success(db_conn: sqlite3.Connection) -> None:
    """posted_at should be set on a job after it is successfully posted."""
    _insert_scored_job(db_conn, score=80, url="https://example.com/job/80")
    channel = _make_channel()

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        await run_herald(db_conn, channel)

    row = db_conn.execute(
        "SELECT posted_at FROM jobs WHERE url = ?",
        ("https://example.com/job/80",),
    ).fetchone()
    assert row["posted_at"] is not None


@pytest.mark.asyncio
async def test_herald_hot_embed_is_gold(db_conn: sqlite3.Connection) -> None:
    """Jobs scoring >= PULSE_HOT_THRESHOLD should use gold embed colour."""
    _insert_scored_job(
        db_conn,
        score=85,
        url="https://example.com/hot",
        is_remote=True,
        salary_max=130_000,
    )
    channel = _make_channel()
    captured_embeds: list[discord.Embed] = []

    async def _capture_send(**kwargs) -> MagicMock:
        embed = kwargs.get("embed")
        if embed:
            captured_embeds.append(embed)
        return MagicMock()

    channel.send.side_effect = _capture_send

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        await run_herald(db_conn, channel)

    assert len(captured_embeds) == 1
    assert captured_embeds[0].color.value == 0xFFD700  # Gold


@pytest.mark.asyncio
async def test_herald_normal_embed_is_blue(db_conn: sqlite3.Connection) -> None:
    """Jobs scoring < PULSE_HOT_THRESHOLD but >= 60 should use blue colour."""
    _insert_scored_job(db_conn, score=65, url="https://example.com/normal")
    channel = _make_channel()
    captured_embeds: list[discord.Embed] = []

    async def _capture_send(**kwargs) -> MagicMock:
        embed = kwargs.get("embed")
        if embed:
            captured_embeds.append(embed)
        return MagicMock()

    channel.send.side_effect = _capture_send

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        await run_herald(db_conn, channel)

    assert len(captured_embeds) == 1
    assert captured_embeds[0].color.value == 0x3498DB  # Blue


@pytest.mark.asyncio
async def test_herald_does_not_set_posted_at_on_retry_failure(
    db_conn: sqlite3.Connection,
) -> None:
    """If both attempts to post fail, posted_at must remain NULL."""
    _insert_scored_job(db_conn, score=70, url="https://example.com/fail")
    channel = _make_channel()
    channel.send.side_effect = discord.HTTPException(
        MagicMock(status=500), "Server error"
    )

    with patch("src.agents.herald.asyncio.sleep", new=AsyncMock()):
        posted = await run_herald(db_conn, channel)

    assert posted == 0
    row = db_conn.execute(
        "SELECT posted_at FROM jobs WHERE url = ?",
        ("https://example.com/fail",),
    ).fetchone()
    assert row["posted_at"] is None
