from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from job_discovery.dashboard.interfaces import DashboardJobReader
from job_discovery.dashboard.models import (
    DashboardJobDetail,
    DashboardJobPage,
    DashboardJobQuery,
    DashboardJobSummary,
    DashboardListing,
)
from job_discovery.domain.models import JobRecord, JobSourceListing, ListingStatus


def list_dashboard_jobs(reader: DashboardJobReader, query: DashboardJobQuery) -> DashboardJobPage:
    listings_by_job: dict[UUID, list[JobSourceListing]] = defaultdict(list)
    for listing in reader.list_all_listings():
        listings_by_job[listing.job_id].append(listing)

    summaries: list[DashboardJobSummary] = []
    for record in reader.list_records():
        listings = listings_by_job.get(record.job_id, [])
        if not _matches(record, listings, query):
            continue
        summaries.append(_to_summary(record, listings))

    summaries.sort(key=_sort_timestamp, reverse=True)
    total = len(summaries)
    return DashboardJobPage(items=summaries[: query.limit], total=total)


def get_dashboard_job(reader: DashboardJobReader, job_id: UUID) -> DashboardJobDetail | None:
    record = reader.get_record(job_id)
    if record is None:
        return None
    listings = reader.list_listings(job_id)
    summary = _to_summary(record, listings)
    return DashboardJobDetail(
        **summary.model_dump(),
        description=record.description,
        description_chars=record.description_chars,
        required_years_min=record.required_years_min,
        required_years_max=record.required_years_max,
        coarse_score_reasoning=record.coarse_score_reasoning,
        score_model=record.score_model,
        score_version=record.score_version,
        scored_at=record.scored_at,
        listings=[_to_listing(listing) for listing in _sort_listings(listings)],
    )


def _matches(record: JobRecord, listings: list[JobSourceListing], query: DashboardJobQuery) -> bool:
    if query.eligibility_status is not None and record.eligibility_status is not query.eligibility_status:
        return False
    if query.min_score is not None and (record.coarse_score is None or record.coarse_score < query.min_score):
        return False
    if query.source is not None and not any(listing.source is query.source for listing in listings):
        return False
    return True


def _to_summary(record: JobRecord, listings: list[JobSourceListing]) -> DashboardJobSummary:
    ordered = _sort_listings(listings)
    active = [listing for listing in ordered if listing.status is ListingStatus.ACTIVE]
    preferred = active[0] if active else ordered[0] if ordered else None
    first_seen_at = min(
        (listing.first_seen_at for listing in listings),
        key=_utc_datetime,
        default=record.created_at,
    )
    sources = sorted({listing.source for listing in listings}, key=lambda source: source.value)
    return DashboardJobSummary(
        job_id=record.job_id,
        title=record.canonical_title,
        company=record.canonical_company,
        location=record.canonical_location,
        workplace_type=record.workplace_type,
        salary_text=record.salary_text,
        eligibility_status=record.eligibility_status,
        filter_codes=record.filter_codes,
        coarse_score=record.coarse_score,
        posted_at=preferred.posted_at if preferred else None,
        first_seen_at=first_seen_at,
        sources=sources,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_listing(listing: JobSourceListing) -> DashboardListing:
    return DashboardListing(
        listing_id=listing.listing_id,
        source=listing.source,
        source_url=listing.source_url,
        apply_url=listing.apply_url_canonical,
        posted_at=listing.posted_at,
        posted_at_raw=listing.posted_at_raw,
        posted_at_quality=listing.posted_at_quality,
        first_seen_at=listing.first_seen_at,
        last_seen_at=listing.last_seen_at,
        status=listing.status,
    )


def _sort_listings(listings: list[JobSourceListing]) -> list[JobSourceListing]:
    return sorted(
        listings,
        key=lambda listing: (
            listing.status is ListingStatus.ACTIVE,
            _utc_datetime(listing.posted_at),
            _utc_datetime(listing.last_seen_at),
        ),
        reverse=True,
    )


def _sort_timestamp(job: DashboardJobSummary) -> datetime:
    return _utc_datetime(job.posted_at or job.first_seen_at)


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
