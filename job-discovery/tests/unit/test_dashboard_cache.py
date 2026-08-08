from __future__ import annotations

from uuid import UUID, uuid4

from job_discovery.dashboard.interfaces import DashboardJobReader
from job_discovery.domain.models import JobRecord, JobSourceListing
from job_discovery.repositories.dashboard_cache import CachingDashboardJobReader


class _CountingReader(DashboardJobReader):
    def __init__(self) -> None:
        self.list_records_calls = 0
        self.list_all_listings_calls = 0
        self.get_record_calls = 0
        self.list_listings_calls = 0

    def list_records(self) -> list[JobRecord]:
        self.list_records_calls += 1
        return []

    def list_all_listings(self) -> list[JobSourceListing]:
        self.list_all_listings_calls += 1
        return []

    def get_record(self, job_id: UUID) -> JobRecord | None:
        self.get_record_calls += 1
        return None

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        self.list_listings_calls += 1
        return []


def test_repeated_calls_within_ttl_hit_cache_once() -> None:
    delegate = _CountingReader()
    clock = [0.0]
    reader = CachingDashboardJobReader(delegate, ttl_seconds=30.0, time_source=lambda: clock[0])

    reader.list_records()
    reader.list_records()
    reader.list_all_listings()
    reader.list_all_listings()

    assert delegate.list_records_calls == 1
    assert delegate.list_all_listings_calls == 1


def test_cache_expires_after_ttl() -> None:
    delegate = _CountingReader()
    clock = [0.0]
    reader = CachingDashboardJobReader(delegate, ttl_seconds=30.0, time_source=lambda: clock[0])

    reader.list_records()
    clock[0] = 31.0
    reader.list_records()

    assert delegate.list_records_calls == 2


def test_get_record_and_list_listings_are_never_cached() -> None:
    delegate = _CountingReader()
    reader = CachingDashboardJobReader(delegate, ttl_seconds=30.0)

    job_id = uuid4()
    reader.get_record(job_id)
    reader.get_record(job_id)
    reader.list_listings(job_id)
    reader.list_listings(job_id)

    assert delegate.get_record_calls == 2
    assert delegate.list_listings_calls == 2
