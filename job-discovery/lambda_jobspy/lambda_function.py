"""Lambda: run the real domain pipeline (search -> fetch_detail -> normalize
-> filter -> ingest -> [optional] coarse score) against Indeed + LinkedIn via
jobspy.

Companion to lambda_workday/lambda_function.py, kept as a separate function
on purpose: jobspy's dependency stack (numpy/pandas/tls-client) is heavy and
must not block or bloat the lean Workday-only crawler -- see
job-discovery/README.md's Lambda/Fargate boundary reasoning.

Repository backend is gated on RECORDS_TABLE, LISTINGS_TABLE, DEDUP_KEYS_TABLE
and SOURCE_LOOKUP_TABLE all being set (see repositories/factory.py). Without them
this falls back to a fresh InMemoryJobRepository per invocation. With them,
state accumulates in DynamoDB across invocations AND across this Lambda and
lambda_workday, since both point at the same three tables -- this is what
finally lets a TD posting seen via Workday and via this Lambda merge into
one JobRecord in production, not just in local scripts. this_run_* counts
are split from total_jobs_in_repository because "eligible" quietly stops
meaning "found this run" once the backend persists. Create the tables once
with scripts/create_dynamodb_tables.py.

Coarse scoring is gated the same way: skipped unless both GEMINI_API_KEY and
GEMINI_MODEL are set, so the crawler still works with zero credentials
configured. GEMINI_MODEL has no default -- verify the current free-tier
model name against
https://generativelanguage.googleapis.com/v1beta/models?key=... before
setting it.

Event overrides (all optional):
    {"search_term": "Software Engineer", "location": "Toronto, ON",
     "hours_old": 24, "max_results": 10, "accepted_locations": ["Toronto"],
     "sites": ["indeed", "linkedin"],
     "include_title_keywords": ["software engineer", "qa engineer", ...],
     "skills": ["Python", "AWS"], "target_titles": ["Software Engineer"],
     "min_years_experience": 2, "location_preference": "Toronto"}

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
from job_discovery.application.score import score_eligible_jobs
from job_discovery.domain.filters import FilterConfig
from job_discovery.domain.models import JobQuery, ScoringProfile, SearchQuery, SourceName
from job_discovery.repositories.factory import build_repository
from job_discovery.scoring.gemini_scorer import GeminiCoarseScorer
from job_discovery.sources.jobspy_source import JobSpySource, SourceBlockedError

log = logging.getLogger()
log.setLevel(logging.INFO)

SCORE_VERSION = "v1"
SITE_TO_SOURCE = {"indeed": SourceName.INDEED, "linkedin": SourceName.LINKEDIN}


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    search_term = event.get("search_term", "Software Engineer")
    location = event.get("location", "Toronto, ON")
    hours_old = int(event.get("hours_old", 24))
    max_results = int(event.get("max_results", 10))
    accepted_locations = event.get("accepted_locations", ["Toronto"])
    sites = event.get("sites", ["indeed", "linkedin"])

    run_id = f"lambda-{datetime.now(timezone.utc).isoformat()}"
    repository, repository_backend = build_repository()
    filter_kwargs: dict[str, Any] = {
        "filter_version": "v1",
        "accepted_locations": accepted_locations,
        "min_description_chars": 300,
    }
    if "include_title_keywords" in event:
        filter_kwargs["include_title_keywords"] = event["include_title_keywords"]
    filter_config = FilterConfig(**filter_kwargs)

    listings: list[dict[str, Any]] = []
    for site in sites:
        source_name = SITE_TO_SOURCE.get(site)
        if source_name is None:
            listings.append({"site": site, "stage": "search", "error": f"unknown site {site!r}"})
            continue

        source = JobSpySource(source=source_name, site_name=site)
        query = SearchQuery(
            source=source_name,
            query=search_term,
            location=location,
            hours_old=hours_old,
            max_results=max_results,
            run_id=run_id,
        )

        try:
            refs = source.search(query)
        except SourceBlockedError as exc:
            log.warning("%s blocked: %s", site, exc)
            listings.append({"site": site, "stage": "search", "error": f"blocked: {exc}"[:200]})
            continue
        except Exception as exc:
            log.warning("%s search failed: %s", site, exc)
            listings.append({"site": site, "stage": "search", "error": str(exc)[:200]})
            continue

        for ref in refs:
            try:
                observation = source.fetch_detail(ref)
                result = ingest_observation(observation, repository, filter_config)
            except Exception as exc:
                log.warning("%s detail failed for %s: %s", site, ref.source_url, exc)
                listings.append({"site": site, "stage": "detail", "error": str(exc)[:200]})
                continue

            record = repository.get_record(result.job_id)
            listing = repository.get_listing(observation.source, observation.source_job_id)
            assert record is not None and listing is not None
            listings.append(
                {
                    "site": site,
                    "source_job_id": observation.source_job_id,
                    "apply_url_canonical": listing.apply_url_canonical,
                    "upsert_status": result.status.value,
                    "matched_by": result.matched_by.value if result.matched_by else None,
                    "job_id": str(result.job_id),
                    "title": record.canonical_title,
                    "company": record.canonical_company,
                    "location": record.canonical_location,
                    "workplace_type": record.workplace_type.value,
                    "posted_at_raw": observation.posted_at_raw,
                    "posted_at_quality": listing.posted_at_quality.value,
                    "description_chars": record.description_chars,
                    "eligibility_status": record.eligibility_status.value,
                    "filter_codes": [code.value for code in record.filter_codes],
                    "possible_duplicate_of": str(record.possible_duplicate_of) if record.possible_duplicate_of else None,
                }
            )

    all_records = repository.query(JobQuery(limit=1000))

    scores: list[dict[str, Any]] = []
    scoring_skipped_reason: str | None = None
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_MODEL"):
        profile = ScoringProfile(
            skills=event.get("skills", []),
            target_titles=event.get("target_titles", []),
            min_years_experience=event.get("min_years_experience"),
            location_preference=event.get("location_preference"),
        )
        try:
            scorer = GeminiCoarseScorer()
            scored_records = score_eligible_jobs(repository, scorer, profile, score_version=SCORE_VERSION)
            scores = [
                {
                    "title": r.canonical_title,
                    "company": r.canonical_company,
                    "coarse_score": r.coarse_score,
                    "coarse_score_reasoning": r.coarse_score_reasoning,
                    "required_years_min": r.required_years_min,
                    "required_years_max": r.required_years_max,
                    "requirement_keywords": r.requirement_keywords,
                }
                for r in scored_records
            ]
        except Exception as exc:
            log.warning("scoring setup failed: %s", exc)
            scoring_skipped_reason = str(exc)[:200]
    else:
        scoring_skipped_reason = "GEMINI_API_KEY/GEMINI_MODEL not set -- crawler ran without scoring"

    # With a persistent backend, repository.query() returns every job ever
    # ingested, not just this invocation's -- keep the two counts separate,
    # see lambda_workday/lambda_function.py for the same fix and why.
    this_run_counts = {"eligible": 0, "excluded": 0, "review": 0}
    for item in listings:
        status = item.get("eligibility_status")
        if status in this_run_counts:
            this_run_counts[status] += 1

    response = {
        "run_id": run_id,
        "repository_backend": repository_backend,
        "sites_scanned": sites,
        "this_run_eligible": this_run_counts["eligible"],
        "this_run_excluded": this_run_counts["excluded"],
        "this_run_review": this_run_counts["review"],
        "total_jobs_in_repository": len(all_records),
        "listings": listings,
        "scores": scores,
        "scoring_skipped_reason": scoring_skipped_reason,
    }

    log.info("run %s: %d distinct jobs from %s, %d scored", run_id, len(all_records), sites, len(scores))
    return response


if __name__ == "__main__":
    import sys

    cli_event = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(lambda_handler(cli_event, None), indent=2, ensure_ascii=False))
