"""Proves the merge works when driven by the real per-adapter code paths
(WorkdaySource._parse_detail_response, JobSpySource._row_to_observation),
not just hand-built SourceJobObservation objects like test_repository.py uses.

The Indeed row is synthetic -- built to carry the exact apply URL from the
real td_detail.json fixture -- because this repo has no single capture where
the same requisition was scraped from both channels in the same run. It
still exercises the genuine adapter parsing logic on both sides, not
simplified stand-ins for it.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import DedupKeyKind, SourceJobRef, SourceName, UpsertStatus
from job_discovery.repositories.memory import InMemoryJobRepository
from job_discovery.sources.jobspy_source import _row_to_observation
from job_discovery.sources.workday import _parse_detail_response, _parse_search_response

FIXTURES = Path(__file__).parent.parent / "fixtures" / "workday"
CONFIG = FilterConfig(filter_version="v1", min_description_chars=0)


def test_same_posting_via_workday_and_indeed_merges_into_one_job_record() -> None:
    search_body = json.loads((FIXTURES / "td_search.json").read_text(encoding="utf-8"))
    detail_body = json.loads((FIXTURES / "td_detail.json").read_text(encoding="utf-8"))

    workday_refs = _parse_search_response(
        search_body,
        employer_key="td",
        base_url="https://td.wd3.myworkdayjobs.com",
        site_id="TD_Bank_Careers",
        run_id="run-1",
    )
    workday_observation = _parse_detail_response(
        detail_body, ref=workday_refs[0], employer_name="TD Bank", observed_at=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )
    same_apply_url = workday_observation.apply_url_raw
    assert same_apply_url is not None

    indeed_row = {
        "title": "Software Engineer III",
        "company": "TD",
        "location": "Toronto, ON, CA",
        "date_posted": "2026-08-05",
        "job_url": "https://ca.indeed.com/viewjob?jk=synthetic123",
        "job_url_direct": same_apply_url,
        "is_remote": False,
        "description": "Indeed's own copy of the same posting text.",
    }
    indeed_ref = SourceJobRef(
        source=SourceName.INDEED, source_job_id="synthetic123", source_url=indeed_row["job_url"], run_id="run-1"
    )
    indeed_observation = _row_to_observation(
        indeed_row, indeed_ref, observed_at=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )

    repo = InMemoryJobRepository()
    first = ingest_observation(workday_observation, repo, CONFIG)
    second = ingest_observation(indeed_observation, repo, CONFIG)

    assert second.status is UpsertStatus.LISTING_ADDED
    assert second.job_id == first.job_id
    assert second.matched_by is DedupKeyKind.APPLY_URL

    listings = repo.list_listings(first.job_id)
    assert {listing.source for listing in listings} == {SourceName.WORKDAY, SourceName.INDEED}
