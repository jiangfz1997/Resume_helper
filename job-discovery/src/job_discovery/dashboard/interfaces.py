from __future__ import annotations

from typing import Protocol
from uuid import UUID

from job_discovery.domain.models import JobRecord, JobSourceListing


class DashboardJobReader(Protocol):
    def list_records(self) -> list[JobRecord]: ...

    def list_all_listings(self) -> list[JobSourceListing]: ...

    def get_record(self, job_id: UUID) -> JobRecord | None: ...

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]: ...
