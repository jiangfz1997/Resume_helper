from __future__ import annotations

import boto3
from moto import mock_aws

from candidate_profile.domain.models import (
    ApplicationStatus,
    CandidateProfileInput,
    CreateApplicationFromJob,
    ExtractedJobInfo,
    UpdateApplicationFields,
)
from candidate_profile.repositories.dynamodb import DynamoDBCandidateProfileRepository
from candidate_profile.repositories.schema import create_table


def _repository() -> DynamoDBCandidateProfileRepository:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    create_table(resource, "candidate-profile-data")
    return DynamoDBCandidateProfileRepository("candidate-profile-data", resource=resource)


@mock_aws
def test_profile_round_trips_and_is_isolated_per_user() -> None:
    repository = _repository()
    assert repository.get_profile("user-a") is None

    saved = repository.save_profile("user-a", CandidateProfileInput(full_name="Ada Lovelace", summary="engineer"))
    fetched = repository.get_profile("user-a")

    assert fetched is not None
    assert fetched.full_name == "Ada Lovelace"
    assert fetched.summary == "engineer"
    assert repository.get_profile("user-b") is None
    assert saved.user_id == "user-a"


@mock_aws
def test_application_from_job_is_created_with_applied_status_and_history() -> None:
    repository = _repository()

    application = repository.create_application_from_job(
        "user-a",
        CreateApplicationFromJob(job_id="job-1", company="Acme", title="SDE", jd_text="do things"),
    )

    assert application.status is ApplicationStatus.APPLIED
    assert len(application.status_history) == 1
    assert application.status_history[0].status is ApplicationStatus.APPLIED
    assert repository.list_applications("user-b") == []
    assert repository.list_applications("user-a")[0].application_id == application.application_id


@mock_aws
def test_status_transition_appends_history_and_shows_up_in_the_list() -> None:
    repository = _repository()
    application = repository.create_application_from_job(
        "user-a", CreateApplicationFromJob(company="Acme", title="SDE", jd_text="do things")
    )

    updated = repository.update_application_status(
        "user-a", application.application_id, ApplicationStatus.INTERVIEWING, "phone screen scheduled"
    )

    assert updated is not None
    assert updated.status is ApplicationStatus.INTERVIEWING
    assert len(updated.status_history) == 2
    assert updated.status_history[-1].note == "phone screen scheduled"

    listed = repository.list_applications("user-a")
    assert [item.status for item in listed] == [ApplicationStatus.INTERVIEWING]
    assert repository.list_applications("user-a", ApplicationStatus.APPLIED) == []

    assert repository.update_application_status("user-a", "missing", ApplicationStatus.OFFER, None) is None


@mock_aws
def test_pending_url_application_is_completed_by_extraction_worker() -> None:
    repository = _repository()
    pending = repository.create_application_pending("user-a", "https://example.com/job/1")
    assert pending.extraction_status.value == "extracting"

    repository.complete_application_extraction(
        "user-a",
        pending.application_id,
        ExtractedJobInfo(company="Acme", title="SDE", location="Remote", jd_text="full posting text"),
        raw_html="<html>full page</html>",
    )

    completed = repository.get_application("user-a", pending.application_id)
    assert completed is not None
    assert completed.company == "Acme"
    assert completed.jd_text == "full posting text"
    assert completed.extraction_status.value == "ready"
    assert completed.raw_html == "<html>full page</html>"

    # The snapshot is fetched only per application: it can run to 150KB and
    # nothing renders it, so the list must not carry it.
    listed = repository.list_applications("user-a")[0]
    assert listed.raw_html is None
    assert listed.jd_text == "full posting text"


@mock_aws
def test_extraction_failure_is_recorded_and_fields_can_be_edited_and_deleted() -> None:
    repository = _repository()
    pending = repository.create_application_pending("user-a", "https://example.com/job/1")

    repository.fail_application_extraction("user-a", pending.application_id, "timed out")
    failed = repository.get_application("user-a", pending.application_id)
    assert failed is not None
    assert failed.extraction_status.value == "failed"
    assert failed.extraction_error == "timed out"

    edited = repository.update_application_fields(
        "user-a", pending.application_id, UpdateApplicationFields(company="Manually Entered Co")
    )
    assert edited is not None
    assert edited.company == "Manually Entered Co"

    repository.delete_application("user-a", pending.application_id)
    assert repository.get_application("user-a", pending.application_id) is None
