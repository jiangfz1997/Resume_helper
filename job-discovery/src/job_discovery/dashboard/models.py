from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from job_discovery.domain.models import EligibilityStatus, FilterCode, ListingStatus, PostedAtQuality, SourceName, WorkplaceType


class DashboardJobQuery(BaseModel):
    eligibility_status: EligibilityStatus | None = None
    min_score: int | None = Field(default=None, ge=1, le=10)
    source: SourceName | None = None
    limit: int = Field(default=50, ge=1, le=100)


class DashboardListing(BaseModel):
    listing_id: UUID
    source: SourceName
    source_url: str
    apply_url: str | None = None
    posted_at: datetime | None = None
    posted_at_raw: str | None = None
    posted_at_quality: PostedAtQuality
    first_seen_at: datetime
    last_seen_at: datetime
    status: ListingStatus


class DashboardJobSummary(BaseModel):
    job_id: UUID
    title: str
    company: str
    location: str | None = None
    workplace_type: WorkplaceType
    salary_text: str | None = None
    eligibility_status: EligibilityStatus
    filter_codes: list[FilterCode] = Field(default_factory=list)
    coarse_score: int | None = None
    posted_at: datetime | None = None
    first_seen_at: datetime
    sources: list[SourceName] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DashboardJobDetail(DashboardJobSummary):
    description: str | None = None
    description_chars: int
    required_years_min: int | None = None
    required_years_max: int | None = None
    coarse_score_reasoning: str | None = None
    score_model: str | None = None
    score_version: str | None = None
    scored_at: datetime | None = None
    listings: list[DashboardListing] = Field(default_factory=list)


class DashboardJobPage(BaseModel):
    schema_version: str = "job-dashboard.v1"
    items: list[DashboardJobSummary]
    total: int
