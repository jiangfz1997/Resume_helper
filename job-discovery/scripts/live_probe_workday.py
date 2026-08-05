"""Manual, network-hitting run of the full pipeline against a real Workday
tenant: search -> fetch_detail -> normalize -> filter -> ingest.

Not part of `pytest` -- see tests/unit/test_workday_source.py for the
offline, fixture-replayed equivalent. Run this only when you want to verify
the live site still matches the shape the fixtures were captured from.

    python scripts/live_probe_workday.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import JobQuery, SearchQuery, SourceName
from job_discovery.repositories.memory import InMemoryJobRepository
from job_discovery.sources.workday import WorkdaySource

RUN_ID = f"live-{datetime.now(timezone.utc).isoformat()}"

EMPLOYERS = [
    WorkdaySource(
        employer_key="td",
        employer_name="TD Bank",
        tenant="td",
        site_id="TD_Bank_Careers",
        base_url="https://td.wd3.myworkdayjobs.com",
    ),
    WorkdaySource(
        employer_key="cibc",
        employer_name="CIBC",
        tenant="cibc",
        site_id="search",
        base_url="https://cibc.wd3.myworkdayjobs.com",
    ),
]

FILTER_CONFIG = FilterConfig(filter_version="v1", accepted_locations=["Toronto"], min_description_chars=300)


def main() -> None:
    repo = InMemoryJobRepository()

    for source in EMPLOYERS:
        query = SearchQuery(
            source=SourceName.WORKDAY, query="Software Engineer", hours_old=24, max_results=3, run_id=RUN_ID
        )
        print(f"\n== {source.employer_name} ==")
        refs = source.search(query)
        print(f"  search: {len(refs)} refs")

        for ref in refs[:2]:
            observation = source.fetch_detail(ref)
            result = ingest_observation(observation, repo, FILTER_CONFIG)
            record = repo.get_record(result.job_id)
            assert record is not None
            print(
                f"  [{result.status.value}] {record.canonical_title!r} @ {record.canonical_company} "
                f"| {record.canonical_location} | {record.workplace_type.value} "
                f"| desc={record.description_chars}ch "
                f"| eligibility={record.eligibility_status.value} {record.filter_codes}"
            )

    print(f"\ntotal distinct jobs ingested: {len(repo.query(JobQuery(limit=1000)))}")


if __name__ == "__main__":
    main()
