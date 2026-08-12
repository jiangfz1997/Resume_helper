from datetime import datetime, timezone
import json

from job_discovery.domain.models import SearchQuery, SourceName
from job_discovery.domain.models import EligibilityStatus, SourceJobObservation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.normalize import build_candidate
from job_discovery.application.ingest import ingest_observation
from job_discovery.repositories.memory import InMemoryJobRepository
from job_discovery.sources import simplify_source as module
from job_discovery.sources.simplify_source import (
    SimplifyCanadaSource,
    SimplifyGitHubSource,
    _is_canada_location,
    _parse_github_rows,
)


def _next_data(page_props: dict) -> str:
    payload = {"props": {"pageProps": page_props}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'


def test_canada_source_reads_structured_list_and_detail(monkeypatch):
    list_html = _next_data({"initialJobHits": [{
        "id": "posting-1", "title": "Software Engineer", "company_name": "Acme",
        "locations": ["Toronto, ON, Canada"], "travel_requirements": "Hybrid",
    }]})
    detail_html = _next_data({"jobPosting": {
        "id": "posting-1", "title": "Software Engineer", "description": "<p>Build useful software.</p>",
        "url": "https://boards.example/jobs/1?utm_source=simplify", "start_date": "2026-08-10T12:00:00",
        "locations": [{"value": "Toronto, ON, Canada"}], "min_salary": 70000, "max_salary": 90000,
        "currency_type": "CAD", "job": {"company": {"name": "Acme"}},
    }})
    monkeypatch.setattr(module, "_request_text", lambda url, timeout=30: list_html if "/l/" in url else detail_html)
    monkeypatch.setattr(module, "_resolve_apply_url", lambda url, timeout=15: "https://boards.example/jobs/1?utm_source=simplify")

    source = SimplifyCanadaSource()
    refs = source.search(SearchQuery(
        source=SourceName.SIMPLIFY_CANADA, query="", max_results=10, run_id="run-1"
    ))
    observation = source.fetch_detail(refs[0])
    candidate = build_candidate(observation)

    assert refs[0].source is SourceName.SIMPLIFY_CANADA
    assert observation.apply_url_raw == "https://boards.example/jobs/1?utm_source=simplify"
    assert observation.description_raw == "Build useful software."
    assert observation.salary_text_raw == "CAD 70000–90000"
    assert candidate.is_new_grad is True
    assert candidate.new_grad_signals == ["curated:simplify-canada"]


def test_github_parser_handles_continuation_rows_and_closed_jobs():
    readme = """
    <table><tbody>
      <tr><td><strong>🔥 Acme</strong></td><td>Software Engineer I</td><td>Toronto, ON, Canada</td>
          <td><a href="https://boards.example/jobs/1?utm_source=Simplify"><img alt="Apply"></a>
              <a href="https://simplify.jobs/p/one"><img alt="Simplify"></a></td><td>2d</td></tr>
      <tr><td>↳</td><td>Backend Developer</td><td>Remote in Canada</td>
          <td><a href="https://boards.example/jobs/2"><img alt="Apply"></a></td><td>0d</td></tr>
      <tr><td>Old Co</td><td>Closed Role</td><td>Toronto</td>
          <td><a href="https://boards.example/jobs/3"><img alt="Application is closed"></a></td><td>5d</td></tr>
    </tbody></table>
    """
    rows = _parse_github_rows(readme, 10)

    assert len(rows) == 2
    assert rows[0]["company"] == "Acme"
    assert rows[0]["apply_url"].startswith("https://boards.example/jobs/1")
    assert rows[1]["company"] == "Acme"
    assert rows[1]["posted"] == "0 days ago"


def test_github_source_marks_curated_rows_as_new_grad(monkeypatch):
    readme = """<table><tr><td>Acme</td><td>Software Engineer I</td><td>Toronto, Canada</td>
    <td><a href="https://boards.example/jobs/1">Apply</a></td><td>1d</td></tr></table>"""
    monkeypatch.setattr(module, "_request_text", lambda url, timeout=30: readme)
    source = SimplifyGitHubSource()
    ref = source.search(SearchQuery(
        source=SourceName.SIMPLIFY_GITHUB, query="", max_results=10, run_id="run-2"
    ))[0]
    candidate = build_candidate(source.fetch_detail(ref))

    assert candidate.is_new_grad is True
    assert candidate.new_grad_signals == ["curated:simplify-github"]
    assert candidate.posted_at is not None


def test_github_source_only_returns_explicit_canada_locations(monkeypatch):
    rows = [
        ("US", "Long Beach, CA Denver, CO"),
        ("Remote", "Remote"),
        ("Canada", "Toronto, ON, Canada"),
        ("Province", "Vancouver, BC"),
    ]
    readme = "<table>" + "".join(
        f'<tr><td>{company}</td><td>Software Engineer I</td><td>{location}</td>'
        f'<td><a href="https://boards.example/jobs/{company}">Apply</a></td><td>1d</td></tr>'
        for company, location in rows
    ) + "</table>"
    monkeypatch.setattr(module, "_request_text", lambda url, timeout=30: readme)

    source = SimplifyGitHubSource()
    refs = source.search(SearchQuery(
        source=SourceName.SIMPLIFY_GITHUB, query="", max_results=10, run_id="run-canada"
    ))
    locations = {source.summary(ref)["location"] for ref in refs}

    assert locations == {"Toronto, ON, Canada", "Vancouver, BC"}
    assert _is_canada_location("Anaheim, CA") is False
    assert _is_canada_location("Remote") is False


def test_metadata_only_curated_merge_keeps_richer_eligibility_and_adds_new_grad_tag():
    repository = InMemoryJobRepository()
    config = FilterConfig(filter_version="test", min_description_chars=300)
    common = {
        "apply_url_raw": "https://boards.example/jobs/1",
        "title_raw": "Software Engineer I",
        "company_raw": "Acme",
        "location_raw": "Toronto, Canada",
        "observed_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
        "run_id": "run-1",
    }
    first = SourceJobObservation(
        source=SourceName.WORKDAY, source_job_id="workday-1", source_url="https://workday.example/1",
        description_raw="Build and maintain backend software systems. " * 20, **common,
    )
    second = SourceJobObservation(
        source=SourceName.SIMPLIFY_GITHUB, source_job_id="github-1", source_url=module.GITHUB_REPO_URL,
        description_raw=None, new_grad_hint="curated:simplify-github", **common,
    )
    first_result = ingest_observation(first, repository, config)
    second_result = ingest_observation(second, repository, config)
    record = repository.get_record(first_result.job_id)

    assert second_result.job_id == first_result.job_id
    assert record is not None
    assert record.eligibility_status is EligibilityStatus.ELIGIBLE
    assert record.is_new_grad is True
