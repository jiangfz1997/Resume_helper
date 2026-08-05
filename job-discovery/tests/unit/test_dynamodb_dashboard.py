from __future__ import annotations

from datetime import datetime, timezone

import boto3
from moto import mock_aws

from job_discovery.application.ingest import ingest_observation
from job_discovery.dashboard.models import DashboardJobQuery
from job_discovery.dashboard.service import list_dashboard_jobs
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import SourceJobObservation, SourceName
from job_discovery.repositories.dynamodb import DynamoDBJobRepository
from job_discovery.repositories.dynamodb_dashboard import DynamoDBDashboardJobReader
from job_discovery.repositories.dynamodb_schema import create_tables


@mock_aws
def test_reader_scans_existing_job_tables() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    create_tables(resource, "records", "listings", "dedup-keys", "source-lookup")
    repository = DynamoDBJobRepository("records", "listings", "dedup-keys", "source-lookup", resource=resource)
    observed_at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    ingest_observation(
        SourceJobObservation(
            source=SourceName.WORKDAY,
            source_job_id="R-1",
            source_url="https://example.com/job/R-1",
            apply_url_raw="https://example.com/apply/R-1",
            title_raw="Software Engineer",
            company_raw="Example",
            location_raw="Toronto, ON",
            description_raw="A sufficiently detailed software engineering description.",
            observed_at=observed_at,
            run_id="run-1",
        ),
        repository,
        FilterConfig(filter_version="v1", min_description_chars=0),
    )
    reader = DynamoDBDashboardJobReader("records", "listings", resource=resource)

    page = list_dashboard_jobs(reader, DashboardJobQuery())

    assert page.total == 1
    assert page.items[0].title == "Software Engineer"
    assert page.items[0].sources == [SourceName.WORKDAY]
