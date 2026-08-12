from __future__ import annotations

from datetime import datetime

import boto3
from moto import mock_aws

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import SourceJobObservation, SourceName
from job_discovery.maintenance.cleanup_source import build_source_cleanup_plan, execute_source_cleanup_plan
from job_discovery.repositories.dynamodb import DynamoDBJobRepository
from job_discovery.repositories.dynamodb_schema import create_tables


def _observation(source: SourceName, source_job_id: str, apply_url: str) -> SourceJobObservation:
    return SourceJobObservation(
        source=source,
        source_job_id=source_job_id,
        source_url=f"https://example.com/{source.value}/{source_job_id}",
        apply_url_raw=apply_url,
        title_raw="Software Engineer",
        company_raw="Example",
        location_raw="Toronto, ON, Canada",
        observed_at=datetime(2026, 8, 12, 12, 0),
        run_id="run-1",
    )


@mock_aws
def test_cleanup_removes_github_only_jobs_and_preserves_shared_jobs() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    create_tables(resource, "records", "listings", "dedup", "lookup")
    resource.create_table(
        TableName="users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "entity_key", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}, {"AttributeName": "entity_key", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    repository = DynamoDBJobRepository("records", "listings", "dedup", "lookup", resource=resource)
    config = FilterConfig(filter_version="v1", min_description_chars=0)

    github_only = ingest_observation(
        _observation(SourceName.SIMPLIFY_GITHUB, "us-only", "https://example.com/apply/us"), repository, config
    )
    shared = ingest_observation(
        _observation(SourceName.SIMPLIFY_GITHUB, "shared", "https://example.com/apply/shared"), repository, config
    )
    ingest_observation(
        _observation(SourceName.WORKDAY, "ca-shared", "https://example.com/apply/shared"), repository, config
    )
    canada = ingest_observation(
        _observation(SourceName.SIMPLIFY_CANADA, "ca-only", "https://example.com/apply/ca"), repository, config
    )
    resource.Table("users").put_item(Item={
        "user_id": "user-1", "entity_key": f"JOB#{github_only.job_id}", "job_id": str(github_only.job_id)
    })

    table_args = {
        "records_table": "records", "listings_table": "listings", "dedup_keys_table": "dedup",
        "source_lookup_table": "lookup", "user_data_table": "users",
    }
    plan = build_source_cleanup_plan(resource, source="simplify_github", **table_args)

    assert len(plan.listings) == 2
    assert {item["job_id"] for item in plan.records} == {str(github_only.job_id)}
    assert plan.preserved_job_ids == [str(shared.job_id)]
    assert len(plan.user_states) == 1

    execute_source_cleanup_plan(resource, plan, **table_args)

    assert repository.get_record(github_only.job_id) is None
    assert repository.get_record(shared.job_id) is not None
    assert repository.get_record(canada.job_id) is not None
    assert repository.get_listing(SourceName.SIMPLIFY_GITHUB, "shared") is None
    assert repository.get_listing(SourceName.WORKDAY, "ca-shared") is not None
    assert resource.Table("users").scan()["Items"] == []
    remaining_dedup = resource.Table("dedup").scan()["Items"]
    assert not any(item["job_id"] == str(github_only.job_id) for item in remaining_dedup)
