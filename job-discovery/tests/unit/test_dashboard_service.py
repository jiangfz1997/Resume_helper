from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from job_discovery.dashboard.models import (
    DashboardJobQuery,
    DashboardJobUserState,
    DiscoveryRunReport,
    JobLifecycleStatus,
)
from job_discovery.dashboard.service import get_dashboard_job, get_scoring_queue, list_dashboard_jobs, list_dashboard_runs
from job_discovery.domain.models import (
    EligibilityStatus,
    JobRecord,
    JobSourceListing,
    ListingStatus,
    PostedAtQuality,
    SourceName,
    WorkplaceType,
)

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


class FakeDashboardReader:
    def __init__(self, records: list[JobRecord], listings: list[JobSourceListing]) -> None:
        self.records = records
        self.listings = listings

    def list_records(self) -> list[JobRecord]:
        return self.records

    def list_all_listings(self) -> list[JobSourceListing]:
        return self.listings

    def get_record(self, job_id: UUID) -> JobRecord | None:
        return next((record for record in self.records if record.job_id == job_id), None)

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        return [listing for listing in self.listings if listing.job_id == job_id]


def _record(title: str, score: int | None, status: EligibilityStatus = EligibilityStatus.ELIGIBLE) -> JobRecord:
    return JobRecord(
        job_id=uuid4(),
        canonical_title=title,
        canonical_company="Example",
        canonical_location="Toronto, ON",
        workplace_type=WorkplaceType.HYBRID,
        description=f"Description for {title}",
        description_chars=1000,
        eligibility_status=status,
        coarse_score=score,
        created_at=NOW,
        updated_at=NOW,
    )


def _listing(record: JobRecord, source: SourceName, posted_at: datetime | None = NOW) -> JobSourceListing:
    return JobSourceListing(
        listing_id=uuid4(),
        job_id=record.job_id,
        source=source,
        source_job_id=str(uuid4()),
        source_url="https://example.com/job",
        apply_url_canonical="https://example.com/apply",
        posted_at=posted_at,
        posted_at_quality=PostedAtQuality.EXACT,
        first_seen_at=NOW,
        last_seen_at=NOW,
        last_seen_run_id="run-1",
        status=ListingStatus.ACTIVE,
    )


def test_list_filters_and_joins_sources() -> None:
    strong = _record("Backend Engineer", 9)
    strong.required_years_min = 2
    strong.required_years_max = 4
    strong.requirement_keywords = ["Python", "AWS"]
    weak = _record("QA Engineer", 4)
    reader = FakeDashboardReader(
        [weak, strong],
        [_listing(strong, SourceName.WORKDAY), _listing(strong, SourceName.INDEED), _listing(weak, SourceName.LINKEDIN)],
    )

    page = list_dashboard_jobs(reader, DashboardJobQuery(min_score=8, source=SourceName.WORKDAY))

    assert page.total == 1
    assert page.items[0].job_id == strong.job_id
    assert page.items[0].sources == [SourceName.INDEED, SourceName.WORKDAY]
    assert page.items[0].required_years_min == 2
    assert page.items[0].required_years_max == 4
    assert page.items[0].requirement_keywords == ["Python", "AWS"]


def test_detail_includes_description_and_listings() -> None:
    record = _record("Software Engineer", 8)
    reader = FakeDashboardReader([record], [_listing(record, SourceName.WORKDAY)])

    detail = get_dashboard_job(reader, record.job_id)

    assert detail is not None
    assert detail.description == record.description
    assert detail.listings[0].apply_url == "https://example.com/apply"


def test_list_normalizes_mixed_timezone_timestamps() -> None:
    older = _record("Older Engineer", 7)
    newer = _record("Newer Engineer", 8)
    reader = FakeDashboardReader(
        [older, newer],
        [
            _listing(older, SourceName.INDEED, datetime(2026, 8, 4, tzinfo=timezone.utc)),
            _listing(newer, SourceName.LINKEDIN, datetime(2026, 8, 5)),
        ],
    )

    page = list_dashboard_jobs(reader, DashboardJobQuery())

    assert [item.job_id for item in page.items] == [newer.job_id, older.job_id]


def test_runs_group_jobs_by_first_discovery_run_with_legacy_fallback() -> None:
    current_a = _record("Backend Engineer", 8)
    current_b = _record("Frontend Engineer", 7)
    legacy = _record("Legacy Engineer", 6)
    current_a.first_discovered_run_id = "lambda-2026-08-05T12:00Z"
    current_b.first_discovered_run_id = "lambda-2026-08-05T12:00Z"
    legacy.created_at = datetime(2026, 8, 4, 17, 42, tzinfo=timezone.utc)
    reader = FakeDashboardReader([legacy, current_a, current_b], [])

    page = list_dashboard_runs(reader)

    assert [run.run_id for run in page.items] == ["lambda-2026-08-05T12:00Z", "legacy-2026-08-04T17:00Z"]
    assert page.items[0].new_jobs_count == 2


def test_run_reports_add_health_counts() -> None:
    record = _record("Backend Engineer", 8)
    record.first_discovered_run_id = "run-1"
    reader = FakeDashboardReader([record], [])
    report = DiscoveryRunReport(
        run_id="run-1", runner="jobspy", started_at=NOW, completed_at=NOW,
        sources=["indeed", "linkedin"], observed_count=10, new_jobs_count=3,
        eligible_count=6, review_count=2, excluded_count=2, error_count=1,
    )

    run = list_dashboard_runs(reader, [report]).items[0]

    assert run.new_jobs_count == 3
    assert run.observed_count == 10
    assert run.status == "partial"
    assert run.sources == ["indeed", "linkedin"]


def test_archived_jobs_are_excluded_from_scoring_queue() -> None:
    active = _record("Active Engineer", None)
    archived = _record("Old Engineer", None)
    active_listing = _listing(active, SourceName.INDEED)
    active_listing.last_seen_at = datetime.now(timezone.utc)
    archived_listing = _listing(archived, SourceName.WORKDAY)
    archived_listing.last_seen_at = datetime.now(timezone.utc) - timedelta(days=31)
    state = DashboardJobUserState(
        job_id=active.job_id, coarse_score=8, profile_version=2,
        updated_at=datetime.now(timezone.utc),
    )
    reader = FakeDashboardReader([active, archived], [active_listing, archived_listing])

    page = list_dashboard_jobs(reader, DashboardJobQuery())
    queue = get_scoring_queue(reader, [state], profile_version=2)

    assert next(job for job in page.items if job.job_id == archived.job_id).lifecycle_status is JobLifecycleStatus.ARCHIVED
    assert queue.scored_current == 1
    assert queue.pending == 0
    assert queue.queued == 0
    assert queue.failed == 0
    assert queue.archived_skipped == 1
