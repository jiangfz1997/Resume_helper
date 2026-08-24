"""Contract tests: the same behavioral guarantees must hold for every
JobRepository implementation. Parametrized over InMemoryJobRepository and
DynamoDBJobRepository (moto-backed -- no real AWS, no network, no
credentials needed) so the two can never quietly diverge. See
repositories/dynamodb.py's module docstring for why that matters here: the
merge/dedup cascade is the part of this project most likely to regress
silently if reimplemented by hand per backend.

Supersedes the old test_repository.py and test_dedup_merge_policy.py, which
only ever exercised InMemoryJobRepository.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import boto3
import pytest
from moto import mock_aws

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import (
    CoarseScore,
    DedupKeyKind,
    JobCategory,
    SourceJobObservation,
    SourceName,
    UpsertStatus,
)
from job_discovery.repositories.dynamodb import DynamoDBJobRepository
from job_discovery.repositories.dynamodb_schema import create_tables
from job_discovery.repositories.memory import InMemoryJobRepository

CONFIG = FilterConfig(filter_version="v1", min_description_chars=0)

TD_WORKDAY_APPLY_URL = (
    "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers/job/.../Software-Engineer-III_R_1500774"
)


@pytest.fixture(params=["memory", "dynamodb"])
def repository(request):
    if request.param == "memory":
        yield InMemoryJobRepository()
        return

    mock = mock_aws()
    mock.start()
    try:
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        create_tables(resource, "records", "listings", "dedup-keys", "source-lookup")
        yield DynamoDBJobRepository("records", "listings", "dedup-keys", "source-lookup", resource=resource)
    finally:
        mock.stop()


def _observation(
    source: SourceName,
    source_job_id: str,
    apply_url: str | None,
    observed_at: datetime,
    description: str | None = None,
    company: str = "TD",
    title: str = "Software Engineer III",
) -> SourceJobObservation:
    return SourceJobObservation(
        source=source,
        source_job_id=source_job_id,
        source_url=f"https://example.com/{source.value}/{source_job_id}",
        apply_url_raw=apply_url,
        title_raw=title,
        company_raw=company,
        location_raw="Toronto, ON, CA",
        description_raw=description,
        observed_at=observed_at,
        run_id=f"run-{observed_at.isoformat()}",
    )


def test_first_observation_creates_a_job(repository) -> None:
    result = ingest_observation(
        _observation(SourceName.WORKDAY, "R_1500774", TD_WORKDAY_APPLY_URL, datetime(2026, 8, 5, 9, 0)),
        repository,
        CONFIG,
    )
    assert result.status is UpsertStatus.JOB_CREATED
    record = repository.get_record(result.job_id)
    assert record is not None
    assert record.first_discovered_run_id == "run-2026-08-05T09:00:00"


def test_ingest_tags_job_category_from_title(repository) -> None:
    sde = ingest_observation(
        _observation(SourceName.WORKDAY, "R_1", None, datetime(2026, 8, 5, 9, 0), title="Backend Developer"),
        repository,
        CONFIG,
    )
    qa = ingest_observation(
        _observation(SourceName.WORKDAY, "R_2", None, datetime(2026, 8, 5, 9, 0), title="QA Engineer"),
        repository,
        CONFIG,
    )
    other = ingest_observation(
        _observation(SourceName.WORKDAY, "R_3", None, datetime(2026, 8, 5, 9, 0), title="CNC Machinist"),
        repository,
        CONFIG,
    )

    assert repository.get_record(sde.job_id).job_category is JobCategory.SDE
    assert repository.get_record(qa.job_id).job_category is JobCategory.QA
    assert repository.get_record(other.job_id).job_category is None


def test_same_posting_via_a_second_source_adds_a_listing_not_a_new_job(repository) -> None:
    """The TD case from the real Lambda probe: Workday and Indeed both
    surfaced the same requisition with an identical apply URL."""
    first = ingest_observation(
        _observation(SourceName.WORKDAY, "R_1500774", TD_WORKDAY_APPLY_URL, datetime(2026, 8, 5, 9, 0)),
        repository,
        CONFIG,
    )
    second = ingest_observation(
        _observation(SourceName.INDEED, "jk_d75d84f8", TD_WORKDAY_APPLY_URL, datetime(2026, 8, 5, 9, 5)),
        repository,
        CONFIG,
    )

    assert second.status is UpsertStatus.LISTING_ADDED
    assert second.job_id == first.job_id
    listings = repository.list_listings(first.job_id)
    assert {listing.source for listing in listings} == {SourceName.WORKDAY, SourceName.INDEED}


def test_different_companies_do_not_merge_on_the_weak_key(repository) -> None:
    a = ingest_observation(
        _observation(SourceName.INDEED, "1", None, datetime(2026, 8, 5, 9, 0), company="TD"), repository, CONFIG
    )
    b = ingest_observation(
        _observation(SourceName.LINKEDIN, "2", None, datetime(2026, 8, 5, 9, 0), company="CIBC"), repository, CONFIG
    )
    assert a.job_id != b.job_id


def test_repeat_observation_does_not_change_first_seen_at(repository) -> None:
    first_seen = datetime(2026, 8, 5, 9, 0)
    later = datetime(2026, 8, 5, 21, 0)

    first = ingest_observation(_observation(SourceName.WORKDAY, "R_1", None, first_seen), repository, CONFIG)
    ingest_observation(_observation(SourceName.WORKDAY, "R_1", None, later), repository, CONFIG)

    listing = repository.get_listing(SourceName.WORKDAY, "R_1")
    assert listing is not None
    assert listing.first_seen_at == first_seen
    assert listing.last_seen_at == later
    assert first.job_id == listing.job_id


def test_updated_description_refreshes_record(repository) -> None:
    result = ingest_observation(
        _observation(SourceName.WORKDAY, "R_1", None, datetime(2026, 8, 5, 9, 0), description="short"),
        repository,
        CONFIG,
    )
    updated = ingest_observation(
        _observation(
            SourceName.WORKDAY, "R_1", None, datetime(2026, 8, 5, 21, 0), description="a longer description now"
        ),
        repository,
        CONFIG,
    )

    assert updated.status is UpsertStatus.LISTING_UPDATED
    record = repository.get_record(result.job_id)
    assert record is not None
    assert record.description == "a longer description now"
    assert record.description_chars == len("a longer description now")


def test_updated_description_refreshes_extracted_years(repository) -> None:
    result = ingest_observation(
        _observation(
            SourceName.WORKDAY, "R_years", None, datetime(2026, 8, 5, 9, 0),
            description="Requires 8 years of professional experience.",
        ),
        repository,
        FilterConfig(filter_version="v1", min_description_chars=0, max_required_years=5),
    )
    ingest_observation(
        _observation(
            SourceName.WORKDAY, "R_years", None, datetime(2026, 8, 5, 21, 0),
            description="Requires 3 years of professional experience.",
        ),
        repository,
        FilterConfig(filter_version="v2", min_description_chars=0, max_required_years=5),
    )

    record = repository.get_record(result.job_id)
    assert record is not None
    assert (record.required_years_min, record.required_years_max) == (3, None)
    assert record.eligibility_status.value == "eligible"


def test_no_change_reports_unchanged(repository) -> None:
    obs = _observation(SourceName.WORKDAY, "R_1", None, datetime(2026, 8, 5, 9, 0), description="same text")
    ingest_observation(obs, repository, CONFIG)
    repeat = ingest_observation(
        _observation(SourceName.WORKDAY, "R_1", None, datetime(2026, 8, 5, 10, 0), description="same text"),
        repository,
        CONFIG,
    )
    assert repeat.status is UpsertStatus.LISTING_UNCHANGED


def test_weak_key_flags_but_does_not_merge(repository) -> None:
    """Reproduces the real TD case (R_1490005 / R_1500633, 2026-08-05): two
    different requisitions sharing title+company+location must not collapse
    into one JobRecord."""
    first = ingest_observation(
        _observation(
            SourceName.WORKDAY,
            "td:R_1490005",
            "https://td.wd3.myworkdayjobs.com/.../Software-Engineer-III_R_1490005",
            datetime(2026, 8, 5, 9, 0),
            description="requisition R_1490005 full JD text",
        ),
        repository,
        CONFIG,
    )
    second = ingest_observation(
        _observation(
            SourceName.WORKDAY,
            "td:R_1500633",
            "https://td.wd3.myworkdayjobs.com/.../Software-Engineer-III_R_1500633",
            datetime(2026, 8, 5, 9, 5),
            description="requisition R_1500633 full JD text, worded differently",
        ),
        repository,
        CONFIG,
    )

    assert second.status is UpsertStatus.JOB_CREATED
    assert second.job_id != first.job_id
    assert second.possible_duplicate_of == first.job_id

    second_record = repository.get_record(second.job_id)
    assert second_record is not None
    assert second_record.possible_duplicate_of == first.job_id
    assert second_record.duplicate_matched_by is DedupKeyKind.COMPANY_TITLE_LOCATION


def test_matching_apply_url_auto_merges(repository) -> None:
    shared_url = "https://td.wd3.myworkdayjobs.com/.../Software-Engineer-III_R_1490005"
    first = ingest_observation(
        _observation(SourceName.WORKDAY, "ref-a", shared_url, datetime(2026, 8, 5, 9, 0)), repository, CONFIG
    )
    second = ingest_observation(
        _observation(SourceName.WORKDAY, "ref-b", shared_url, datetime(2026, 8, 5, 9, 5)), repository, CONFIG
    )
    assert second.status is UpsertStatus.LISTING_ADDED
    assert second.job_id == first.job_id
    assert second.matched_by is DedupKeyKind.APPLY_URL


def test_record_score_updates_the_record(repository) -> None:
    result = ingest_observation(
        _observation(SourceName.WORKDAY, "R_1", None, datetime(2026, 8, 5, 9, 0), description="x" * 500),
        repository,
        CONFIG,
    )
    repository.record_score(
        result.job_id,
        CoarseScore(score=8, reasoning="good fit", model="fake-model", scored_at=datetime(2026, 8, 5, 10, 0)),
        score_version="v1",
    )
    record = repository.get_record(result.job_id)
    assert record is not None
    assert record.coarse_score == 8
    assert record.score_version == "v1"


def test_record_score_persists_keywords_without_touching_ingest_years(repository) -> None:
    """The scorer owns requirement_keywords; ingest owns the years. Two
    writers on required_years_* left the live table with 93 records carrying a
    year and 48 carrying a score, overlapping on one -- scoring must not be
    able to move a value the seniority filter depends on."""
    result = ingest_observation(
        _observation(
            SourceName.WORKDAY,
            "R_1",
            None,
            datetime(2026, 8, 5, 9, 0),
            description="Requires 2-5 years of professional experience. " + "x" * 500,
        ),
        repository,
        CONFIG,
    )
    repository.record_score(
        result.job_id,
        CoarseScore(
            score=7,
            reasoning="good fit",
            model="fake-model",
            scored_at=datetime(2026, 8, 5, 10, 0),
            requirement_keywords=["Python", "AWS"],
        ),
        score_version="v1",
    )
    record = repository.get_record(result.job_id)
    assert record is not None
    assert record.required_years_min == 2
    assert record.required_years_max == 5
    assert record.requirement_keywords == ["Python", "AWS"]


def test_record_requirements_does_not_write_a_shared_fit_score(repository) -> None:
    result = ingest_observation(
        _observation(SourceName.WORKDAY, "R_requirements", None, datetime(2026, 8, 5, 9, 0), description="x" * 500),
        repository,
        CONFIG,
    )
    repository.record_requirements(
        result.job_id,
        CoarseScore(
            score=9, reasoning="personal fit", model="fake-model", scored_at=datetime(2026, 8, 5, 10, 0),
            requirement_keywords=["Python", "AWS"],
        ),
    )
    record = repository.get_record(result.job_id)
    assert record is not None
    assert record.requirement_keywords == ["Python", "AWS"]
    assert record.coarse_score is None


def test_record_score_raises_for_unknown_job(repository) -> None:
    with pytest.raises(KeyError):
        repository.record_score(
            UUID("00000000-0000-0000-0000-000000000000"),
            CoarseScore(score=5, reasoning="x", model="m", scored_at=datetime(2026, 8, 5)),
            score_version="v1",
        )


def test_record_requirements_raises_for_unknown_job(repository) -> None:
    with pytest.raises(KeyError):
        repository.record_requirements(
            UUID("00000000-0000-0000-0000-000000000000"),
            CoarseScore(
                score=5, reasoning="x", model="m", scored_at=datetime(2026, 8, 5),
                requirement_keywords=["Python"],
            ),
        )
