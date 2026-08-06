from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import boto3
from moto import mock_aws

from job_discovery.dashboard.models import DashboardJobUserStatus
from job_discovery.domain.models import CoarseScore
from job_discovery.domain.settings import DiscoverySettingsInput, ScoringProfileInput
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository


@mock_aws
def test_user_state_is_isolated_and_persists_views_and_statuses() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    resource.create_table(
        TableName="user-state",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "entity_key", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "entity_key", "KeyType": "RANGE"},
        ],
    )
    repository = DynamoDBDashboardUserStateRepository("user-state", resource=resource)
    job_id = uuid4()

    repository.mark_job_viewed("user-a", job_id)
    repository.set_job_status("user-a", job_id, DashboardJobUserStatus.APPLIED)
    repository.mark_run_viewed("user-a", "lambda-2026-08-05T12:00Z")

    state = repository.get_snapshot("user-a")
    assert state.jobs[0].job_id == job_id
    assert state.jobs[0].status is DashboardJobUserStatus.APPLIED
    assert state.jobs[0].first_viewed_at is not None
    assert state.runs[0].run_id == "lambda-2026-08-05T12:00Z"
    assert repository.get_snapshot("user-b").jobs == []


@mock_aws
def test_profiles_scores_and_shared_discovery_settings_are_isolated_correctly() -> None:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    resource.create_table(
        TableName="user-data", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "entity_key", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "entity_key", "KeyType": "RANGE"},
        ],
    )
    repository = DynamoDBDashboardUserStateRepository("user-data", resource=resource)
    first = repository.save_scoring_profile(
        "user-a", ScoringProfileInput(skills=["Python"], target_titles=["Backend Engineer"])
    )
    second = repository.save_scoring_profile(
        "user-b", ScoringProfileInput(skills=["Playwright"], target_titles=["SDET"])
    )

    assert first.profile_version == 1
    assert second.skills == ["Playwright"]
    assert {profile.user_id for profile in repository.list_scoring_profiles()} == {"user-a", "user-b"}

    job_id = uuid4()
    repository.record_user_score(
        "user-a", job_id,
        CoarseScore(score=9, reasoning="Python match", model="fake", scored_at=datetime.now(timezone.utc)),
        "prompt:hash", first.profile_version,
    )
    repository.record_user_score(
        "user-b", job_id,
        CoarseScore(score=6, reasoning="partial QA match", model="fake", scored_at=datetime.now(timezone.utc)),
        "prompt:hash", second.profile_version,
    )
    assert repository.get_snapshot("user-a").jobs[0].coarse_score == 9
    assert repository.get_snapshot("user-b").jobs[0].coarse_score == 6

    settings = repository.save_discovery_settings(
        DiscoverySettingsInput(search_terms=["Software Engineer", "SDET"], hours_old=12)
    )
    assert settings.config_version == 1
    assert repository.get_discovery_settings().search_terms == ["Software Engineer", "SDET"]
