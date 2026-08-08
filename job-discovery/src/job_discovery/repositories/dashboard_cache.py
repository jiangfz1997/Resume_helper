from __future__ import annotations

import time
from typing import Callable
from uuid import UUID

from job_discovery.dashboard.interfaces import DashboardJobReader
from job_discovery.domain.models import JobRecord, JobSourceListing


class CachingDashboardJobReader(DashboardJobReader):
    """Wraps a DashboardJobReader and caches its two full-table reads.

    list_records() and list_all_listings() are DynamoDB Scans and dominate
    dashboard latency; get_record() and list_listings() are already cheap
    primary-key/query reads and are passed through uncached.
    """

    def __init__(
        self,
        delegate: DashboardJobReader,
        ttl_seconds: float,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._delegate = delegate
        self._ttl_seconds = ttl_seconds
        self._time_source = time_source
        self._records_cache: tuple[float, list[JobRecord]] | None = None
        self._listings_cache: tuple[float, list[JobSourceListing]] | None = None

    def list_records(self) -> list[JobRecord]:
        if self._records_cache is not None and self._is_fresh(self._records_cache[0]):
            return self._records_cache[1]
        records = self._delegate.list_records()
        self._records_cache = (self._time_source(), records)
        return records

    def list_all_listings(self) -> list[JobSourceListing]:
        if self._listings_cache is not None and self._is_fresh(self._listings_cache[0]):
            return self._listings_cache[1]
        listings = self._delegate.list_all_listings()
        self._listings_cache = (self._time_source(), listings)
        return listings

    def get_record(self, job_id: UUID) -> JobRecord | None:
        return self._delegate.get_record(job_id)

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        return self._delegate.list_listings(job_id)

    def _is_fresh(self, cached_at: float) -> bool:
        return self._time_source() - cached_at < self._ttl_seconds
