from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
            scored_at=datetime.now(timezone.utc),
            requirement_keywords=["Python", "AWS"],
        )


class RecordingScorer:
    def __init__(self) -> None:
        self.jobs: list[JobRecord] = []

    def score(self, job: JobRecord, profile: ScoringProfile) -> CoarseScore:
        del profile
        self.jobs.append(job)
        return CoarseScore(
            score=7, reasoning="recorded", model="fake",
            scored_at=datetime.now(timezone.utc),
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


@mock_aws
def test_blocked_company_is_never_sent_to_the_scorer() -> None:
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
    for index, company in enumerate(["Jobright.ai", "Acme Corp"]):
        ingest_observation(
            SourceJobObservation(
                source=SourceName.WORKDAY, source_job_id=f"R_{index}",
                source_url=f"https://example.com/R_{index}", title_raw="Software Engineer",
                company_raw=company, location_raw="Toronto",
                # Distinct text per posting, otherwise the description hash
                # would merge the two into one deduplicated record.
                description_raw=f"A detailed job description at {company} " * 30,
                observed_at=datetime(2026, 8, 5, 9, 0), run_id="run-1",
            ),
            jobs,
            FilterConfig(filter_version="v1", min_description_chars=0),
        )
    user_data.save_scoring_profile("user-a", ScoringProfileInput(skills=["Python"]))
    user_data.block_company("user-a", "Jobright.ai")

    assert score_jobs_for_users(jobs, user_data, ProfileAwareScorer(), "prompt-v1") == (1, 0)

    scored = user_data.get_snapshot("user-a").jobs
    assert len(scored) == 1
    record = jobs.get_record(scored[0].job_id)
    assert record is not None and record.canonical_company == "Acme Corp"


@mock_aws
def test_max_age_days_keeps_the_daily_run_off_the_backlog() -> None:
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
    ingested = [
        ingest_observation(
            SourceJobObservation(
                source=SourceName.WORKDAY, source_job_id=f"R_{index}",
                source_url=f"https://example.com/R_{index}", title_raw="Software Engineer",
                company_raw=f"Company {index}", location_raw="Toronto",
                description_raw=f"A detailed job description number {index} " * 30,
                observed_at=datetime(2026, 8, 5, 9, 0), run_id="run-1",
            ),
            jobs,
            FilterConfig(filter_version="v1", min_description_chars=0),
        )
        for index in range(2)
    ]
    # ingest stamps created_at from observed_at, so both records start stale.
    stale = jobs.get_record(ingested[0].job_id)
    fresh = jobs.get_record(ingested[1].job_id)
    assert stale is not None and fresh is not None
    stale.created_at = datetime.now(timezone.utc) - timedelta(days=9)
    fresh.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    user_data.save_scoring_profile("user-a", ScoringProfileInput(skills=["Python"]))

    assert score_jobs_for_users(
        jobs, user_data, ProfileAwareScorer(), "prompt-v1", max_age_days=2
    ) == (1, 0)
    scored = user_data.get_snapshot("user-a").jobs
    assert [state.job_id for state in scored] == [ingested[1].job_id]

    # An operator pressing "Score now" on that old posting still reaches it.
    assert score_jobs_for_users(
        jobs, user_data, ProfileAwareScorer(), "prompt-v1",
        job_ids={ingested[0].job_id}, max_age_days=2,
    ) == (1, 0)
    assert {state.job_id for state in user_data.get_snapshot("user-a").jobs} == {
        ingested[0].job_id, ingested[1].job_id
    }


@mock_aws
def test_scheduled_scoring_skips_a_range_above_the_years_cap() -> None:
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
    for index, description in enumerate([
        "Requires 5-8 years of professional experience. " + "x" * 400,
        "Requires 3 years of professional experience. " + "y" * 400,
    ]):
        ingest_observation(
            SourceJobObservation(
                source=SourceName.WORKDAY, source_job_id=f"R_cap_{index}",
                source_url=f"https://example.com/R_cap_{index}", title_raw="Software Engineer",
                company_raw=f"Company {index}", location_raw="Toronto", description_raw=description,
                observed_at=datetime.now(timezone.utc), run_id="run-cap",
            ),
            jobs,
            FilterConfig(filter_version="v1", min_description_chars=0),
        )
    user_data.save_scoring_profile("user-a", ScoringProfileInput(skills=["Python"]))
    scorer = RecordingScorer()

    assert score_jobs_for_users(
        jobs, user_data, scorer, "prompt-v1", max_required_years=5
    ) == (1, 0)
    assert [(job.required_years_min, job.required_years_max) for job in scorer.jobs] == [(3, None)]


@mock_aws
def test_limit_prioritizes_three_year_role_over_older_five_year_role() -> None:
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
    now = datetime.now(timezone.utc)
    for index, (years, observed_at) in enumerate([(5, now - timedelta(hours=4)), (3, now)]):
        ingest_observation(
            SourceJobObservation(
                source=SourceName.WORKDAY, source_job_id=f"R_priority_{index}",
                source_url=f"https://example.com/R_priority_{index}", title_raw="Software Engineer",
                company_raw=f"Priority Company {index}", location_raw="Toronto",
                description_raw=f"Requires {years} years of professional experience. " + "z" * 400,
                observed_at=observed_at, run_id="run-priority",
            ),
            jobs,
            FilterConfig(filter_version="v1", min_description_chars=0),
        )
    user_data.save_scoring_profile("user-a", ScoringProfileInput(skills=["Python"]))
    scorer = RecordingScorer()

    assert score_jobs_for_users(
        jobs, user_data, scorer, "prompt-v1", limit=1, max_required_years=5
    ) == (1, 0)
    assert scorer.jobs[0].required_years_min == 3
