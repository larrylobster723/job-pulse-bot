"""Database initialisation module.

Creates the SQLite database file and applies the schema idempotently.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

__all__ = ["init_db"]

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: str) -> None:
    """Create the SQLite database and apply the schema.

    Idempotent — safe to call multiple times. Uses CREATE TABLE IF NOT EXISTS
    so existing data is never lost.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """
    logger.info("Initialising database at %s", db_path)
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_sql)
        conn.commit()
    logger.info("Database initialised successfully")


if __name__ == "__main__":
    import sys

    from src.config import DB_PATH, LOG_LEVEL

    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    init_db(path)
