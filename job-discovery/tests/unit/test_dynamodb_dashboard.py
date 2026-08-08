from __future__ import annotations

from datetime import datetime, timezone

import boto3
from moto import mock_aws

from job_discovery.application.ingest import ingest_observation
from job_discovery.dashboard.models import DashboardJobQuery
from job_discovery.dashboard.service import get_dashboard_job, list_dashboard_jobs
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import CoarseScore, SourceJobObservation, SourceName
from job_discovery.repositories.dynamodb import DynamoDBJobRepository
from job_discovery.repositories.dynamodb_dashboard import DynamoDBDashboardJobReader
from job_discovery.repositories.dynamodb_schema import create_tables

LONG_DESCRIPTION = "A sufficiently detailed software engineering description. " * 200


def _seed(resource: object) -> DynamoDBJobRepository:
    create_tables(resource, "records", "listings", "dedup-keys", "source-lookup")
    repository = DynamoDBJobRepository("records", "listings", "dedup-keys", "source-lookup", resource=resource)
    observed_at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    result = ingest_observation(
        SourceJobObservation(
            source=SourceName.WORKDAY,
            source_job_id="R-1",
            source_url="https://example.com/job/R-1",
            apply_url_raw="https://example.com/apply/R-1",
            title_raw="Software Engineer",
            company_raw="Example",
            location_raw="Toronto, ON",
            description_raw=LONG_DESCRIPTION,
            posted_at_raw="Posted 3 days ago",
            observed_at=observed_at,
            run_id="run-1",
        ),
        repository,
        FilterConfig(filter_version="v1", min_description_chars=0),
    )
    repository.record_score(
        result.job_id,
        CoarseScore(
            score=8,
            reasoning="Strong overlap with the target profile. " * 50,
            model="test-model",
            scored_at=observed_at,
            required_years_min=3,
            required_years_max=5,
            requirement_keywords=["python", "aws"],
        ),
        "test-v1",
    )
    return repository


@mock_aws
def test_reader_scans_existing_job_tables() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    _seed(resource)
    reader = DynamoDBDashboardJobReader("records", "listings", resource=resource)

    page = list_dashboard_jobs(reader, DashboardJobQuery())

    assert page.total == 1
    assert page.items[0].title == "Software Engineer"
    assert page.items[0].sources == [SourceName.WORKDAY]


@mock_aws
def test_list_projection_covers_every_summary_field() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    _seed(resource)
    reader = DynamoDBDashboardJobReader("records", "listings", resource=resource)

    summary = list_dashboard_jobs(reader, DashboardJobQuery()).items[0]

    assert summary.company == "Example"
    assert summary.location == "Toronto, ON"
    assert summary.primary_listing_url == "https://example.com/apply/R-1"
    assert summary.coarse_score == 8
    assert summary.required_years_min == 3
    assert summary.required_years_max == 5
    assert summary.requirement_keywords == ["python", "aws"]
    assert summary.first_discovered_run_id == "run-1"
    assert summary.lifecycle_status is not None
    assert summary.eligibility_status is not None
    assert summary.first_seen_at is not None
    assert summary.last_seen_at is not None


@mock_aws
def test_list_scans_skip_large_text_blobs() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    _seed(resource)
    reader = DynamoDBDashboardJobReader("records", "listings", resource=resource)

    record = reader.list_records()[0]

    assert record.description is None
    assert record.coarse_score_reasoning is None
    assert record.description_chars == len(LONG_DESCRIPTION)
    assert record.coarse_score == 8


@mock_aws
def test_detail_path_stays_unprojected() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    repository = _seed(resource)
    reader = DynamoDBDashboardJobReader("records", "listings", resource=resource)
    job_id = reader.list_records()[0].job_id

    detail = get_dashboard_job(reader, job_id)

    assert detail is not None
    assert detail.description == LONG_DESCRIPTION
    assert detail.coarse_score_reasoning is not None
    assert detail.listings[0].posted_at_raw == "Posted 3 days ago"
    assert repository.get_record(job_id) is not None
