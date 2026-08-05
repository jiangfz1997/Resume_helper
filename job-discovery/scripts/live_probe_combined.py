"""Manual run: Workday (TD, CIBC, RBC) + jobspy (Indeed, LinkedIn) into one
shared repository, to observe real cross-source merges when they happen --
not staged with a synthetic pairing like test_cross_source_merge.py.

    python scripts/live_probe_combined.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import JobQuery, SearchQuery, SourceName
from job_discovery.repositories.memory import InMemoryJobRepository
from job_discovery.sources.jobspy_source import JobSpySource
from job_discovery.sources.workday import WorkdaySource

RUN_ID = f"live-{datetime.now(timezone.utc).isoformat()}"
FILTER_CONFIG = FilterConfig(filter_version="v1", accepted_locations=["Toronto"], min_description_chars=300)

WORKDAY_EMPLOYERS = [
    WorkdaySource("td", "TD Bank", "td", "TD_Bank_Careers", "https://td.wd3.myworkdayjobs.com"),
    WorkdaySource("cibc", "CIBC", "cibc", "search", "https://cibc.wd3.myworkdayjobs.com"),
    WorkdaySource("rbc", "RBC", "rbc", "RBCGLOBAL1", "https://rbc.wd3.myworkdayjobs.com"),
]
JOBSPY_SOURCES = [
    JobSpySource(source=SourceName.INDEED, site_name="indeed"),
    JobSpySource(source=SourceName.LINKEDIN, site_name="linkedin"),
]


def run(source, repo, search_term: str, max_results: int) -> None:
    query = SearchQuery(source=source.source, query=search_term, max_results=max_results, run_id=RUN_ID)
    try:
        refs = source.search(query)
    except Exception as exc:
        print(f"  {getattr(source, 'employer_name', getattr(source, 'site_name', '?'))}: search failed: {exc}")
        return

    for ref in refs:
        try:
            observation = source.fetch_detail(ref)
        except Exception as exc:
            print(f"  detail failed for {ref.source_url}: {exc}")
            continue
        result = ingest_observation(observation, repo, FILTER_CONFIG)
        record = repo.get_record(result.job_id)
        assert record is not None
        tag = ""
        if result.status.value == "listing_added":
            tag = f" <-- MERGED via {result.matched_by.value}"
        elif result.possible_duplicate_of:
            tag = f" (flagged possible dup, not merged)"
        print(
            f"  [{result.status.value}] {record.canonical_title!r} @ {record.canonical_company} "
            f"| {record.canonical_location} | {record.eligibility_status.value}{tag}"
        )


def main() -> None:
    repo = InMemoryJobRepository()

    for source in WORKDAY_EMPLOYERS:
        print(f"\n== Workday: {source.employer_name} ==")
        run(source, repo, "Software Engineer", 5)

    for source in JOBSPY_SOURCES:
        print(f"\n== jobspy: {source.site_name} ==")
        run(source, repo, "Software Engineer", 10)

    all_records = repo.query(JobQuery(limit=1000))
    merged = [
        r for r in all_records if len(repo.list_listings(r.job_id)) > 1
    ]
    print(f"\ndistinct jobs: {len(all_records)}")
    print(f"jobs with more than one source listing: {len(merged)}")
    for record in merged:
        listings = repo.list_listings(record.job_id)
        sources = ", ".join(sorted(listing.source.value for listing in listings))
        print(f"  {record.canonical_title!r} @ {record.canonical_company} -- sources: {sources}")


if __name__ == "__main__":
    main()
