"""Lambda: run the real domain pipeline (search -> fetch_detail -> normalize
-> filter -> ingest) against a small Workday
employer set.

Out of scope here, on purpose:
  - jobspy-backed sources (Indeed/LinkedIn) -- separate Lambda, see
    job-discovery/lambda_probe/ and job-discovery/README.md's reasoning for
    keeping ATS and aggregator sources in different functions

Repository backend is gated on RECORDS_TABLE, LISTINGS_TABLE, DEDUP_KEYS_TABLE
and SOURCE_LOOKUP_TABLE all being set (see repositories/factory.py). Without them
this falls back to a fresh InMemoryJobRepository per invocation -- nothing
persists, dedup only works within one run. With them, state accumulates in
DynamoDB across invocations: cross-source merges (Workday vs. this Lambda's
own repeat runs, or lambda_jobspy writing to the same tables) actually work,
and this_run_* counts in the response are split from total_jobs_in_repository
because "eligible" quietly stops meaning "found this run" once the backend
persists. Create the tables once with scripts/create_dynamodb_tables.py.

When USER_DATA_TABLE is set, discovery settings are read from the dashboard's
shared system item. The event/default settings are a compatibility fallback.
Personalized scoring is intentionally handled later by job-discovery-score.

Event overrides (all optional):
    {"search_term": "Software Engineer", "max_results": 3,
     "accepted_locations": ["Toronto"],
     "include_title_keywords": ["software engineer", "qa engineer", ...]}

include_title_keywords defaults to domain.filters.DEFAULT_INCLUDE_TITLE_KEYWORDS
when omitted from the event entirely; pass [] explicitly to disable the
relevance check. Without it, a posting can only be excluded by location or
seniority -- a CNC Machinist posting slipped through as "eligible" in a real
run on 2026-08-05 purely because it happened to also fail on location.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from job_discovery.application.ingest import ingest_observation
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import JobQuery, SearchQuery, SourceName
from job_discovery.domain.settings import DiscoverySettings
from job_discovery.repositories.dynamodb_dashboard_state import DynamoDBDashboardUserStateRepository
from job_discovery.repositories.factory import build_repository
from job_discovery.sources.workday import WorkdaySource

log = logging.getLogger()
log.setLevel(logging.INFO)

# Verified reachable from AWS egress in the Phase 0 probe (job-discovery/reports/aws-all.json).
EMPLOYERS: list[dict[str, str]] = [
    {
        "employer_key": "td",
        "employer_name": "TD Bank",
        "tenant": "td",
        "site_id": "TD_Bank_Careers",
        "base_url": "https://td.wd3.myworkdayjobs.com",
    },
    {
        "employer_key": "cibc",
        "employer_name": "CIBC",
        "tenant": "cibc",
        "site_id": "search",
        "base_url": "https://cibc.wd3.myworkdayjobs.com",
    },
    {
        "employer_key": "rbc",
        "employer_name": "RBC",
        "tenant": "rbc",
        "site_id": "RBCGLOBAL1",
        "base_url": "https://rbc.wd3.myworkdayjobs.com",
    },
]


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    settings = _load_settings(event)

    started_at = datetime.now(timezone.utc)
    run_id = str(event.get("run_id") or f"lambda-{started_at.strftime('%Y-%m-%dT%H:00Z')}")
    repository, repository_backend = build_repository()
    filter_kwargs: dict[str, Any] = {
        "filter_version": f"config-{settings.config_version}",
        "accepted_locations": settings.accepted_locations,
        "include_title_keywords": settings.include_title_keywords,
        "exclude_title_keywords": settings.exclude_title_keywords,
        "review_title_keywords": settings.review_title_keywords,
        "min_description_chars": settings.min_description_chars,
    }
    filter_config = FilterConfig(**filter_kwargs)

    listings: list[dict[str, Any]] = []
    for employer in EMPLOYERS:
        for search_term in settings.search_terms:
            source = WorkdaySource(**employer)
            query = SearchQuery(
                source=SourceName.WORKDAY, query=search_term,
                max_results=settings.workday_max_results, run_id=run_id,
            )
            try:
                refs = source.search(query)
            except Exception as exc:
                log.warning("%s search failed: %s", employer["employer_name"], exc)
                listings.append({"employer": employer["employer_name"], "query": search_term, "stage": "search", "error": str(exc)[:200]})
                continue

            for ref in refs:
                try:
                    observation = source.fetch_detail(ref)
                    result = ingest_observation(observation, repository, filter_config)
                except Exception as exc:
                    log.warning("%s detail failed: %s", ref.source_url, exc)
                    listings.append({"employer": employer["employer_name"], "query": search_term, "stage": "detail", "error": str(exc)[:200]})
                    continue
                record = repository.get_record(result.job_id)
                listing = repository.get_listing(observation.source, observation.source_job_id)
                assert record is not None and listing is not None
                listings.append({
                    "employer": employer["employer_name"], "query": search_term,
                    "source_job_id": observation.source_job_id, "apply_url_canonical": listing.apply_url_canonical,
                    "upsert_status": result.status.value,
                    "matched_by": result.matched_by.value if result.matched_by else None,
                    "job_id": str(result.job_id), "title": record.canonical_title,
                    "location": record.canonical_location, "workplace_type": record.workplace_type.value,
                    "posted_at_raw": observation.posted_at_raw, "posted_at_quality": listing.posted_at_quality.value,
                    "description_chars": record.description_chars, "eligibility_status": record.eligibility_status.value,
                    "filter_codes": [code.value for code in record.filter_codes],
                    "possible_duplicate_of": str(record.possible_duplicate_of) if record.possible_duplicate_of else None,
                })

    all_records = repository.query(JobQuery(limit=1000))

    # With a persistent backend, repository.query() returns every job ever
    # ingested, not just this invocation's -- these two counts must stay
    # separate or "eligible" silently changes meaning the day this Lambda
    # gets a DynamoDB-backed repository instead of a fresh in-memory one.
    this_run_counts = {"eligible": 0, "excluded": 0, "review": 0}
    for item in listings:
        status = item.get("eligibility_status")
        if status in this_run_counts:
            this_run_counts[status] += 1

    response = {
        "run_id": run_id,
        "repository_backend": repository_backend,
        "employers_scanned": len(EMPLOYERS),
        "search_terms": settings.search_terms,
        "this_run_eligible": this_run_counts["eligible"],
        "this_run_excluded": this_run_counts["excluded"],
        "this_run_review": this_run_counts["review"],
        "total_jobs_in_repository": len(all_records),
        "listings": listings,
        "scoring": "handled by job-discovery-score",
    }

    log.info(
        "run %s: %d distinct jobs from %d employers",
        run_id,
        len(all_records),
        len(EMPLOYERS),
    )
    return response


def _load_settings(event: dict[str, Any]) -> DiscoverySettings:
    table_name = os.environ.get("USER_DATA_TABLE")
    if table_name:
        return DynamoDBDashboardUserStateRepository(table_name).get_discovery_settings()
    search_terms = event.get("search_terms") or [event.get("search_term", "Software Engineer")]
    return DiscoverySettings(
        search_terms=search_terms, workday_max_results=int(event.get("max_results", 3)),
        accepted_locations=event.get("accepted_locations", ["Toronto"]),
        include_title_keywords=event.get("include_title_keywords", FilterConfig(filter_version="v1").include_title_keywords),
    )


if __name__ == "__main__":
    import sys

    cli_event = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(lambda_handler(cli_event, None), indent=2, ensure_ascii=False))
