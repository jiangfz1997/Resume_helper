from __future__ import annotations

from datetime import datetime, timezone

import boto3
from moto import mock_aws

from job_discovery.application.ingest import ingest_observation
from job_discovery.application.personalized_score import score_jobs_for_users
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import CoarseScore, JobRecord, ScoringProfile, SourceJobObservation, SourceName
from job_discovery.domain.settings import ScoringProfileInput
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository
from job_discovery.repositories.memory import InMemoryJobRepository


class ProfileAwareScorer:
    def score(self, job: JobRecord, profile: ScoringProfile) -> CoarseScore:
        del job
        score = 9 if "Python" in profile.skills else 6
        return CoarseScore(
            score=score, reasoning=",".join(profile.skills), model="fake",
            scored_at=datetime.now(timezone.utc), required_years_min=2,
            requirement_keywords=["Python", "AWS"],
        )


@mock_aws
def test_existing_score_for_one_user_does_not_skip_a_second_user() -> None:
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
    user_data = DynamoDBDashboardUserStateRepository("user-data", resource=resource)
    jobs = InMemoryJobRepository()
    result = ingest_observation(
        SourceJobObservation(
            source=SourceName.WORKDAY, source_job_id="R_1", source_url="https://example.com/R_1",
            title_raw="Software Engineer", company_raw="Example", location_raw="Toronto",
            description_raw="A detailed job description" * 30, observed_at=datetime(2026, 8, 5, 9, 0),
            run_id="run-1",
        ),
        jobs,
        FilterConfig(filter_version="v1", min_description_chars=0),
    )
    user_data.save_scoring_profile("user-a", ScoringProfileInput(skills=["Python"]))

    assert score_jobs_for_users(jobs, user_data, ProfileAwareScorer(), "prompt-v1") == (1, 0)
    user_data.save_scoring_profile("user-b", ScoringProfileInput(skills=["Playwright"]))
    assert score_jobs_for_users(jobs, user_data, ProfileAwareScorer(), "prompt-v1") == (1, 0)

    assert user_data.get_snapshot("user-a").jobs[0].coarse_score == 9
    assert user_data.get_snapshot("user-b").jobs[0].coarse_score == 6
    shared_job = jobs.get_record(result.job_id)
    assert shared_job is not None
    assert shared_job.coarse_score is None
    assert shared_job.required_years_min == 2
