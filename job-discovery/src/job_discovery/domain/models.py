"""Pydantic contracts for the discovery pipeline.

Four distinct stages, four distinct types -- never conflate them:

    JobSource.search()       -> SourceJobRef
    JobSource.fetch_detail() -> SourceJobObservation   (source-native, unnormalized)
    normalize.build_candidate() -> NormalizedJobCandidate  (canonical fields, not yet matched)
    JobRepository.upsert_observation() -> JobRecord + JobSourceListing  (persisted)

SourceTask and DiscoveryRun (architecture doc 7.2) are deferred until the
dispatcher exists; SearchQuery below is the minimal input JobSource.search()
needs and is not a replacement for that run-tracking model.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class SourceName(str, Enum):
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    INDEED = "indeed"
    LINKEDIN = "linkedin"


class WorkplaceType(str, Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class PostedAtQuality(str, Enum):
    """How much a filter is allowed to trust posted_at.

    exact/relative can drive a strict "posted in the last N hours" filter.
    inferred is sortable but not filterable. unknown means fall back to
    first_seen_at -- this is the normal case for LinkedIn, which returned
    a null posted date in every probe run regardless of hours_old.
    """

    EXACT = "exact"
    RELATIVE = "relative"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    REVIEW = "review"


class FilterCode(str, Enum):
    LOCATION_MISMATCH = "location_mismatch"
    EXCLUDED_TITLE = "excluded_title"
    REVIEW_TITLE = "review_title"
    TITLE_NOT_RELEVANT = "title_not_relevant"
    DESCRIPTION_TOO_SHORT = "description_too_short"
    DESCRIPTION_MISSING = "description_missing"


class ListingStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    CLOSED = "closed"


class DedupKeyKind(str, Enum):
    """Priority order, strongest first. deduplicate.py emits in this order;
    repositories must probe in this order and stop at the first match."""

    SOURCE_ID = "source_id"
    APPLY_URL = "apply_url"
    DESCRIPTION_HASH = "description_hash"
    COMPANY_TITLE_LOCATION = "company_title_location"


class UpsertStatus(str, Enum):
    JOB_CREATED = "job_created"
    LISTING_ADDED = "listing_added"
    LISTING_UPDATED = "listing_updated"
    LISTING_UNCHANGED = "listing_unchanged"


class SearchQuery(BaseModel):
    """Minimal input to JobSource.search(). Not SourceTask -- no attempt
    counter, no expiry, no status. Add those when the dispatcher exists."""

    source: SourceName
    query: str
    location: str | None = None
    hours_old: int = 24
    max_results: int = 50
    run_id: str


class SourceJobRef(BaseModel):
    """Lightweight handle returned by search(), enough to fetch detail.
    Carries run_id because fetch_detail() has no other way to know which
    run it belongs to -- interfaces.JobSource.fetch_detail() takes only
    this ref, not the original SearchQuery."""

    source: SourceName
    source_job_id: str
    source_url: str
    run_id: str


class SourceJobObservation(BaseModel):
    """One fetch, source-native values mapped onto common field names but
    not yet normalized, hashed, or matched against anything."""

    source: SourceName
    source_job_id: str
    source_url: str
    apply_url_raw: str | None = None
    title_raw: str
    company_raw: str
    location_raw: str | None = None
    workplace_type_raw: str | None = None
    posted_at_raw: str | None = None
    description_raw: str | None = None
    salary_text_raw: str | None = None
    observed_at: datetime
    run_id: str


class NormalizedJobCandidate(BaseModel):
    """Output of normalize.build_candidate(). Canonical values, computed
    fields filled in, but not yet checked against the repository."""

    source: SourceName
    source_job_id: str
    source_url: str
    apply_url_raw: str | None = None
    apply_url_canonical: str | None = None
    title: str
    normalized_title: str
    company: str
    normalized_company: str
    location: str | None = None
    normalized_location: str | None = None
    workplace_type: WorkplaceType
    posted_at: datetime | None = None
    posted_at_raw: str | None = None
    posted_at_quality: PostedAtQuality
    description: str | None = None
    description_chars: int
    description_hash: str | None = None
    salary_text: str | None = None
    observed_at: datetime
    run_id: str


class DedupKey(BaseModel):
    kind: DedupKeyKind
    value: str


class DedupMatch(BaseModel):
    job_id: UUID
    matched_by: DedupKeyKind
    matched_key: str


class EligibilityDecision(BaseModel):
    """Immutable result of filters.apply_hard_filters(). Never mutate a
    candidate or record in place to attach eligibility -- pass this instead."""

    status: EligibilityStatus
    codes: list[FilterCode] = Field(default_factory=list)
    filter_version: str


class JobSourceListing(BaseModel):
    """One (job, source) pairing. A JobRecord can have several -- this is
    what lets the same posting be seen via both Indeed and Workday without
    collapsing into a single-source record."""

    listing_id: UUID
    job_id: UUID
    source: SourceName
    source_job_id: str
    source_url: str
    apply_url_canonical: str | None = None
    posted_at: datetime | None = None
    posted_at_raw: str | None = None
    posted_at_quality: PostedAtQuality
    first_seen_at: datetime
    last_seen_at: datetime
    first_miss_at: datetime | None = None
    consecutive_misses: int = 0
    last_seen_run_id: str
    status: ListingStatus = ListingStatus.ACTIVE


class JobRecord(BaseModel):
    """The persisted, cross-source canonical entity. Listings are fetched
    separately via JobRepository.list_listings(), not embedded, so updating
    one listing never requires rewriting this whole record."""

    job_id: UUID
    canonical_title: str
    canonical_company: str
    canonical_location: str | None = None
    workplace_type: WorkplaceType
    description: str | None = None
    description_chars: int
    description_hash: str | None = None
    salary_text: str | None = None
    required_years_min: int | None = None
    required_years_max: int | None = None
    requirement_keywords: list[str] = Field(default_factory=list)
    # Set only on a COMPANY_TITLE_LOCATION-only match: a real Lambda run
    # against TD found two different requisitions (R_1490005, R_1500633)
    # sharing title+company+location, which the weak key alone cannot tell
    # apart from a genuine duplicate. Flag for review instead of merging --
    # only SOURCE_ID and APPLY_URL/DESCRIPTION_HASH matches auto-merge.
    possible_duplicate_of: UUID | None = None
    duplicate_matched_by: DedupKeyKind | None = None
    eligibility_status: EligibilityStatus = EligibilityStatus.REVIEW
    filter_codes: list[FilterCode] = Field(default_factory=list)
    filter_version: str | None = None
    coarse_score: int | None = None
    coarse_score_reasoning: str | None = None
    score_model: str | None = None
    score_version: str | None = None
    scored_at: datetime | None = None
    user_status: str = "new"
    created_at: datetime
    updated_at: datetime


class UpsertResult(BaseModel):
    status: UpsertStatus
    job_id: UUID
    listing_id: UUID
    matched_by: DedupKeyKind | None = None
    possible_duplicate_of: UUID | None = None


class JobQuery(BaseModel):
    eligibility_status: EligibilityStatus | None = None
    min_score: int | None = None
    source: SourceName | None = None
    limit: int = 100


class ScoringProfile(BaseModel):
    """What gets sent to the scorer -- never resume text. Deliberately a
    structured subset (skills, target titles, experience, location), the
    same boundary the architecture doc's future Flow 2 handoff assumes:
    this project owns coarse scoring, a separate resume project owns resume
    content, and the two never share a payload."""

    skills: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    min_years_experience: int | None = None
    location_preference: str | None = None


class CoarseScore(BaseModel):
    score: int
    reasoning: str
    model: str
    scored_at: datetime
    required_years_min: int | None = None
    required_years_max: int | None = None
    requirement_keywords: list[str] = Field(default_factory=list)
