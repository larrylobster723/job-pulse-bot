"""Bot entry point for TechPulse Jobs Bot.

Initialises the Discord bot, scheduler, and pipeline orchestration.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timezone

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

from src.agents.dedup import run_dedup
from src.agents.herald import run_herald
from src.agents.pulse import run_pulse
from src.agents.recon import get_enabled_sources, run_recon
from src.bot.commands import setup as setup_commands
from src.db.init import init_db

try:
    from src.config import (
        DB_PATH,
        DISCORD_BOT_TOKEN,
        DISCORD_GUILD_ID,
        DISCORD_JOBS_CHANNEL_ID,
        ENABLED_SOURCES,
        LOG_LEVEL,
        POLL_INTERVAL_SECONDS,
    )
except RuntimeError as _cfg_err:
    raise SystemExit(f"Configuration error: {_cfg_err}") from _cfg_err

__all__ = ["bot"]

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_log = logging.getLogger(__name__)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
_bot_start_time: datetime = datetime.now(timezone.utc)
_scheduler: AsyncIOScheduler | None = None


async def run_pipeline(bot_instance: commands.Bot) -> None:
    """Execute the full RECON → DEDUP → PULSE → HERALD pipeline.

    Pipeline errors are caught and logged — the bot is never crashed.

    Args:
        bot_instance: The running Discord bot, used to resolve the jobs channel.
    """
    t_start = time.monotonic()
    _log.info("Pipeline run starting")

    try:
        channel = bot_instance.get_channel(DISCORD_JOBS_CHANNEL_ID)
        if channel is None:
            _log.error("Jobs channel %d not found — skipping herald", DISCORD_JOBS_CHANNEL_ID)

        sources = get_enabled_sources(ENABLED_SOURCES)

        with sqlite3.connect(DB_PATH) as conn:
            new_raw = run_recon(conn, sources)
            _log.info("Recon: %d new raw jobs", new_raw)

        with sqlite3.connect(DB_PATH) as conn:
            new_jobs = run_dedup(conn)
            _log.info("Dedup: %d new canonical jobs", new_jobs)

        with sqlite3.connect(DB_PATH) as conn:
            scored = run_pulse(conn)
            _log.info("Pulse: %d jobs scored", scored)

        if channel is not None and isinstance(channel, discord.TextChannel):
            with sqlite3.connect(DB_PATH) as conn:
                posted = await run_herald(conn, channel)
            _log.info("Herald: %d jobs posted", posted)

    except Exception as exc:
        _log.error("Pipeline error (bot continues): %s", exc, exc_info=True)

    elapsed = time.monotonic() - t_start
    _log.info("Pipeline run finished in %.2fs", elapsed)


@bot.event
async def on_ready() -> None:
    """Handle the bot's ready event.

    Syncs guild-scoped slash commands, initialises the DB, and starts
    the APScheduler pipeline job. Called once when the bot connects.
    """
    global _scheduler, _bot_start_time  # noqa: PLW0603
    _bot_start_time = datetime.now(timezone.utc)

    _log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")

    init_db(DB_PATH)

    guild = discord.Object(id=DISCORD_GUILD_ID)
    setup_commands(bot, _bot_start_time, guild=guild)
    synced = await bot.tree.sync(guild=guild)
    _log.info("Synced %d slash commands to guild %d", len(synced), DISCORD_GUILD_ID)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_pipeline,
        trigger="interval",
        seconds=POLL_INTERVAL_SECONDS,
        args=[bot],
        max_instances=1,
        id="pipeline",
    )
    _scheduler.start()
    _log.info(
        "Scheduler started — pipeline runs every %ds", POLL_INTERVAL_SECONDS
    )

    # Run immediately on first boot so the channel is populated right away.
    asyncio.create_task(run_pipeline(bot))


def main() -> None:
    """Entry point — start the Discord bot."""
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
