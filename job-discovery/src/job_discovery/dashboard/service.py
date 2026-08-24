from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from datetime import datetime, timedelta, timezone
from uuid import UUID

from job_discovery.dashboard.interfaces import DashboardJobReader, DashboardUserStateRepository
from job_discovery.dashboard.models import (
    DashboardBootstrap,
    DashboardJobDetail,
    DashboardJobPage,
    DashboardJobQuery,
    DashboardJobSummary,
    DashboardListing,
    DashboardScoringQueue,
    DashboardRunPage,
    DashboardRunSummary,
    DiscoveryRunReport,
    DashboardJobUserState,
    DashboardJobUserStatus,
    JobLifecycleStatus,
)
from job_discovery.domain.models import EligibilityStatus, JobRecord, JobSourceListing, ListingStatus
from job_discovery.domain.normalize import normalize_company
from job_discovery.domain.scoring_policy import is_scoreable_by_years


def list_dashboard_jobs(
    reader: DashboardJobReader,
    query: DashboardJobQuery,
    blocked_companies: Collection[str] = (),
) -> DashboardJobPage:
    blocked = _normalized_blocklist(blocked_companies)
    listings_by_job: dict[UUID, list[JobSourceListing]] = defaultdict(list)
    for listing in reader.list_all_listings():
        listings_by_job[listing.job_id].append(listing)

    summaries: list[DashboardJobSummary] = []
    for record in reader.list_records():
        listings = listings_by_job.get(record.job_id, [])
        if _is_blocked(record, blocked) or not _matches(record, listings, query):
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
        coarse_score_reasoning=record.coarse_score_reasoning,
        score_model=record.score_model,
        score_version=record.score_version,
        scored_at=record.scored_at,
        listings=[_to_listing(listing) for listing in _sort_listings(listings)],
    )


def list_dashboard_runs(
    reader: DashboardJobReader, reports: list[DiscoveryRunReport] | None = None
) -> DashboardRunPage:
    grouped: dict[str, list[JobRecord]] = defaultdict(list)
    for record in reader.list_records():
        if record.eligibility_status is EligibilityStatus.EXCLUDED:
            continue
        grouped[_first_run_id(record)].append(record)
    fallback_runs = [
        DashboardRunSummary(
            run_id=run_id,
            discovered_at=min((record.created_at for record in records), key=_utc_datetime),
            new_jobs_count=len(records),
        )
        for run_id, records in grouped.items()
    ]
    if not reports:
        fallback_runs.sort(key=lambda run: _utc_datetime(run.discovered_at), reverse=True)
        return DashboardRunPage(items=fallback_runs)

    fallback_by_id = {run.run_id: run for run in fallback_runs}
    reports_by_run: dict[str, list[DiscoveryRunReport]] = defaultdict(list)
    for report in reports:
        reports_by_run[report.run_id].append(report)
    runs: list[DashboardRunSummary] = []
    for run_id in set(fallback_by_id) | set(reports_by_run):
        parts = reports_by_run.get(run_id, [])
        fallback = fallback_by_id.get(run_id)
        errors = sum(part.error_count for part in parts)
        observed = sum(part.observed_count for part in parts)
        runs.append(DashboardRunSummary(
            run_id=run_id,
            discovered_at=min((part.started_at for part in parts), default=fallback.discovered_at if fallback else datetime.now(timezone.utc)),
            new_jobs_count=sum(part.new_jobs_count for part in parts) if parts else fallback.new_jobs_count,
            observed_count=observed,
            eligible_count=sum(part.eligible_count for part in parts),
            review_count=sum(part.review_count for part in parts),
            excluded_count=sum(part.excluded_count for part in parts),
            error_count=errors,
            sources=sorted({source for part in parts for source in part.sources}),
            status="failed" if errors and not observed else "partial" if errors else "ok",
        ))
    runs.sort(key=lambda run: _utc_datetime(run.discovered_at), reverse=True)
    return DashboardRunPage(items=runs)


