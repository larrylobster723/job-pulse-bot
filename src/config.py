"""Configuration module for TechPulse Jobs Bot.

Loads all settings from environment variables via python-dotenv.
No magic numbers or hardcoded values anywhere else in the codebase.
"""

from __future__ import annotations

import logging
import os
from typing import Final

from dotenv import load_dotenv

__all__ = [
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "DISCORD_JOBS_CHANNEL_ID",
    "DB_PATH",
    "POLL_INTERVAL_SECONDS",
    "DEDUP_THRESHOLD",
    "PULSE_POST_THRESHOLD",
    "PULSE_HOT_THRESHOLD",
    "SALARY_MARKET_MEDIAN_USD",
    "ENABLED_SOURCES",
    "LOG_LEVEL",
]

load_dotenv()

_log = logging.getLogger(__name__)


def _require(key: str) -> str:
    """Return the value of a required environment variable.

    Args:
        key: The environment variable name.

    Returns:
        The string value of the variable.

    Raises:
        RuntimeError: If the variable is not set or is empty.
    """
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return value


def _get_int(key: str, default: int) -> int:
    """Return an environment variable parsed as int, with a default.

    Args:
        key: The environment variable name.
        default: Fallback value if the variable is absent or unparseable.

    Returns:
        Integer value.
    """
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("Invalid integer for %s=%r, using default %d", key, raw, default)
        return default


def _get_list(key: str, default: list[str]) -> list[str]:
    """Return an environment variable parsed as a comma-separated list.

    Args:
        key: The environment variable name.
        default: Fallback value if the variable is absent.

    Returns:
        List of stripped, non-empty strings.
    """
    raw = os.getenv(key)
    if raw is None:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# Required settings
DISCORD_BOT_TOKEN: Final[str] = _require("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID: Final[int] = int(_require("DISCORD_GUILD_ID"))
DISCORD_JOBS_CHANNEL_ID: Final[int] = int(_require("DISCORD_JOBS_CHANNEL_ID"))

# Optional settings with defaults
DB_PATH: Final[str] = os.getenv("DB_PATH", "jobs.db")
POLL_INTERVAL_SECONDS: Final[int] = _get_int("POLL_INTERVAL_SECONDS", 3600)
DEDUP_THRESHOLD: Final[int] = _get_int("DEDUP_THRESHOLD", 85)
PULSE_POST_THRESHOLD: Final[int] = _get_int("PULSE_POST_THRESHOLD", 60)
PULSE_HOT_THRESHOLD: Final[int] = _get_int("PULSE_HOT_THRESHOLD", 80)
SALARY_MARKET_MEDIAN_USD: Final[int] = _get_int("SALARY_MARKET_MEDIAN_USD", 80_000)
ENABLED_SOURCES: Final[list[str]] = _get_list(
    "ENABLED_SOURCES", ["remoteok", "arbeitnow"]
)
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO")
