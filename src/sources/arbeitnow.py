"""Arbeitnow job source adapter.

Fetches job listings from the Arbeitnow public job board API.
"""

from __future__ import annotations

import logging
from json import JSONDecodeError

import requests

from src.sources.base import JobSource, RawJob

__all__ = ["ArbeitnowSource"]

_log = logging.getLogger(__name__)

_API_URL = "https://arbeitnow.com/api/job-board-api"
_REQUEST_TIMEOUT = 30


class ArbeitnowSource(JobSource):
    """Job source adapter for https://arbeitnow.com/api/job-board-api.

    Salary data is not available from this source.
    """

    @property
    def source_name(self) -> str:
        """Return the unique identifier for this source.

        Returns:
            The string "arbeitnow".
        """
        return "arbeitnow"

    def fetch(self) -> list[RawJob]:
        """Fetch current job listings from Arbeitnow.

        Returns:
            A list of :class:`~src.sources.base.RawJob` instances.
        """
        _log.info("Fetching jobs from Arbeitnow")
        try:
            response = requests.get(_API_URL, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            _log.error("Arbeitnow request failed: %s", exc)
            raise

        try:
            payload = response.json()
        except JSONDecodeError as exc:
            _log.error("Arbeitnow returned invalid JSON: %s", exc)
            raise

        jobs: list[RawJob] = []
        try:
            items = payload["data"]
        except KeyError as exc:
            _log.error("Arbeitnow response missing 'data' field: %s", exc)
            return jobs

        for item in items:
            try:
                tags = item.get("tags") or []
                tags_raw = ",".join(str(t) for t in tags) if tags else None

                jobs.append(
                    RawJob(
                        source=self.source_name,
                        external_id=str(item["slug"]),
                        title=str(item["title"]),
                        company=str(item["company_name"]),
                        location_raw=item.get("location") or None,
                        salary_raw=None,  # Arbeitnow does not expose salary
                        tags_raw=tags_raw,
                        url=str(item["url"]),
                    )
                )
            except KeyError as exc:
                _log.warning("Skipping Arbeitnow item missing field %s: %r", exc, item)

        _log.info("Arbeitnow returned %d jobs", len(jobs))
        return jobs
