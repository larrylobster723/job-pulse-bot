"""Recon agent — fetches jobs from all enabled sources and stores raw records.

Iterates over all configured job sources, calls fetch(), and persists results
to the raw_jobs table. Source-level errors are logged and skipped so one bad
source never crashes the pipeline.
"""

from __future__ import annotations

import logging
import sqlite3

from src.db.queries import (
    finish_pipeline_run,
    insert_pipeline_run,
    insert_raw_job,
)
from src.sources.arbeitnow import ArbeitnowSource
from src.sources.base import JobSource
from src.sources.remoteok import RemoteOKSource

__all__ = ["SOURCE_REGISTRY", "get_enabled_sources", "run_recon"]

_log = logging.getLogger(__name__)

SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    "remoteok": RemoteOKSource,
    "arbeitnow": ArbeitnowSource,
}


def get_enabled_sources(enabled: list[str]) -> list[JobSource]:
    """Instantiate job sources by name from the registry.

    Unknown names are logged and skipped.

    Args:
        enabled: List of source name strings (e.g. ["remoteok", "arbeitnow"]).

    Returns:
        List of instantiated :class:`~src.sources.base.JobSource` objects.
    """
    sources: list[JobSource] = []
    for name in enabled:
        cls = SOURCE_REGISTRY.get(name)
        if cls is None:
            _log.warning("Unknown source %r — skipping", name)
            continue
        sources.append(cls())
    return sources


def run_recon(conn: sqlite3.Connection, sources: list[JobSource]) -> int:
    """Fetch jobs from all sources and persist them to raw_jobs.

    Each source error is caught, logged, and skipped. The UNIQUE constraint
    on (source, external_id) makes this idempotent.

    Args:
        conn: Active SQLite connection.
        sources: List of instantiated job source adapters.

    Returns:
        Total count of newly inserted raw job rows.
    """
    run_id = insert_pipeline_run(conn, "recon")
    conn.commit()

    total_new = 0
    status = "success"

    for source in sources:
        try:
            jobs = source.fetch()
        except Exception as exc:
            _log.error("Source %r failed during fetch: %s", source.source_name, exc)
            status = "error"
            continue

        new_count = 0
        for job in jobs:
            try:
                inserted = insert_raw_job(
                    conn,
                    source=job.source,
                    external_id=job.external_id,
                    title=job.title,
                    company=job.company,
                    location_raw=job.location_raw,
                    salary_raw=job.salary_raw,
                    tags_raw=job.tags_raw,
                    url=job.url,
                )
                if inserted:
                    new_count += 1
            except sqlite3.Error as exc:
                _log.error(
                    "DB error inserting job %r from %r: %s",
                    job.external_id,
                    source.source_name,
                    exc,
                )

        conn.commit()
        _log.info(
            "Source %r: %d new jobs inserted (%d fetched)",
            source.source_name,
            new_count,
            len(jobs),
        )
        total_new += new_count

    finish_pipeline_run(conn, run_id, total_new, status)
    conn.commit()
    _log.info("Recon complete — %d new raw jobs", total_new)
    return total_new
