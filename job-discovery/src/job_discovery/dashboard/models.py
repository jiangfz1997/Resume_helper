from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from job_discovery.domain.models import EligibilityStatus, FilterCode, ListingStatus, PostedAtQuality, SourceName, WorkplaceType


class DashboardJobQuery(BaseModel):
    eligibility_status: EligibilityStatus | None = None
    min_score: int | None = Field(default=None, ge=1, le=10)
    source: SourceName | None = None
    limit: int = Field(default=50, ge=1, le=500)


class JobLifecycleStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


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
    required_years_min: int | None = None
    required_years_max: int | None = None
    requirement_keywords: list[str] = Field(default_factory=list)
    first_discovered_run_id: str
    posted_at: datetime | None = None
    first_seen_at: datetime
    sources: list[SourceName] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    lifecycle_status: JobLifecycleStatus


class DashboardJobDetail(DashboardJobSummary):
    description: str | None = None
    description_chars: int
    coarse_score_reasoning: str | None = None
    score_model: str | None = None
    score_version: str | None = None
    scored_at: datetime | None = None
    listings: list[DashboardListing] = Field(default_factory=list)


class DashboardJobPage(BaseModel):
    schema_version: str = "job-dashboard.v1"
    items: list[DashboardJobSummary]
    total: int


class DashboardJobUserStatus(str, Enum):
    NEW = "new"
    SAVED = "saved"
    SELECTED = "selected"
    APPLIED = "applied"
    REJECTED = "rejected"


class DashboardRunSummary(BaseModel):
    run_id: str
    discovered_at: datetime
    new_jobs_count: int
    observed_count: int = 0
    eligible_count: int = 0
    review_count: int = 0
    excluded_count: int = 0
    error_count: int = 0
    sources: list[str] = Field(default_factory=list)
    status: str = "unknown"


class DiscoveryRunReport(BaseModel):
    run_id: str
    runner: str
    started_at: datetime
    completed_at: datetime
    sources: list[str] = Field(default_factory=list)
    observed_count: int = 0
    new_jobs_count: int = 0
    eligible_count: int = 0
    review_count: int = 0
    excluded_count: int = 0
    error_count: int = 0


class DashboardScoringQueue(BaseModel):
    eligible_total: int
    scored_current: int
    pending: int
    queued: int
    failed: int
    archived_skipped: int


class DashboardRunPage(BaseModel):
    items: list[DashboardRunSummary]


class DashboardJobUserState(BaseModel):
    job_id: UUID
    status: DashboardJobUserStatus = DashboardJobUserStatus.NEW
    first_viewed_at: datetime | None = None
    last_viewed_at: datetime | None = None
    updated_at: datetime
    coarse_score: int | None = None
    coarse_score_reasoning: str | None = None
    score_model: str | None = None
    score_version: str | None = None
    profile_version: int | None = None
    scored_at: datetime | None = None
    scoring_status: str | None = None
    scoring_profile_version: int | None = None
    score_error: str | None = None


class DashboardRunUserState(BaseModel):
    run_id: str
    viewed_at: datetime


class DashboardUserStateSnapshot(BaseModel):
    jobs: list[DashboardJobUserState] = Field(default_factory=list)
    runs: list[DashboardRunUserState] = Field(default_factory=list)


class UpdateJobStateRequest(BaseModel):
    status: DashboardJobUserStatus
