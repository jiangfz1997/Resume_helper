"""Pure-function tests for the parsing surface of JobSpySource -- no network,
no jobspy/pandas import needed since _row_to_observation takes a plain dict.

Fixture values below are real rows observed in job-discovery/lambda_probe's
Lambda run on 2026-08-05 against Indeed and LinkedIn for "Software Engineer"
in Toronto, ON, not synthesized.
"""

from datetime import datetime

from job_discovery.domain.models import SourceJobRef, SourceName, WorkplaceType
from job_discovery.domain.normalize import build_candidate
from job_discovery.sources.jobspy_source import (
    _block_signal,
    _clean,
    _extract_source_job_id,
    _row_to_observation,
)

TD_INDEED_ROW = {
    "title": "Software Engineer III",
    "company": "TD",
    "location": "Toronto, ON, CA",
    "date_posted": "2026-08-04",
    "job_url": "https://ca.indeed.com/viewjob?jk=d75d84f8135605af",
    "job_url_direct": (
        "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers/job/"
        "TD-Terrace---160-Front-Street-West-Corporate-Toronto-Ontario/Software-Engineer-III_R_1500774"
    ),
    "is_remote": False,
    "description": "x" * 500,
}

LINKEDIN_ROW = {
    "title": "Software Engineer",
    "company": "Opendoor",
    "location": "Toronto, Ontario, Canada",
    "date_posted": None,
    "job_url": "https://www.linkedin.com/jobs/view/4420991755",
    "job_url_direct": float("nan"),
    "is_remote": True,
    "description": "y" * 4395,
}


def test_clean_treats_nan_and_none_as_missing() -> None:
    assert _clean(float("nan")) is None
    assert _clean(None) is None
    assert _clean("  ") is None
    assert _clean("Toronto, ON") == "Toronto, ON"


def test_extract_source_job_id_from_indeed_url() -> None:
    assert _extract_source_job_id("https://ca.indeed.com/viewjob?jk=d75d84f8135605af", "indeed") == "d75d84f8135605af"


def test_extract_source_job_id_from_linkedin_url() -> None:
    assert _extract_source_job_id("https://www.linkedin.com/jobs/view/4420991755", "linkedin") == "4420991755"


def test_row_to_observation_prefers_job_url_direct_over_job_url() -> None:
    ref = SourceJobRef(
        source=SourceName.INDEED, source_job_id="d75d84f8135605af", source_url=TD_INDEED_ROW["job_url"], run_id="run-1"
    )
    observation = _row_to_observation(TD_INDEED_ROW, ref, observed_at=datetime(2026, 8, 5))
    assert observation.apply_url_raw == TD_INDEED_ROW["job_url_direct"]


def test_row_to_observation_falls_back_to_job_url_when_direct_is_nan() -> None:
    ref = SourceJobRef(source=SourceName.LINKEDIN, source_job_id="4420991755", source_url=LINKEDIN_ROW["job_url"], run_id="run-1")
    observation = _row_to_observation(LINKEDIN_ROW, ref, observed_at=datetime(2026, 8, 5))
    assert observation.apply_url_raw == LINKEDIN_ROW["job_url"]


def test_is_remote_true_becomes_remote_workplace_type() -> None:
    ref = SourceJobRef(source=SourceName.LINKEDIN, source_job_id="4420991755", source_url=LINKEDIN_ROW["job_url"], run_id="run-1")
    observation = _row_to_observation(LINKEDIN_ROW, ref, observed_at=datetime(2026, 8, 5))
    candidate = build_candidate(observation)
    assert candidate.workplace_type is WorkplaceType.REMOTE


def test_linkedin_null_posted_at_is_unknown_quality() -> None:
    """Matches every LinkedIn probe run: date_posted was null 40/40 times."""
    ref = SourceJobRef(source=SourceName.LINKEDIN, source_job_id="4420991755", source_url=LINKEDIN_ROW["job_url"], run_id="run-1")
    observation = _row_to_observation(LINKEDIN_ROW, ref, observed_at=datetime(2026, 8, 5))
    assert observation.posted_at_raw is None


def test_block_signal_detects_zip_recruiter_style_403() -> None:
    """Reproduces the real ZipRecruiter log line captured in Phase 0:
    jobspy logs the block, it does not raise."""
    messages = [
        "INFO: JobSpy:ZipRecruiter - scraping",
        'ERROR: ZipRecruiter response status code 403 with response: {"error_code":"forbidden cf-waf"}',
    ]
    assert _block_signal(messages) is not None


def test_block_signal_is_none_for_clean_run() -> None:
    assert _block_signal(["INFO: JobSpy:Indeed - finished scraping"]) is None
