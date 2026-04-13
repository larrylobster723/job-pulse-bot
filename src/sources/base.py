"""Abstract base class and shared dataclass for job sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

__all__ = ["RawJob", "JobSource"]


@dataclass
class RawJob:
    """A raw job record fetched from an external source.

    Attributes:
        source: Source identifier string (e.g. "remoteok").
        external_id: The source's own unique ID for this job.
        title: Job title as returned by the source.
        company: Company name as returned by the source.
        location_raw: Unparsed location string, or None.
        salary_raw: Unparsed salary string, or None.
        tags_raw: Comma-separated tags string, or None.
        url: Direct URL to the job posting.
    """

    source: str
    external_id: str
    title: str
    company: str
    location_raw: str | None
    salary_raw: str | None
    tags_raw: str | None
    url: str


class JobSource(ABC):
    """Abstract base class that all job source adapters must implement.

    Subclasses declare a :attr:`source_name` and implement :meth:`fetch`
    to return a list of :class:`RawJob` objects.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this source (e.g. "remoteok").

        Returns:
            A lowercase string identifier with no spaces.
        """

    @abstractmethod
    def fetch(self) -> list[RawJob]:
        """Fetch current job listings from the source.

        Returns:
            A list of :class:`RawJob` instances.

        Raises:
            requests.RequestException: On network-level errors.
        """