def get_scoring_queue(
    reader: DashboardJobReader,
    states: list[DashboardJobUserState],
    profile_version: int | None,
    blocked_companies: Collection[str] = (),
    max_required_years: int | None = None,
) -> DashboardScoringQueue:
    blocked = _normalized_blocklist(blocked_companies)
    listings_by_job: dict[UUID, list[JobSourceListing]] = defaultdict(list)
    for listing in reader.list_all_listings():
        listings_by_job[listing.job_id].append(listing)
    current_scores = {
        state.job_id for state in states
        if state.coarse_score is not None and state.profile_version == profile_version
    }
    queued = {
        state.job_id for state in states
        if state.scoring_status == "queued" and state.scoring_profile_version == profile_version
    }
    failed = {
        state.job_id for state in states
        if state.scoring_status == "failed" and state.scoring_profile_version == profile_version
    }
    skipped = {
        state.job_id for state in states
        if state.status in {DashboardJobUserStatus.APPLIED, DashboardJobUserStatus.REJECTED}
    }
    all_eligible = [
        record for record in reader.list_records()
        if record.eligibility_status is EligibilityStatus.ELIGIBLE and not _is_blocked(record, blocked)
    ]
    seniority_skipped = {
        record.job_id for record in all_eligible
        if not is_scoreable_by_years(record, max_required_years)
    }
    eligible = [record for record in all_eligible if record.job_id not in seniority_skipped]
    archived = {
        record.job_id for record in eligible
        if _lifecycle_status(record, listings_by_job.get(record.job_id, [])) is JobLifecycleStatus.ARCHIVED
    }
    candidates = {record.job_id for record in eligible} - archived - skipped
    unscored = candidates - current_scores
    return DashboardScoringQueue(
        eligible_total=len(eligible),
        scored_current=len(candidates & current_scores),
        pending=len(unscored - queued - failed),
        queued=len(unscored & queued),
        failed=len(unscored & failed),
        archived_skipped=len(archived),
        seniority_skipped=len(seniority_skipped),
    )


def get_dashboard_bootstrap(
    reader: DashboardJobReader,
    state_repository: DashboardUserStateRepository,
    user_id: str,
    query: DashboardJobQuery,
) -> DashboardBootstrap:
    """Reads the user snapshot and scoring profile once each and shares them
    across the pieces that need them, so a page load costs one scan of each
    table rather than one per concurrent request."""
    snapshot = state_repository.get_snapshot(user_id)
    profile = state_repository.get_scoring_profile(user_id)
    settings = state_repository.get_discovery_settings()
    blocked_companies = state_repository.list_blocked_companies(user_id)
    return DashboardBootstrap(
        jobs=list_dashboard_jobs(reader, query, blocked_companies),
        runs=list_dashboard_runs(reader, state_repository.list_discovery_runs()),
        user_state=snapshot,
        scoring_profile=profile,
        scoring_queue=get_scoring_queue(
            reader, snapshot.jobs, profile.profile_version if profile else None, blocked_companies,
            settings.max_required_years,
        ),
        blocked_companies=blocked_companies,
    )


def _normalized_blocklist(companies: Collection[str]) -> frozenset[str]:
    return frozenset(normalize_company(company) for company in companies)


def _is_blocked(record: JobRecord, blocked: frozenset[str]) -> bool:
    return bool(blocked) and normalize_company(record.canonical_company) in blocked


def _matches(record: JobRecord, listings: list[JobSourceListing], query: DashboardJobQuery) -> bool:
    if query.eligibility_status is not None and record.eligibility_status is not query.eligibility_status:
        return False
    if query.min_score is not None and (record.coarse_score is None or record.coarse_score < query.min_score):
        return False
    if query.source is not None and not any(listing.source is query.source for listing in listings):
        return False
    if query.job_category is not None and record.job_category is not query.job_category:
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
    last_seen_at = max((listing.last_seen_at for listing in listings), key=_utc_datetime, default=record.updated_at)
    return DashboardJobSummary(
        job_id=record.job_id,
        title=record.canonical_title,
        company=record.canonical_company,
        location=record.canonical_location,
        workplace_type=record.workplace_type,
        salary_text=record.salary_text,
        job_category=record.job_category,
        primary_listing_url=(preferred.apply_url_canonical or preferred.source_url) if preferred else None,
        eligibility_status=record.eligibility_status,
        filter_codes=record.filter_codes,
        coarse_score=record.coarse_score,
        required_years_min=record.required_years_min,
        required_years_max=record.required_years_max,
        is_new_grad=record.is_new_grad,
        new_grad_signals=record.new_grad_signals,
        requirement_keywords=record.requirement_keywords,
        first_discovered_run_id=_first_run_id(record),
        posted_at=preferred.posted_at if preferred else None,
        first_seen_at=first_seen_at,
        sources=sources,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_seen_at=last_seen_at,
        lifecycle_status=_lifecycle_status(record, listings),
    )


def _lifecycle_status(record: JobRecord, listings: list[JobSourceListing]) -> JobLifecycleStatus:
    last_seen = max((listing.last_seen_at for listing in listings), key=_utc_datetime, default=record.updated_at)
    age = datetime.now(timezone.utc) - _utc_datetime(last_seen)
    if age >= timedelta(days=30):
        return JobLifecycleStatus.ARCHIVED
    if age >= timedelta(days=7):
        return JobLifecycleStatus.STALE
    return JobLifecycleStatus.ACTIVE


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


def _first_run_id(record: JobRecord) -> str:
    if record.first_discovered_run_id:
        return record.first_discovered_run_id
    created_at = _utc_datetime(record.created_at)
    return f"legacy-{created_at.strftime('%Y-%m-%dT%H:00Z')}"


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
