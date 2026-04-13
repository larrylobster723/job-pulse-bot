"""RemoteOK job source adapter.

Fetches job listings from the RemoteOK public API.
"""

from __future__ import annotations

import json
import logging
from json import JSONDecodeError

import requests

from src.sources.base import JobSource, RawJob

__all__ = ["RemoteOKSource"]

_log = logging.getLogger(__name__)

_API_URL = "https://remoteok.com/api"
_REQUEST_TIMEOUT = 30


class RemoteOKSource(JobSource):
    """Job source adapter for https://remoteok.com/api.

    The first element of the JSON array is metadata and is skipped.
    """

    @property
    def source_name(self) -> str:
        """Return the unique identifier for this source.

        Returns:
            The string "remoteok".
        """
        return "remoteok"

    def fetch(self) -> list[RawJob]:
        """Fetch current remote job listings from RemoteOK.

        Returns:
            A list of :class:`~src.sources.base.RawJob` instances.
        """
        _log.info("Fetching jobs from RemoteOK")
        try:
            response = requests.get(
                _API_URL,
                timeout=_REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            _log.error("RemoteOK request failed: %s", exc)
            raise

        try:
            data = response.json()
        except JSONDecodeError as exc:
            _log.error("RemoteOK returned invalid JSON: %s", exc)
            raise

        # First element is always metadata — skip it.
        jobs: list[RawJob] = []
        for item in data[1:]:
            try:
                salary_min = item.get("salary_min")
                salary_max = item.get("salary_max")
                if salary_min is not None and salary_max is not None:
                    salary_raw = f"{salary_min}-{salary_max}"
                else:
                    salary_raw = None

                tags = item.get("tags") or []
                tags_raw = ",".join(str(t) for t in tags) if tags else None

                jobs.append(
                    RawJob(
                        source=self.source_name,
                        external_id=str(item["id"]),
                        title=str(item["position"]),
                        company=str(item["company"]),
                        location_raw=item.get("location") or None,
                        salary_raw=salary_raw,
                        tags_raw=tags_raw,
                        url=str(item["url"]),
                    )
                )
            except KeyError as exc:
                _log.warning("Skipping RemoteOK item missing field %s: %r", exc, item)

        _log.info("RemoteOK returned %d jobs", len(jobs))
        return jobs
