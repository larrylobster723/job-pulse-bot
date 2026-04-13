"""Herald agent — posts scored jobs to the Discord jobs channel.

Reads unposted jobs above PULSE_POST_THRESHOLD, builds rich embeds, and
sends them to the configured channel with rate-limiting between posts.
On Discord HTTP errors it retries once before logging and skipping.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3

import discord

from src.bot.embeds import build_job_embed
from src.db.queries import (
    finish_pipeline_run,
    get_unposted_jobs,
    insert_pipeline_run,
    mark_job_posted,
)

try:
    from src.config import PULSE_HOT_THRESHOLD, PULSE_POST_THRESHOLD
except RuntimeError:
    PULSE_POST_THRESHOLD = 60
    PULSE_HOT_THRESHOLD = 80

__all__ = ["run_herald"]

_log = logging.getLogger(__name__)

_RATE_LIMIT_SLEEP = 6       # seconds between posts
_RETRY_SLEEP = 10           # seconds before retry after HTTPException


async def run_herald(
    conn: sqlite3.Connection,
    channel: discord.TextChannel,
) -> int:
    """Post unposted, scored jobs to the Discord channel.

    Jobs with score >= PULSE_HOT_THRESHOLD get a gold embed; others get blue.
    On discord.HTTPException the message is retried once; if it fails again the
    job is skipped and posted_at is NOT set.

    Args:
        conn: Active SQLite connection.
        channel: The Discord text channel to post into.

    Returns:
        Number of jobs successfully posted.
    """
    run_id = insert_pipeline_run(conn, "herald")
    conn.commit()

    jobs = get_unposted_jobs(conn, PULSE_POST_THRESHOLD)
    _log.info("Herald: %d jobs eligible for posting", len(jobs))

    posted_count = 0

    for job in jobs:
        embed = build_job_embed(job)

        async def _send() -> None:
            """Send the embed to the channel (extracted for retry logic)."""
            await channel.send(embed=embed)

        try:
            await _send()
        except discord.HTTPException as exc:
            _log.warning(
                "Discord HTTPException posting job id=%s, retrying in %ds: %s",
                job["id"],
                _RETRY_SLEEP,
                exc,
            )
            await asyncio.sleep(_RETRY_SLEEP)
            try:
                await _send()
            except discord.HTTPException as retry_exc:
                _log.error(
                    "Retry failed for job id=%s — skipping: %s", job["id"], retry_exc
                )
                await asyncio.sleep(_RATE_LIMIT_SLEEP)
                continue

        mark_job_posted(conn, job["id"])
        conn.commit()
        posted_count += 1
        _log.debug("Posted job id=%s score=%s", job["id"], job.get("pulse_score"))

        await asyncio.sleep(_RATE_LIMIT_SLEEP)

    finish_pipeline_run(conn, run_id, posted_count, "success")
    conn.commit()
    _log.info("Herald complete — %d jobs posted", posted_count)
    return posted_count
