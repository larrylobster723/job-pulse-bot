"""Discord embed builder functions for TechPulse Jobs Bot.

Provides pure functions that convert data dicts into discord.Embed objects.
"""

from __future__ import annotations

import discord

try:
    from src.config import PULSE_HOT_THRESHOLD
except RuntimeError:
    PULSE_HOT_THRESHOLD = 80

__all__ = ["build_job_embed", "build_status_embed", "build_error_embed"]

_COLOR_HOT = 0xFFD700    # Gold
_COLOR_NORMAL = 0x3498DB  # Blue
_COLOR_ERROR = 0xFF4444   # Red
_COLOR_STATUS = 0x2ECC71  # Green


def _format_salary(salary_min: int | None, salary_max: int | None) -> str | None:
    """Format a salary range as a human-readable string.

    Args:
        salary_min: Annual minimum in USD, or None.
        salary_max: Annual maximum in USD, or None.

    Returns:
        Formatted string like "$80K–$120K", or None if both are absent or zero.
    """
    # Treat 0 same as None — no meaningful salary data
    min_val = salary_min if salary_min else None
    max_val = salary_max if salary_max else None

    if min_val is None and max_val is None:
        return None

    def _fmt(value: int) -> str:
        """Format an integer USD value as a short string like $80K."""
        return f"${value // 1000}K"

    if min_val is not None and max_val is not None:
        if min_val == max_val:
            return _fmt(min_val)
        return f"{_fmt(min_val)}–{_fmt(max_val)}"
    if min_val is not None:
        return f"{_fmt(min_val)}+"
    if max_val is not None:
        return f"Up to {_fmt(max_val)}"
    return None


def _format_timestamp(ts: str | None) -> str:
    """Format an ISO timestamp to a human-readable string.

    Args:
        ts: ISO 8601 timestamp string or None.

    Returns:
        Formatted string like "Apr 13, 2026 04:08 UTC", or "?" if unparseable.
    """
    if not ts:
        return "?"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, AttributeError):
        return ts


def build_job_embed(job: dict) -> discord.Embed:
    """Build a rich Discord embed for a single job posting.

    Gold colour (0xFFD700) and "🔥 HOT MATCH" footer for jobs scoring at or
    above PULSE_HOT_THRESHOLD; blue (0x3498DB) and "TechPulse Jobs" otherwise.

    Args:
        job: A dict with the columns from the jobs table.

    Returns:
        A fully populated :class:`discord.Embed` instance.
    """
    score: int = job.get("pulse_score") or 0
    is_hot = score >= PULSE_HOT_THRESHOLD

    embed = discord.Embed(
        title=job.get("title", "Untitled Position"),
        url=job.get("url") or None,
        color=_COLOR_HOT if is_hot else _COLOR_NORMAL,
    )

    embed.add_field(name="Company", value=job.get("company", "Unknown"), inline=True)

    location = job.get("location_country")
    if location:
        embed.add_field(name="Location", value=location, inline=True)

    salary_str = _format_salary(
        job.get("salary_min_usd"), job.get("salary_max_usd")
    )
    if salary_str:
        embed.add_field(name="Salary", value=salary_str, inline=True)

    embed.add_field(name="PULSE Score", value=str(score), inline=True)

    footer_text = "🔥 HOT MATCH" if is_hot else "TechPulse Jobs"
    embed.set_footer(text=footer_text)

    return embed


def build_status_embed(status: dict) -> discord.Embed:
    """Build a Discord embed summarising pipeline status.

    Args:
        status: Dict returned by :func:`~src.db.queries.get_pipeline_status`.

    Returns:
        A :class:`discord.Embed` with pipeline stats fields.
    """
    embed = discord.Embed(title="Pipeline Status", color=_COLOR_STATUS)

    embed.add_field(
        name="Raw Jobs (last hour)",
        value=str(status.get("raw_jobs_last_hour", 0)),
        inline=True,
    )
    embed.add_field(
        name="Total Jobs",
        value=str(status.get("total_jobs", 0)),
        inline=True,
    )

    avg = status.get("avg_score_last_24h")
    embed.add_field(
        name="Avg Score (24 h)",
        value=f"{avg:.1f}" if avg is not None else "—",
        inline=True,
    )

    last_run = status.get("last_run")
    if last_run:
        finished = _format_timestamp(
            last_run.get("finished_at") or last_run.get("started_at")
        )
        embed.add_field(
            name="Last Pipeline Run",
            value=(
                f"Agent: **{last_run.get('agent', '?')}**\n"
                f"Status: {last_run.get('status', '?')}\n"
                f"Jobs: {last_run.get('jobs_processed', 0)}\n"
                f"At: {finished}"
            ),
            inline=False,
        )
    else:
        embed.add_field(name="Last Pipeline Run", value="No runs recorded", inline=False)

    uptime = status.get("uptime")
    if uptime is not None:
        embed.add_field(name="Bot Uptime", value=uptime, inline=True)

    embed.set_footer(text="TechPulse Jobs")
    return embed


def build_error_embed(message: str) -> discord.Embed:
    """Build a simple error embed.

    Args:
        message: Human-readable error description.

    Returns:
        A red :class:`discord.Embed` with the error message.
    """
    embed = discord.Embed(
        title="Error",
        description=message,
        color=_COLOR_ERROR,
    )
    embed.set_footer(text="TechPulse Jobs")
    return embed
