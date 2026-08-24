from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from job_discovery.dashboard.models import (
    DashboardJobQuery,
    DashboardJobUserState,
    DashboardUserStateSnapshot,
    DiscoveryRunReport,
    JobLifecycleStatus,
)
from job_discovery.dashboard.service import (
    get_dashboard_bootstrap,
    get_dashboard_job,
    get_scoring_queue,
    list_dashboard_jobs,
    list_dashboard_runs,
)
from job_discovery.domain.settings import DiscoverySettings, UserScoringProfile
from job_discovery.repositories.dashboard_cache import CachingDashboardJobReader
from job_discovery.domain.models import (
    EligibilityStatus,
    JobCategory,
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
        self.record_scans = 0
        self.listing_scans = 0

    def list_records(self) -> list[JobRecord]:
        self.record_scans += 1
        return self.records

    def list_all_listings(self) -> list[JobSourceListing]:
        self.listing_scans += 1
        return self.listings

    def get_record(self, job_id: UUID) -> JobRecord | None:
        return next((record for record in self.records if record.job_id == job_id), None)

    def list_listings(self, job_id: UUID) -> list[JobSourceListing]:
        return [listing for listing in self.listings if listing.job_id == job_id]


def _record(
    title: str,
    score: int | None,
    status: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    category: JobCategory | None = None,
) -> JobRecord:
    return JobRecord(
        job_id=uuid4(),
        canonical_title=title,
        canonical_company="Example",
        canonical_location="Toronto, ON",
        workplace_type=WorkplaceType.HYBRID,
        description=f"Description for {title}",
        description_chars=1000,
        job_category=category,
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


def test_list_filters_by_job_category() -> None:
    sde = _record("Backend Engineer", 8, category=JobCategory.SDE)
    qa = _record("QA Engineer", 6, category=JobCategory.QA)
    reader = FakeDashboardReader([sde, qa], [_listing(sde, SourceName.WORKDAY), _listing(qa, SourceName.WORKDAY)])

    page = list_dashboard_jobs(reader, DashboardJobQuery(job_category=JobCategory.QA))

    assert [item.job_id for item in page.items] == [qa.job_id]
    assert page.items[0].job_category is JobCategory.QA


def test_list_includes_primary_listing_url_for_cards() -> None:
    record = _record("Backend Engineer", 8)
    reader = FakeDashboardReader([record], [_listing(record, SourceName.WORKDAY)])

    page = list_dashboard_jobs(reader, DashboardJobQuery())

    assert page.items[0].primary_listing_url == "https://example.com/apply"


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


def test_scoring_queue_excludes_jobs_above_experience_cap() -> None:
    early = _record("Junior Backend Engineer", None)
    early.required_years_min = 3
    senior = _record("Backend Engineer", None)
    senior.required_years_min = 5
    senior.required_years_max = 8
    reader = FakeDashboardReader(
        [early, senior],
        [_listing(early, SourceName.INDEED), _listing(senior, SourceName.WORKDAY)],
    )

    queue = get_scoring_queue(reader, [], profile_version=1, max_required_years=5)

    assert queue.eligible_total == 1
    assert queue.pending == 1
    assert queue.seniority_skipped == 1


def test_blocked_company_leaves_the_list_and_the_scoring_queue() -> None:
    blocked = _record("Backend Engineer", None)
    blocked.canonical_company = "Jobright.ai"
    kept = _record("QA Engineer", None)
    kept.canonical_company = "Jobright Media"
    reader = FakeDashboardReader(
        [blocked, kept], [_listing(blocked, SourceName.INDEED), _listing(kept, SourceName.INDEED)]
    )

    page = list_dashboard_jobs(reader, DashboardJobQuery(), ["jobright.ai"])
    queue = get_scoring_queue(reader, [], profile_version=1, blocked_companies=["jobright.ai"])

    # Exact match after normalization: a company that merely starts with the
    # blocked name stays visible.
    assert [job.company for job in page.items] == ["Jobright Media"]
    assert page.total == 1
    assert queue.eligible_total == 1
    assert queue.pending == 1


def test_blocking_is_case_and_whitespace_insensitive() -> None:
    record = _record("Backend Engineer", None)
    record.canonical_company = "  Jobright.AI  "
    reader = FakeDashboardReader([record], [_listing(record, SourceName.INDEED)])

    page = list_dashboard_jobs(reader, DashboardJobQuery(), ["jobright.ai"])

    assert page.items == []


class CountingStateRepository:
    def __init__(
        self,
        snapshot: DashboardUserStateSnapshot,
        profile: UserScoringProfile | None,
        reports: list[DiscoveryRunReport],
    ) -> None:
        self.snapshot = snapshot
        self.profile = profile
        self.reports = reports
        self.blocked_companies: list[str] = []
        self.snapshot_calls = 0
        self.profile_calls = 0
        self.blocklist_calls = 0

    def get_snapshot(self, user_id: str) -> DashboardUserStateSnapshot:
        self.snapshot_calls += 1
        return self.snapshot

    def list_blocked_companies(self, user_id: str) -> list[str]:
        self.blocklist_calls += 1
        return self.blocked_companies

    def get_scoring_profile(self, user_id: str) -> UserScoringProfile | None:
        self.profile_calls += 1
        return self.profile

    def list_discovery_runs(self) -> list[DiscoveryRunReport]:
        return self.reports

    def get_discovery_settings(self) -> DiscoverySettings:
        return DiscoverySettings(max_required_years=5)


def _bootstrap_fixtures() -> tuple[FakeDashboardReader, CountingStateRepository]:
    scored = _record("Backend Engineer", 9)
    unscored = _record("QA Engineer", None)
    reader = FakeDashboardReader(
        [scored, unscored],
        [_listing(scored, SourceName.WORKDAY), _listing(unscored, SourceName.INDEED)],
    )
    snapshot = DashboardUserStateSnapshot(
        jobs=[DashboardJobUserState(job_id=scored.job_id, coarse_score=9, profile_version=2, updated_at=NOW)]
    )
    profile = UserScoringProfile(user_id="user-1", skills=["Python"], active=True, profile_version=2, updated_at=NOW)
    return reader, CountingStateRepository(snapshot, profile, [])


def test_bootstrap_matches_the_endpoints_it_replaces() -> None:
    reader, repository = _bootstrap_fixtures()
    query = DashboardJobQuery()

    bootstrap = get_dashboard_bootstrap(reader, repository, "user-1", query)

    assert bootstrap.jobs == list_dashboard_jobs(reader, query)
    assert bootstrap.runs == list_dashboard_runs(reader, repository.reports)
    assert bootstrap.user_state == repository.snapshot
    assert bootstrap.scoring_profile == repository.profile
    assert bootstrap.scoring_queue == get_scoring_queue(reader, repository.snapshot.jobs, 2)


def test_bootstrap_reads_user_state_and_profile_once() -> None:
    reader, repository = _bootstrap_fixtures()

    get_dashboard_bootstrap(reader, repository, "user-1", DashboardJobQuery())

    assert repository.snapshot_calls == 1
    assert repository.profile_calls == 1
    assert repository.blocklist_calls == 1


def test_bootstrap_hides_blocked_companies_and_reports_them() -> None:
    reader, repository = _bootstrap_fixtures()
    repository.blocked_companies = ["example"]

    bootstrap = get_dashboard_bootstrap(reader, repository, "user-1", DashboardJobQuery())

    assert bootstrap.jobs.items == []
    assert bootstrap.blocked_companies == ["example"]
    assert bootstrap.scoring_queue.eligible_total == 0


def test_bootstrap_scans_each_table_once_behind_the_cache() -> None:
    reader, repository = _bootstrap_fixtures()
    cached = CachingDashboardJobReader(reader, ttl_seconds=30.0)

    get_dashboard_bootstrap(cached, repository, "user-1", DashboardJobQuery())

    assert reader.record_scans == 1
    assert reader.listing_scans == 1


def test_bootstrap_without_a_profile_reports_no_current_scores() -> None:
    reader, repository = _bootstrap_fixtures()
    repository.profile = None

    bootstrap = get_dashboard_bootstrap(reader, repository, "user-1", DashboardJobQuery())

    assert bootstrap.scoring_profile is None
    assert bootstrap.scoring_queue.scored_current == 0
