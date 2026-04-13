"""Slash command definitions for TechPulse Jobs Bot.

All commands are guild-scoped and non-ephemeral. DB errors return an error
embed rather than raising so the bot remains responsive.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.embeds import build_error_embed, build_job_embed, build_status_embed
from src.db.queries import get_pipeline_status

try:
    from src.config import DB_PATH, PULSE_POST_THRESHOLD
except RuntimeError:
    DB_PATH = "jobs.db"
    PULSE_POST_THRESHOLD = 60

__all__ = ["setup"]

_log = logging.getLogger(__name__)

_MAX_RESULTS = 10


def _get_conn(db_path: str) -> sqlite3.Connection:
    """Open and return a SQLite connection with row_factory set.

    Args:
        db_path: Path to the SQLite file.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


class PulseGroup(app_commands.Group):
    """Slash command group for /pulse subcommands."""

    def __init__(self) -> None:
        """Initialise the /pulse command group."""
        super().__init__(name="pulse", description="TechPulse job search commands")

    @app_commands.command(name="today", description="Top jobs scored in the last 24 hours")
    async def today(self, interaction: discord.Interaction) -> None:
        """Post the top-10 PULSE-scored jobs from the last 24 hours.

        Args:
            interaction: The Discord slash command interaction.
        """
        try:
            with _get_conn(DB_PATH) as conn:
                since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                rows = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE first_seen_at > ?
                      AND pulse_score >= ?
                    ORDER BY pulse_score DESC
                    LIMIT ?
                    """,
                    (since, PULSE_POST_THRESHOLD, _MAX_RESULTS),
                ).fetchall()
        except sqlite3.Error as exc:
            _log.error("/pulse today DB error: %s", exc)
            await interaction.response.send_message(
                embed=build_error_embed("Database error fetching today's jobs."),
                ephemeral=False,
            )
            return

        if not rows:
            embed = discord.Embed(
                description="No jobs scored ≥60 in the last 24 hours. Check back soon! 🔍",
                color=0x3498DB,
            )
            embed.set_footer(text="TechPulse Jobs")
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        await interaction.response.send_message(
            embed=build_job_embed(dict(rows[0])), ephemeral=False
        )
        for row in rows[1:]:
            await interaction.followup.send(embed=build_job_embed(dict(row)))

    @app_commands.command(name="search", description="Search jobs by keyword")
    @app_commands.describe(keyword="Title, company, or tag to search for")
    async def search(self, interaction: discord.Interaction, keyword: str) -> None:
        """Search jobs by keyword across title, company, and tags.

        Args:
            interaction: The Discord slash command interaction.
            keyword: Search term to filter jobs by.
        """
        pattern = f"%{keyword}%"
        try:
            with _get_conn(DB_PATH) as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE (title LIKE ?
                        OR company LIKE ?
                        OR tags_raw LIKE ?)
                      AND pulse_score IS NOT NULL
                    ORDER BY pulse_score DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, _MAX_RESULTS),
                ).fetchall()
        except sqlite3.Error as exc:
            _log.error("/pulse search DB error: %s", exc)
            await interaction.response.send_message(
                embed=build_error_embed(f"Database error searching for '{keyword}'."),
                ephemeral=False,
            )
            return

        if not rows:
            embed = discord.Embed(
                description=f"No jobs found matching '{keyword}'.",
                color=0x3498DB,
            )
            embed.set_footer(text="TechPulse Jobs")
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        await interaction.response.send_message(
            embed=build_job_embed(dict(rows[0])), ephemeral=False
        )
        for row in rows[1:]:
            await interaction.followup.send(embed=build_job_embed(dict(row)))


class PipelineGroup(app_commands.Group):
    """Slash command group for /pipeline subcommands."""

    def __init__(self, bot_start_time: datetime) -> None:
        """Initialise the /pipeline command group.

        Args:
            bot_start_time: UTC datetime when the bot started, for uptime calc.
        """
        super().__init__(name="pipeline", description="Pipeline monitoring commands")
        self._bot_start_time = bot_start_time

    @app_commands.command(name="status", description="Show pipeline and bot status")
    async def status(self, interaction: discord.Interaction) -> None:
        """Post an embed with pipeline stats, last run info, and bot uptime.

        Args:
            interaction: The Discord slash command interaction.
        """
        try:
            with _get_conn(DB_PATH) as conn:
                pipeline_status = get_pipeline_status(conn)
        except sqlite3.Error as exc:
            _log.error("/pipeline status DB error: %s", exc)
            await interaction.response.send_message(
                embed=build_error_embed("Database error fetching pipeline status."),
                ephemeral=False,
            )
            return

        uptime_delta = datetime.now(timezone.utc) - self._bot_start_time
        total_seconds = int(uptime_delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        pipeline_status["uptime"] = f"{hours}h {minutes}m {seconds}s"

        await interaction.response.send_message(
            embed=build_status_embed(pipeline_status), ephemeral=False
        )


def setup(bot: commands.Bot, bot_start_time: datetime) -> None:
    """Register all slash command groups on the bot's command tree.

    Args:
        bot: The Discord bot instance.
        bot_start_time: UTC datetime when the bot started.
    """
    bot.tree.add_command(PulseGroup())
    bot.tree.add_command(PipelineGroup(bot_start_time))
