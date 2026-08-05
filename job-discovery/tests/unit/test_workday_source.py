"""Replays saved responses from tests/fixtures/workday/ -- no network calls.
Fixtures were captured live from td.wd3.myworkdayjobs.com on 2026-08-05; see
scripts/live_probe_workday.py to refresh them against the real site."""

import json
from datetime import datetime, timezone
from pathlib import Path

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import EligibilityStatus, PostedAtQuality, SourceName, WorkplaceType
from job_discovery.domain.normalize import build_candidate
from job_discovery.repositories.memory import InMemoryJobRepository
from job_discovery.sources.workday import _parse_detail_response, _parse_search_response, strip_html

FIXTURES = Path(__file__).parent.parent / "fixtures" / "workday"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_search_response_maps_external_path_into_source_job_id() -> None:
    body = _load("td_search.json")
    refs = _parse_search_response(
        body, employer_key="td", base_url="https://td.wd3.myworkdayjobs.com", site_id="TD_Bank_Careers", run_id="run-1"
    )
    assert len(refs) == 3
    assert refs[0].source is SourceName.WORKDAY
    assert refs[0].source_job_id.startswith("td:/job/")
    assert refs[0].run_id == "run-1"


def test_parse_detail_response_strips_html_and_maps_apply_url() -> None:
    search_body = _load("td_search.json")
    refs = _parse_search_response(
        search_body,
        employer_key="td",
        base_url="https://td.wd3.myworkdayjobs.com",
        site_id="TD_Bank_Careers",
        run_id="run-1",
    )
    detail_body = _load("td_detail.json")
    observation = _parse_detail_response(
        detail_body, ref=refs[0], employer_name="TD Bank", observed_at=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )

    assert observation.title_raw == "Software Engineer III"
    assert observation.company_raw == "TD Bank"
    assert observation.apply_url_raw is not None and observation.apply_url_raw.startswith("https://")
    assert observation.description_raw is not None
    assert "<p" not in observation.description_raw
    assert "<b>" not in observation.description_raw
    assert "Work Location" in observation.description_raw


def test_strip_html_keeps_text_drops_tags() -> None:
    assert strip_html("<p><b>Hours:</b></p>37.5<p></p>") == "Hours:\n37.5"


def test_workday_candidate_uses_remote_type_hint_over_location_guess() -> None:
    """Workday's own remoteType ("On Site") must win even though the location
    text alone ("Toronto, Ontario") gives no workplace-type signal."""
    search_body = _load("td_search.json")
    refs = _parse_search_response(
        search_body,
        employer_key="td",
        base_url="https://td.wd3.myworkdayjobs.com",
        site_id="TD_Bank_Careers",
        run_id="run-1",
    )
    detail_body = _load("td_detail.json")
    observation = _parse_detail_response(
        detail_body, ref=refs[0], employer_name="TD Bank", observed_at=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )
    candidate = build_candidate(observation)
    assert candidate.workplace_type is WorkplaceType.ONSITE


def test_workday_posted_today_parses_as_relative_not_unknown() -> None:
    search_body = _load("td_search.json")
    refs = _parse_search_response(
        search_body,
        employer_key="td",
        base_url="https://td.wd3.myworkdayjobs.com",
        site_id="TD_Bank_Careers",
        run_id="run-1",
    )
    detail_body = _load("td_detail.json")
    assert detail_body["jobPostingInfo"]["postedOn"] == "Posted Today"

    observation = _parse_detail_response(
        detail_body, ref=refs[0], employer_name="TD Bank", observed_at=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )
    candidate = build_candidate(observation)
    assert candidate.posted_at_quality is PostedAtQuality.RELATIVE
    assert candidate.posted_at == observation.observed_at


def test_workday_observation_ingests_end_to_end() -> None:
    search_body = _load("td_search.json")
    refs = _parse_search_response(
        search_body,
        employer_key="td",
        base_url="https://td.wd3.myworkdayjobs.com",
        site_id="TD_Bank_Careers",
        run_id="run-1",
    )
    detail_body = _load("td_detail.json")
    observation = _parse_detail_response(
        detail_body, ref=refs[0], employer_name="TD Bank", observed_at=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )

    repo = InMemoryJobRepository()
    result = ingest_observation(observation, repo, FilterConfig(filter_version="v1", min_description_chars=300))
    record = repo.get_record(result.job_id)

    assert record is not None
    assert record.canonical_company == "TD Bank"
    assert record.description_chars > 300
    assert record.eligibility_status is EligibilityStatus.ELIGIBLE
