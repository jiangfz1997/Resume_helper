"""Manual, network-hitting run of the full pipeline through JobSpySource
(Indeed + LinkedIn): search -> fetch_detail -> normalize -> filter -> ingest.

Not part of pytest -- see tests/unit/test_jobspy_source.py for the offline
equivalent.

    python scripts/live_probe_jobspy.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import JobQuery, SearchQuery, SourceName
from job_discovery.repositories.memory import InMemoryJobRepository
from job_discovery.sources.jobspy_source import JobSpySource

RUN_ID = f"live-{datetime.now(timezone.utc).isoformat()}"
FILTER_CONFIG = FilterConfig(filter_version="v1", accepted_locations=["Toronto"], min_description_chars=300)


def main() -> None:
    repo = InMemoryJobRepository()
    sources = [
        JobSpySource(source=SourceName.INDEED, site_name="indeed"),
        JobSpySource(source=SourceName.LINKEDIN, site_name="linkedin"),
    ]

    for source in sources:
        query = SearchQuery(
            source=source.source, query="Software Engineer", location="Toronto, ON", max_results=10, run_id=RUN_ID
        )
        print(f"\n== {source.site_name} ==")
        try:
            refs = source.search(query)
        except Exception as exc:
            print(f"  search failed: {exc}")
            continue
        print(f"  search: {len(refs)} refs")

        for ref in refs:
            observation = source.fetch_detail(ref)
            result = ingest_observation(observation, repo, FILTER_CONFIG)
            record = repo.get_record(result.job_id)
            assert record is not None
            print(
                f"  [{result.status.value}] {record.canonical_title!r} @ {record.canonical_company} "
                f"| {record.canonical_location} | {record.workplace_type.value} "
                f"| desc={record.description_chars}ch | {record.eligibility_status.value}"
                + (f" dup_of={result.possible_duplicate_of}" if result.possible_duplicate_of else "")
            )

    all_records = repo.query(JobQuery(limit=1000))
    print(f"\ndistinct jobs: {len(all_records)}")
    print(f"eligible: {sum(1 for r in all_records if r.eligibility_status.value == 'eligible')}")
    print(f"excluded: {sum(1 for r in all_records if r.eligibility_status.value == 'excluded')}")
    print(f"review: {sum(1 for r in all_records if r.eligibility_status.value == 'review')}")


if __name__ == "__main__":
    main()
