"""Dedup agent — deduplicates raw jobs and promotes them to the jobs table.

Reads unprocessed raw_jobs, applies fuzzy matching against already-seen jobs
to detect near-duplicates, parses salary and location, and inserts unique jobs
into the canonical jobs table.
"""

from __future__ import annotations

import logging
import re
import sqlite3

from rapidfuzz import fuzz

from src.db.queries import (
    finish_pipeline_run,
    get_unprocessed_raw_jobs,
    insert_job,
    insert_pipeline_run,
    mark_raw_job_processed,
)

try:
    from src.config import DEDUP_THRESHOLD
except RuntimeError:
    DEDUP_THRESHOLD = 85

__all__ = ["parse_salary", "parse_location", "run_dedup"]

_log = logging.getLogger(__name__)

# Mapping of common location strings to ISO 3166-1 alpha-2 codes.
_LOCATION_MAP: dict[str, str] = {
    "united states": "US",
    "usa": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "germany": "DE",
    "deutschland": "DE",
    "canada": "CA",
    "australia": "AU",
    "france": "FR",
    "netherlands": "NL",
    "spain": "ES",
    "portugal": "PT",
    "india": "IN",
    "brazil": "BR",
    "singapore": "SG",
    "poland": "PL",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
}

_REMOTE_TERMS = frozenset({"remote", "worldwide", "anywhere", "global", "work from home", "wfh"})

# Matches patterns like: "80000-120000", "80,000-120,000", "$80k-$120k", "80K"
_SALARY_RANGE_RE = re.compile(
    r"\$?\s*(\d[\d,]*)\s*[kK]?\s*[-–—to]+\s*\$?\s*(\d[\d,]*)\s*[kK]?",
    re.IGNORECASE,
)
_SALARY_SINGLE_RE = re.compile(
    r"\$?\s*(\d[\d,]+)\s*[kK]?",
    re.IGNORECASE,
)


def parse_salary(salary_raw: str | None) -> tuple[int | None, int | None]:
    """Parse a raw salary string into a (min_usd, max_usd) annual tuple.

    Handles formats: "100000-150000", "$100k", "100K-150K", "80,000", None.
    Values ending in K/k are multiplied by 1000. Values ≤ 999 are treated as
    hourly rates and converted to annual (× 2080).

    Args:
        salary_raw: Raw salary string from the job source, or None.

    Returns:
        A tuple of (salary_min_usd, salary_max_usd), both may be None.
    """
    if not salary_raw:
        return None, None

    def _to_int(raw: str, has_k: bool) -> int:
        value = int(raw.replace(",", ""))
        if has_k:
            value *= 1000
        elif value <= 999:
            # Likely an hourly rate — convert to annual.
            value *= 2080
        return value

    range_match = _SALARY_RANGE_RE.search(salary_raw)
    if range_match:
        raw_lo, raw_hi = range_match.group(1), range_match.group(2)
        has_k = "k" in salary_raw.lower()
        try:
            return _to_int(raw_lo, has_k), _to_int(raw_hi, has_k)
        except ValueError:
            pass

    single_match = _SALARY_SINGLE_RE.search(salary_raw)
    if single_match:
        raw_val = single_match.group(1)
        has_k = "k" in salary_raw.lower()
        try:
            value = _to_int(raw_val, has_k)
            return value, value
        except ValueError:
            pass

    _log.debug("Could not parse salary_raw=%r", salary_raw)
    return None, None


def parse_location(location_raw: str | None) -> str | None:
    """Normalise a raw location string to a country code or "REMOTE".

    Args:
        location_raw: Raw location string from the job source, or None.

    Returns:
        "REMOTE" for remote/worldwide locations, an ISO country code for
        known countries, or None for unrecognised input.
    """
    if not location_raw:
        return None

    lower = location_raw.strip().lower()

    if any(term in lower for term in _REMOTE_TERMS):
        return "REMOTE"

    # Try direct lookup first (whole string, then last comma-separated part).
    if lower in _LOCATION_MAP:
        return _LOCATION_MAP[lower]

    parts = [p.strip() for p in lower.split(",")]
    for part in reversed(parts):
        if part in _LOCATION_MAP:
            return _LOCATION_MAP[part]
        # Two-letter uppercase code check (e.g. "New York, US")
        if re.match(r"^[a-z]{2}$", part):
            code = part.upper()
            # Validate it's a plausible ISO code by checking all-alpha
            return code

    return None


def run_dedup(conn: sqlite3.Connection) -> int:
    """Deduplicate unprocessed raw jobs and promote unique ones to jobs table.

    Uses rapidfuzz token_set_ratio on "title + company" to detect near-
    duplicate postings. Unique jobs are parsed and inserted into the canonical
    jobs table.

    Args:
        conn: Active SQLite connection.

    Returns:
        Number of new jobs inserted into the jobs table.
    """
    run_id = insert_pipeline_run(conn, "dedup")
    conn.commit()

    unprocessed = get_unprocessed_raw_jobs(conn)
    _log.info("Dedup: %d unprocessed raw jobs to evaluate", len(unprocessed))

    # Build a list of canonical "title + company" strings already in jobs.
    # Use index-based access so this works regardless of the connection's row_factory.
    seen_signatures: list[str] = [
        f"{row[0]} {row[1]}".lower()
        for row in conn.execute("SELECT title, company FROM jobs").fetchall()
    ]

    inserted_count = 0

    for raw in unprocessed:
        signature = f"{raw['title']} {raw['company']}".lower()

        # Fuzzy-match against all previously seen signatures.
        # token_sort_ratio respects all tokens (including company name) while
        # tolerating reordering, unlike token_set_ratio which ignores unique tokens.
        is_duplicate = any(
            fuzz.token_sort_ratio(signature, seen) >= DEDUP_THRESHOLD
            for seen in seen_signatures
        )

        if is_duplicate:
            _log.debug("Duplicate detected, skipping: %r", raw["title"])
            mark_raw_job_processed(conn, raw["id"])
            conn.commit()
            continue

        # Parse salary and location.
        salary_min, salary_max = parse_salary(raw.get("salary_raw"))
        location_country = parse_location(raw.get("location_raw"))

        inserted = insert_job(
            conn,
            title=raw["title"],
            company=raw["company"],
            location_country=location_country,
            salary_min_usd=salary_min,
            salary_max_usd=salary_max,
            tags_raw=raw.get("tags_raw"),
            url=raw["url"],
            source=raw["source"],
        )

        mark_raw_job_processed(conn, raw["id"])
        conn.commit()

        if inserted:
            seen_signatures.append(signature)
            inserted_count += 1
            _log.debug("Inserted new job: %r @ %r", raw["title"], raw["company"])

    finish_pipeline_run(conn, run_id, inserted_count, "success")
    conn.commit()
    _log.info("Dedup complete — %d new jobs inserted", inserted_count)
    return inserted_count
